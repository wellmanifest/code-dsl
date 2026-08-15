# Ticket 002: Restore managed governance lock conformance

- **ID**: ticket-002
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Created**: 2026-08-15

## Goal and scope

`main@1552771` fails its own governance gate. The merge of pull request 1
carried commit `9179330` ("Point schema IDs at wellmanifest.com so packs
resolve the live host"), which edited five files that the adopted
`wellmanifest/new-project@0.17.0` standard pins by SHA-256 in
`.governance/manifest.lock.json`. The trusted lock was not regenerated, so
`./project/governance-check.sh --actor agent` reports five `GOV-SYNC-001`
errors on `main` and on every branch cut from it, including the still-open
`ticket/001-code-dsl-standard`.

This ticket restores the five managed files to their pinned content and
realigns the derived `.governance/manifest.json`, which the pinned
`manifest.schema.json` constrains to the same attestation predicate constant.
Scope is governance-owned paths only.

## Acceptance criteria

- [x] AC-01: Every file listed in `.governance/manifest.lock.json`
  hashes to its pinned SHA-256 without the lock itself being edited.
- [x] AC-02: `./project/governance-check.sh --actor agent` reports
  `GOV-PASS` with zero errors and zero warnings.
- [x] AC-03: No published contract path changes. `dsl-manifest.json`,
  `spec/`, `schemas/`, `proto/`, `examples/`, `src/`, `tests/` and `docs/`
  are byte-identical to the accepted base.

## Participants

- Human participant: unresolved; no user-* file was created by this script.
- Agent participant: [ai-codex.md](ai-codex.md)

## Non-goals

- Upgrading the adopted governance standard from `0.17.0` to `0.18.x`.
- Regenerating, weakening or editing `.governance/manifest.lock.json`.
- Changing the published Code DSL schema IDs, which already resolve through
  `wellmanifest.com` in `schemas/` and are untouched here.
- Refreshing the three stale artifact digests in `examples/dsl-manifest.json`;
  those belong to ticket-001 and to the integration workstream.

## Decision record

`GOV-SYNC-001` offers two remediations: restore the pinned file, or perform an
explicit standard upgrade and regenerate the lock. Upstream
`wellmanifest/new-project` is now at `0.18.1` and does use the `.com` host in
these five files, so an upgrade is a legitimate future path. It is not the
right move here:

- The upgrade would rewrite the trusted lock as a side effect of a defect fix,
  which is the exact pattern that produced this breakage.
- `0.17.0 -> 0.18.1` carries unreviewed changes far beyond the host string.
- The `.com` edit was described as making published schema IDs resolve to the
  live host. That intent lives in `schemas/`, which already uses `.com` and is
  not touched by this restore. Inside `.governance/` the changed values are two
  managed schema `$id`s and one attestation predicate constant; the repository
  emits no attestations, so restoring them changes no observable behavior.

Restoring the pinned content is therefore the minimal remediation that returns
`main` to a passing gate without expanding the change surface. Adopting
`0.18.x` remains available as a separate, explicitly approved governance
ticket.

## Validation evidence

- Managed-file digest audit against the untouched lock: PASS.
- Governance gate: `GOV-PASS`, zero errors, zero warnings.
- Published contract paths versus the accepted base: empty diff.
- Command transcripts: [ai-codex-logs.txt](ai-codex-logs.txt).

## Publication state

The repair is complete and validated locally on
`ticket/002-restore-governance-lock-conformance`, cut from the exact accepted
base `1552771`. Remote update, pull request, merge, tag and release are not
authorized by this ticket and were not performed.

## Downstream order

1. Merge this ticket so `main` reports `GOV-PASS` again.
2. Rebase `ticket/001-code-dsl-standard` onto the repaired `main`; its
   `AC-11` digest refresh is correct and independently verified, but it
   cannot pass the gate while it inherits the broken `.governance` state.
3. Re-run the ticket-001 gate at the exact rebased head before review.
