#!/usr/bin/env python3
"""Dependency-free conformance checker for Wellmanifest Code DSL 0.1."""

from __future__ import annotations

import argparse
import copy
import errno
import json
import math
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
    GIT_BRANCH_RE,
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
    "GIT_BRANCH_RE",
    "ID_RE",
    "LANGUAGE_RE",
    "OPERATIONS",
    "RFC3339_RE",
    "SEMANTIC",
    "SHA_RE",
    "SYMBOL_KINDS",
    "SYNTAX",
    "URI_RE",
    "Finding",
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


def _check_utf8_str(value: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _StrictJsonError("lone UTF-16 surrogate is forbidden") from exc


def _check_no_symlink_ancestors(path: str | Path, *, include_self: bool = False) -> Path:
    raw_path = os.fspath(path)
    path_obj = Path(raw_path)
    raw_parts = path_obj.parts if include_self else path_obj.parts[:-1]
    if path_obj.is_absolute():
        cur = Path(path_obj.anchor)
        walk_parts = raw_parts[1:]
    else:
        cwd = Path.cwd()
        if len(cwd.parts) > 2 and cwd.is_symlink():
            raise _StrictJsonError(f"symlink ancestor is forbidden: {cwd}")
        for anc in cwd.parents:
            if len(anc.parts) > 2 and anc.is_symlink():
                raise _StrictJsonError(f"symlink ancestor is forbidden: {anc}")
        cur = cwd
        walk_parts = raw_parts
    for part in walk_parts:
        if part in ("", "."):
            continue
        cur = cur / part
        if part != ".." and len(cur.parts) > 2 and cur.is_symlink():
            raise _StrictJsonError(f"symlink ancestor is forbidden: {cur}")
    abs_path = Path(os.path.abspath(raw_path))
    if include_self and abs_path.is_symlink():
        raise _StrictJsonError(f"symlink path is forbidden: {path_obj}")
    if any(anc.is_symlink() for anc in abs_path.parents if len(anc.parts) > 2):
        raise _StrictJsonError(f"symlink ancestor is forbidden: {path_obj}")
    return abs_path


def _validate_json_tree(root: Any) -> None:
    stack: list[tuple[Any, int]] = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            raise _StrictJsonError("JSON nesting depth exceeded")
        if isinstance(current, dict):
            for key, val in current.items():
                if isinstance(key, str):
                    _check_utf8_str(key)
                stack.append((val, depth + 1))
        elif isinstance(current, list):
            for val in current:
                stack.append((val, depth + 1))
        elif isinstance(current, str):
            _check_utf8_str(current)
        elif isinstance(current, float) and not math.isfinite(current):
            raise _StrictJsonError("non-finite JSON float is forbidden")
        elif not isinstance(current, bool) and isinstance(current, int):
            try:
                ok = math.isfinite(float(current))
            except OverflowError:
                ok = False
            if not ok:
                raise _StrictJsonError("JSON integer magnitude exceeds finite range")


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

    def _finite_float(token: str) -> float:
        parsed_float = float(token)
        if not math.isfinite(parsed_float):
            raise _StrictJsonError(f"non-finite JSON number {token}")
        return parsed_float

    def _finite_int(token: str) -> int:
        if len(token.removeprefix("-")) > 309:
            raise _StrictJsonError("JSON integer magnitude exceeds finite range")
        parsed_int = int(token)
        try:
            ok = math.isfinite(float(parsed_int))
        except OverflowError:
            ok = False
        if not ok:
            raise _StrictJsonError("JSON integer magnitude exceeds finite range")
        return parsed_int

    _check_utf8_str(raw)
    try:
        parsed = json.loads(
            raw,
            object_pairs_hook=_no_duplicates,
            parse_constant=_no_constants,
            parse_float=_finite_float,
            parse_int=_finite_int,
        )
    except RecursionError as error:
        raise _StrictJsonError("JSON nesting depth exceeded") from error
    except ValueError as error:
        raise _StrictJsonError(str(error)) from error
    _validate_json_tree(parsed)
    return parsed


def _safe_read_json(path: Path) -> Any:
    raw_path = os.fspath(path)
    _check_no_symlink_ancestors(raw_path, include_self=False)
    lst = os.lstat(raw_path)
    if stat.S_ISLNK(lst.st_mode):
        raise _StrictJsonError("symlink input is forbidden")
    if not stat.S_ISREG(lst.st_mode):
        raise _StrictJsonError("input must be a regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(raw_path, flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise _StrictJsonError("symlink input is forbidden") from exc
        raise
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise _StrictJsonError("input must be a regular file")
        if (st.st_dev, st.st_ino) != (lst.st_dev, lst.st_ino):
            raise _StrictJsonError("input inode changed during open")
        if st.st_size > MAX_CODE_DSL_BYTES:
            raise _StrictJsonError("input exceeds maximum byte budget")
        chunks = bytearray()
        while True:
            chunk = os.read(fd, min(65536, MAX_CODE_DSL_BYTES + 1 - len(chunks)))
            if not chunk:
                break
            chunks.extend(chunk)
            if len(chunks) > MAX_CODE_DSL_BYTES:
                raise _StrictJsonError("input exceeds maximum byte budget")
    finally:
        os.close(fd)
    return _strict_loads(bytes(chunks).decode("utf-8"))


def validate_document(data: Any) -> list[Finding]:
    try:
        _validate_json_tree(data)
    except _StrictJsonError as exc:
        return [Finding(SYNTAX, "$", f"invalid JSON value: {exc}")]
    return Validator().validate(data)


def load_and_validate(path: Path) -> list[Finding]:
    try:
        data = _safe_read_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError, _StrictJsonError) as exc:
        return [Finding(SYNTAX, str(path), f"cannot parse JSON: {exc}")]
    return validate_document(data)


def discover(target: Path) -> list[Path]:
    try:
        _check_no_symlink_ancestors(target, include_self=False)
    except _StrictJsonError:
        return [target]
    if target.is_symlink() or target.is_file():
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
