# Transaction links

Every tool that displays a Firefly transaction must provide a link to open its parent transaction in Firefly for review. Return the parent transaction ID as `group_id`, including when displaying individual journals or splits. Use the shared `fireflyLink(group_id, label)` helper in `sidecar/static/app.js`.

Browser links must use `FIREFLY_PUBLIC_URL`, exposed as `firefly_public_url` by bootstrap. Never fall back to the internal `FIREFLY_URL`. Keep support for external URLs hosted under a subpath, safe URL schemes, escaped labels, and opening links in a new tab with `noopener noreferrer`.

Relevant checks: `python -m unittest discover -s tests`, `node tests/test_ui.cjs`, and `node tests/test_loading.cjs`.
