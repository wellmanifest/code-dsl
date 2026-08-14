---
participant-id: agent:codex
participant: codex
role: agent
ticket: ticket-001
---
# Participant: codex (AI agent)

## Understanding

The requested result is a new Wellmanifest standard repository, not a universal
replacement for existing language servers. Its stable name is `code-dsl`
because it standardizes code semantics; LSP is a protocol binding that supplies
observations. The standard must let an agent request trusted structural facts
before using an LLM, normalize results across worktrees and languages, and keep
all effects under external CQRS/Event Sourcing and policy authority.

The repository is a Wellmanifest `domain_pack`. An executable LSP gateway or
daemon remains outside Wellmanifest and adopts this pack. The user request to
create the standard and repository is recorded as
`SESSION_EXECUTION_AUTHORIZATION`. It also authorizes exactly one local
governance seed-baseline commit because this repository has an unborn `HEAD`;
it does not authorize remote creation, push, pull request, tag, release, or
merge.

On 2026-08-14 the user instructed `wypchnij wszystko`, expanding the session
authorization to creation of the public `wellmanifest/code-dsl` remote,
implementation commit, ticket-branch push, and pull-request creation. It does
not replace independent current-head merge approval and does not authorize a
tag or release.

## Execution plan

1. Establish an immutable local governance baseline from the published
   `wellmanifest/new-project` package.
2. Define the normative Code DSL standard and its LSP 3.17 mapping.
3. Define a canonical Protobuf model and strict JSON projection.
4. Add valid and invalid examples plus a dependency-free validator.
5. Document the gateway/semantic-core boundary and LSP-first agent flow.
6. Run governance, schema, semantic, syntax, manifest, and container checks.
7. Review the complete diff and record remaining publication limitations.
8. Refresh manifest digests affected by the final public schema-ID change and
   re-run the current shared DSL checker before protected publication.

## Actual changes

- Initialized the bounded ticket and recorded SESSION_EXECUTION_AUTHORIZATION
  from the request to execute this work.
- Selected `code-dsl` as the repository name and `wellmanifest.code` as the
  stable DSL namespace.
- Adopted published `wellmanifest/new-project` v0.17.0 by immutable commit.
- Created the one authorized local governance seed-baseline commit
  `368ed0bde1965f402e93f4a041e16e43b9c27b85` and recorded it as the delivery
  base before adding implementation files.
- Opened local ticket branch `ticket/001-code-dsl-standard`; no remote was
  configured.
- Initially kept remote repository creation and publication outside the first
  authorization, then recorded the user's explicit publication instruction.
- Created the public `wellmanifest/code-dsl` GitHub repository, enabled
  automatic deletion of merged head branches, and pushed only the governed
  seed baseline to `main` before publishing implementation work.
- Committed the implementation as
  `18572acba198b5535d03abaf81fb0fe38016f6d0`, pushed the ticket branch, and
  opened publication PR <https://github.com/wellmanifest/code-dsl/pull/1>.
- Defined `wellmanifest.code/v1` in proto3 and a closed
  `wellmanifest.code/json/v1` projection.
- Defined exactly six read-only LSP 3.17 operations and operation-specific
  query/result invariants.
- Added stable semantic URI versus mutable artifact URI rules, parsed root
  confinement, path-traversal rejection, freshness, completeness, and server,
  workspace, Git, document, and configuration provenance.
- Added one valid end-to-end document set covering every operation and one
  fail-closed fixture covering unstable identity, root escape, bad operands,
  and language limits.
- Added the dependency-free `code_dsl_check.py`, built-in mutation tests, nine
  unit tests, and deterministic ordering/correlation checks.
- Added the Wellmanifest DSL adoption manifest with an immutable lock to
  `wellmanifest/dsl`, exact artifact digests, typed LLM input boundary, and
  normalized diagnostic documentation.
- Added architecture and logic-flow guidance with five Mermaid diagrams.
- Validated locally and in a networkless read-only Python 3.12 container.
- Reopened the matching integration ticket after the cross-DSL audit found
  that three artifact hashes predated the last schema-ID correction.
- Refreshed all three hashes and passed the current DSL manifest/standards
  checker, Code DSL runtime, nine tests, Ruff and the networkless read-only
  Docker self-test.
- Rebuilt the publication candidate from exact governed `main@368ed0b` and
  replayed only ticket-owned implementation, public-host and evidence changes.
- Left the original branch and its `9179330` managed-governance drift intact
  for auditability; the clean branch has no `.governance` delta.
- Passed governance with zero findings plus current DSL validate/standards,
  runtime, nine tests, Ruff, Python compilation, Protobuf compilation and the
  networkless read-only Docker suite on the clean lineage.

## Acceptance evidence

- AC-01/AC-04/AC-05/AC-06: `spec/CODE_DSL_STANDARD.md`.
- AC-02: `proto/wellmanifest/code/v1/code_dsl.proto`; `grpc_tools.protoc` PASS.
- AC-03: `schemas/code-dsl.schema.json`; Draft 2020-12 metaschema and fixture
  validation PASS.
- AC-07: `examples/valid/subactor-workspace.code-dsl.json` and
  `examples/invalid/boundary-and-limit.code-dsl.json`.
- AC-08: `src/code_dsl_check.py`, `tests/test_code_dsl.py`; self-test and all
  nine unit tests PASS.
- AC-09: `docs/ARCHITECTURE.md`, `docs/LOGIC_FLOW.md`, and diagnostic pages.
- AC-10: governance, DSL manifest/hash, Ruff, compile, schema, links, scans,
  container, diff, and test checks recorded in `ai-codex-logs.txt`.

## Risks

- Raw LSP responses vary by server and version; provenance and completeness
  must be mandatory before an agent treats a snapshot as reusable evidence.
- `file:` locations change between worktrees; stable semantic identities must
  never be derived from absolute paths.
- A gateway that accepts arbitrary server commands becomes an execution
  boundary; this descriptive standard must not grant that authority.
- Protobuf and JSON representations may drift unless tag numbers, field
  meanings, and conformance fixtures are reviewed together.

## Blockers

- None for the requested local standard and repository.
- Remote creation, implementation commit, branch push, and pull-request
  creation are now authorized. Trusted merge and release approval remain
  separate external boundaries.
- The local clean candidate has no implementation blocker. The original
  remote PR still targets the quarantined history and must not be merged as-is;
  updating its remote head requires the separate publication boundary.

## Unfinished scope

- Local Mermaid rendering is not evidenced because the installed CLI could not
  access the snap-confined Chromium binary. The diagrams were discovered, but
  a render pass is not claimed.
- Tag, release, and merge remain outside the publication instruction until the
  exact pushed head passes protected checks and independent review.
