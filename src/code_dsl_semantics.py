"""Cross-document semantic, canonical ordering, and workspace boundary checks for Code DSL 0.1."""

from __future__ import annotations

import posixpath
from typing import Any
from urllib.parse import urlsplit

from code_dsl_shapes import (
    BOUNDARY,
    SEMANTIC,
    SYNTAX,
    Finding,
    ShapeValidator,
    _fully_unquote,
    _is_strict_int,
)


class Validator(ShapeValidator):
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
        ws_list: list[tuple[str, int, dict[str, Any]]] = []
        q_list: list[tuple[str, int, dict[str, Any]]] = []
        snap_list: list[tuple[int, dict[str, Any]]] = []

        for index, doc in documents:
            kind = doc.get("kind")
            if not isinstance(kind, str):
                continue
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
            else:
                target[identifier] = (index, doc)
            if kind == "workspace":
                ws_list.append((identifier, index, doc))
            elif kind == "query":
                q_list.append((identifier, index, doc))
            else:
                snap_list.append((index, doc))

        for workspace_id, index, workspace in ws_list:
            self.workspace_semantic(workspace_id, index, workspace)
        for query_id, index, query in q_list:
            self.query_semantic(query_id, index, query, workspaces)
        for index, snapshot in snap_list:
            self.snapshot_semantic(index, snapshot, workspaces, queries)

    def workspace_semantic(self, workspace_id: str, index: int, workspace: dict[str, Any]) -> None:
        path = f"$.documents[{index}]"
        servers = workspace.get("languageServers")
        limits = workspace.get("limits")
        if not isinstance(servers, list) or not isinstance(limits, dict):
            return
        server_ids = [
            server["serverId"]
            for server in servers
            if isinstance(server, dict) and isinstance(server.get("serverId"), str)
        ]
        languages = [
            server["language"]
            for server in servers
            if isinstance(server, dict) and isinstance(server.get("language"), str)
        ]
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
        if _is_strict_int(maximum) and len(servers) > maximum:
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
        ws_id = query.get("workspaceId")
        workspace_entry = workspaces.get(ws_id) if isinstance(ws_id, str) else None
        if workspace_entry is None:
            self.add(SEMANTIC, f"{path}.workspaceId", "query references an unknown workspace")
            return
        workspace = workspace_entry[1]
        operation = query.get("operation")
        document = query.get("documentUri")
        position = query.get("position")
        symbol = query.get("symbol")
        include = query.get("includeDeclaration")
        expected = (
            {
                "diagnostics": (True, False, False, False),
                "hover": (True, True, False, False),
                "definition": (True, True, False, False),
                "references": (True, True, False, True),
            }.get(operation)
            if isinstance(operation, str)
            else None
        )
        if expected is None and isinstance(operation, str):
            expected = {
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
        if isinstance(document, str) and isinstance(workspace.get("rootUri"), str):
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
        ws_id = snapshot.get("workspaceId")
        q_id = snapshot.get("queryId")
        workspace_entry = workspaces.get(ws_id) if isinstance(ws_id, str) else None
        query_entry = queries.get(q_id) if isinstance(q_id, str) else None
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
        if (
            isinstance(status, str)
            and status in {"partial", "unavailable"}
            and not isinstance(reason, str)
        ):
            self.add(SEMANTIC, f"{path}.incompleteReason", f"{status} snapshots require a reason")

        producer = snapshot.get("producer")
        raw_servers = workspace.get("languageServers")
        servers = raw_servers if isinstance(raw_servers, list) else []
        if isinstance(producer, dict):
            matching = [
                server
                for server in servers
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
                git = workspace.get("git")
                if isinstance(git, dict):
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
        list_fields: dict[str, list[Any]] = {}
        for field in ("symbols", "locations", "diagnostics"):
            raw_list = results.get(field)
            list_fields[field] = raw_list if isinstance(raw_list, list) else []
        payload = {
            "symbols": bool(list_fields["symbols"]),
            "locations": bool(list_fields["locations"]),
            "diagnostics": bool(list_fields["diagnostics"]),
            "hover": results.get("hover") is not None,
        }
        snap_op = snapshot.get("operation")
        allowed_field = (
            {
                "diagnostics": "diagnostics",
                "hover": "hover",
                "definition": "locations",
                "references": "locations",
                "document_symbols": "symbols",
                "workspace_symbols": "symbols",
            }.get(snap_op)
            if isinstance(snap_op, str)
            else None
        )
        for field, populated in payload.items():
            if populated and field != allowed_field:
                self.add(
                    SEMANTIC, f"{path}.results.{field}", "result field does not match the operation"
                )
        if status == "unavailable" and any(payload.values()):
            self.add(
                SEMANTIC, f"{path}.results", "unavailable snapshots must have an empty payload"
            )

        result_count = sum(len(items) for items in list_fields.values()) + int(
            results.get("hover") is not None
        )
        if _is_strict_int(query.get("maxResults")) and result_count > query["maxResults"]:
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
            loc_keys = [self.location_key(item) for item in locations]
            if all(key is not None for key in loc_keys):
                self.require_sorted_unique(loc_keys, f"{path}.results.locations")

        diagnostics = results.get("diagnostics", [])
        if isinstance(diagnostics, list) and all(isinstance(item, dict) for item in diagnostics):
            diag_keys = [self.diagnostic_key(item) for item in diagnostics]
            if all(key is not None for key in diag_keys):
                self.require_sorted_unique(diag_keys, f"{path}.results.diagnostics")
            for index, diagnostic in enumerate(diagnostics):
                values = diagnostic.get("relatedDomainUris")
                if isinstance(values, list) and all(isinstance(item, str) for item in values):
                    self.require_sorted_unique(
                        values, f"{path}.results.diagnostics[{index}].relatedDomainUris"
                    )

    def check_result_boundaries(self, results: dict[str, Any], root_uri: str, path: str) -> None:
        raw_locations = results.get("locations")
        if isinstance(raw_locations, list):
            for index, location in enumerate(raw_locations):
                if isinstance(location, dict) and isinstance(location.get("artifactUri"), str):
                    self.confined(
                        root_uri,
                        location["artifactUri"],
                        f"{path}.results.locations[{index}].artifactUri",
                    )
        for field in ("symbols", "diagnostics"):
            raw_items = results.get(field)
            if not isinstance(raw_items, list):
                continue
            for index, item in enumerate(raw_items):
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
        raw_root, root_converged = _fully_unquote(root.path)
        raw_artifact, artifact_converged = _fully_unquote(artifact.path)
        if (
            not root_converged
            or not artifact_converged
            or root.query
            or root.fragment
            or artifact.query
            or artifact.fragment
            or "\x00" in raw_root
            or "\x00" in raw_artifact
            or "\\" in raw_root
            or "\\" in raw_artifact
            or ".." in raw_root.split("/")
            or ".." in raw_artifact.split("/")
        ):
            self.add(BOUNDARY, path, "artifact URI escapes the workspace root")
            return
        root_path = posixpath.normpath(raw_root)
        artifact_path = posixpath.normpath(raw_artifact)
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
            artifact_uri = location["artifactUri"]
            start = location["range"]["start"]
            end = location["range"]["end"]
            coords = (start["line"], start["character"], end["line"], end["character"])
        except (KeyError, TypeError):
            return None
        if not isinstance(artifact_uri, str) or not all(_is_strict_int(item) for item in coords):
            return None
        return (artifact_uri, *coords)

    @classmethod
    def diagnostic_key(cls, diagnostic: dict[str, Any]) -> tuple[Any, ...] | None:
        raw_location = diagnostic.get("location")
        if not isinstance(raw_location, dict):
            return None
        location = cls.location_key(raw_location)
        if location is None:
            return None
        severity = diagnostic.get("severity")
        code = diagnostic.get("code")
        message = diagnostic.get("message")
        if not all(isinstance(item, str) for item in (severity, code, message)):
            return None
        return (*location[:3], severity, code, message)
