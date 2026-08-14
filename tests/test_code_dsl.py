from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
