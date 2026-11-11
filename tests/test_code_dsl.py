from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "src" / "code_dsl_check.py"
SPEC = importlib.util.spec_from_file_location("code_dsl_check", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
code_dsl_check = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = code_dsl_check
SPEC.loader.exec_module(code_dsl_check)


class CodeDslConformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.valid_path = ROOT / "examples" / "valid" / "subactor-workspace.code-dsl.json"
        cls.invalid_path = ROOT / "examples" / "invalid" / "boundary-and-limit.code-dsl.json"
        cls.valid = json.loads(cls.valid_path.read_text(encoding="utf-8"))

    def codes(self, document: dict) -> set[str]:
        return {finding.code for finding in code_dsl_check.validate_document(document)}

    def test_valid_example_passes(self) -> None:
        self.assertEqual([], code_dsl_check.validate_document(self.valid))

    def test_invalid_example_fails_closed(self) -> None:
        findings = code_dsl_check.load_and_validate(self.invalid_path)
        self.assertIn(code_dsl_check.BOUNDARY, {finding.code for finding in findings})
        self.assertIn(code_dsl_check.SEMANTIC, {finding.code for finding in findings})

    def test_valid_example_covers_exact_baseline_operations(self) -> None:
        operations = {
            document["operation"]
            for document in self.valid["documents"]
            if document["kind"] == "query"
        }
        self.assertEqual(code_dsl_check.OPERATIONS, operations)
        snapshot_operations = {
            document["operation"]
            for document in self.valid["documents"]
            if document["kind"] == "snapshot"
        }
        self.assertEqual(code_dsl_check.OPERATIONS, snapshot_operations)

    def test_unknown_root_and_nested_properties_are_rejected(self) -> None:
        root_mutation = copy.deepcopy(self.valid)
        root_mutation["unknown"] = True
        self.assertIn(code_dsl_check.SYNTAX, self.codes(root_mutation))

        nested_mutation = copy.deepcopy(self.valid)
        workspace = nested_mutation["documents"][0]
        workspace["limits"]["burst"] = 4
        self.assertIn(code_dsl_check.SYNTAX, self.codes(nested_mutation))

    def test_query_operands_are_operation_specific(self) -> None:
        mutation = copy.deepcopy(self.valid)
        query = next(
            document
            for document in mutation["documents"]
            if document.get("operation") == "references" and document["kind"] == "query"
        )
        query["includeDeclaration"] = None
        self.assertIn(code_dsl_check.SEMANTIC, self.codes(mutation))

    def test_snapshot_payload_must_match_operation(self) -> None:
        mutation = copy.deepcopy(self.valid)
        snapshot = next(
            document
            for document in mutation["documents"]
            if document.get("operation") == "hover" and document["kind"] == "snapshot"
        )
        snapshot["results"]["locations"] = [
            {
                "artifactUri": "file:///workspace/subactor-api/src/billing.rs",
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 0, "character": 1},
                },
                "domainUri": None,
            }
        ]
        self.assertIn(code_dsl_check.SEMANTIC, self.codes(mutation))

    def test_path_escape_is_security_critical(self) -> None:
        mutation = copy.deepcopy(self.valid)
        query = next(document for document in mutation["documents"] if document["kind"] == "query")
        query["documentUri"] = "file:///workspace/other/outside.rs"
        findings = code_dsl_check.validate_document(mutation)
        boundary = [finding for finding in findings if finding.code == code_dsl_check.BOUNDARY]
        self.assertTrue(boundary)
        self.assertTrue(all(finding.security for finding in boundary))

    def test_range_end_before_start_is_rejected(self) -> None:
        mutation = copy.deepcopy(self.valid)
        diagnostic_snapshot = next(
            document
            for document in mutation["documents"]
            if document.get("operation") == "diagnostics" and document["kind"] == "snapshot"
        )
        diagnostic_snapshot["results"]["diagnostics"][0]["location"]["range"] = {
            "start": {"line": 9, "character": 0},
            "end": {"line": 8, "character": 0},
        }
        self.assertIn(code_dsl_check.SEMANTIC, self.codes(mutation))

    def test_public_schema_and_proto_contracts_are_present(self) -> None:
        schema = json.loads((ROOT / "schemas" / "code-dsl.schema.json").read_text(encoding="utf-8"))
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertFalse(schema["additionalProperties"])

        proto = (ROOT / "proto" / "wellmanifest" / "code" / "v1" / "code_dsl.proto").read_text(
            encoding="utf-8"
        )
        for message in ("CodeDocumentSet", "Workspace", "SemanticQuery", "SemanticSnapshot"):
            self.assertIn(f"message {message}", proto)

    def test_double_encoded_and_backslash_uri_traversal_rejected(self) -> None:
        for bad_uri in (
            "file:///workspace/subactor-api/%252e%252e/other/secret.rs",
            "file:///workspace/subactor-api\\..\\other\\secret.rs",
            "file:///workspace/subactor-api/src/billing.rs%00.txt",
        ):
            mutation = copy.deepcopy(self.valid)
            query = next(doc for doc in mutation["documents"] if doc["kind"] == "query")
            query["documentUri"] = bad_uri
            findings = code_dsl_check.validate_document(mutation)
            self.assertIn(code_dsl_check.BOUNDARY, {f.code for f in findings}, bad_uri)

    def test_strict_rfc3339_timestamps_enforced(self) -> None:
        for bad_ts in ("2026-08-14", "2026-08-14T12:00:00", "2026-08-14 12:00:00Z"):
            mutation = copy.deepcopy(self.valid)
            snapshot = next(doc for doc in mutation["documents"] if doc["kind"] == "snapshot")
            snapshot["observedAt"] = bad_ts
            self.assertIn(code_dsl_check.SYNTAX, self.codes(mutation), bad_ts)

    def test_mixed_type_diagnostics_and_bool_limits_do_not_crash(self) -> None:
        mutation = copy.deepcopy(self.valid)
        diagnostic_snapshot = next(
            doc
            for doc in mutation["documents"]
            if doc.get("operation") == "diagnostics" and doc["kind"] == "snapshot"
        )
        valid_diag = copy.deepcopy(diagnostic_snapshot["results"]["diagnostics"][0])
        bad_diag = copy.deepcopy(valid_diag)
        bad_diag["severity"] = 42
        diagnostic_snapshot["results"]["diagnostics"] = [valid_diag, bad_diag]
        self.assertIn(code_dsl_check.SYNTAX, self.codes(mutation))

        bool_mutation = copy.deepcopy(self.valid)
        bool_mutation["documents"][0]["limits"]["maxLanguagesPerWorkspace"] = False
        query = next(doc for doc in bool_mutation["documents"] if doc["kind"] == "query")
        query["maxResults"] = True
        codes = self.codes(bool_mutation)
        self.assertIn(code_dsl_check.SYNTAX, codes)

    def test_duplicate_json_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dup = Path(directory) / "dup.code-dsl.json"
            dup.write_text('{"schema":"a","schema":"b","documents":[]}\n', encoding="utf-8")
            findings = code_dsl_check.load_and_validate(dup)
            self.assertEqual([code_dsl_check.SYNTAX], [f.code for f in findings])

            link = Path(directory) / "symlink.code-dsl.json"
            link.symlink_to(self.valid_path)
            link_findings = code_dsl_check.load_and_validate(link)
            self.assertEqual([code_dsl_check.SYNTAX], [f.code for f in link_findings])
            self.assertEqual(1, code_dsl_check.main(["validate", str(link)]))
            self.assertEqual(1, code_dsl_check.main(["validate", directory]))

            deep = Path(directory) / "deep.code-dsl.json"
            deep.write_text('{"a":' * 128 + "1" + "}" * 128, encoding="utf-8")
            deep_findings = code_dsl_check.load_and_validate(deep)
            self.assertEqual([code_dsl_check.SYNTAX], [f.code for f in deep_findings])
            self.assertIn("nesting depth", deep_findings[0].message)

    def test_unhashable_fields_non_list_containers_and_module_line_budgets(self) -> None:
        for mod_name in ("code_dsl_check.py", "code_dsl_shapes.py", "code_dsl_semantics.py"):
            lines = len((ROOT / "src" / mod_name).read_text(encoding="utf-8").splitlines())
            self.assertLess(lines, 500, f"{mod_name} has {lines} lines")

        mutation = copy.deepcopy(self.valid)
        workspace = mutation["documents"][0]
        workspace["locality"] = {"unhashable": 1}
        workspace["git"] = ["not-a-dict"]
        workspace["languageServers"] = [
            {
                "serverId": ["unhashable"],
                "language": {"unhashable": 1},
                "command": ["rust-analyzer"],
                "transport": "stdio",
                "version": "1.0",
                "configurationDigest": "sha256:" + "0" * 64,
            }
        ]
        query = next(doc for doc in mutation["documents"] if doc["kind"] == "query")
        query["operation"] = {"unhashable": 1}
        query["freshness"] = ["unhashable"]
        query["documentUri"] = 12345
        snapshot = next(doc for doc in mutation["documents"] if doc["kind"] == "snapshot")
        snapshot["operation"] = ["unhashable"]
        snapshot["status"] = {"unhashable": 1}
        snapshot["results"]["symbols"] = 999
        codes = self.codes(mutation)
        self.assertIn(code_dsl_check.SYNTAX, codes)

        bad_Refs = copy.deepcopy(self.valid)
        bad_Refs["documents"][1]["workspaceId"] = {"unhashable": 1}
        bad_Refs["documents"][-1]["workspaceId"] = ["unhashable"]
        bad_Refs["documents"][-1]["queryId"] = {"unhashable": 1}
        self.assertIn(code_dsl_check.SYNTAX, self.codes(bad_Refs))
        self.assertIn(code_dsl_check.SEMANTIC, self.codes(bad_Refs))

    def test_symlink_ancestor_and_json_number_surrogate_bounds_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real"
            real.mkdir()
            valid_copy = real / "valid.code-dsl.json"
            valid_copy.write_text(json.dumps(self.valid), encoding="utf-8")

            sym_dir = root / "sym_dir"
            sym_dir.symlink_to(real)
            trav = Path(f"{sym_dir}/../real/valid.code-dsl.json")
            self.assertEqual(
                [code_dsl_check.SYNTAX], [f.code for f in code_dsl_check.load_and_validate(trav)]
            )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(1, code_dsl_check.main(["validate", f"{sym_dir}/../real"]))

            sub = root / "sub"
            sub.mkdir()
            old_cwd = Path.cwd()
            try:
                os.chdir(sub)
                rel_findings = code_dsl_check.load_and_validate(
                    Path("../sym_dir/valid.code-dsl.json")
                )
                self.assertEqual([code_dsl_check.SYNTAX], [f.code for f in rel_findings])
            finally:
                os.chdir(old_cwd)

            for idx, payload in enumerate(
                (
                    '{"schema":"wellmanifest.code/json/v1","documents":[' + ("9" * 5000) + "]}\n",
                    '{"schema":"wellmanifest.code/json/v1","documents":[1e999]}\n',
                    '{"schema":"\\ud800","documents":[]}\n',
                )
            ):
                bad_file = real / f"bad-{idx}.code-dsl.json"
                bad_file.write_text(payload, encoding="utf-8")
                res = code_dsl_check.load_and_validate(bad_file)
                self.assertEqual([code_dsl_check.SYNTAX], [f.code for f in res], payload[:40])

        deep: Any = "leaf"
        for _ in range(70):
            deep = {"a": deep}
        self.assertEqual(
            [code_dsl_check.SYNTAX], [f.code for f in code_dsl_check.validate_document(deep)]
        )

        surr = copy.deepcopy(self.valid)
        surr["schema"] = "\ud800"
        self.assertEqual(
            [code_dsl_check.SYNTAX], [f.code for f in code_dsl_check.validate_document(surr)]
        )

    def test_nanosecond_timestamps_control_chars_git_branch_and_duplicate_id_confinement(
        self,
    ) -> None:
        nano = copy.deepcopy(self.valid)
        snap = next(doc for doc in nano["documents"] if doc["kind"] == "snapshot")
        snap["observedAt"] = "2026-08-14T12:00:00.123456789Z"
        self.assertEqual([], code_dsl_check.validate_document(nano))

        for bad_ts in ("2026-08-14T12:00:00.1234567890Z", "2026-08-14T12:00:00Z\n"):
            bad = copy.deepcopy(self.valid)
            next(d for d in bad["documents"] if d["kind"] == "snapshot")["observedAt"] = bad_ts
            self.assertIn(code_dsl_check.SYNTAX, self.codes(bad), repr(bad_ts))

        multiline_hover = copy.deepcopy(self.valid)
        hover_snap = next(
            d
            for d in multiline_hover["documents"]
            if d["kind"] == "snapshot" and d["operation"] == "hover"
        )
        hover_snap["results"]["hover"]["value"] = "line 1\n\tline 2"
        self.assertEqual([], code_dsl_check.validate_document(multiline_hover))

        bad_ctrl = copy.deepcopy(multiline_hover)
        bad_ctrl["documents"][0]["languageServers"][0]["command"] = ["pyright\x00"]
        self.assertIn(code_dsl_check.SYNTAX, self.codes(bad_ctrl))

        bad_hover_ctrl = copy.deepcopy(multiline_hover)
        next(
            d
            for d in bad_hover_ctrl["documents"]
            if d["kind"] == "snapshot" and d["operation"] == "hover"
        )["results"]["hover"]["value"] = "ansi \x1b[31mred"
        self.assertIn(code_dsl_check.SYNTAX, self.codes(bad_hover_ctrl))

        for bad_branch in ("../../HEAD", "-option", "feat@{0}", "main.lock"):
            branch_mut = copy.deepcopy(self.valid)
            branch_mut["documents"][0]["git"]["branch"] = bad_branch
            self.assertIn(code_dsl_check.SYNTAX, self.codes(branch_mut), bad_branch)

        for query_or_frag in (
            "file:///workspace/subactor-api/src/billing.rs?raw=1",
            "file:///workspace/subactor-api/src/billing.rs#L1",
        ):
            qf_mut = copy.deepcopy(self.valid)
            next(d for d in qf_mut["documents"] if d["kind"] == "query")["documentUri"] = (
                query_or_frag
            )
            self.assertIn(code_dsl_check.BOUNDARY, self.codes(qf_mut), query_or_frag)

        dup_escape = copy.deepcopy(self.valid)
        first_query = next(d for d in dup_escape["documents"] if d["kind"] == "query")
        second_query = copy.deepcopy(first_query)
        first_query["documentUri"] = "file:///workspace/outside/escape.rs"
        dup_escape["documents"].append(second_query)
        dup_codes = self.codes(dup_escape)
        self.assertIn(code_dsl_check.SEMANTIC, dup_codes)
        self.assertIn(code_dsl_check.BOUNDARY, dup_codes)


if __name__ == "__main__":
    unittest.main()
