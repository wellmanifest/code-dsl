# CODE-SYNTAX-001

## Meaning

A Code DSL JSON document is malformed, uses the wrong schema identifier, has
an unknown property, omits a required property, or supplies a value of the
wrong type or format.

## Cause

The producer did not emit the closed `wellmanifest.code/json/v1` projection or
the consumer attempted to validate a document from another contract version.

## Resolution

Validate against `schemas/code-dsl.schema.json`, remove unknown properties,
restore every required explicit `null`, and rerun
`python3 src/code_dsl_check.py validate <path>`. Do not silently coerce the
document.
