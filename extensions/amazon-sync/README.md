# Firefly Sidecar Amazon Sync (Chrome)

This companion uses the Amazon Spain collector and parsing utilities from
[Xenolphthalein/order-history-exporter-for-amazon](https://github.com/Xenolphthalein/order-history-exporter-for-amazon),
pinned at `39142ed3a969c55846f12a172eea83d5720dc080` (Unlicense; see vendor/LICENSE).
Vendored sources are under vendor/src. The collector completion handler sends
selected order fields to the companion background worker instead of downloading
JSON. Recipient addresses are excluded from submission. No Amazon cookies or
passwords are sent to the sidecar.

## Build

Use Node 22+:

```
npm ci --ignore-scripts
npm run build
```

The output is `sidecar/amazon-extension/` in the repository. It is committed so
Python/Docker users do not need Node. Rebuild it after changing extension code.
The sidecar serves a ZIP from Amazon Sync → Download Chrome extension.

## Install and use

1. Set `AMAZON_SYNC_TOKEN` to a dedicated random secret of at least 32 characters
   (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) and restart.
2. Download the ZIP from the sidecar, extract it, open `chrome://extensions`,
   enable Developer mode, choose Load unpacked, and select the extracted folder.
3. Open the extension popup. Enter the sidecar URL (including a subpath if used)
   and sync token. Save and grant access to your sidecar origin.
   Use HTTPS for a remotely accessible sidecar. The token authorizes importing
   orders only; it cannot read transactions or apply enrichment.
4. Sign in to Amazon.es, choose a date range, and click Sync now. A dedicated tab
   navigates Amazon order pages; leave it open until completion. The collector
   also requests payment details. Popup progress survives closing the popup.
5. In Sidecar → Amazon Sync, choose the Firefly transaction dates and tolerance,
   click Find matches, Review match, then Update description & notes.

The optional daily alarm collects the preceding 90 days while Chrome is running.
It opens a tab and may require your attention if Amazon requests sign-in/MFA or
verification. It does not bypass those steps. Click Stop if a run stalls, complete
sign-in, then start a new run. Chrome and Amazon page changes can interrupt runs.

If submission fails, use Retry sending collected orders. Repeated imports update
existing orders rather than creating duplicates. Pending data and the sync token
are stored in extension-local storage on this Chrome profile; protect the profile.
No Amazon account label is required.
Installing this companion is separate from installing/updating the upstream store
extension. It is initially limited to Amazon.es/EUR.

## Matching and limitations

Matching suggests Amazon withdrawal journals with equal currency/amount and a
configurable date distance. Payment amounts/dates take precedence, followed by
charged amount and then order total. Order-total fallbacks always need manual
verification. Equal charges can be ambiguous. Splits are matched at journal level;
item allocations, combined charges, gift-card accounting, cancellations and refund
enrichment are not automated. Signed refund records are retained but excluded
from withdrawal matching. There is no automatic Firefly mutation on import.

Enrichment updates the matched journal description and appends product titles, order ID and order URL to notes. It never
creates transactions, splits, categories or links. Every write uses Activity
auditing. Reviews become stale if their order or transaction changes. Payment
assignments are reserved before writing, preventing another journal from using
the same payment even when a response is lost. Retry the same review to recover;
inspect Activity after an uncertain write. Automatic reassignment is deliberately
not provided in this first version.

Live Amazon collection must be tested on your authenticated account; automated
fixtures cannot establish that the current Spain page layout works for every
order type. No live Amazon credentials are required for the regression tests.

### Updating to 0.1.1

Version 0.1.1 starts collection from the collector's own readiness message rather
than inspecting Chrome tab URL fields. It supports Amazon.es with English or
Spanish display language, locale-prefixed URLs and the bare amazon.es host.
Sign-in/verification pages keep the pending sync rather than cancelling it.

After updating/rebuilding the PR container, download and extract the extension
ZIP again, replace the unpacked extension's files, and click Reload on its
chrome://extensions card. Confirm version 0.1.1. Close previous sync tabs and
click Stop once to clear a stale job, then start Sync now.

### Updating to 0.1.2

Version 0.1.2 isolates the collector's Amazon page sessionStorage from the original
Order History Exporter. The original extension may stay installed: it must not
resume a Sidecar sync as a JSON export. Close old sync/export tabs after updating
and start a fresh sync to discard tab-local state from previous versions.
Successful submission displays “Synced N orders” in the companion popup. No JSON
file is downloaded or needs to be deleted.

### Recovering a queued collection (0.1.3)

Stop collection preserves orders already collected for submission. If an import
failed, select Retry sending collected orders; the popup now shows the sidecar's
structured validation error (or a network/redirect error) and queued order count.
To abandon the queued browser copy instead, choose Discard collected orders,
then Sync now. Discard does not remove anything already stored in Sidecar.
The popup preserves the actual outcome rather than replacing it with a generic
“Request accepted” message.

### Interface update (0.1.4)

The companion popup reuses the upstream exporter's layout and styling, with
connection settings, a date-range section, a gold Sync button and grouped recovery
actions. Connection settings collapse after configuration. The sidecar Amazon
Sync page has an order-and-payment card layout with responsive filters. Both
manual date ranges default to today minus 14 days through today in local time.
The optional daily background sync retains its 90-day reconciliation window.

### Description and branding update (0.1.5)

Reviews now show the proposed journal description as well as notes. The description
uses Toolbox's format: `Amazon <order ID>: <items>`; each title is shortened to
50 characters, quantities above one use `2x`, and the complete description is
bounded at Firefly's supported 1,000 characters. Other journals and the group title
are preserved. Existing financial-field verification still applies.

The account-label field and its display have been removed. Internal routing for
previous installations is retained for compatibility, while notes use an opaque
deduplication marker. Reviewing an older match replaces its account-bearing
marker without duplicating item notes. Existing Firefly notes are changed only
when their match is explicitly reviewed and applied again.

The extension has parcel/smile, firefly and export-arrow icons at Chrome's native
sizes. Source artwork and a Pillow renderer are in `icons/`. Amazon Sync has an
Amazon-style sidebar mark; Activity is the final sidebar action.
