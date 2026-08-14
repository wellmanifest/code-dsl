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

## Execution plan

1. Establish an immutable local governance baseline from the published
   `wellmanifest/new-project` package.
2. Define the normative Code DSL standard and its LSP 3.17 mapping.
3. Define a canonical Protobuf model and strict JSON projection.
4. Add valid and invalid examples plus a dependency-free validator.
5. Document the gateway/semantic-core boundary and LSP-first agent flow.
6. Run governance, schema, semantic, syntax, manifest, and container checks.
7. Review the complete diff and record remaining publication limitations.

## Actual changes

- Initialized the bounded ticket and recorded SESSION_EXECUTION_AUTHORIZATION
  from the request to execute this work.
- Selected `code-dsl` as the repository name and `wellmanifest.code` as the
  stable DSL namespace.
- Adopted published `wellmanifest/new-project` v0.17.0 by immutable commit.
- Kept remote repository creation and publication outside this authorization.

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

- None inside the recorded intent; proceed without a second confirmation.
- New authority remains required for destructive action, secret access, new
  external coordination, material objective expansion and trusted merge.
