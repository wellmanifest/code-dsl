# Ticket 007: Modularize code_dsl_check under 500 lines and harden unhashable JSON and file I/O

- **ID**: ticket-007
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-11

## Goal and scope

Split `src/code_dsl_check.py` (930 lines) into three cohesive modules strictly under 500 lines (`src/code_dsl_shapes.py`, `src/code_dsl_semantics.py`, `src/code_dsl_check.py`), eliminate unhashable/non-container runtime crashes across structural and semantic checks, and harden file loading:
- Extract primitive validators, structural shapes, and `O_NOFOLLOW | O_NONBLOCK` regular-file JSON loading (`<= 4 MiB`, `MAX_JSON_DEPTH = 64`, `RecursionError` guard) into `src/code_dsl_shapes.py`.
- Extract cross-document semantic checks, canonical ordering, and URI boundary confinement into `src/code_dsl_semantics.py`, guarding set/dict lookups and container traversals against unhashable or malformed JSON types (`locality`, `operation`, `freshness`, `status`, `hover.format`, `symbol.kind`, `severity`, `workspaceId`, `queryId`, `serverId`, `language`, `documentUri`, `git`, `languageServers`, `results.*`).
- Reject symlinked files and symlinked directories during CLI target discovery, keep `src/code_dsl_check.py` public exports intact, update `parser-contract` digests in `examples/dsl-manifest.json`, and expand `tests/test_code_dsl.py`.

## Acceptance criteria

- [x] AC-01: Scope is approved by a human owner (continuous hardening/modularity session).
- [x] AC-02: `src/code_dsl_check.py`, `src/code_dsl_shapes.py`, and `src/code_dsl_semantics.py` stay strictly under 500 lines and fail closed without runtime `TypeError`/`AttributeError`/`RecursionError` crashes.
- [x] AC-03: `ruff check`, `unittest`, `src/code_dsl_check.py self-test`, `dsl_check.py validate examples/dsl-manifest.json`, `./project/governance-check.sh --actor ci`, and `wellman check` pass.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
