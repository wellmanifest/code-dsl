# Ticket 001: Define Code DSL and normalized LSP intelligence standard

- **ID**: ticket-001
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-08-14

## Goal and scope

Create the first usable Wellmanifest standard for code intelligence. The
standard will normalize workspace configuration and read-only semantic results
obtained from existing language servers while preserving a strict boundary
between stable domain identity, mutable source locations, and runtime
authority.

The repository is named `code-dsl` because its subject is the semantic model
of code, while LSP is one binding and evidence source. A future LSP gateway may
adopt this contract but is not hosted here.

## Acceptance criteria

- [x] AC-01: A normative standard defines identity, workspace, operation,
  snapshot, provenance, lifecycle, compatibility, and security requirements.
- [x] AC-02: A canonical Protobuf contract models workspaces, queries,
  locations, symbols, diagnostics, and semantic snapshots.
- [x] AC-03: A closed Draft 2020-12 JSON Schema provides a deterministic JSON
  projection with no unknown fields.
- [x] AC-04: The standard maps exactly six baseline agent operations to LSP:
  diagnostics, hover, definition, references, document symbols, and workspace
  symbols.
- [x] AC-05: Stable domain URIs remain distinct from `file:` artifact
  locations across worktrees and remote workspaces.
- [x] AC-06: Server identity, version, configuration digest, workspace
  revision, document version, and completeness make result freshness explicit.
- [x] AC-07: Valid and invalid examples cover workspace limits, queries,
  snapshots, URI separation, and fail-closed validation.
- [x] AC-08: A dependency-free CLI validates JSON projection shape plus
  semantic invariants and exposes stable `CODE-*` diagnostic codes.
- [x] AC-09: Architecture and logic-flow documentation includes Mermaid views
  and keeps LSP evidence separate from CQRS/Event Sourcing authority.
- [x] AC-10: Governance, unit tests, DSL manifest validation, syntax checks,
  and optional-container validation pass with recorded evidence.

## Participants

- Human participant: unresolved; no user-* file was created by this script.
- Agent participant: [ai-codex.md](ai-codex.md)

## Non-goals

- Implementing or supervising `rust-analyzer`, Pyright, TypeScript language
  servers, or any other language server.
- Hosting `subactor-lsp-gateway`, an editor extension, WebSocket service, NATS
  adapter, or agent runtime in Wellmanifest.
- Replacing Protobuf domain contracts, CQRS command authority, event stores,
  test suites, compilers, or language-specific type checkers.
- Treating LSP output, a model response, or a source location as execution or
  merge authority.

## Validation evidence

- Governance: PASS with zero errors and warnings.
- Wellmanifest DSL manifest structure, artifact hashes, documentation catalog,
  standards lock, and publication tier: PASS.
- Draft 2020-12 metaschema and valid/invalid JSON projection checks: PASS.
- Code DSL validator, built-in mutations, and 9 unit tests: PASS.
- Ruff check/format, Python compilation, and Protobuf compilation through
  `grpc_tools.protoc`: PASS.
- Networkless, read-only Python 3.12 container validation: PASS using an image
  pinned by digest.
- Markdown links, diff whitespace, secret patterns, and absolute local paths:
  PASS.
- Mermaid CLI discovered all five diagrams, but local rendering could not use
  the snap-confined Chromium binary. Diagram source remains unrendered local
  evidence and is not reported as a passing render check.

## Publication state

The local implementation is complete and validated. On 2026-08-14 the user
authorized creation of the public remote, implementation commit, ticket-branch
push, and pull-request creation. The ticket remains
`IN_PROGRESS / PUBLICATION` through protected checks and independent
current-head review. Merge, tag, and release are not authorized by this
instruction.
