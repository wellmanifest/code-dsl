# Code DSL logic flow

## Workspace lifecycle

```mermaid
stateDiagram-v2
    [*] --> Declared
    Declared --> Queued: pool limit reached
    Declared --> Starting: capacity available
    Queued --> Starting: slot released
    Starting --> Indexing: initialize succeeds
    Starting --> Unavailable: start / initialize fails
    Indexing --> Ready: index complete
    Indexing --> Unavailable: timeout
    Ready --> Ready: semantic query
    Ready --> Stale: revision or document changes
    Stale --> Indexing: refresh
    Ready --> Stopped: idle timeout
    Unavailable --> Starting: explicit retry policy
    Stopped --> [*]
```

Pool limits count workspaces. `maxLanguagesPerWorkspace` separately bounds the
number of language-server processes configured for one workspace.

## Query normalization

```mermaid
sequenceDiagram
    participant A as Agent/editor
    participant G as Gateway
    participant L as Language server
    participant N as Code DSL normalizer
    participant V as Conformance checker

    A->>G: query(workspaceId, operation, operands)
    G->>G: authorize workspace and select server
    G->>L: mapped LSP 3.17 request
    alt capability available
        L-->>G: typed LSP result / null
        G->>N: result + server/workspace/document provenance
        N->>N: normalize URIs, ranges, order, completeness
        N->>V: CodeDocumentSet
        alt conforms
            V-->>A: complete or partial snapshot
        else boundary or semantic failure
            V-->>A: typed CODE-* finding
        end
    else capability unavailable
        G->>N: unavailable + explicit reason + provenance
        N->>V: unavailable snapshot
        V-->>A: conforming unavailable snapshot
    end
```

Failure to obtain data is represented, not guessed. A legacy push diagnostic
may be normalized only when the gateway can correlate its document version and
the declared server/workspace provenance.

## LSP-first agent change flow

```mermaid
flowchart TD
    Start[Authorized ticket and worktree] --> Diagnostics[Live diagnostics]
    Diagnostics --> Structure[Definitions, references, symbols]
    Structure --> Domain[Contract and capability relations]
    Domain --> Plan[LLM proposes a bounded plan]
    Plan --> Policy{External policy authorizes edit?}
    Policy -->|no| Stop[Record blocked proposal]
    Policy -->|yes| Edit[Apply bounded edit]
    Edit --> Refresh[Refresh document/revision state]
    Refresh --> Validate[Fresh diagnostics + tests + contract checks]
    Validate --> Receipt[External audit/event receipt]
```

The LLM is downstream of typed evidence. The policy/CQRS boundary remains the
only path to effects, and fresh validation is required after source changes.
