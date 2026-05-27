# Reserva Reconciler — Session 2
**Date:** 2026-05-23 → 2026-05-24  
**Operator:** Milind Murthy

---

## Work Completed

### 1. Fee account names configured
- Set `PLATFORM_FEE_ACCOUNT = "Service Fee"` and `PROCESSING_FEE_ACCOUNT = "Payment Processing Fee"` in `backend/exporters/sales_receipt_csv.py` (previously placeholders).

### 2. Sales Receipt CSV generated (first clean run)
- 2,903 receipts, $0 skipped, 0 recon failures.
- Gross $650,911.98 | Platform fees $2,211.01 | Processing fees $3,507.13 | Net $645,193.84.

### 3. Date bug investigated — confirmed non-issue
- User reported `*SalesReceiptDate` might be set to today's date. Investigation confirmed the code was correct: `_fmt_date` slices `purchased_at` to `YYYY-MM-DD`. Dates spanned 01/08/2022 → 05/23/2026 across 950 unique days.

### 4. Designation data probed for donor_selects campaigns
- Confirmed `designation_id` is a top-level field on every Classy transaction.
- Campaign 470798 has 4 distinct designation IDs: 177011, 177017, 177018, 177019.
- Pulled full org-level designations list (11 designations for org 83147).
- All 4 designation IDs used in NEEDS_REVIEW transactions have non-empty `external_reference_id` → 100% auto-resolvable.

### 5. Designation → class resolution wired (normalize.py)
- **`classy.py`**: replaced individual `fetch_designation()` (in-memory) with `fetch_org_designations()` — fetches all org designations, file-caches to `tokens/designations_cache.json` with 1-hour TTL.
- **`normalize.py`**: `donor_selects` branch now resolves `qbo_class` from `designation_id → designations cache → external_reference_id`. `mapping_status` set to `"mapped"` when resolved, `"needs_mapping"` if blank. `qbo_account` still comes from campaign_mapping.
- Result: 619 previously-NEEDS_REVIEW transactions resolved. `unmapped_count: 0` across all 2,903 transactions.

### 6. Class name corrections in campaign_mapping.json
Fixed three typos/inconsistencies in `qbo_class` values:
| Before | After |
|---|---|
| `Conservation: Dracula Reserve` (space) | `Conservation:Dracula Reserve` |
| `Adalbra` | `Aldabra` → then corrected again to `Conservation:Friends of Aldabra` |
| `Conservation:Community Projects` | `Conservation:DYR Community Projects` |

### 7. CLASS_NORMALIZATION shim added to sales_receipt_csv.py (TEMPORARY)
Corrects typos in Classy's `external_reference_id` values until Callie fixes them at source:
```python
CLASS_NORMALIZATION = {
    "Conservation: Dracula Reserve":   "Conservation:Dracula Reserve",
    "Aldabra":                         "Conservation:Friends of Aldabra",
    "Conservation:Community Projects": "Conservation:DYR Community Projects",
    "Conservation:Columbia":           "Conservation:Colombia",
}
```
- `KNOWN_GOOD_QB_CLASSES` set added; any class not in the list logs a WARNING at export time.
- JE exporter imports this dict directly from `sales_receipt_csv.py` — single source of truth.

### 8. Journal Entry CSV exporter built
- New file: `backend/exporters/journal_entry_csv.py`
- Groups transactions by calendar month. Per JE:
  - DEBIT Undeposited Funds = sum(net_amount)
  - DEBIT Service Fee = sum(platform_fee)
  - DEBIT Payment Processing Fee = sum(processing_fee)
  - CREDIT one line per (qbo_account, qbo_class) = sum(gross_amount)
- JournalDate = last day of month (MM/DD/YYYY).
- Cent-adjustment logic: if JE off by ≤$0.01, adjusts largest credit line; logs adjustment.
- Endpoints added to main.py: `GET /export/journal-entries/report` and `GET /export/journal-entries/download`.
- Result: 53 monthly JEs, 0 balance failures, 0 cent adjustments.

### 9. +543.69 gross discrepancy investigated — confirmed new live donations
- SR CSV (old, May 23 23:05): 2,903 transactions, gross $650,980.94.
- JE export (May 24 13:05): 2,924 transactions, gross $651,524.63.
- Difference: 19 new donations from May 24 morning, dominated by "Run for the Rainforest 2026" (campaign 782016). Sum = $543.69 exactly. All `mapped`, none `needs_mapping`.

### 10. QuickBooks sandbox chart-of-accounts probed
- Completed QB OAuth flow (HTTP mode, realm_id: 9341457143434467).
- Pulled 96 accounts from sandbox.
- `Youth Council Fundraising Campaigns:Classy Fundraising Pages` (Id: 1150040004): Active, AccountType=Income, AccountSubType=DiscountsRefundsGiven, ParentRef=1150040003.
- FQN matches the string in campaign_mapping.json exactly — no hidden characters, clean ASCII.
- Note: `AccountSubType: DiscountsRefundsGiven` is unusual for an income account; may cause issues at QBO import time.

---

## Open Items as of 2026-05-24

- **QB import format unverified**: `*LineAccount` in SR CSV vs `*ProductService` — test in QBO sandbox before live company.
- **`AccountSubType: DiscountsRefundsGiven`** on the Youth Council income accounts — confirm with Marcus/Callie whether this is correct or needs reclassification in QB.
- **CLASS_NORMALIZATION shim** — 4 entries need Callie to fix in Classy's designation `external_reference_id` values, then remove each entry from the shim:
  1. `"Conservation: Dracula Reserve"` (space after colon)
  2. `"Aldabra"` (should be `"Conservation:Friends of Aldabra"`)
  3. `"Conservation:Community Projects"` (should be `"Conservation:DYR Community Projects"`)
  4. `"Conservation:Columbia"` (should be `"Conservation:Colombia"`)
- **Expected control totals in journal_entry_csv.py** are stale (reflect pre-session data). Update or replace with self-consistency check.
- **QB OAuth token** expires at 2026-05-24T19:10:44 UTC — will need re-auth next session.

## Files on Desktop
- `journal_entries_20260524_133435.csv` — latest JE export (53 JEs, 2,924 transactions)

## Key numbers (end of session)
| Metric | Value |
|---|---|
| Total transactions | 2,924 |
| Gross | $651,524.63 |
| Net (Undeposited Funds) | $645,776.11 |
| Platform fees (Service Fee) | $2,223.62 |
| Processing fees | $3,524.90 |
| Monthly JEs | 53 |
| Distinct QB classes used | 9 |
