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

Each row represents a tagged journal, including an unsplit transaction. On load, the queue checks its full parent transaction against all nearby transactions (including untagged ones) within ±3 days, using the Duplicate checker's exact summed total, currency, type and account rules. Matching candidates appear in an expandable **Potential duplicates** column with totals, split breakdowns and Firefly links. Checks are advisory and do not block validation. Unsupported groups show **Manual review needed**; failed lookups show **Check unavailable**, never a misleading clean result. Nearby overlapping date windows are fetched together, and no transaction is compared against itself. Up to 20 matches per parent are displayed, with the full count shown. Use the row checkboxes or **Select all visible transactions** to select multiple journals, then **Mark selected validated**. Search filters do not clear hidden selections; the selection count shows the total and visible counts. Bulk validation runs sequentially, records each Firefly write in Activity, removes successful rows, and retains failed selections with an error summary. **Clear selection** resets the selection. Deletion remains an individual action with its transaction preview.

**Mark validated** removes only `TODO_TAG` from that journal, preserving other tags, amounts, categories and sibling splits. Categorized transactions and all transaction types are included. The action reads the latest tags before updating, disables rules and webhooks, and verifies the result. A retry is safe if the tag was already removed. Reload after an error to inspect the current queue.

**Categorize** is available per row or via **Categorize selected**. Choose source/destination accounts, category, budget and subscription from Firefly's existing choices. Each field defaults to **Keep unchanged**; category, budget and subscription also support **Clear assignment**. Account options must be valid for every selected transaction type; choose homogeneous groups if a mixed selection has no common account option. Budget and subscription changes apply only to withdrawals; deposits and transfers retain those fields. Tags (including todo), amounts and unselected sibling journals are preserved. The dialog shows current details and external Firefly links for each selected journal.

Categorization checks for changes since opening, applies each journal separately with rules/webhooks disabled, verifies the result and records it in Activity. Successful rows are deselected; failed rows remain in the dialog for inspection/retry. The review queue reloads after applying. Dialog sessions expire after ten minutes or a restart; reopen a stale dialog before trying again. Up to 200 journals can be selected per categorization dialog. Reads and no-op updates are not logged as Firefly changes.

**Mark as Refund** is available only for deposit journals. The dialog searches withdrawals in a configurable date interval, comparing each whole withdrawal's exact split sum to the selected deposit journal amount in the same currency. Defaults: preceding 90 days and an absolute amount tolerance of 1.00 in deposit currency. Set `REFUND_LOOKBACK_DAYS` and `REFUND_AMOUNT_TOLERANCE` to change the defaults, or adjust them in the dialog. Candidates show parent totals, split breakdowns and external Firefly links. Single-journal candidates show journal details directly. **Require the withdrawal to use the same asset account as the deposit** is checked by default and compares withdrawal sources with the deposit destination; uncheck it to include other asset accounts. Groups with mixed currencies/accounts/dates or invalid amounts are excluded.

Choose a withdrawal, select one or more splits, and click **Create Refund link**. Single-journal withdrawals are selected automatically. Firefly links journals, so only the explicitly selected journals in the withdrawal are linked to the deposit journal: deposit `inward_id`, withdrawal `outward_id` (the deposit refunds the withdrawal in Firefly’s display). **Also remove the deposit's todo tag** is optional and unchecked by default. Existing matching Refund links are reused on retries. Reversed links bearing the exact `Firefly Sidecar refund match` note from older versions are corrected in place when the same withdrawal is selected again, with corrections recorded in Activity. Unrelated or duplicate links are not automatically changed; conflicting Refund links on the deposit block a different selection. If an operation pauses, inspect Activity and retry the selection. Searches expire after ten minutes; after a restart, search again and existing links will still be reused. Financial changes since search block confirmation. After linking, **Mark as cash** is applied to the deposit journal and the selected withdrawal journals only: categories, budgets and subscriptions are cleared, withdrawal destinations and the deposit source become Cash account. Amounts and tags are preserved, apart from the optional deposit todo removal. Cash-account resolution happens before link creation; partial cash updates can be retried without duplicating links or repeating successful cash writes. Each link and optional todo removal is recorded in Activity.

