# CODE-SEMANTIC-001

## Meaning

A structurally valid Code DSL document violates a semantic invariant such as
operation operands, workspace limits, result type, provenance correlation,
canonical order, uniqueness, or range ordering.

## Cause

The normalizer combined incompatible LSP data, omitted required uncertainty,
or produced a snapshot that cannot be correlated to its declared workspace and
query.

## Resolution

Recreate the document from the typed workspace and query, preserve partial or
unavailable status, sort and deduplicate normalized arrays, and rerun the
validator. Do not fill missing evidence with model-generated values.
