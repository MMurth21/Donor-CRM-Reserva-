# Session Log — Reserva Reconciler Build
**Date:** 2026-05-22 → 2026-05-23
**Repo:** `~/Donor-CRM-Reserva-/reserva-reconciler/`
**Participants:** Milind (Reserva YLT) + Claude (claude-sonnet-4-6)
**Session type:** Full product build from zero

---

## What We Were Building

A donor CRM reconciler for **Reserva: The Youth Land Trust**. The org uses Classy (GoFundMe Pro) for fundraising and QuickBooks Online for accounting. Before this project, reconciliation was done manually — pulling a Classy donations report and hand-matching it to QBO entries.

The goal: pull all Classy transactions, normalize them, map each campaign to a QBO account + class, and ultimately generate a QBO-importable CSV. No QB API writes. Read-only Classy data, file-only export.

**Stack chosen:** FastAPI (Python 3.9, arm64 Mac) + React/Vite, self-signed SSL, two OAuth integrations.

---

## Arc of the Session

### Phase 1 — Repo Setup (resistance heavy)

**Prompt:** "I will be working on a CRM in a repository named ReservaYLT. Do you have access to this?"

GitHub access wasn't set up. Three different tokens were tried:
- Token 1: `github_pat_11CAPNVHY0SMhbq4bQRvnW_...` — didn't work
- Token 2: `github_pat_11CAPNVHY0FO2TVxtoDRnm_...` — didn't work
- Token 3: `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` — worked

**Riff:** Milind wanted to work off an existing `ReservaYLT` repo. After access issues, the decision was made to work fresh in a new repo `Donor-CRM-Reserva-`. Old tokens were purged from the conversation.

**Resistance:** Git auth friction, expired/scoped tokens, URL confusion with the clone command (`it clone` vs `git clone`).

**Success:** Got a clean working directory and fresh repo.

---

### Phase 2 — Scaffold (fast, no major resistance)

**Prompt:** Full FastAPI + React scaffold request with specific directory structure.

Built in one pass:
```
reserva-reconciler/
  backend/   ← FastAPI, uvicorn, SSL
  frontend/  ← Vite + React
```

CORS was initially set to `allow_origins=["http://localhost:5173"]`. This caused a problem later when Vite picked port `:5176` (port already in use). Fixed to `allow_origin_regex=r"http://localhost:\d+"`.

**Self-signed SSL cert:** Generated with `openssl req -x509 ...` for `127.0.0.1`. Backend runs at `https://127.0.0.1:8000`. Vite proxies to it with `secure: false`.

---

### Phase 3 — QuickBooks OAuth (resistance: intuitlib unavailable)

**Prompt:** Add QB OAuth2 mirroring the planned Classy auth pattern.

**Resistance:** `intuitlib` is not available for Python 3.9/arm64. Spent time diagnosing this before pivoting.

**Riff:** Rewrote `quickbooks_oauth.py` using `httpx` directly against Intuit's OAuth endpoints:
- `QB_AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"`
- `QB_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"`

Token stored in `tokens/quickbooks.json` with `expires_at` ISO timestamp for TTL checks.

**Success:** QB login + callback + status endpoints working without intuitlib.

---

### Phase 4 — Classy OAuth (multiple resistance points)

**Prompt:** "Add Classy / GoFundMe Pro OAuth 2.0 mirroring QB auth pattern."

First attempt used `auth_code` flow — wrong. Classy's token endpoint (`https://api.classy.org/oauth2/auth`) requires `client_credentials`. Browser redirect to that URL → 405 Method Not Allowed.

**Riff:** Rewrote to `client_credentials` grant. POST directly to the token URL with `Content-Type: application/x-www-form-urlencoded`.

**Resistance (hidden bug):** The `CLASSY_CLIENT_SECRET` in `.env` was:
```
CLASSY_CLIENT_SECRET=<zbOh6LiPifBpldEe>
```
The angle brackets were literal — Milind copied them from a credential doc that used `<value>` as a placeholder convention. The token endpoint returned `invalid_client`. Diagnosed by running `curl` directly against the token endpoint and seeing the encoded `%3CzbOh6...%3E` in the request body. Fixed by stripping `<>` from the `.env` value.

