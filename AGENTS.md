# Transaction links

Every tool that displays a Firefly transaction must provide a link to open its parent transaction in Firefly for review. Return the parent transaction ID as `group_id`, including when displaying individual journals or splits. Use the shared `fireflyLink(group_id, label)` helper in `sidecar/static/app.js`.

Browser links must use `FIREFLY_PUBLIC_URL`, exposed as `firefly_public_url` by bootstrap. Never fall back to the internal `FIREFLY_URL`. Keep support for external URLs hosted under a subpath, safe URL schemes, escaped labels, and opening links in a new tab with `noopener noreferrer`.

Relevant checks: `python -m unittest discover -s tests`, `node tests/test_ui.cjs`, and `node tests/test_loading.cjs`.

# Activity auditing

All Firefly mutations must go through the server-supplied `AuditedFirefly` client so Activity records intent before sending the write and records its outcome. Never bypass it with a separate client or direct HTTP writes. Preserve the existing reimbursement operation/resume records as well as individual change events.

# Single-journal transaction display

All existing and future tools must show a single journal's description, journal ID, accounts and amount directly in the transaction line/card. Do not display a “1 split” / “1 journal” count or place a lone journal behind expandable split details. Use the shared `transactionJournalDetails(row)` renderer for normalized parent transaction cards (the `splits` array), and `duplicateCard` for full parent cards. Only multi-journal transactions should display counts and expandable breakdowns. Flat per-journal tables should keep journal information inline.
