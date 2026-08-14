#!/usr/bin/env python3
"""Dependency-free conformance checker for Wellmanifest Code DSL 0.1."""

from __future__ import annotations

import argparse
import copy
import json
import posixpath
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

SYNTAX = "CODE-SYNTAX-001"
SEMANTIC = "CODE-SEMANTIC-001"
BOUNDARY = "CODE-BOUNDARY-001"

URI_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:[^\s]+$")
DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
SHA_RE = re.compile(r"^[a-f0-9]{40}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
LANGUAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+._-]*$")

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


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    message: str

    @property
    def security(self) -> bool:
        return self.code == BOUNDARY


class Validator:
    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def add(self, code: str, path: str, message: str) -> None:
        finding = Finding(code, path, message)
        if finding not in self.findings:
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
        pattern: re.Pattern[str] | None = None,
    ) -> bool:
        if not isinstance(value, str) or (nonempty and not value):
            self.add(SYNTAX, path, "expected a non-empty string")
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
        decoded_parts = unquote(parsed.path).split("/")
        if ".." in decoded_parts:
            self.add(BOUNDARY, path, "URI path traversal is forbidden")
        if stable and parsed.scheme.lower() == "file":
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
        if doc["locality"] not in {"local", "remote"}:
            self.add(SYNTAX, f"{path}.locality", "expected local or remote")

        git = doc["git"]
        git_fields = ("worktree", "branch", "revision", "dirty")
        if self.closed(git, f"{path}.git", git_fields, git_fields):
            if not isinstance(git["worktree"], bool):
                self.add(SYNTAX, f"{path}.git.worktree", "expected a boolean")
            if git["branch"] is not None:
                self.string(git["branch"], f"{path}.git.branch")
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
        if doc["operation"] not in OPERATIONS:
            self.add(SYNTAX, f"{path}.operation", "unknown operation")
        if doc["documentUri"] is not None:
            self.uri(doc["documentUri"], f"{path}.documentUri", stable=False)
        if doc["position"] is not None:
            self.position(doc["position"], f"{path}.position")
        if doc["symbol"] is not None and not isinstance(doc["symbol"], str):
            self.add(SYNTAX, f"{path}.symbol", "expected a string or null")
        if doc["includeDeclaration"] is not None and not isinstance(
            doc["includeDeclaration"], bool
        ):
            self.add(SYNTAX, f"{path}.includeDeclaration", "expected a boolean or null")
        if doc["freshness"] not in {"live", "cached_allowed"}:
            self.add(SYNTAX, f"{path}.freshness", "unknown freshness")
        self.integer(doc["maxResults"], f"{path}.maxResults", 1)
        if isinstance(doc["maxResults"], int) and doc["maxResults"] > 10000:
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
        if doc["operation"] not in OPERATIONS:
            self.add(SYNTAX, f"{path}.operation", "unknown operation")
        if doc["status"] not in {"complete", "partial", "unavailable"}:
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
        fields = ("artifactUri", "version", "digest")
        for index, document in enumerate(documents):
            item_path = f"{path}.documents[{index}]"
            if not self.closed(document, item_path, fields, fields):
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
                if value["hover"]["format"] not in {"plaintext", "markdown"}:
                    self.add(SYNTAX, f"{hover_path}.format", "unknown markup format")
                if not isinstance(value["hover"]["value"], str):
                    self.add(SYNTAX, f"{hover_path}.value", "expected a string")

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
        if value["kind"] not in SYMBOL_KINDS:
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
        for field in ("source", "code", "message"):
            self.string(value[field], f"{path}.{field}")
        if value["severity"] not in {"error", "warning", "information", "hint"}:
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
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            self.add(SYNTAX, path, "expected an RFC 3339 date-time")

    def validate(self, data: Any) -> list[Finding]:
        root_fields = ("schema", "documents")
        if not isinstance(data, dict):
            self.add(SYNTAX, "$", "expected a document-set object")
            return self.findings
        allowed = ("$schema", "schema", "documents")
        if not self.closed(data, "$", root_fields, allowed):
            return self.findings
        if data["schema"] != "wellmanifest.code/json/v1":
            self.add(SYNTAX, "$.schema", "unsupported Code DSL schema")
        documents = data["documents"]
        if not isinstance(documents, list) or not documents:
            self.add(SYNTAX, "$.documents", "expected a non-empty array")
            return self.findings

        shaped_documents: list[tuple[int, dict[str, Any]]] = []
        for index, document in enumerate(documents):
            path = f"$.documents[{index}]"
            if not isinstance(document, dict):
                self.add(SYNTAX, path, "expected an object")
                continue
            kind = document.get("kind")
            if kind == "workspace":
                self.workspace_shape(document, path)
            elif kind == "query":
                self.query_shape(document, path)
            elif kind == "snapshot":
                self.snapshot_shape(document, path)
            else:
                self.add(SYNTAX, f"{path}.kind", "expected workspace, query, or snapshot")
                continue
            shaped_documents.append((index, document))

        self.semantic(shaped_documents)
        return sorted(
            self.findings, key=lambda finding: (finding.path, finding.code, finding.message)
        )

    def semantic(self, documents: list[tuple[int, dict[str, Any]]]) -> None:
        workspaces: dict[str, tuple[int, dict[str, Any]]] = {}
        queries: dict[str, tuple[int, dict[str, Any]]] = {}
        snapshots: dict[str, tuple[int, dict[str, Any]]] = {}

        for index, doc in documents:
            kind = doc.get("kind")
            id_field = {
                "workspace": "workspaceId",
                "query": "queryId",
                "snapshot": "snapshotId",
            }.get(kind)
            if id_field is None or not isinstance(doc.get(id_field), str):
                continue
            target = {"workspace": workspaces, "query": queries, "snapshot": snapshots}[kind]
            identifier = doc[id_field]
            if identifier in target:
                self.add(
                    SEMANTIC, f"$.documents[{index}].{id_field}", "duplicate document identity"
                )
            target[identifier] = (index, doc)

        for workspace_id, (index, workspace) in workspaces.items():
            self.workspace_semantic(workspace_id, index, workspace)
        for query_id, (index, query) in queries.items():
            self.query_semantic(query_id, index, query, workspaces)
        for _, (index, snapshot) in snapshots.items():
            self.snapshot_semantic(index, snapshot, workspaces, queries)

    def workspace_semantic(self, workspace_id: str, index: int, workspace: dict[str, Any]) -> None:
        path = f"$.documents[{index}]"
        servers = workspace.get("languageServers")
        limits = workspace.get("limits")
        if not isinstance(servers, list) or not isinstance(limits, dict):
            return
        server_ids = [server.get("serverId") for server in servers if isinstance(server, dict)]
        languages = [server.get("language") for server in servers if isinstance(server, dict)]
        if len(server_ids) != len(set(server_ids)):
            self.add(SEMANTIC, f"{path}.languageServers", "server IDs must be unique")
        if len(languages) != len(set(languages)):
            self.add(SEMANTIC, f"{path}.languageServers", "languages must be unique")
        sort_keys = [
            (server.get("language"), server.get("serverId"))
            for server in servers
            if isinstance(server, dict)
        ]
        if all(isinstance(item[0], str) and isinstance(item[1], str) for item in sort_keys):
            self.require_sorted_unique(sort_keys, f"{path}.languageServers")
        maximum = limits.get("maxLanguagesPerWorkspace")
        if isinstance(maximum, int) and len(servers) > maximum:
            self.add(
                SEMANTIC,
                f"{path}.limits.maxLanguagesPerWorkspace",
                "configured language servers exceed the workspace limit",
            )
        git = workspace.get("git")
        if isinstance(git, dict) and git.get("dirty") is False and git.get("revision") is None:
            self.add(SEMANTIC, f"{path}.git.revision", "a clean Git workspace requires a revision")
        self.uri(workspace_id, f"{path}.workspaceId", stable=True)

    def query_semantic(
        self,
        query_id: str,
        index: int,
        query: dict[str, Any],
        workspaces: dict[str, tuple[int, dict[str, Any]]],
    ) -> None:
        path = f"$.documents[{index}]"
        workspace_entry = workspaces.get(query.get("workspaceId"))
        if workspace_entry is None:
            self.add(SEMANTIC, f"{path}.workspaceId", "query references an unknown workspace")
            return
        workspace = workspace_entry[1]
        operation = query.get("operation")
        document = query.get("documentUri")
        position = query.get("position")
        symbol = query.get("symbol")
        include = query.get("includeDeclaration")
        expected = {
            "diagnostics": (True, False, False, False),
            "hover": (True, True, False, False),
            "definition": (True, True, False, False),
            "references": (True, True, False, True),
            "document_symbols": (True, False, False, False),
            "workspace_symbols": (False, False, True, False),
        }.get(operation)
        if expected is not None:
            values = (
                document is not None,
                position is not None,
                symbol is not None,
                include is not None,
            )
            if values != expected:
                self.add(SEMANTIC, path, f"operands do not match operation {operation!r}")
        if document is not None and isinstance(workspace.get("rootUri"), str):
            self.confined(workspace["rootUri"], document, f"{path}.documentUri")
        self.uri(query_id, f"{path}.queryId", stable=True)

    def snapshot_semantic(
        self,
        index: int,
        snapshot: dict[str, Any],
        workspaces: dict[str, tuple[int, dict[str, Any]]],
        queries: dict[str, tuple[int, dict[str, Any]]],
    ) -> None:
        path = f"$.documents[{index}]"
        workspace_entry = workspaces.get(snapshot.get("workspaceId"))
        query_entry = queries.get(snapshot.get("queryId"))
        if workspace_entry is None:
            self.add(SEMANTIC, f"{path}.workspaceId", "snapshot references an unknown workspace")
            return
        if query_entry is None:
            self.add(SEMANTIC, f"{path}.queryId", "snapshot references an unknown query")
            return
        workspace = workspace_entry[1]
        query = query_entry[1]
        if query.get("workspaceId") != snapshot.get("workspaceId"):
            self.add(SEMANTIC, f"{path}.workspaceId", "snapshot and query workspace differ")
        if query.get("operation") != snapshot.get("operation"):
            self.add(SEMANTIC, f"{path}.operation", "snapshot and query operation differ")

        status = snapshot.get("status")
        reason = snapshot.get("incompleteReason")
        if status == "complete" and reason is not None:
            self.add(SEMANTIC, f"{path}.incompleteReason", "complete snapshots require null")
        if status in {"partial", "unavailable"} and not isinstance(reason, str):
            self.add(SEMANTIC, f"{path}.incompleteReason", f"{status} snapshots require a reason")

        producer = snapshot.get("producer")
        if isinstance(producer, dict):
            matching = [
                server
                for server in workspace.get("languageServers", [])
                if isinstance(server, dict) and server.get("serverId") == producer.get("serverId")
            ]
            if not matching:
                self.add(
                    SEMANTIC,
                    f"{path}.producer.serverId",
                    "producer is not configured in the workspace",
                )
            else:
                server = matching[0]
                if server.get("version") != producer.get("serverVersion"):
                    self.add(
                        SEMANTIC,
                        f"{path}.producer.serverVersion",
                        "producer version differs from workspace configuration",
                    )
                if server.get("configurationDigest") != producer.get("configurationDigest"):
                    self.add(
                        SEMANTIC,
                        f"{path}.producer.configurationDigest",
                        "producer configuration digest differs from workspace configuration",
                    )

        subject = snapshot.get("subject")
        root_uri = workspace.get("rootUri")
        if isinstance(subject, dict):
            documents = subject.get("documents", [])
            if isinstance(documents, list):
                uris = [
                    document.get("artifactUri")
                    for document in documents
                    if isinstance(document, dict)
                ]
                if all(isinstance(uri, str) for uri in uris):
                    self.require_sorted_unique(uris, f"{path}.subject.documents")
                    if isinstance(root_uri, str):
                        for item_index, uri in enumerate(uris):
                            self.confined(
                                root_uri, uri, f"{path}.subject.documents[{item_index}].artifactUri"
                            )
            if snapshot.get("stale") is False:
                git = workspace.get("git", {})
                if subject.get("dirty") != git.get("dirty"):
                    self.add(
                        SEMANTIC,
                        f"{path}.subject.dirty",
                        "fresh snapshot dirty state differs from workspace",
                    )
                if subject.get("workspaceRevision") != git.get("revision"):
                    self.add(
                        SEMANTIC,
                        f"{path}.subject.workspaceRevision",
                        "fresh snapshot revision differs from workspace",
                    )

        results = snapshot.get("results")
        if not isinstance(results, dict):
            return
        payload = {
            "symbols": bool(results.get("symbols")),
            "locations": bool(results.get("locations")),
            "diagnostics": bool(results.get("diagnostics")),
            "hover": results.get("hover") is not None,
        }
        allowed_field = {
            "diagnostics": "diagnostics",
            "hover": "hover",
            "definition": "locations",
            "references": "locations",
            "document_symbols": "symbols",
            "workspace_symbols": "symbols",
        }.get(snapshot.get("operation"))
        for field, populated in payload.items():
            if populated and field != allowed_field:
                self.add(
                    SEMANTIC, f"{path}.results.{field}", "result field does not match the operation"
                )
        if status == "unavailable" and any(payload.values()):
            self.add(
                SEMANTIC, f"{path}.results", "unavailable snapshots must have an empty payload"
            )

        result_count = sum(
            len(results.get(field, [])) for field in ("symbols", "locations", "diagnostics")
        )
        result_count += int(results.get("hover") is not None)
        if isinstance(query.get("maxResults"), int) and result_count > query["maxResults"]:
            self.add(SEMANTIC, f"{path}.results", "result count exceeds the query bound")

        self.check_result_order(results, path)
        if isinstance(root_uri, str):
            self.check_result_boundaries(results, root_uri, path)

    def check_result_order(self, results: dict[str, Any], path: str) -> None:
        symbols = results.get("symbols", [])
        if isinstance(symbols, list) and all(isinstance(item, dict) for item in symbols):
            keys = [(item.get("domainUri"), item.get("qualifiedName")) for item in symbols]
            if all(isinstance(a, str) and isinstance(b, str) for a, b in keys):
                self.require_sorted_unique(keys, f"{path}.results.symbols")
            for index, symbol in enumerate(symbols):
                for field in ("references", "capabilities"):
                    values = symbol.get(field)
                    if isinstance(values, list) and all(isinstance(item, str) for item in values):
                        self.require_sorted_unique(
                            values, f"{path}.results.symbols[{index}].{field}"
                        )

        locations = results.get("locations", [])
        if isinstance(locations, list) and all(isinstance(item, dict) for item in locations):
            keys = [self.location_key(item) for item in locations]
            if all(key is not None for key in keys):
                self.require_sorted_unique(keys, f"{path}.results.locations")

        diagnostics = results.get("diagnostics", [])
        if isinstance(diagnostics, list) and all(isinstance(item, dict) for item in diagnostics):
            keys = [self.diagnostic_key(item) for item in diagnostics]
            if all(key is not None for key in keys):
                self.require_sorted_unique(keys, f"{path}.results.diagnostics")
            for index, diagnostic in enumerate(diagnostics):
                values = diagnostic.get("relatedDomainUris")
                if isinstance(values, list) and all(isinstance(item, str) for item in values):
                    self.require_sorted_unique(
                        values, f"{path}.results.diagnostics[{index}].relatedDomainUris"
                    )

    def check_result_boundaries(self, results: dict[str, Any], root_uri: str, path: str) -> None:
        for field in ("locations",):
            for index, location in enumerate(results.get(field, [])):
                if isinstance(location, dict) and isinstance(location.get("artifactUri"), str):
                    self.confined(
                        root_uri,
                        location["artifactUri"],
                        f"{path}.results.{field}[{index}].artifactUri",
                    )
        for field in ("symbols", "diagnostics"):
            for index, item in enumerate(results.get(field, [])):
                if not isinstance(item, dict):
                    continue
                location = item.get("location")
                if isinstance(location, dict) and isinstance(location.get("artifactUri"), str):
                    self.confined(
                        root_uri,
                        location["artifactUri"],
                        f"{path}.results.{field}[{index}].location.artifactUri",
                    )

    def confined(self, root_uri: str, artifact_uri: str, path: str) -> None:
        root = urlsplit(root_uri)
        artifact = urlsplit(artifact_uri)
        root_path = posixpath.normpath(unquote(root.path))
        artifact_path = posixpath.normpath(unquote(artifact.path))
        same_origin = (root.scheme.lower(), root.netloc) == (
            artifact.scheme.lower(),
            artifact.netloc,
        )
        within = artifact_path == root_path or artifact_path.startswith(root_path.rstrip("/") + "/")
        if not same_origin or not within:
            self.add(BOUNDARY, path, "artifact URI escapes the workspace root")

    def require_sorted_unique(self, values: list[Any], path: str) -> None:
        if values != sorted(values):
            self.add(SEMANTIC, path, "array is not in canonical order")
        if len(values) != len(set(values)):
            self.add(SEMANTIC, path, "array contains duplicate keys")

    @staticmethod
    def location_key(location: dict[str, Any]) -> tuple[Any, ...] | None:
        try:
            start = location["range"]["start"]
            end = location["range"]["end"]
            return (
                location["artifactUri"],
                start["line"],
                start["character"],
                end["line"],
                end["character"],
            )
        except (KeyError, TypeError):
            return None

    @classmethod
    def diagnostic_key(cls, diagnostic: dict[str, Any]) -> tuple[Any, ...] | None:
        location = cls.location_key(diagnostic.get("location", {}))
        if location is None:
            return None
        return (
            *location[:3],
            diagnostic.get("severity"),
            diagnostic.get("code"),
            diagnostic.get("message"),
        )


