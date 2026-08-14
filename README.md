# wellmanifest/code-dsl

Normative Wellmanifest domain pack for a code-specific DSL and normalized
Language Server Protocol (LSP) intelligence.

`code-dsl` gives editors, agents, gateways, and CI one language-neutral model
for workspaces, semantic queries, symbols, locations, diagnostics, and result
provenance. Mature language servers remain responsible for Rust, TypeScript,
Python, and other programming-language semantics.

## Repository boundary

This repository owns:

- the normative Code DSL standard;
- its Protobuf model and strict JSON projection;
- valid and invalid conformance examples;
- a dependency-free deterministic validator;
- architecture and logic-flow guidance.

This repository does not run an LSP gateway, editor extension, agent runtime,
or language-server process. Those products adopt this standard and remain in
their runtime-owning organizations.

## Planned entry points

- `spec/CODE_DSL_STANDARD.md` — normative requirements;
- `proto/wellmanifest/code/v1/code_dsl.proto` — canonical semantic model;
- `schemas/code-dsl.schema.json` — strict JSON projection;
- `src/code_dsl_check.py` — conformance CLI;
- `docs/ARCHITECTURE.md` and `docs/LOGIC_FLOW.md` — integration guidance.

Status: `0.1.0-dev`, governed implementation in `project/ticket-001`.