**Mark as cash** is available per journal or for the current multi-selection. It clears category, budget and subscription (`bill_id`). For a withdrawal it replaces only the destination with Firefly's Cash account; for a deposit it replaces only the source. Transfers retain both accounts. Amounts, descriptions, tags (including todo), and unselected sibling splits are preserved. Each write is verified and recorded as **Mark as cash** in Activity. The queue reloads afterward to refresh accounts and duplicate checks. Bulk actions run sequentially and report individual failures.

The Cash account is detected with the accounts API's `cash` filter. If Firefly returns more than one account, configure `CASH_ACCOUNT_ID` with the ID of its Cash account. Transfers do not require cash-account lookup.

**Delete transaction** is available on review rows and on expanded duplicate candidates. It opens a fresh preview with a Firefly link and every journal. Confirming deletes the whole parent transaction, including all splits; there is no undo in the sidecar. Confirmation expires after ten minutes and is rejected if the transaction changed since preview. After deletion the review queue refreshes and the reimbursement/duplicate caches are invalidated. Deleting an untagged duplicate candidate is supported. No automatic deletion occurs.

The queue has its own service and API namespace so future review actions and links to other tools can be added here.

### Split transaction

Use **Split transaction** on a Transaction review row. The dialog defaults to a regular 50% split; choose a percentage or fixed amount and a description for the new portion. Both portions retain the original accounts, category, budget, subscription and tags. The remainder keeps its original description. Regular splitting preserves validation status and must leave a positive remainder.

Check **Mark the selected portion as reimbursement** to use the existing reimbursement behavior. The reimbursable portion uses cash settings and `REIMBURSE_TAG` (default `Reimburse`); partial reimbursements create a split named **Reimbursement**. All journals in the parent transaction are validated by removing todo. A full 100% reimbursement keeps the original description and amount without adding a split. The separate Reimbursements matching tool is unchanged.

Existing group titles are retained; a newly split transaction uses the original description as its group title. Currency rounding and subtraction keep both portions equal to the original total, including proportional foreign amounts. Rules and webhooks are disabled. Activity records **Split transaction** or **Mark as reimbursement**, as appropriate. Snapshot checks and verification guard against stale or uncertain saves; inspect Firefly and Activity before reopening an uncertain operation.

## GBITs (Curve Go Back in Time)

In **Transaction review**, use **Mark as GBIT** on the new card charge or refund deposit, or use the multi-selection action. The action covers the entire parent transaction: every journal is marked as cash, todo is removed, and `GBIT_TAG` is added while preserving other tags. Withdrawals and deposits are supported; transfers are rejected. The original expense should not be flagged: it retains its financial categorization.

`GBIT_TAG` defaults to literal `#GBIT` and must differ from `TODO_TAG`. By default, Firefly must have transaction link types named **GBIT** and **GBIT Refund**. Set `GBIT_LINK_TYPE` and `GBIT_REFUND_LINK_TYPE` to use different existing names (case-sensitive); the two names must be distinct and nonempty. Restart after changing configuration. Saved operations retain their original link type names and IDs, so they can still resume after a configuration change if those Firefly link types remain available. The service uses their existing IDs; it does not silently create custom link types.

Open **GBITs** to load pending flagged charges and refund deposits, plus original withdrawals from the last 90 days. Change the original-expense date range and reload as needed. Tagged charges and refunds are not restricted by that range. Choose the new charge, original expense, and optional refund deposit. Beneath the original-expense dropdown, split expenses show journal checkboxes: explicitly select the journals to link and leave unrelated fees unchecked. A single journal is selected automatically. Links and split details use the external Firefly URL. All participants must have the same currency; amount differences are shown as warnings without blocking review.

The confirmation shows **original expense → new charge (GBIT)** and **refund deposit → original expense (GBIT Refund)**. The confirmation shows only the selected original journals and their selected total. Each selected original journal is linked to every corresponding new/refund journal (for GBIT, `inward_id` is the original and `outward_id` is the new charge; for GBIT Refund, `inward_id` is the refund deposit and `outward_id` is the original expense). The new charge and refund are marked as cash, including when tags were applied manually. The original expense's amounts, accounts, category, budget, subscription and other tags are retained.

