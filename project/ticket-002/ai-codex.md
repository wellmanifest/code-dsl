---
participant-id: agent:codex
participant: codex
role: agent
ticket: ticket-002
---
# Participant: codex (AI agent)

## Understanding

`main` cannot pass its own governance gate. Pull request 1 merged commit
`9179330`, which rewrote five files that `.governance/manifest.lock.json` pins
by SHA-256, without regenerating that lock. The gate therefore reports five
`GOV-SYNC-001` errors on `main` and on `ticket/001-code-dsl-standard`, which
blocks the remaining publication work rather than any single ticket.

The defect is confined to `.governance/`. The published Code DSL contract in
`schemas/`, `spec/` and `proto/` is unaffected and already resolves through the
live `wellmanifest.com` host, so the stated purpose of `9179330` survives a
restore untouched.

## Execution plan

1. Reproduce `GOV-FAIL` on the exact accepted base `1552771`.
2. Establish which of the two `GOV-SYNC-001` remediations applies, including
   what upstream `new-project` looks like today.
3. Restore the five pinned files byte-for-byte from the governed baseline
   `368ed0b` and verify each digest against the untouched lock.
4. Realign the derived `.governance/manifest.json`, which the pinned
   `manifest.schema.json` constrains to the same predicate constant.
5. Prove no published contract path moved, then record evidence.

## Actual changes

- Restored `.governance/diagnostics.schema.json`,
  `.governance/governance_check.py`, `.governance/manifest.base.json`,
  `.governance/manifest.schema.json` and
  `.governance/remediation-intent.schema.json` from `368ed0b`; all five now
  match their pinned digests.
- Restored the pinned `signedAttestationPredicateType` in the derived
  `.governance/manifest.json`, which otherwise fails the pinned schema's
  `const` constraint with `GOV-MANIFEST-001`.
- Recorded the bounded delivery contract in `intent.json` at complexity `M`,
  because the restore is six files and is not separable: any partial slice
  leaves the gate failing.
- All 34 locked files match; the lock itself is unmodified.

## Decisions

- Chose "restore the pinned file" over "explicit standard upgrade and
  regenerate the lock". Upstream `new-project` is now `0.18.1` and does carry
  the `.com` host, so the upgrade is a real option, but performing it here
  would rewrite the trusted lock as a side effect of a defect fix and would
  import unreviewed `0.17.0 -> 0.18.1` changes into a publication branch.
- Did not fix the three stale digests in `examples/dsl-manifest.json`. They are
  genuinely stale on `main`, but they are integration-workstream paths already
  owned by `ticket-001@dc8ece0`, which fixes them correctly.

## Blockers

- None inside the recorded intent; proceed without a second confirmation.
- New authority remains required for destructive action, secret access, new
  external coordination, material objective expansion and trusted merge.
- Remote update and merge of this branch, and the subsequent rebase of
  `ticket/001-code-dsl-standard`, are outside the granted authority and were
  not performed.
