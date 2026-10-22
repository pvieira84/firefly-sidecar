# Firefly Sidecar

A self-hosted web toolbox alongside Firefly III. Transaction review is the default entry point for validating new imports. The Reimbursements tool lets you choose a deposit, select shared-expense splits, review, then link and clear their pending tag.

The sidebar and tables take inspiration from Firefly III / AdminLTE and the [AI Categorizer](https://github.com/ejagombar/FireflyIII-AI-Categorizer). This is an independent implementation with no AI dependency.

## Run with Docker

Requires Docker with Compose. No prebuilt image is published; Compose builds from this source.

```bash
cp .env.example .env
# Edit .env: set FIREFLY_URL and FIREFLY_TOKEN.
chmod 600 .env
docker compose up -d --build
```

Open **http://localhost:8088**, then **Connection → Test connection**.

Create a Firefly III Personal Access Token under your profile → OAuth → Personal Access Tokens. The API token stays on the server and is never returned to the browser.

### Reach your Firefly instance

`FIREFLY_URL` must be reachable from the sidecar container. `localhost` inside it points to the sidecar itself.

Either add the `sidecar` service from `compose.yaml` to your existing Firefly Compose project, or connect this project to Firefly's Docker network. For the latter, create `compose.override.yaml`, substituting the actual network name:

```yaml
services:
  sidecar:
    networks:
      - firefly
networks:
  firefly:
    external: true
    name: your_firefly_network
```

Set `FIREFLY_URL` to Firefly's internal service address, for example `http://app:8080`, using its actual network alias and port. An accessible HTTPS URL also works. TLS is verified; for a private CA, mount a trust bundle and set `SSL_CERT_FILE`.

The default published port accepts local connections only. For remote access, use an authenticated HTTPS reverse proxy and add the browser-facing hostname to `SIDECAR_HOSTS`. Optional built-in Basic Auth is enabled by setting `SIDECAR_PASSWORD` (username defaults to `sidecar`). Do not expose the unauthenticated app directly to the internet.

### Optional token secret

Instead of `FIREFLY_TOKEN`, mount a token file and set `FIREFLY_TOKEN_FILE=/run/secrets/firefly_token`:

```yaml
services:
  sidecar:
    environment:
      FIREFLY_TOKEN_FILE: /run/secrets/firefly_token
    secrets:
      - firefly_token
secrets:
  firefly_token:
    file: ./firefly-token.txt
```

Ensure the file is readable by container UID 10001. Keep `.env` and token files out of Git.

## Transaction review

The sidecar opens on **Transaction review**. Set `TODO_TAG=todo` in `.env` (use the exact tag, including a literal `#` if present), then restart the sidecar. The queue loads automatically once when first opened. Click **Load from Firefly** to fetch it again. Search by description, account, category or tag.

Each row represents a tagged journal, including an unsplit transaction. On load, the queue checks its full parent transaction against all nearby transactions (including untagged ones) within ±3 days, using the Duplicate checker's exact summed total, currency, type and account rules. Matching candidates appear in an expandable **Potential duplicates** column with totals, split breakdowns and Firefly links. Checks are advisory and do not block validation. Unsupported groups show **Manual review needed**; failed lookups show **Check unavailable**, never a misleading clean result. Nearby overlapping date windows are fetched together, and no transaction is compared against itself. Up to 20 matches per parent are displayed, with the full count shown. **Mark validated** removes only `TODO_TAG` from that journal, preserving other tags, amounts, categories and sibling splits. Categorized transactions and all transaction types are included. The action reads the latest tags before updating, disables rules and webhooks, and verifies the result. A retry is safe if the tag was already removed. Reload after an error to inspect the current queue.

**Delete transaction** is available on review rows and on expanded duplicate candidates. It opens a fresh preview with a Firefly link and every journal. Confirming deletes the whole parent transaction, including all splits; there is no undo in the sidecar. Confirmation expires after ten minutes and is rejected if the transaction changed since preview. After deletion the review queue refreshes and the reimbursement/duplicate caches are invalidated. Deleting an untagged duplicate candidate is supported. No automatic deletion occurs.

The queue has its own service and API namespace so future review actions and links to other tools can be added here.

## Duplicate checker

Open **Duplicate checker** to automatically scan the last seven days once. Change the start/end dates and maximum days apart (default 3, range 0–31), then click **Load from Firefly** to scan again. Both members of a pair must be inside the selected range.

The checker compares whole parent transactions by the exact decimal sum of all their journals. Currency and transaction type must match; withdrawals require the same source account, deposits the same destination account, and transfers the same source/destination pair. It never compares a transaction against itself. Matching descriptions and shared external IDs are displayed as supporting evidence, not proof of duplication.

Candidate pairs show dates, totals, tags, journal breakdowns and links to Firefly. Groups with mixed currencies, relevant accounts or dates, or invalid amounts are separately listed for manual review. Only the first 500 candidate pairs are shown when the results are large; narrow the range to see more. This tool only reads data; it does not delete, edit or tag transactions.

## Reimbursements

For an expense split into your categorized €30 share and uncategorized €15 and €5 `Reimbursement` splits tagged `Reimburse`:

1. Set both deposit dates and click **Load from Firefly**, then choose the €20 incoming deposit. Options represent individual deposit journals, including split deposits.
2. Select the €15 and €5 pending reimbursement rows.
3. Click **Review match** to inspect the total and link direction.
4. Click **Link & remove pending tag**.

The sidecar creates a **Reimbursement** link per selected expense journal. The expense is `inward_id` (“is (partially) reimbursed by”); the deposit is `outward_id` (“(partially) reimburses”). It verifies each link before removing the pending tag. Your categorized share, amounts and other tags are preserved. Rules and webhooks are disabled for the tag update.

Candidates must be withdrawals with no category and the configured reimbursement tag. Their split description does not affect eligibility. Tag names are case-sensitive. The default tag name is `Reimburse`; if your actual Firefly tag includes a literal `#`, set `REIMBURSE_TAG=#Reimburse`.

Each reimbursement row displays all of its tags. Search by parent title, merchant, account, tag, amount or journal ID. Additional tags do not exclude an otherwise eligible split. The deposit date range defaults to seven days ago through today, using the browser’s local date. Reimbursements load automatically once when the tool is first opened, using the displayed dates. Change the dates and click **Load from Firefly** to reload. Returning to a tool keeps its loaded data until you reload it or refresh the browser. Date filters affect deposits only; older outstanding expense splits remain visible. API collections are paginated internally.

### Recovery and limits

- **Activity** retains reviews and operation results in SQLite. Reopen an interrupted operation to resume it. Existing matching links are reused, including after a lost HTTP response or restart.
- All selected journals are checked again before the first write. Changed financial fields or conflicting reimbursement links stop the operation.
- The link and tag endpoints cannot be committed atomically. Partial completion is possible. Processing stops on the first error, recorded in Activity. A linked split may retain its pending tag until a retry clears it.
- Selected reimbursements may total less or more than the deposit. Both the selection view and review dialog show the difference as a warning, without blocking confirmation. Each selected split is linked and its pending tag removed; no amount allocation or remaining debt is tracked. Mixed currencies and incremental allocation of previously linked deposits are not supported. Use an existing Activity operation to resume a partially completed match.
- Run one sidecar instance per Firefly connection. Local locking serializes its writes. The API has no compare-and-swap here; avoid simultaneous edits by Firefly or another automation while applying. Group updates include every sibling journal ID to retain all splits, but only the selected journal receives a tag patch.
- No background financial writes, schedules, expense creation or transaction deletion occur.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `FIREFLY_URL` | required | Firefly base URL; trailing `/api/v1` also accepted |
| `FIREFLY_TOKEN` | required unless token file supplied | Personal Access Token |
| `FIREFLY_TOKEN_FILE` | unset | Mounted token file; takes precedence |
| `FIREFLY_PUBLIC_URL` | unset | External browser URL for all Open in Firefly links |
| `TODO_TAG` | `todo` | Exact tag identifying transactions awaiting validation |
| `REIMBURSE_TAG` | `Reimburse` | Exact pending tag name |
| `REIMBURSE_LINK_TYPE` | `Reimbursement` | Existing Firefly link type name with reimbursement direction |
| `SIDECAR_HOSTS` | `localhost,127.0.0.1,[::1]` | Allowed browser hostnames, without ports |
| `SIDECAR_USERNAME` | `sidecar` | Basic Auth username |
| `SIDECAR_PASSWORD` | empty | Enables Basic Auth when nonempty |
| `DATA_DIR` | `./data`; `/data` in Docker | SQLite activity and recovery data |
| `BIND` | `127.0.0.1`; `0.0.0.0` in Docker | HTTP listen address |
| `PORT` | `8080` | Internal HTTP port |

`REIMBURSE_DESCRIPTION` is no longer used and can be removed from existing environment files.

Restart after configuration changes. Bearer tokens are not logged, stored in SQLite or returned by API endpoints. Firefly redirects are refused to avoid forwarding credentials: use the final canonical URL. Activity contains transaction details, so protect the data volume.

## Activity audit trail

Activity lists every Firefly API write sent by the sidecar: reimbursement links, tag updates and transaction deletion. Each attempt is durably recorded in SQLite before the write, with UTC timestamps, request details, transaction IDs, tag differences and before/after snapshots where available. Deleted transactions retain their before snapshot. Reimbursement operations and resume controls remain below the change log.

`completed` means Firefly accepted the request. `uncertain` means a write was attempted but its result was not received reliably; inspect Firefly before retrying. `blocked` means preparation failed before the write. `pending` can remain after a crash. A post-write snapshot failure is displayed separately. Writes are prevented when their initial audit record cannot be saved. Reads, previews and already-validated no-ops do not create change events. Use **Load older changes** to browse older entries; entries persist in the existing data volume. Changes made before this update cannot be reconstructed, although previous reimbursement operation records remain available.

Future tools must use the audited client supplied by the server for every API mutation. Do not instantiate an independent client or bypass the wrapper. API credentials are not recorded; known credential fields are redacted from structured payloads. Activity contains financial data and deleted transaction snapshots, so retain it as part of the sidecar backup.

## Backup and updates

Securely retain `.env`, any token secret and the `sidecar-data` volume. The database stores reviews and recovery context; Firefly remains the financial source of truth. Back up SQLite while stopped, or use SQLite's backup API. Restore the database before resuming interrupted operations. `docker compose down -v` discards activity and recovery records.

After replacing source, update with `docker compose up -d --build`.

## Open transactions in Firefly

Set `FIREFLY_PUBLIC_URL` to the external browser-facing Firefly base URL (for example `https://firefly.example.com` or `https://example.com/firefly`). Transaction review, reimbursement rows and selected deposits, match review, Activity and duplicate results use this URL to open their parent transactions in a new tab. The internal `FIREFLY_URL` is only used for API access, never as a fallback for transaction links. If the external URL is missing or invalid, transaction names remain plain text.

## Development and adding tools

Python 3.11+ and standard library; plain JavaScript/CSS. No Python or npm runtime dependencies.

```bash
# Export real connection configuration first.
python3 -m sidecar.server

# Checks.
python3 -m unittest discover -s tests -v
node --check sidecar/static/app.js
node tests/test_ui.cjs
node tests/test_loading.cjs

# Disposable sample-data UI; never touches a real Firefly account.
python3 tests/preview.py
# Open http://localhost:4173
```

The sample preview resets on restart and is excluded from the production image.

| Area | Responsibility |
| --- | --- |
| `sidecar/client.py` | Shared Firefly authentication, transport, pagination and journal lookup |
| `sidecar/store.py` | Persistent reviews and activity |
| `sidecar/tools/__init__.py` | Tool registry |
| `sidecar/tools/reimbursements.py` | Reimbursement eligibility, review, application and recovery |
| `sidecar/server.py` | HTTP routes, CSRF, host checks and optional authentication |
| `sidecar/static/` | Shared dashboard shell and tool UI |
| `tests/` | Service and HTTP integration tests |

Add a future tool as a module under `sidecar/tools/`, register it in `TOOLS`, add its namespaced routes in `server.py`, and add a sidebar entry and view. Reuse the client and shared shell. Every future tool displaying a transaction must supply its parent `group_id` and render a link with the shared `fireflyLink(group_id, label)` helper. Always use `FIREFLY_PUBLIC_URL`; never construct transaction links from the internal API URL. Arbitrary third-party plugins are not dynamically loaded.

## Verification

Automated tests pass, covering the HTTP review/apply journey against a stateful Firefly test double, own-share preservation, exact decimals, stale selections, conflicting links, host/CSRF checks and retry recovery. JavaScript and Python syntax checks pass.

API contracts were checked against the [official v6.7.8 OpenAPI specification](https://github.com/firefly-iii/api-docs/blob/v6.7.8/dist/firefly-iii-v6.7.8-v1.yaml), [link transformer](https://github.com/firefly-iii/firefly-iii/blob/develop/app/Transformers/TransactionLinkTransformer.php), [link type seeder](https://github.com/firefly-iii/firefly-iii/blob/develop/database/seeders/LinkTypeSeeder.php) and group-update implementation. The Docker image uses Python 3.13; automated tests ran under Python 3.12.

No live Firefly instance or credentials were supplied. Live API compatibility, Docker execution and visual browser QA remain unverified: Docker and the browser preview supervisor were unavailable in the build environment. Start with a small known reimbursement and inspect its links and split tags in Firefly after setup.