**Success:** `curl -k https://127.0.0.1:8000/auth/classy/test` returned a live Classy API response. First real data in.

---

### Phase 5 — Transaction Fetching + Normalization

**Prompt:** "Add a read-only Classy transactions probe" → "Build the Classy → canonical normalization layer."

**Key design decision on field mapping** (required inspection of raw Classy JSON):
- Classy field names differ from their documentation labels
- `fees_amount` = total fees (platform + processing)
- `pp_fees_amount` = payment processor fee only
- `platform_fee` is **computed**: `fees_amount − pp_fees_amount` (clamped ≥ 0)
- `donation_net_amount` = net after all fees
- Reconciliation check: `platform_fee + processing_fee + net == gross` (within $0.01)

**Resistance:** Python 3.9 rejects `str | None` union type annotation (PEP 604 syntax requires 3.10+). Removed return type annotation from `get_campaign_name()`.

**Success:** Normalization layer built. Fee math verified manually: `0.40 + 0.68 + 15.00 = 16.08 ✓`

---

### Phase 6 — Campaign Cache + Mapping System

**Prompt:** "Add a cached Classy campaign list." Then: "Replace backend/data/campaign_mapping.json entirely..."

**Design:** 1-hour TTL file caches for campaign list and campaign totals (full scan = 37 pages × 100 = 3,664 transactions).

**Resistance:** `_load_mapping()` was reading top-level keys from the JSON file, but the structure was `{"_meta": {}, "campaigns": {}}`. The function iterated `raw.keys()` and got `_meta` and `campaigns` as campaign IDs. Fixed: `campaigns = raw.get("campaigns", raw)` — handles both nested and legacy flat format.

**Resistance:** `fetch_campaign_totals` returned `{cid: float}` (old format) instead of `{cid: {"total_gross": float, "txn_count": int}}` (new format). The old format was cached to disk. Fixed by adding format detection: `isinstance(sample, dict)` — if the cached format is old, force refresh.

**Resistance:** Campaigns `470798` and `719401` were in `campaign_mapping.json` but the normalizer still reported them as `needs_mapping`. Debug endpoint `/debug/mapping-join` revealed the issue was upstream in `fetch_all_campaigns`, not the mapping file itself. Root cause: wrong cache format persisting.

**Campaign 396456 — $0 gross investigation:**
Milind noticed a campaign in the unmapped list with $0 gross. Raw Classy JSON inspection confirmed all money fields were genuinely $0 — free ticketed event registrations (not donations). Added filter: exclude `gross_amount ≤ 0` from mapping queue and transaction table.

**Riff on `_is_incomplete`:** Campaigns with `donor_selects: true` intentionally have null `qbo_class` (the donor designates at time of gift). The incomplete check was amended to short-circuit on `donor_selects`.

**Atomic file write:** Used `os.replace(tmp, MAPPING_FILE)` rather than direct write to prevent truncation mid-write if the server crashes during save.

**Seed mapping file:** 23 campaigns seeded from Milind's "CLASSY DONATIONS KEY" spreadsheet. Two campaigns flagged `needs_review` in `_meta`: `470798` (Support Reserva) and `542875` (Help Reserva Grow on Giving Tuesday!) — both `donor_selects: true`.

---

### Phase 7 — Campaign Mapping UI

**Prompt:** "Build the in-app campaign mapping UI for the Reserva reconciler."

Built `MappingPanel.jsx` + `CampaignRow.jsx`:
- Grid layout: `1fr 80px 90px 200px 200px 90px 56px`
- `SelectOrNew` component: select from existing QBO account/class values, or type a new one
- `+ add new…` sentinel triggers inline text input with Enter/Escape handling
- `donor_selects` checkbox disables the dropdowns (greyed out) since no fixed destination
- Save button disabled until `donorSelects` OR (`account.trim() && cls.trim()`)
- On success: row removed from panel, POST `/mapping/assign` persists atomically

**Design system:** Earth tones — `--bg #f2ede8`, `--surface #faf7f4`, `--accent #5c7a5c`, `--platform #4a7c6f`. Set once in `index.css`.

---

### Phase 8 — Transaction Table

