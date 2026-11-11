# Ticket 006: Harden Code DSL URI traversal, RFC 3339, mixed-type sort safety, and pytest integration

- **ID**: ticket-006
- **Owner**: agent:antigravity
- **Status**: DONE
- **Workflow state**: DONE
- **Created**: 2026-11-11

## Session authorization

- `SESSION_EXECUTION_AUTHORIZATION`: Autonomous execution, testing, and protected publication requested by the repository owner.

## Goal and scope

Harden `src/code_dsl_check.py`, `pyproject.toml`, `examples/dsl-manifest.json`, and `tests/test_code_dsl.py`:

1. Optimize `Validator.add()` deduplication from $O(N^2)$ list scanning to $O(1)$ set membership.
2. Harden `Validator.uri()` and `Validator.confined()` against double-encoded (`%252e%252e`), backslash (`\`), and NUL (`%00`) path traversal smuggling (`CODE-BOUNDARY-001`).
3. Enforce strict RFC 3339 date-time timestamps (`T`/`t` separator + explicit timezone) in `Validator.timestamp()`.
4. Guard `location_key()`, `diagnostic_key()`, `maxResults`, and `maxLanguagesPerWorkspace` against mixed-type `sorted()` `TypeError` crashes and Python `isinstance(True, int)` pitfalls.
5. Reject duplicate JSON keys and non-finite JSON constants in `load_and_validate()`, wire standalone `pytest` in `pyproject.toml`, and synchronize `examples/dsl-manifest.json` digest.

## Acceptance criteria

- [x] AC-01: Double-encoded/backslash/NUL URI traversal, naive/date-only timestamps, duplicate JSON keys, boolean integer fields, and mixed-type diagnostic/location arrays fail closed without `TypeError` crashes.
- [x] AC-02: `examples/dsl-manifest.json` digest, `unittest`, `pytest -q`, `ruff`, `./project/governance-check.sh --base origin/main`, and `wellman check` pass cleanly.