If the refund has not arrived, apply the new-charge link alone: the GBIT remains **awaiting_refund**, and its tags stay. Select the same original/new pair and original journals again when the flagged refund is available. A GBIT completes only after both complete link sets have been verified; only then are GBIT tags removed from the participants. Todo has already been removed during flagging. No other tags are cleared.

Reviews and interrupted operations are saved in SQLite. **Saved GBIT operations → Inspect & resume** reopens an interrupted review, including after restart. Matching existing links are reused. Conflicting links, changed financial fields, changed journal sets and changed link types block application. Partial tag cleanup can be resumed after all links exist. Activity records each cash update, link and tag update independently. Keep the sidecar data volume for recovery.

## Duplicate checker

Open **Duplicate checker** to automatically scan the last seven days once. Change the start/end dates and maximum days apart (default 3, range 0–31), then click **Load from Firefly** to scan again. Both members of a pair must be inside the selected range.

The checker compares whole parent transactions by the exact decimal sum of all their journals. Currency and transaction type must match; withdrawals require the same source account, deposits the same destination account, and transfers the same source/destination pair. It never compares a transaction against itself. Matching descriptions and shared external IDs are displayed as supporting evidence, not proof of duplication.

Candidate pairs show dates, totals, tags, journal breakdowns and links to Firefly. Groups with mixed currencies, relevant accounts or dates, or invalid amounts are separately listed for manual review. Candidate pairs are paginated in batches of 500. The summary explicitly shows whether more are available; use **Load more candidates** below the results to retrieve the next batch. The same original date range and tolerance are used for subsequent batches. This tool only reads data; it does not delete, edit or tag transactions.

## Reimbursements

For an expense split into your categorized €30 share and uncategorized €15 and €5 `Reimbursement` splits tagged `Reimburse`:

1. Set both deposit dates and click **Load from Firefly**, then choose the €20 incoming deposit. Options represent individual deposit journals, including split deposits.
2. Select the €15 and €5 pending reimbursement rows.
3. Click **Review match** to inspect the total and link direction.
4. Click **Link & remove pending tag**.

The sidecar creates a **Reimbursement** link per selected expense journal. The deposit is `inward_id`; the expense is `outward_id`, so Firefly displays the deposit as reimbursing the expense. It verifies each link before removing the pending tag. Your categorized share, amounts and other tags are preserved. Rules and webhooks are disabled for the tag update.

Candidates must be withdrawals with the configured reimbursement tag; a category does not exclude them. Their split description does not affect eligibility. Tag names are case-sensitive. The default tag name is `Reimburse`; if your actual Firefly tag includes a literal `#`, set `REIMBURSE_TAG=#Reimburse`.

Each reimbursement row displays all of its tags. Search by parent title, merchant, account, tag, amount or journal ID. Additional tags do not exclude an otherwise eligible split. The deposit date range defaults to seven days ago through today, using the browser’s local date. Reimbursements load automatically once when the tool is first opened, using the displayed dates. Change the dates and click **Load from Firefly** to reload. Returning to a tool keeps its loaded data until you reload it or refresh the browser. Date filters affect deposits only; older outstanding expense splits remain visible. API collections are paginated internally. Short nonempty pages are followed until the reported last page; an empty page stops immediately, even if Firefly reports inflated totals.

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
| `REFUND_LOOKBACK_DAYS` | `90` | Default days before the deposit to search withdrawals |
| `REFUND_AMOUNT_TOLERANCE` | `1.00` | Default absolute amount difference allowed, in deposit currency |
| `CASH_ACCOUNT_ID` | unset | Optional explicit Firefly Cash account ID for Mark as cash |
| `GBIT_LINK_TYPE` | `GBIT` | Existing Firefly link type for original expense → new charge |
| `GBIT_REFUND_LINK_TYPE` | `GBIT Refund` | Existing Firefly link type for refund deposit → original expense |
| `GBIT_TAG` | `#GBIT` | Exact tag for pending Curve Go Back in Time matches |
| `TODO_TAG` | `todo` | Exact tag identifying transactions awaiting validation |
| `REIMBURSE_TAG` | `Reimburse` | Exact pending tag name |
| `REIMBURSE_LINK_TYPE` | `Reimbursement` | Existing Firefly link type name with reimbursement direction |
| `SIDECAR_BASE_PATH` | empty | Public URL prefix, e.g. `/sidecar`; accepts preserved or stripped proxy paths |
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
node tests/test_gbit_ui.cjs
node tests/test_categorize_ui.cjs

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

