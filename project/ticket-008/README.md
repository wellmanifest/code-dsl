# Ticket 008: Harden Code DSL symlink-ancestor I/O, JSON number/surrogate bounds, nanosecond RFC3339, and control-char safety

- **ID**: ticket-008
- **Owner**: tom
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-11

## Goal and scope

SESSION_EXECUTION_AUTHORIZATION: On 2026-11-11 user authorized continuous testing, bug-fixing, optimization, and hardening across `wellmanifest/*` standard repositories.

Harden `src/code_dsl_check.py`, `src/code_dsl_shapes.py`, and `src/code_dsl_semantics.py` while keeping every module strictly below 500 lines:
- Reject symlinked ancestor paths (`sym_dir/../real`, `../sym_dir`) before `os.path.abspath` and verify `(st_dev, st_ino)` inode parity in `_safe_read_json` and `discover`.
- Bound JSON integers (`<= 309` digits), finite floats, lone UTF-16 surrogates, and nesting depth (`<= 64`) in both `_strict_loads` and programmatic `validate_document`.
- Anchor all regexes with `\A...\Z`, support 1–9 digit RFC3339 fractional seconds in `ShapeValidator.timestamp`, reject C0/DEL/C1 control characters and unsafe `git.branch` refs, reject `file:` URI query/fragment components, and evaluate semantic/boundary rules across all duplicate-ID documents.
- Synchronize `examples/dsl-manifest.json` parser-contract digests, expand `tests/test_code_dsl.py`, and reconcile merged `ticket-006` and `ticket-007` to `DONE`.

## Acceptance criteria

- [x] AC-01: Symlink-parent traversal, 5000-digit integers, `1e999` floats, lone surrogates, deep programmatic payloads, trailing-newline/10-digit timestamps, control characters, unsafe git branch refs, `file:` URI queries/fragments, and duplicate-ID boundary escapes fail closed without unhandled exceptions, while 9-digit nanosecond RFC3339 timestamps pass.
- [x] AC-02: All modules in `src/` and `tests/` remain strictly `< 500` lines, `examples/dsl-manifest.json` passes `dsl_check.py validate`, and `ruff`, `unittest`, `code_dsl_check.py self-test`, `./project/governance-check.sh --base origin/main`, and `wellman check` pass with 0 errors.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
