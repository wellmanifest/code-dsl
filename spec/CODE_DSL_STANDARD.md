# Wellmanifest Code DSL Standard 0.1

Status: pre-stable normative draft

Canonical contract: `wellmanifest.code/v1`

JSON projection: `wellmanifest.code/json/v1`

LSP binding: `3.17`

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT,
RECOMMENDED, MAY, and OPTIONAL are normative when written in uppercase.

## 1. Purpose and boundary

Code DSL gives tools a language-neutral contract for describing code
workspaces, asking semantic questions, and returning normalized code
intelligence. It enables an editor or agent to use language-server evidence
before asking a language model to infer repository structure.

Code DSL does not analyze programming languages. Rust semantics remain with
`rust-analyzer`, TypeScript semantics with a TypeScript language server, Python
semantics with Pyright or another configured server, and so on. It also does
not authorize a command, filesystem write, rename, build, deployment, CQRS
transition, or domain event.

The standard defines a descriptive domain pack. A gateway, process supervisor,
editor extension, WebSocket endpoint, or agent runtime is an adopting product
and MUST live outside this Wellmanifest standards repository.

## 2. Layer responsibilities

An implementation MUST keep these responsibilities distinct:

| Layer | Responsibility |
| --- | --- |
| Language server | Syntax, types, imports, symbols, references, and language diagnostics |
| Code DSL normalizer | Stable identities, normalized results, provenance, ordering, and conformance |
| Gateway/supervisor | Process lifecycle, direct argv execution, limits, health, routing, and isolation |
| Domain semantic core | Contract registry, capability graph, Protobuf/CQRS relations, and project policy |
| Effect authority | Approval, command authorization, event persistence, deployment, and receipts |

An LSP response is evidence about code. It MUST NOT be treated as effect
authority or as the source of truth for domain behavior. CQRS/Event Sourcing
contracts and their authorized runtime remain outside this descriptive model.

## 3. Representations

The canonical semantic model is the proto3 contract
`proto/wellmanifest/code/v1/code_dsl.proto`. Field numbers and enum meanings are
part of compatibility. A conforming implementation MUST preserve unknown
Protobuf fields when its runtime supports that operation.

`schemas/code-dsl.schema.json` defines the closed JSON projection. The JSON
projection uses lower-case vocabulary tokens instead of generated ProtoJSON
enum names. A conforming serializer MUST map these tokens without changing
meaning and MUST reject unknown JSON properties.

The top-level `CodeDocumentSet`/JSON `documents` collection permits one
exchange to carry related workspace, query, and snapshot documents. Every
document is independently identified and typed.

LSP JSON-RPC messages, workspace YAML, editor settings, model prompts, and
generated source are bindings or projections. They MUST NOT redefine Code DSL
semantics.

## 4. Identity and locations

Every `workspaceId`, `queryId`, `snapshotId`, symbol `domainUri`, capability,
and related semantic URI MUST be an absolute, stable URI. The `file` scheme is
for artifact locations and MUST NOT be used for semantic identity.

`rootUri`, `documentUri`, and `artifactUri` are mutable locations. They MAY
change between a main checkout, Git worktree, container, remote workspace, or
developer machine without changing semantic identity.

An implementation:

1. MUST NOT derive a stable semantic URI from an absolute local path alone;
2. MUST reject path traversal in decoded artifact URI paths;
3. MUST confine queried documents and returned locations to the declared
   workspace root unless an explicit, separately authorized dependency-root
   policy permits them;
4. MUST preserve a domain URI when the artifact moves between worktrees;
5. MUST compare URI scheme, authority, and normalized path when enforcing root
   confinement, not use an unparsed string prefix.

Recommended workspace identities use `code://workspace/<name>`. Domain
extensions such as `subactor://actor/billing` MAY be retained directly.

## 5. Workspace document

A `workspace` document declares one analysis root, its Git state, configured
language servers, and resource limits.

Each language-server entry MUST include:

- a stable server ID and language ID;
- an argv array, never a shell command string;
- the `stdio` transport in version 0.1;
- an observed or pinned server version;
- a SHA-256 digest of effective initialization/configuration inputs.

The gateway MUST resolve executable paths through trusted configuration and an
allowlist. It MUST invoke argv directly and MUST NOT pass a manifest command
through a shell. Merely declaring a command does not grant execution authority.

Within one workspace, server IDs and language IDs MUST be unique. The number
of configured language servers MUST NOT exceed `maxLanguagesPerWorkspace`.
`maxLocalWorkspaces` and `maxRemoteWorkspaces` limit concurrent workspaces,
not programming languages or individual requests.

A supervisor SHOULD run at most one process for a `(workspaceId, language)`
pair, stop idle processes after `idleShutdownSeconds`, and fail explicitly when
`indexingTimeoutSeconds` is exceeded. A worktree is a distinct workspace even
when it points to the same repository.

## 6. Query document and LSP mapping

Version 0.1 defines exactly six read-only operations:

