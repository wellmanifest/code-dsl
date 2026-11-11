#!/usr/bin/env python3
"""Dependency-free conformance checker for Wellmanifest Code DSL 0.1."""

from __future__ import annotations

import argparse
import copy
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

_SRC_DIR = str(Path(__file__).resolve().parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from code_dsl_semantics import Validator  # noqa: E402
from code_dsl_shapes import (  # noqa: E402
    BOUNDARY,
    DIGEST_RE,
    ID_RE,
    LANGUAGE_RE,
    OPERATIONS,
    RFC3339_RE,
    SEMANTIC,
    SHA_RE,
    SYMBOL_KINDS,
    SYNTAX,
    URI_RE,
    Finding,
)

MAX_CODE_DSL_BYTES = 4 * 1024 * 1024
MAX_JSON_DEPTH = 64

__all__ = [
    "BOUNDARY",
    "DIGEST_RE",
    "Finding",
    "ID_RE",
    "LANGUAGE_RE",
    "OPERATIONS",
    "RFC3339_RE",
    "SEMANTIC",
    "SHA_RE",
    "SYMBOL_KINDS",
    "SYNTAX",
    "URI_RE",
    "Validator",
    "build_parser",
    "discover",
    "load_and_validate",
    "main",
    "self_test",
    "validate_document",
    "validate_target",
]


class _StrictJsonError(ValueError):
    """Raised when raw JSON violates duplicate-key, finite-number, depth, or regular-file rules."""


def _strict_loads(raw: str) -> Any:
    def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _StrictJsonError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def _no_constants(token: str) -> Any:
        raise _StrictJsonError(f"non-finite JSON constant {token}")

    try:
        parsed = json.loads(raw, object_pairs_hook=_no_duplicates, parse_constant=_no_constants)
    except RecursionError as error:
        raise _StrictJsonError("JSON nesting depth exceeded") from error

    stack: list[tuple[Any, int]] = [(parsed, 0)]
    while stack:
        current, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            raise _StrictJsonError("JSON nesting depth exceeded")
        if isinstance(current, dict):
            stack.extend(
                (val, depth + 1) for val in current.values() if isinstance(val, (dict, list))
            )
        elif isinstance(current, list):
            stack.extend((val, depth + 1) for val in current if isinstance(val, (dict, list)))
    return parsed


def _safe_read_json(path: Path) -> Any:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(os.fspath(path), flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise _StrictJsonError("input must be a regular file")
        if st.st_size > MAX_CODE_DSL_BYTES:
            raise _StrictJsonError("input exceeds maximum byte budget")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_CODE_DSL_BYTES:
                raise _StrictJsonError("input exceeds maximum byte budget")
            chunks.append(chunk)
    finally:
        os.close(fd)
    return _strict_loads(b"".join(chunks).decode("utf-8"))


def validate_document(data: Any) -> list[Finding]:
    return Validator().validate(data)


def load_and_validate(path: Path) -> list[Finding]:
    try:
        data = _safe_read_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError, _StrictJsonError) as exc:
        return [Finding(SYNTAX, str(path), f"cannot parse JSON: {exc}")]
    return validate_document(data)


def discover(target: Path) -> list[Path]:
    if target.is_symlink():
        return [target]
    if target.is_file():
        return [target]
    if target.is_dir():
        discovered: list[Path] = []
        for root_dir, dirnames, filenames in os.walk(target, followlinks=False):
            root_path = Path(root_dir)
            kept_dirs: list[str] = []
            for dirname in sorted(dirnames):
                candidate_dir = root_path / dirname
                if candidate_dir.is_symlink():
                    discovered.append(candidate_dir)
                else:
                    kept_dirs.append(dirname)
            dirnames[:] = kept_dirs
            for name in sorted(filenames):
                if name.endswith(".code-dsl.json"):
                    discovered.append(root_path / name)
        return discovered
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

    data = _safe_read_json(valid)
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
