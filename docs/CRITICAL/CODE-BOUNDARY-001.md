# CODE-BOUNDARY-001

## Risk

A semantic identity uses a mutable `file:` URI, an artifact URI contains path
traversal, or a query/result escapes its declared workspace root. Accepting the
document could mix worktrees, expose unrelated files, or attach authority to
the wrong symbol.

## Detection

Run `python3 src/code_dsl_check.py validate <path>`. The checker parses URI
scheme, authority, and decoded normalized path and reports the exact offending
field.

## Remediation

Assign a non-`file` stable URI to semantic entities. Rebase artifact locations
under the declared workspace root. If an external dependency root is required,
declare and authorize it in the adopting runtime's separate policy; do not
weaken this document to permit an implicit escape.

## Verification

Rerun validation and confirm that no `CODE-BOUNDARY-001` finding remains. Then
verify the resolved artifact path against the supervisor's workspace and
access-control policy. Documentation alone never waives this critical finding.