**Prompt:** "Build the main transaction table — the primary CEO/bookkeeper view. React + the existing /classy/transactions/normalized data. Read-only display, no QB writes."

**Backend addition:** `GET /classy/transactions/all` — fetches all 37 pages at 100/page, normalizes everything, filters `gross > 0`, caches to `tokens/transactions_cache.json` with 1-hour TTL. First load is ~30 seconds (live Classy API). Subsequent loads instant.

**`TransactionTable.jsx`** — 11 columns in QB-reconciliation order:
```
transaction_date | donor_name | campaign_name | platform |
gross_amount | platform_fee | processing_fee | net_amount |
qbo_account | qbo_class | mapping_status
```

Features:
- Summary bar: total rows, gross, platform fee, processing fee, net, unmapped count — all update live as filters change. Shows "filtered / full" split when a filter is active.
- Text search: donor name + campaign name (case-insensitive)
- Date range filter (start/end)
- Sortable headers (click toggles asc/desc; money cols default desc, text cols default asc)
- Status badges: `mapped` (green), `needs mapping` (amber), `donor selects` (gray)
- Platform badge styled in GoFundMe Pro color (`--platform`)
- Alternating row backgrounds; ellipsis + title tooltip on long text cells
- `App.jsx` tabbed nav: Transactions (default) | Campaign Mapping

---

### Phase 9 — QBO CSV Export

**Prompt:** "Build the QuickBooks Sales Receipt CSV export. Generates a QBO-importable CSV from the normalized + mapped transactions. FILE ONLY — must NOT post to the QuickBooks API and must NOT touch the live/production company."

**Key spec decisions:**
- Input: `mapping_status in {mapped, donor_selects}` — skip `needs_mapping`, count skips
- Multi-line Sales Receipt per transaction:
  - Row 1: header + income line (account = `qbo_account`, amount = `gross_amount`)
  - Row 2: platform fee deduction (omit if zero)
  - Row 3: processing fee deduction (omit if zero)
  - Deposit amount = `net_amount`
- `donor_selects` rows: `qbo_class` left blank, `NEEDS_REVIEW = Y` column flag
- Validation report: per-receipt recon check + file totals + skipped count

**Architecture:** `backend/exporters/sales_receipt_csv.py` — standalone module, config constants at top.

**Two endpoints:**
- `GET /export/sales-receipts/report` → JSON validation report
- `GET /export/sales-receipts/download` → streams CSV file (UTF-8 with BOM for Excel)

**Frontend:** "Export to QBO CSV" button fetches report and shows it inline. "Download CSV" link appears after report loads. Report panel shows: receipts written, skipped, recon failures (listed individually), file totals, column list, and a warning banner if fee account names are still placeholders.

**Column format used** (needs verification with Marcus before first sandbox import):
```
*SalesReceiptNo | *Customer | *SalesReceiptDate | *DepositTo | Memo
| NEEDS_REVIEW | *LineAccount | *LineAmount | LineClass | LineDescription
```

**Known open question:** QBO's built-in CSV import for Sales Receipts is item-based (`*ProductService`). This file uses account names directly in `*LineAccount`. Three paths to resolve: (a) use account names via a compatible importer, (b) remap to `*ProductService` using matching QBO items, or (c) switch to Deposits/Journal Entries format. Must test in QBO sandbox before live company.

---

## Config Constants — Not Yet Filled In

These are placeholders in `backend/exporters/sales_receipt_csv.py`. Fill in before first import:

```python
PLATFORM_FEE_ACCOUNT   = "<<CONFIRM EXACT QB NAME>>"   # e.g. "GoFundMe Pro Fees"
PROCESSING_FEE_ACCOUNT = "<<CONFIRM EXACT QB NAME>>"   # e.g. "Payment Processing Fees"
DEPOSIT_TO_ACCOUNT     = "Undeposited Funds"           # standard QBO clearing account
```

---

## Resistance Log (All Bugs Hit)