def validate_document(data: Any) -> list[Finding]:
    return Validator().validate(data)


def load_and_validate(path: Path) -> list[Finding]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [Finding(SYNTAX, str(path), f"cannot parse JSON: {exc}")]
    return validate_document(data)


def discover(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    if target.is_dir():
        return sorted(target.rglob("*.code-dsl.json"))
    return []


def validate_target(target: Path) -> tuple[list[Path], list[tuple[Path, Finding]]]:
    paths = discover(target)
    findings: list[tuple[Path, Finding]] = []
    if not paths:
        findings.append((target, Finding(SYNTAX, str(target), "no Code DSL documents found")))
    for path in paths:
        findings.extend((path, finding) for finding in load_and_validate(path))
    return paths, findings


def self_test() -> int:
    root = Path(__file__).resolve().parents[1]
    valid = root / "examples" / "valid" / "subactor-workspace.code-dsl.json"
    invalid = root / "examples" / "invalid" / "boundary-and-limit.code-dsl.json"

    valid_findings = load_and_validate(valid)
    if valid_findings:
        for finding in valid_findings:
            print(f"SELF-TEST valid fixture: {finding.code} {finding.path}: {finding.message}")
        return 1

    invalid_findings = load_and_validate(invalid)
    observed_codes = {finding.code for finding in invalid_findings}
    if not {SEMANTIC, BOUNDARY} <= observed_codes:
        observed = ", ".join(sorted(observed_codes))
        print(f"SELF-TEST invalid fixture: expected semantic and boundary findings, got {observed}")
        return 1

    data = json.loads(valid.read_text(encoding="utf-8"))
    mutation = copy.deepcopy(data)
    mutation["unexpected"] = True
    if SYNTAX not in {finding.code for finding in validate_document(mutation)}:
        print("SELF-TEST closed shape: unknown property was accepted")
        return 1

    mutation = copy.deepcopy(data)
    query = next(document for document in mutation["documents"] if document["kind"] == "query")
    query["documentUri"] = "file:///workspace/other/outside.rs"
    if BOUNDARY not in {finding.code for finding in validate_document(mutation)}:
        print("SELF-TEST boundary: root escape was accepted")
        return 1

    print("CODE-DSL SELF-TEST PASS")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="validate a Code DSL file or directory")
    validate.add_argument("target", type=Path)
    subparsers.add_parser("self-test", help="run built-in conformance mutations")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "self-test":
        return self_test()

    paths, findings = validate_target(args.target)
    if findings:
        for source, finding in findings:
            print(f"{finding.code} {source}:{finding.path}: {finding.message}")
        return 1
    print(f"CODE-DSL PASS: {len(paths)} document set(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
