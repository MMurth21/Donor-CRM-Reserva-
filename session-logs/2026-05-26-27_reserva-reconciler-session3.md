# Reserva Reconciler — Session 3
**Date:** 2026-05-26 → 2026-05-27  
**Operator:** Milind Murthy

---

## Work Completed

### 1. JE exporter rebuilt as forward-only, single-month

Full rewrite of `backend/exporters/journal_entry_csv.py`. The old exporter generated all 53 historical months at once; the new one takes a required `?month=YYYY-MM` parameter and exports only that month.

**Structure per JE:**
| Row type | Account | Side |
|---|---|---|
| Clearing | Classy Pay Clearing Account | DEBIT — one line per processor present |
| Service Fee | Service Fee | DEBIT — one per (processor, campaign_id, designation_id) |
| Proc Fee | Payment Processing Fee | DEBIT — one per (processor, campaign_id, designation_id) |
| Income | qbo_account | CREDIT — one per (qbo_account, qbo_class), with Class |

**Description format:**
- Clearing: `"May 2026 Total - Stripe - NET"`
- Fee lines: `"May 2026 Stripe - Campaign 470798 / Designation ID 177011"`
- Credits: `"May 2026 Donations"`

**Replaced** stale `EXPECTED_TOTALS` dict with a self-consistency balance check (debits == credits to the penny, with ≤$0.01 cent-adjustment on largest credit line if needed).

---

### 2. Three-bucket exclusion logic

Every mapped transaction in the target month is classified into exactly one bucket before the JE is built:

| Bucket | Criteria | In JE? | Validation output |
|---|---|---|---|
| `known_txns` | processor ∈ {Stripe, PayPal} | ✓ | Counted in JE gross |
| `offline` | processor="" AND payment_method="Offline" | ✗ | "Offline donations excluded (handled separately by bookkeeper)" — count + total gross |
| `zero_dollar` | gross ≤ 0 | ✗ | Shown as a count only, no alarm |
| `legacy_unknown` | anything else | ✗ | "LEGACY/UNKNOWN PROCESSORS — INVESTIGATE" with per-transaction detail |

Validation headline: `"JE includes N transactions ($X). Excluded: M offline ($Y, booked separately), P zero-dollar, Q unknown (investigate if >0)."`

A clean month shows Q = 0. A month with `PayPalCommerce` transactions shows Q > 0 as the signal to add it to `_PROCESSOR_MAP`.

---

### 3. normalize.py — three new fields

Added to every normalized transaction output:

| Field | Source | Purpose |
|---|---|---|
| `processor` | `payment_gateway` → `_PROCESSOR_MAP` | "Stripe" / "PayPal" / raw-value-if-unknown |
| `designation_id` | `tx["designation_id"]` pass-through | Fee line grouping key in JE |
| `payment_method` | `tx["payment_method"]` pass-through | Distinguishes offline gifts (null gateway) from other null-gateway rows |

`_PROCESSOR_MAP` normalises case variants: `stripe/stripe_ach → "Stripe"`, `paypal/paypal_ec/paypal_rest → "PayPal"`.

---

### 4. main.py — endpoint and cache updates

- **JE endpoints** now require `?month=YYYY-MM`; return HTTP 422 if missing or malformed.
- **`_cache_schema_valid()`** checks that the cached transactions have `processor`, `designation_id`, and `payment_method`. Stale cache (missing any of these) is automatically re-fetched on the next API call — no manual deletion required.

---

### 5. Read-only probes (no code changes)

**`payment_gateway` audit — all 3,736 transactions:**

| Value | Count | Mapping |
|---|---|---|
| Stripe | 2,194 | → Stripe ✓ |
| (none/null) | 1,229 | offline gifts (434 gross>0) + zero-dollar tickets (795) |
| PayPalCommerce | 212 | PayPal's modern REST gateway — NOT yet in `_PROCESSOR_MAP` |
| Classy Pay | 101 | Legacy processor, zero in recent months |

**April 2026 (most recent full month):** 30 Stripe, 4 PayPalCommerce (legacy_unknown), 1 offline ($25,000 gift).

**`PayPalCommerce` decision pending:** Adding `"paypalcommerce": "PayPal"` to `_PROCESSOR_MAP` will move those 4 April transactions from `legacy_unknown` into the JE. Deferred to next session.

**Offline donation breakdown:**
- 434 transactions, gross > 0, total $525,857.64 all-time. All `payment_method="Offline"`, `fees=0`, `net=gross`.
- Option A chosen: exclude from JE, report clearly, bookkeeper handles separately.
- 795 zero-gross rows are free-ticket registrations (payment_method="Classy Pay"). Already excluded by gross>0 filter, not reported as issues.

**Recurring donation plans:**
- `/organizations/83147/recurring-donation-plans` returns 200 — 50 active plans.
- All Stripe, all monthly. Fields present: `campaign_id`, `designation_id`, `donation_amount`, `frequency`, `status`, `next_processing_date`, `schedule` (12-entry array of charge days).
- Individual transactions carry `recurring_donation_plan_id` linking back to the plan.
- **No JE change needed**: recurring charges already surface in the transactions endpoint as normal `status='success'` rows and are picked up by the monthly filter automatically.
- Plan endpoint enables forward-looking cash flow projections — not implemented this session.

---

## Open Items (updated)

- **`PayPalCommerce` → `_PROCESSOR_MAP`**: add `"paypalcommerce": "PayPal"` to fix 4 April transactions being flagged as legacy_unknown. Low risk, one-line change.
- **QB import format**: SR CSV `*LineAccount` still unverified with accountant — test in QBO sandbox before first import.
- **CLASS_NORMALIZATION shim**: 4 entries for Callie to fix in Classy `external_reference_id`, then remove.
- **QB OAuth token**: expired 2026-05-24 — re-auth needed before any QB write operations.
- **First live JE run**: `DELETE backend/tokens/transactions_cache.json` (or just hit any export endpoint — cache auto-busts on schema mismatch), then `GET /export/journal-entries/report?month=2026-05` to review before downloading.