Add a future tool as a module under `sidecar/tools/`, register it in `TOOLS`, add its namespaced routes in `server.py`, and add a sidebar entry and view. Reuse the client and shared shell. Single-journal transactions show journal details directly across all tools, without a split count or expandable split section. Parent cards use the shared `transactionJournalDetails(row)` renderer; only multi-journal parents show an expandable breakdown. Every future tool displaying a transaction must supply its parent `group_id` and render a link with the shared `fireflyLink(group_id, label)` helper. Always use `FIREFLY_PUBLIC_URL`; never construct transaction links from the internal API URL. Arbitrary third-party plugins are not dynamically loaded.

## Verification

Automated tests pass, covering the HTTP review/apply journey against a stateful Firefly test double, own-share preservation, exact decimals, stale selections, conflicting links, host/CSRF checks and retry recovery. JavaScript and Python syntax checks pass.

API contracts were checked against the [official v6.7.8 OpenAPI specification](https://github.com/firefly-iii/api-docs/blob/v6.7.8/dist/firefly-iii-v6.7.8-v1.yaml), [link transformer](https://github.com/firefly-iii/firefly-iii/blob/develop/app/Transformers/TransactionLinkTransformer.php), [link type seeder](https://github.com/firefly-iii/firefly-iii/blob/develop/database/seeders/LinkTypeSeeder.php) and group-update implementation. The Docker image uses Python 3.13; automated tests ran under Python 3.12.

No live Firefly instance or credentials were supplied. Live API compatibility, Docker execution and visual browser QA remain unverified: Docker and the browser preview supervisor were unavailable in the build environment. Start with a small known reimbursement and inspect its links and split tags in Firefly after setup.

### Reverse proxy under /sidecar

Set `SIDECAR_BASE_PATH=/sidecar` and add your public hostname to `SIDECAR_HOSTS`. Recreate the container after changing `.env`. This setting is separate from `FIREFLY_PUBLIC_URL`, which remains the external Firefly URL.

For an nginx proxy on the same host as the published sidecar port:

```nginx
location = /sidecar {
    return 308 /sidecar/$is_args$args;
}
location /sidecar/ {
    proxy_pass http://127.0.0.1:8088;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Use the sidecar service address and container port instead if the proxy runs in a separate container. Both prefix-preserving and prefix-stripping proxies are supported. Open `/sidecar/`; the UI assets and all API requests use the configured prefix. `/healthz` remains available for container health checks.

### Install as an app (PWA)

Serve Sidecar over HTTPS (localhost also works for development). Open its public URL, then use the browser's install option or the **Install Sidecar** button when available. On iPhone/iPad, use Safari's Share → Add to Home Screen. The installed app opens in its own window and respects `SIDECAR_BASE_PATH`, including `/sidecar/`.

The service worker caches only a generic offline notice. Reviewing transactions and making changes require a connection to the server. It does not cache financial data, queue writes or replay failed requests. Normal authentication still applies.

In Transaction review, **Delete selected** previews all selected parent transactions and every journal they contain, including unselected siblings. Each parent is deleted once, with up to 100 parents per batch. Cancel makes no changes. Confirmed deletions use the same stale checks and Activity auditing as individual deletion; the batch stops on the first error. Inspect Activity before retrying an uncertain result.

The Duplicate checker provides a delete icon on either transaction in each candidate pair. It opens the same full-parent confirmation as Transaction review, records deletion in Activity, and refreshes duplicate candidates after confirmation. Only the transaction whose delete icon you clicked is removed; its entire split group is included.

In the Duplicate checker, select individual transaction cards and use **Delete selected** for a batch. The same parent appearing in several pairs shares one checkbox selection and is previewed/deleted once. **Clear selection** resets the batch. Successes are removed from the selection; failures and unprocessed transactions stay selected. Changing the search date range or days-apart setting and reloading clears the old selection. All batch deletions use the shared confirmation and Activity logging.

Duplicate candidates bearing the configured `TODO_TAG` are preselected for deletion on their first appearance in a search. You can uncheck any candidate or clear the selection; those choices persist when reloading the same search or loading more pages. Changing the date range or days-apart filter and reloading starts a fresh selection. Preselection never deletes anything automatically: the full deletion confirmation remains required.

### Activity filters and pages

Activity shows 25 changes per page by default, with Previous/Next navigation, matching result totals and optional 50/100-row pages. Apply filters for action, outcome (completed, pending, uncertain or blocked), exact parent transaction ID, and inclusive UTC start/end dates. Filters run in SQLite before pagination and Reset returns to all changes on the first page. Timestamps still display in your browser’s local timezone; date filter labels explicitly use UTC. Reimbursement operations appear directly in the same timeline. Choose the Reimbursement action filter to find them; incomplete entries provide Open review or Inspect & retry controls. Existing operations are included automatically, including records older than the former 50-entry history limit. Individual Firefly write records are retained alongside operation summaries. No activity records are removed by pagination or filters.

**Mark as cash** (individual or bulk Transaction review action) removes the configured `TODO_TAG` by default, preserving all other tags. Set `MARK_CASH_REMOVE_TODO=false` to keep todo instead; the default is `true`. Recreate the container after changing this setting. It does so even when the transaction already has cash settings. Refund matching retains its separate remove-todo checkbox behavior.

Across tools, transactions with a single journal display their parent **Transaction ID**. Multi-journal transactions retain **Journal IDs** for individual splits, including when only one journal is selected for GBIT. Selection and API updates continue using journal IDs internally.

Transaction review groups pending splits beneath a single parent transaction heading. The heading shows the full parent total (including journals without todo), duplicate checks, and the parent delete action once. Each pending journal retains its own details and actions. The parent checkbox selects the visible pending journals in that transaction; search can show only matching journals without changing the full transaction total.

Completed reimbursement operations in Activity offer **Inspect & verify links**. Open the saved review and apply it to correct reversed links created by older sidecar versions. Only reversed links with the exact saved operation note are corrected in place; unrelated links block the operation. Corrections use the audited client, preserve amounts and other tags, and are safe to retry. Current financial details must still match the saved review. Links without a saved sidecar operation must be corrected in Firefly.

On a split transaction's parent row in Transaction review, **Mark transaction validated (all pending splits)** removes `TODO_TAG` from every pending split in that parent, including splits hidden by search. It saves the group in one audited update, preserves all other tags and financial details, and verifies the result. Individual split validation and selection-based validation remain available.


Pending GBITs use compact summaries and hide completed matches, including older reviews of the same match. Completed operations are available in Activity using the GBIT action filter; original, new-charge and refund transaction IDs can all be used to find them. **Inspect & verify links** opens a saved review. Confirming it verifies the links and repairs reversed GBIT Refund links created by Sidecar for those exact journals, preserving link IDs. Manual or ambiguous conflicting links require inspection in Firefly. Ordinary transaction writes remain individually audited.


When a GBIT original expense has splits, choose **Original journals for the new charge** independently from **Original splits refunded by this deposit** (beneath the refund selector). The latter accepts one or more original journals and is required when selecting a refund. Single-journal expenses are selected automatically. The review shows both selections and totals; only the selected original journals receive their respective link types. Existing saved reviews retain their original selections.

Split withdrawal candidates remain searchable when their full total exceeds the deposit amount, so individual splits can be refunded. The refund dialog displays the selected total and any difference from the deposit before confirmation. Unselected splits retain their accounts, category, budget, subscription and tags.


Reimbursements loads a paginated Firefly tag search and groups matching journals under their parent transaction. It does not scan withdrawal history or fetch every parent separately. The configured reimbursement tag determines inclusion for withdrawals, including categorized splits; untagged siblings remain excluded. Deposit dates do not restrict outstanding expenses.


## Consistency checker

The **Consistency checker** checks every matching transaction journal in the selected scope. Scanning is read-only. It verifies the Cash account on withdrawal destinations or deposit sources, and cleared category, budget and subscription. Transfers keep both accounts.

| Rule | Journals requiring cash settings |
| --- | --- |
| GBIT | Journals with `GBIT_TAG`, replacement withdrawals on `GBIT_LINK_TYPE` links, and deposits on `GBIT_REFUND_LINK_TYPE` links |
| Reimbursements | Journals with `REIMBURSE_TAG` and withdrawals on `REIMBURSE_LINK_TYPE` links |
| Refunds | Both deposit and withdrawal journals on a `Refund` link |

Configured link names and the GBIT / GBIT From and GBIT Refund / GBIT Refunds aliases are recognized. The original GBIT purchase keeps its treatment unless another rule applies. Rules are checked per journal; unrelated siblings are not required to be cash.

Choose dates (past week by default, no date-range length cap), transaction type, rules, one or more accounts, exact tag or transaction ID, then **Run full check**. Nothing runs automatically on navigation. The job follows every transaction page and every journal-link page sequentially, rather than issuing parallel database-heavy lookups. Live progress shows collection pages and then journals checked against the discovered total. **Stop check** stops after the current Firefly request and clearly marks the scope as incomplete.

**Results per page** (25/50/100) affects display only. Previous/Next, Show all, and Inconsistent only reuse the completed report without rechecking Firefly. Inconsistent only is the default and also keeps failed/incomplete checks visible. All evaluated transactions includes consistent journals and journals without an applicable rule. Display pagination covers the full report, not a single transaction-fetch page.

Date/type filters are sent to Firefly. The searchable account dropdown accepts multiple selections, including inactive accounts. No selection means all accounts. Matching either source or destination is sufficient. Each selected account uses its transactions endpoint; results are merged and journal IDs are deduplicated before link checks. Otherwise an exact tag uses the tag endpoint. When tags and accounts are combined, tag matching is checked within each account page. An explicit transaction ID loads only that parent and still applies the other filters. Counterparts outside the filters are not recursively scanned.

Checks run in memory with at most two active jobs per Sidecar process; up to three older completed reports are retained alongside the latest report, with 30-minute retention cleanup when a new job starts. A restart discards reports; rerun the check if needed. Scanning makes no transaction writes or Activity-history changes.


Inconsistent entries use a red status badge. **Review fix** opens a cash-settings preview for one journal; **Apply fix** applies those changes through the audited Mark as cash workflow. It preserves amounts, descriptions, tags (including todo), transfer accounts, and unrelated siblings. The server verifies the transaction has not changed since scanning or previewing, rechecks that a cash rule still applies, and rejects incomplete checks. Successful fixes update the saved report and appear as **Mark as cash** in Activity. Preview tokens expire after ten minutes and cannot be replayed. If a write has an uncertain outcome, inspect Activity and rerun the check before trying again.


Each consistency entry has **Recheck**. After a manual edit in Firefly, use it to read the current parent transaction and re-evaluate that journal and its links against the original scan filters. The saved report and counts update without rescanning other entries or writing to Firefly. Resolved entries leave the default Inconsistent only view; they remain inspectable in All evaluated transactions. Entries that no longer match the original scope are marked accordingly. Incomplete checks remain visible.


Transaction review defaults to the **Todo** queue. Its **Queue** dropdown also offers **Reimbursements** (`REIMBURSE_TAG`) and **GBITs** (`GBIT_TAG`). These queues show tagged journals independently of todo, preserving parent grouping, totals, duplicate checks and per-journal actions. Switching queues clears the selection. Validation always removes only `TODO_TAG`; journals remain in the reimbursement/GBIT queue while they retain the corresponding tag.


Transaction review also offers **Period (all tags)**. Selecting it shows From/To dates prefilled with today and seven days earlier, clears stale results and selections, and waits for **Load from Firefly**. It includes every journal in the selected inclusive period without a tag requirement. Editing either date clears the results and requires another explicit load; navigation does not trigger the first period fetch. After loading, actions can refresh that same period as usual. Todo remains the default queue.


### Shared UI conventions

Transaction amounts use the same presentation across review, reimbursements, duplicates, GBITs, Activity, consistency results and confirmation dialogs: withdrawals are negative and red, deposits positive and green, and transfers unsigned and blue. Exact-decimal calculations and Firefly payloads remain unchanged. Balance differences and counters remain neutral. Native transaction selectors use the same signs and type colors.

All tool filters share control sizes, spacing, focus treatment and responsive grids. On phones, transaction tables become labelled cards with selection and actions retained; split grouping remains visible. Navigation, dialogs, GBIT comparisons and action rows adapt to narrow widths, and inputs use mobile-friendly touch targets.

Transaction review keeps **Load from Firefly** with the filters. From/To use equal-width columns, and the queue hint aligns with the controls. Mobile empty messages span the card, and row actions wrap inside it. Single-journal review rows show their description once and retain the transaction ID; split descriptions and journal IDs remain visible. Transaction tags use the same escaped pills using the exact Firefly tag names throughout review, Reimbursements, duplicate/GBIT cards, delete previews and Activity tag changes.

Reimbursements and Duplicate checker use the Review metadata layout: description, transaction/journal ID, accounts, category and tags (including per-split categories and tags). Load from Firefly actions use the shared blue primary style; the duplicate checker keeps its load action alongside the desktop filters.

Reimbursement expense labels prefer the Firefly group title, including in the Review reimbursement queue; the journal description is used only when no group title exists. Duplicate cards show their date after metadata and keep deletion in a bottom action row.

### Convert a reviewed transaction to a transfer

Deposits and withdrawals in Transaction review have a **Convert to transfer** row action. The dialog previews every journal in the parent transaction, including splits outside the current queue. Conversion applies to the whole parent because Firefly requires one transaction type per group. Choose an active asset or liability account different from the existing account. Withdrawals show only the destination selector and retain their source; deposits show only the source selector and retain their destination. Amounts, dates, currencies, descriptions, categories and all tags (including todo) stay unchanged. Budget and subscription assignments are cleared.

The conversion is CSRF protected and recorded in Activity as **Convert to transfer**. The server rechecks the parent and account availability before writing, disables rules and webhooks, and verifies the result. Changed or expired previews must be reopened. A submitted preview cannot be replayed after an uncertain write; inspect Firefly and reopen the action before retrying.

Refund searches include withdrawals paid from a different account by default, supporting refunds received as gift-card credit. The optional same-account filter restricts candidates to the refund destination account; the dialog reports otherwise matching transactions excluded by it. Amount tolerance cannot override this account filter. For purchases with a separate fee, select only the journals actually refunded.

## Amazon Sync (Chrome companion)

Amazon Sync receives Amazon Spain orders directly from a companion Chrome
extension, stores them locally and suggests matches to Firefly withdrawal
journals. Each enrichment is reviewed and appends order/item details to notes;
the matched journal description uses the Toolbox Amazon format; financial fields are kept. Imports never mutate Firefly.

Set a dedicated `AMAZON_SYNC_TOKEN` (32+ random characters), restart, and open
**Amazon Sync** in the sidecar to download the extension. Extract it and use
Chrome's **Load unpacked**. Configure your sidecar URL and token,
sign in to Amazon.es and click **Sync now**. Optional daily collection runs while
Chrome is open; sign-in/MFA and page changes can require intervention.

See [extension setup, build instructions and matching limitations](extensions/amazon-sync/README.md).
This first version supports Amazon.es/EUR, manual review, charge matching and
description/notes enrichment. Refund enrichment, automatic item splitting and unattended
server-side collection are outside this version.
