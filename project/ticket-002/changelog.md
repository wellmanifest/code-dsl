# Ticket Changelog (ticket-002)

## [0.2.0] - 2026-08-15

- Restored the five lock-pinned managed governance files that `9179330`
  changed without regenerating `.governance/manifest.lock.json`.
- Realigned `.governance/manifest.json` with the pinned attestation predicate
  constant required by `manifest.schema.json`.
- Recorded the bounded delivery contract and the remediation decision that
  rejects an implicit `0.17.0 -> 0.18.1` standard upgrade.
- Governance gate returns to `GOV-PASS` with zero errors and zero warnings.

## [0.1.0] - 2026-08-15

- Initial governance scaffold created.
- No human participant identity or content was generated.