| Bug | Root cause | Fix |
|-----|-----------|-----|
| `intuitlib` not available | Python 3.9 / arm64 incompatibility | Rewrote QB OAuth with raw `httpx` |
| Classy auth → 405 | Used `auth_code` redirect flow; Classy requires `client_credentials` POST | Rewrote to client_credentials |
| `invalid_client` on Classy token | Secret had literal `<zbOh6LiPifBpldEe>` angle brackets from doc convention | Stripped `<>` from `.env` |
| `str \| None` type annotation → SyntaxError | Python 3.9 doesn't support union syntax (PEP 604); needs 3.10+ | Removed return annotation |
| Campaign 470798 shows as `needs_mapping` | `_load_mapping()` iterated top-level keys; file had `{"_meta":{}, "campaigns":{}}` nesting | Added `raw.get("campaigns", raw)` |
| Campaign totals cache stale | Old format was `{cid: float}`; new format is `{cid: {"total_gross", "txn_count"}}` | Added `isinstance(sample, dict)` format check + force refresh |
| CORS blocking Vite | `allow_origins=["localhost:5173"]`; Vite picked port 5176 | Changed to `allow_origin_regex=r"http://localhost:\d+"` |
| uvicorn port 8000 in use | Previous process not killed | `lsof -ti :8000 \| xargs kill -9` |
| Vite proxy URL with `?` failing in shell | Unquoted `?` is a shell glob | Quoted all test URLs in curl commands |
| Campaign 396456 in unmapped queue | Had $0 gross; all fields genuinely $0 (free event) | Added `gross > 0` filter to unmapped and transaction endpoints |
| `mkdir` failing "File exists" | Directory already existed from earlier attempt | Skipped mkdir |
| `load_dotenv` assertion error in script context | Called without `dotenv_path` | Added explicit path: `load_dotenv(dotenv_path=".env")` |
| `_meta.campaign_count` stale | Was 21; grew to 22 then 23 as campaigns were added | Updated count manually each time |

---

## Successes Log

- Full FastAPI + React scaffold with SSL in one pass
- Both OAuth flows (QB + Classy) working on Python 3.9/arm64 without unavailable packages
- Classy transaction normalization with correct fee math, verified against live data
- Campaign totals scan (3,664 transactions) completing with 1-hour cache
- 23-campaign seed mapping file with correct account/class mapping
- Campaign mapping UI: SelectOrNew pattern, atomic file writes, live removal on save
- Full transaction table: 11 columns, live filtering, sortable, summary bar updating
- Tab navigation between Transactions and Campaign Mapping views
- QBO CSV exporter: multi-line Sales Receipts, fee deduction lines, recon validation, NEEDS_REVIEW flag, UTF-8 BOM for Excel
- Export report UI inline before download — shows failures before anything touches QBO

---

## What's Not Done Yet

- `PLATFORM_FEE_ACCOUNT` and `PROCESSING_FEE_ACCOUNT` constants not yet filled in
- QBO CSV column format not yet verified against actual QBO sandbox import template
- QuickBooks OAuth used but no actual QB data reads/writes implemented yet (intentional — file-only scope)
- No authentication on the web app (runs locally only)
- Transaction cache doesn't invalidate when new mapping is saved (1-hour TTL is acceptable for now)
- `donor_selects` rows export with blank `qbo_class` — Marcus needs to assign class at import time

---

## Files Created / Modified This Session

```
reserva-reconciler/
  backend/
    main.py                          ← all FastAPI routes
    auth/
      quickbooks_oauth.py            ← QB OAuth (httpx, no intuitlib)
      classy_oauth.py                ← Classy client_credentials
    connectors/
      classy.py                      ← fetchers + 1-hour caches
      normalize.py                   ← canonical normalization + fee math
    exporters/
      __init__.py
      sales_receipt_csv.py           ← QBO CSV generator + validation report
    data/
      campaign_mapping.json          ← 23-campaign seed (hand-maintained)
    tokens/                          ← gitignored; runtime token + cache files
  frontend/
    vite.config.js                   ← proxy config (mapping/auth/classy/health/export)
    src/
      index.css                      ← earth-tone design system
      App.jsx                        ← tab nav (Transactions | Campaign Mapping)
      MappingPanel.jsx               ← unmapped campaign list
      CampaignRow.jsx                ← per-row with SelectOrNew dropdowns
      TransactionTable.jsx           ← main CEO/bookkeeper view + export UI
```
