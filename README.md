# Firefly Sidecar

A self-hosted web toolbox alongside Firefly III. Reimbursements is its first tool: choose a deposit, select shared-expense splits, review, then link and clear their pending tag.

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

## Reimbursements

For an expense split into your categorized €30 share and uncategorized €15 and €5 `Reimbursement` splits tagged `Reimburse`:

1. Choose the €20 incoming deposit. Options represent individual deposit journals, including split deposits.
2. Select the €15 and €5 pending reimbursement rows.
3. Click **Review match** to inspect the total and link direction.
4. Click **Link & remove pending tag**.

The sidecar creates a **Reimbursement** link per selected expense journal. The expense is `inward_id` (“is (partially) reimbursed by”); the deposit is `outward_id` (“(partially) reimburses”). It verifies each link before removing the pending tag. Your categorized share, amounts and other tags are preserved. Rules and webhooks are disabled for the tag update.

Candidates must be withdrawals with the exact configured description and tag, and no category. Tag names are case-sensitive. The default tag name is `Reimburse`; if your actual Firefly tag includes a literal `#`, set `REIMBURSE_TAG=#Reimburse`.

Search by parent title, merchant, account, amount or journal ID. Date filters affect deposits only; older outstanding expense splits remain visible. API collections are paginated internally.

### Recovery and limits

- **Activity** retains reviews and operation results in SQLite. Reopen an interrupted operation to resume it. Existing matching links are reused, including after a lost HTTP response or restart.
- All selected journals are checked again before the first write. Changed financial fields or conflicting reimbursement links stop the operation.
- The link and tag endpoints cannot be committed atomically. Partial completion is possible. Processing stops on the first error, recorded in Activity. A linked split may retain its pending tag until a retry clears it.
- Version 0.1 requires exact full-deposit matches in one currency, settling each selected split in full. Partial split repayments, mixed currencies and incremental allocation of previously linked deposits are not supported. Split a partial repayment in Firefly first. Use an existing Activity operation to resume a partially completed deposit match.
- Run one sidecar instance per Firefly connection. Local locking serializes its writes. The API has no compare-and-swap here; avoid simultaneous edits by Firefly or another automation while applying. Group updates include every sibling journal ID to retain all splits, but only the selected journal receives a tag patch.
- No background financial writes, schedules, expense creation or transaction deletion occur.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `FIREFLY_URL` | required | Firefly base URL; trailing `/api/v1` also accepted |
| `FIREFLY_TOKEN` | required unless token file supplied | Personal Access Token |
| `FIREFLY_TOKEN_FILE` | unset | Mounted token file; takes precedence |
| `FIREFLY_PUBLIC_URL` | internal URL | Display URL on Connection page |
| `REIMBURSE_TAG` | `Reimburse` | Exact pending tag name |
| `REIMBURSE_DESCRIPTION` | `Reimbursement` | Exact split description |
| `REIMBURSE_LINK_TYPE` | `Reimbursement` | Existing Firefly link type name with reimbursement direction |
| `SIDECAR_HOSTS` | `localhost,127.0.0.1,[::1]` | Allowed browser hostnames, without ports |
| `SIDECAR_USERNAME` | `sidecar` | Basic Auth username |
| `SIDECAR_PASSWORD` | empty | Enables Basic Auth when nonempty |
| `DATA_DIR` | `./data`; `/data` in Docker | SQLite activity and recovery data |
| `BIND` | `127.0.0.1`; `0.0.0.0` in Docker | HTTP listen address |
| `PORT` | `8080` | Internal HTTP port |

Restart after configuration changes. Bearer tokens are not logged, stored in SQLite or returned by API endpoints. Firefly redirects are refused to avoid forwarding credentials: use the final canonical URL. Activity contains transaction details, so protect the data volume.

## Backup and updates

Securely retain `.env`, any token secret and the `sidecar-data` volume. The database stores reviews and recovery context; Firefly remains the financial source of truth. Back up SQLite while stopped, or use SQLite's backup API. Restore the database before resuming interrupted operations. `docker compose down -v` discards activity and recovery records.

After replacing source, update with `docker compose up -d --build`.

## Development and adding tools

Python 3.11+ and standard library; plain JavaScript/CSS. No Python or npm runtime dependencies.

```bash
# Export real connection configuration first.
python3 -m sidecar.server

# Checks.
python3 -m unittest discover -s tests -v
node --check sidecar/static/app.js

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

Add a future tool as a module under `sidecar/tools/`, register it in `TOOLS`, add its namespaced routes in `server.py`, and add a sidebar entry and view. Reuse the client and shared shell. Arbitrary third-party plugins are not dynamically loaded.

## Verification

15 automated tests pass, covering the HTTP review/apply journey against a stateful Firefly test double, own-share preservation, exact decimals, stale selections, conflicting links, host/CSRF checks and retry recovery. JavaScript and Python syntax checks pass.

API contracts were checked against the [official v6.7.8 OpenAPI specification](https://github.com/firefly-iii/api-docs/blob/v6.7.8/dist/firefly-iii-v6.7.8-v1.yaml), [link transformer](https://github.com/firefly-iii/firefly-iii/blob/develop/app/Transformers/TransactionLinkTransformer.php), [link type seeder](https://github.com/firefly-iii/firefly-iii/blob/develop/database/seeders/LinkTypeSeeder.php) and group-update implementation. The Docker image uses Python 3.13; automated tests ran under Python 3.12.

No live Firefly instance or credentials were supplied. Live API compatibility, Docker execution and visual browser QA remain unverified: Docker and the browser preview supervisor were unavailable in the build environment. Start with a small known reimbursement and inspect its links and split tags in Firefly after setup.
