"""Structural shapes and primitive validators for Code DSL 0.1."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import unquote, urlsplit

SYNTAX = "CODE-SYNTAX-001"
SEMANTIC = "CODE-SEMANTIC-001"
BOUNDARY = "CODE-BOUNDARY-001"

URI_RE = re.compile(r"\A[A-Za-z][A-Za-z0-9+.-]*:[^\s]+\Z")
DIGEST_RE = re.compile(r"\Asha256:[a-f0-9]{64}\Z")
SHA_RE = re.compile(r"\A[a-f0-9]{40}\Z")
ID_RE = re.compile(r"\A[a-z0-9][a-z0-9._-]*\Z")
LANGUAGE_RE = re.compile(r"\A[a-z0-9][a-z0-9+._-]*\Z")
GIT_BRANCH_RE = re.compile(
    r"\A(?![/-])(?!.*//)(?!.*\.\.)(?!.*@\{)[^\x00-\x20\x7f-\x9f~^:?*\[\\]+(?<!/)(?<!\.lock)\Z"
)
RFC3339_RE = re.compile(
    r"\A\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.(\d{1,9}))?(?:[Zz]|[+-]\d{2}:\d{2})\Z"
)

OPERATIONS = {
    "diagnostics",
    "hover",
    "definition",
    "references",
    "document_symbols",
    "workspace_symbols",
}

SYMBOL_KINDS = {
    "actor",
    "aggregate",
    "command",
    "event",
    "projection",
    "capability",
    "service",
    "module",
    "type",
    "function",
    "method",
    "field",
    "variable",
    "other",
}


def _is_strict_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int)


def _has_forbidden_controls(value: str, *, multiline: bool = False) -> bool:
    for ch in value:
        code = ord(ch)
        if 0x7F <= code <= 0x9F:
            return True
        if code < 0x20 and (not multiline or ch not in "\n\r\t"):
            return True
    return False


def _fully_unquote(raw_path: str) -> tuple[str, bool]:
    current = raw_path
    for _ in range(8):
        decoded = unquote(current)
        if decoded == current:
            return current, True
        current = decoded
    return current, unquote(current) == current


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    message: str

    @property
    def security(self) -> bool:
        return self.code == BOUNDARY


class ShapeValidator:
    def __init__(self) -> None:
        self.findings: list[Finding] = []
        self._seen: set[Finding] = set()

    def add(self, code: str, path: str, message: str) -> None:
        finding = Finding(code, path, message)
        if finding not in self._seen:
            self._seen.add(finding)
            self.findings.append(finding)

    def closed(
        self,
        value: Any,
        path: str,
        required: Iterable[str],
        allowed: Iterable[str],
    ) -> bool:
        if not isinstance(value, dict):
            self.add(SYNTAX, path, "expected an object")
            return False
        required_set = set(required)
        allowed_set = set(allowed)
        for key in sorted(required_set - value.keys()):
            self.add(SYNTAX, path, f"missing required property {key!r}")
        for key in sorted(value.keys() - allowed_set):
            self.add(SYNTAX, f"{path}.{key}", "unknown property")
        return required_set <= value.keys() and value.keys() <= allowed_set

    def string(
        self,
        value: Any,
        path: str,
        *,
        nonempty: bool = True,
        multiline: bool = False,
        pattern: re.Pattern[str] | None = None,
    ) -> bool:
        if not isinstance(value, str) or (nonempty and not value):
            self.add(SYNTAX, path, "expected a non-empty string")
            return False
        if _has_forbidden_controls(value, multiline=multiline):
            self.add(SYNTAX, path, "string contains forbidden control characters")
            return False
        if pattern is not None and pattern.fullmatch(value) is None:
            self.add(SYNTAX, path, "string does not match the required format")
            return False
        return True

    def integer(self, value: Any, path: str, minimum: int = 0) -> bool:
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            self.add(SYNTAX, path, f"expected an integer >= {minimum}")
            return False
        return True

    def uri(self, value: Any, path: str, *, stable: bool) -> bool:
        if not self.string(value, path, pattern=URI_RE):
            return False
        parsed = urlsplit(value)
        if not parsed.scheme:
            self.add(SYNTAX, path, "URI must have a scheme")
            return False
        decoded_path, converged = _fully_unquote(parsed.path)
        decoded_netloc, netloc_converged = _fully_unquote(parsed.netloc)
        if (
            not converged
            or not netloc_converged
            or "\x00" in decoded_path
            or "\x00" in decoded_netloc
            or "\\" in decoded_path
            or "\\" in decoded_netloc
            or ".." in decoded_path.split("/")
            or ".." in decoded_netloc.split("/")
        ):
            self.add(BOUNDARY, path, "URI path traversal is forbidden")
            return False
        scheme = parsed.scheme.lower()
        if scheme == "file" and (parsed.query or parsed.fragment):
            self.add(BOUNDARY, path, "file: URI query or fragment is forbidden")
            return False
        if stable and scheme == "file":
            self.add(BOUNDARY, path, "file: is an artifact location, not stable identity")
            return False
        return True

    def digest(self, value: Any, path: str) -> bool:
        return self.string(value, path, pattern=DIGEST_RE)

    def position(self, value: Any, path: str) -> bool:
        if not self.closed(value, path, ("line", "character"), ("line", "character")):
            return False
        return self.integer(value.get("line"), f"{path}.line") and self.integer(
            value.get("character"), f"{path}.character"
        )

    def range(self, value: Any, path: str) -> bool:
        if not self.closed(value, path, ("start", "end"), ("start", "end")):
            return False
        start_ok = self.position(value.get("start"), f"{path}.start")
        end_ok = self.position(value.get("end"), f"{path}.end")
        if start_ok and end_ok:
            start = (value["start"]["line"], value["start"]["character"])
            end = (value["end"]["line"], value["end"]["character"])
            if end < start:
                self.add(SEMANTIC, path, "range end precedes range start")
        return start_ok and end_ok

    def location(self, value: Any, path: str) -> bool:
        fields = ("artifactUri", "range", "domainUri")
        if not self.closed(value, path, fields, fields):
            return False
        okay = self.uri(value.get("artifactUri"), f"{path}.artifactUri", stable=False)
        okay = self.range(value.get("range"), f"{path}.range") and okay
        domain_uri = value.get("domainUri")
        if domain_uri is not None:
            okay = self.uri(domain_uri, f"{path}.domainUri", stable=True) and okay
        return okay

    def workspace_shape(self, doc: dict[str, Any], path: str) -> None:
        fields = (
            "kind",
            "workspaceId",
            "rootUri",
            "locality",
            "git",
            "languageServers",
            "limits",
        )
        if not self.closed(doc, path, fields, fields):
            return
        self.uri(doc["workspaceId"], f"{path}.workspaceId", stable=True)
        self.uri(doc["rootUri"], f"{path}.rootUri", stable=False)
        locality = doc["locality"]
        if not isinstance(locality, str) or locality not in {"local", "remote"}:
            self.add(SYNTAX, f"{path}.locality", "expected local or remote")

        git = doc["git"]
        git_fields = ("worktree", "branch", "revision", "dirty")
        if self.closed(git, f"{path}.git", git_fields, git_fields):
            if not isinstance(git["worktree"], bool):
                self.add(SYNTAX, f"{path}.git.worktree", "expected a boolean")
            if git["branch"] is not None:
                self.string(git["branch"], f"{path}.git.branch", pattern=GIT_BRANCH_RE)
            if git["revision"] is not None:
                self.string(git["revision"], f"{path}.git.revision", pattern=SHA_RE)
            if not isinstance(git["dirty"], bool):
                self.add(SYNTAX, f"{path}.git.dirty", "expected a boolean")

        servers = doc["languageServers"]
        if not isinstance(servers, list) or not servers:
            self.add(SYNTAX, f"{path}.languageServers", "expected a non-empty array")
        else:
            for index, server in enumerate(servers):
                self.language_server_shape(server, f"{path}.languageServers[{index}]")

        limits = doc["limits"]
        limit_fields = (
            "maxLocalWorkspaces",
            "maxRemoteWorkspaces",
            "maxLanguagesPerWorkspace",
            "indexingTimeoutSeconds",
            "idleShutdownSeconds",
        )
        if self.closed(limits, f"{path}.limits", limit_fields, limit_fields):
            for field in limit_fields:
                self.integer(limits[field], f"{path}.limits.{field}", 1)

    def language_server_shape(self, value: Any, path: str) -> None:
        fields = (
            "serverId",
            "language",
            "command",
            "transport",
            "version",
            "configurationDigest",
        )
        if not self.closed(value, path, fields, fields):
            return
        self.string(value["serverId"], f"{path}.serverId", pattern=ID_RE)
        self.string(value["language"], f"{path}.language", pattern=LANGUAGE_RE)
        command = value["command"]
        if not isinstance(command, list) or not 1 <= len(command) <= 32:
            self.add(SYNTAX, f"{path}.command", "expected 1..32 argv strings")
        else:
            for index, arg in enumerate(command):
                self.string(arg, f"{path}.command[{index}]")
        if value["transport"] != "stdio":
            self.add(SYNTAX, f"{path}.transport", "version 0.1 requires stdio")
        self.string(value["version"], f"{path}.version")
        self.digest(value["configurationDigest"], f"{path}.configurationDigest")

    def query_shape(self, doc: dict[str, Any], path: str) -> None:
        fields = (
            "kind",
            "queryId",
            "workspaceId",
            "operation",
            "documentUri",
            "position",
            "symbol",
            "includeDeclaration",
            "freshness",
            "maxResults",
        )
        if not self.closed(doc, path, fields, fields):
            return
        self.uri(doc["queryId"], f"{path}.queryId", stable=True)
        self.uri(doc["workspaceId"], f"{path}.workspaceId", stable=True)
        operation = doc["operation"]
        if not isinstance(operation, str) or operation not in OPERATIONS:
            self.add(SYNTAX, f"{path}.operation", "unknown operation")
        if doc["documentUri"] is not None:
            self.uri(doc["documentUri"], f"{path}.documentUri", stable=False)
        if doc["position"] is not None:
            self.position(doc["position"], f"{path}.position")
        if doc["symbol"] is not None:
            self.string(doc["symbol"], f"{path}.symbol", nonempty=False)
        if doc["includeDeclaration"] is not None and not isinstance(
            doc["includeDeclaration"], bool
        ):
            self.add(SYNTAX, f"{path}.includeDeclaration", "expected a boolean or null")
        freshness = doc["freshness"]
        if not isinstance(freshness, str) or freshness not in {"live", "cached_allowed"}:
            self.add(SYNTAX, f"{path}.freshness", "unknown freshness")
        self.integer(doc["maxResults"], f"{path}.maxResults", 1)
        if _is_strict_int(doc["maxResults"]) and doc["maxResults"] > 10000:
            self.add(SYNTAX, f"{path}.maxResults", "must be <= 10000")

    def snapshot_shape(self, doc: dict[str, Any], path: str) -> None:
        fields = (
            "kind",
            "snapshotId",
            "queryId",
            "workspaceId",
            "operation",
            "status",
            "incompleteReason",
            "producer",
            "subject",
            "observedAt",
            "stale",
            "results",
        )
        if not self.closed(doc, path, fields, fields):
            return
        for field in ("snapshotId", "queryId", "workspaceId"):
            self.uri(doc[field], f"{path}.{field}", stable=True)
        operation = doc["operation"]
        if not isinstance(operation, str) or operation not in OPERATIONS:
            self.add(SYNTAX, f"{path}.operation", "unknown operation")
        status = doc["status"]
        if not isinstance(status, str) or status not in {"complete", "partial", "unavailable"}:
            self.add(SYNTAX, f"{path}.status", "unknown snapshot status")
        if doc["incompleteReason"] is not None:
            self.string(doc["incompleteReason"], f"{path}.incompleteReason")
        self.producer_shape(doc["producer"], f"{path}.producer")
        self.subject_shape(doc["subject"], f"{path}.subject")
        self.timestamp(doc["observedAt"], f"{path}.observedAt")
        if not isinstance(doc["stale"], bool):
            self.add(SYNTAX, f"{path}.stale", "expected a boolean")
        self.results_shape(doc["results"], f"{path}.results")

    def producer_shape(self, value: Any, path: str) -> None:
        fields = (
            "binding",
            "protocolVersion",
            "serverId",
            "serverVersion",
            "configurationDigest",
        )
        if not self.closed(value, path, fields, fields):
            return
        if value["binding"] != "lsp":
            self.add(SYNTAX, f"{path}.binding", "expected lsp")
        if value["protocolVersion"] != "3.17":
            self.add(SYNTAX, f"{path}.protocolVersion", "expected 3.17")
        self.string(value["serverId"], f"{path}.serverId", pattern=ID_RE)
        self.string(value["serverVersion"], f"{path}.serverVersion")
        self.digest(value["configurationDigest"], f"{path}.configurationDigest")

    def subject_shape(self, value: Any, path: str) -> None:
        fields = ("workspaceRevision", "dirty", "documents")
        if not self.closed(value, path, fields, fields):
            return
        revision = value["workspaceRevision"]
        if revision is not None:
            self.string(revision, f"{path}.workspaceRevision", pattern=SHA_RE)
        if not isinstance(value["dirty"], bool):
            self.add(SYNTAX, f"{path}.dirty", "expected a boolean")
        documents = value["documents"]
        if not isinstance(documents, list):
            self.add(SYNTAX, f"{path}.documents", "expected an array")
            return
        doc_fields = ("artifactUri", "version", "digest")
        for index, document in enumerate(documents):
            item_path = f"{path}.documents[{index}]"
            if not self.closed(document, item_path, doc_fields, doc_fields):
                continue
            self.uri(document["artifactUri"], f"{item_path}.artifactUri", stable=False)
            if document["version"] is not None:
                self.integer(document["version"], f"{item_path}.version")
            self.digest(document["digest"], f"{item_path}.digest")

    def results_shape(self, value: Any, path: str) -> None:
        fields = ("symbols", "locations", "diagnostics", "hover")
        if not self.closed(value, path, fields, fields):
            return
        for field in ("symbols", "locations", "diagnostics"):
            if not isinstance(value[field], list):
                self.add(SYNTAX, f"{path}.{field}", "expected an array")
                return
        for index, symbol in enumerate(value["symbols"]):
            self.symbol_shape(symbol, f"{path}.symbols[{index}]")
        for index, location in enumerate(value["locations"]):
            self.location(location, f"{path}.locations[{index}]")
        for index, diagnostic in enumerate(value["diagnostics"]):
            self.diagnostic_shape(diagnostic, f"{path}.diagnostics[{index}]")
        if value["hover"] is not None:
            hover_path = f"{path}.hover"
            if self.closed(value["hover"], hover_path, ("format", "value"), ("format", "value")):
                hover_fmt = value["hover"]["format"]
                if not isinstance(hover_fmt, str) or hover_fmt not in {"plaintext", "markdown"}:
                    self.add(SYNTAX, f"{hover_path}.format", "unknown markup format")
                self.string(
                    value["hover"]["value"],
                    f"{hover_path}.value",
                    nonempty=False,
                    multiline=True,
                )

    def symbol_shape(self, value: Any, path: str) -> None:
        fields = (
            "domainUri",
            "language",
            "kind",
            "qualifiedName",
            "location",
            "references",
            "capabilities",
        )
        if not self.closed(value, path, fields, fields):
            return
        self.uri(value["domainUri"], f"{path}.domainUri", stable=True)
        self.string(value["language"], f"{path}.language", pattern=LANGUAGE_RE)
        sym_kind = value["kind"]
        if not isinstance(sym_kind, str) or sym_kind not in SYMBOL_KINDS:
            self.add(SYNTAX, f"{path}.kind", "unknown symbol kind")
        self.string(value["qualifiedName"], f"{path}.qualifiedName")
        if value["location"] is not None:
            self.location(value["location"], f"{path}.location")
        for field in ("references", "capabilities"):
            items = value[field]
            if not isinstance(items, list):
                self.add(SYNTAX, f"{path}.{field}", "expected an array")
                continue
            for index, uri in enumerate(items):
                self.uri(uri, f"{path}.{field}[{index}]", stable=True)

    def diagnostic_shape(self, value: Any, path: str) -> None:
        fields = ("source", "code", "severity", "message", "location", "relatedDomainUris")
        if not self.closed(value, path, fields, fields):
            return
        self.string(value["source"], f"{path}.source")
        self.string(value["code"], f"{path}.code")
        self.string(value["message"], f"{path}.message", multiline=True)
        severity = value["severity"]
        if not isinstance(severity, str) or severity not in {
            "error",
            "warning",
            "information",
            "hint",
        }:
            self.add(SYNTAX, f"{path}.severity", "unknown diagnostic severity")
        self.location(value["location"], f"{path}.location")
        related = value["relatedDomainUris"]
        if not isinstance(related, list):
            self.add(SYNTAX, f"{path}.relatedDomainUris", "expected an array")
        else:
            for index, uri in enumerate(related):
                self.uri(uri, f"{path}.relatedDomainUris[{index}]", stable=True)

    def timestamp(self, value: Any, path: str) -> None:
        if not self.string(value, path):
            return
        match = RFC3339_RE.fullmatch(value)
        if match is None:
            self.add(SYNTAX, path, "expected an RFC 3339 date-time")
            return
        normalized = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
        frac = match.group(1)
        if frac is not None and len(frac) > 6:
            dot_idx = normalized.index(".")
            tz_idx = dot_idx + 1 + len(frac)
            normalized = f"{normalized[:dot_idx]}.{frac[:6]}{normalized[tz_idx:]}"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            self.add(SYNTAX, path, "expected an RFC 3339 date-time")
            return
        if parsed.tzinfo is None:
            self.add(SYNTAX, path, "expected an RFC 3339 date-time")