| Code DSL operation | Required operands | LSP 3.17 method/evidence |
| --- | --- | --- |
| `diagnostics` | `documentUri` | `textDocument/diagnostic`; version-correlated `textDocument/publishDiagnostics` MAY be normalized as fallback evidence |
| `hover` | `documentUri`, `position` | `textDocument/hover` |
| `definition` | `documentUri`, `position` | `textDocument/definition` |
| `references` | `documentUri`, `position`, `includeDeclaration` | `textDocument/references` |
| `document_symbols` | `documentUri` | `textDocument/documentSymbol` |
| `workspace_symbols` | `symbol` (the empty string is allowed) | `workspace/symbol` |

Operands not defined for an operation MUST be `null`. A gateway MUST return a
typed `unavailable` snapshot when a server does not advertise a required
capability. It MUST NOT silently substitute model-generated results.

`freshness=live` requires a request against the current initialized server.
`cached_allowed` permits a cached snapshot only when all provenance fields and
the subject state remain available to the consumer. `maxResults` is a caller
bound, not permission to truncate without declaring the snapshot `partial`.

Rename is intentionally absent from v0.1 because it proposes edits. A future
`rename_preview` operation MUST remain propose-only and MUST use a separate
authorized effect to apply changes.

## 7. Snapshot and provenance

Every snapshot MUST bind:

- its query, workspace, and operation;
- `lsp` as the evidence binding and `3.17` as the protocol version;
- exact server ID, server version, and configuration digest;
- workspace revision or an explicit dirty state;
- every contributing document URI, version when known, and content digest;
- observation time, status, and an incomplete reason when not complete.

`complete` requires `incompleteReason=null`. `partial` and `unavailable`
require a non-empty reason. `unavailable` MUST contain no result payload.

Result fields are operation-specific:

- diagnostics populate only `diagnostics`;
- hover populates only `hover`;
- definition and references populate only `locations`;
- document and workspace symbols populate only `symbols`.

Arrays MUST be deduplicated and sorted by the keys defined in section 8. A
consumer MUST treat `stale=true`, `partial`, `unavailable`, a dirty subject, or
an unknown document version as explicit uncertainty. It MUST NOT coerce that
state into a fresh complete result.

## 8. Normalization and deterministic comparison

A normalizer MUST use zero-based LSP line and UTF-16 code-unit character
coordinates. It MUST validate that a range end is not before its start.

The following sort keys are normative:

- language servers: `(language, serverId)`;
- subject documents: `artifactUri`;
- symbols: `(domainUri, qualifiedName)`;
- locations: `(artifactUri, start.line, start.character, end.line,
  end.character)`;
- diagnostics: `(artifactUri, start.line, start.character, severity, code,
  message)`;
- references, capabilities, and related URIs: Unicode code-point order.

Duplicate entries under the corresponding key MUST be rejected. Observation
timestamps and local artifact paths MUST NOT become semantic identity.
Deterministic Protobuf serialization is an implementation detail and MUST NOT
be assumed to be a cross-implementation semantic hash without a separately
versioned canonicalization profile.

## 9. Diagnostics and security

The conformance CLI exposes three stable diagnostic families:

| Code | Meaning |
| --- | --- |
| `CODE-SYNTAX-001` | JSON parsing or closed projection shape failed |
| `CODE-SEMANTIC-001` | A typed semantic invariant failed |
| `CODE-BOUNDARY-001` | URI identity, traversal, or workspace confinement failed |

`CODE-BOUNDARY-001` is security-critical. A conforming gateway MUST fail
closed on it. Documentation of the code does not waive or resolve a finding.

Initialization options, document text, hover text, diagnostics, and server
logs are untrusted inputs. An implementation MUST enforce size limits, redact
secrets from logs, reject server-initiated effects not covered by policy, and
isolate language-server processes according to the runtime's authority model.

## 10. Agent policy

An agent using Code DSL SHOULD follow this sequence:

1. obtain diagnostics;
2. obtain definitions and references;
3. obtain document/workspace symbols and domain-contract relations;
4. plan with the LLM only after typed evidence is available;
5. edit in the ticket's authorized worktree;
6. rerun fresh diagnostics, tests, and contract validators;
7. record an audit event through an external authorized runtime.

An LLM MAY interpret a conforming snapshot. It MUST remain propose-only and
MUST NOT invent missing provenance, locations, server capabilities, or domain
URIs.

## 11. Conformance and compatibility

A conforming producer MUST:

```bash
python3 src/code_dsl_check.py validate <file-or-directory>
python3 src/code_dsl_check.py self-test
```

It MUST pass the valid examples and reject every invalid example. JSON Schema
validation alone is insufficient; semantic and boundary checks are required.

Compatibility follows Semantic Versioning:

- changing field meaning, removing an operation, changing URI or coordinate
  semantics, weakening provenance, or widening authority is breaking;
- adding an optional normalized operation or result kind is additive;
- clarifying text without changing accepted documents is a fix.

Server-version or LSP-version changes do not automatically change the Code DSL
version, but a changed normalization meaning does.

## 12. References

- [Language Server Protocol 3.17 specification](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/)
- [Protocol Buffers language guide (proto3)](https://protobuf.dev/programming-guides/proto3/)
- [Wellmanifest reusable DSL standard](https://github.com/wellmanifest/dsl)
