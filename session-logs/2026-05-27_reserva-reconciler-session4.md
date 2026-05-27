# Reserva Reconciler — Session 4
**Date:** 2026-05-27  
**Operator:** Milind Murthy

---

## Work Completed

### 1. Donor CRM tab — primary view built

New React component `frontend/src/DonorCRM.jsx` (~530 lines). Added as the default landing tab in `App.jsx` (before Transactions and Campaign Mapping). The component groups all normalized transactions into per-donor records client-side and presents them in a dense, expandable table matching the existing earth-tone utilitarian design system.

---

### 2. Donor grouping logic

Transactions are grouped into donor records using a three-tier key hierarchy:

| Priority | Key format | Condition |
|---|---|---|
| 1 | `sid_{supporter_id}` | `member_supporter_id` present in raw transaction |
| 2 | `em_{djb2hash(email)}` | Only email available (hash keeps PII out of URLs) |
| 3 | `unk` | No supporter ID and no email |

The `donorKey()` function enforces this. Email is never placed in a URL, query string, or console log — a compact djb2 hash is used instead (sufficient for an internal tool; not cryptographic).

---

### 3. Per-donor rollup (collapsed row)

Each collapsed donor row shows:
- Donor name (anon-masked if applicable)
- Email, phone, company (all hidden for anonymous donors)
- Total given (sum of gross across all their transactions)
- Gift count
- First gift date, last gift date
- # distinct campaigns (with tooltip listing campaign names)
- Recurring flag (✓ if any transaction has `recurring_donation_plan_id`)
- Tags (chip display)
- Note button (shows "✏ note" if a note exists, "+ note" otherwise)

---

### 4. Expanded transaction detail

Clicking a donor row expands it to show individual transactions sorted newest-first:

| Column | Notes |
|---|---|
| Date | |
| Campaign | |
| Gross | Suppressed (`[hidden]`) if `donation_amount_is_hidden = true` |
| Plat. Fee | Suppressed if amount hidden |
| Proc. Fee | Suppressed if amount hidden |
| Net | Suppressed if amount hidden |
| Class | `qbo_class` |
| Processor | Stripe / PayPal / raw |
| Recurring | ↻ icon if `recurring_donation_plan_id` set |

Donor comments (`donor_comment`) are shown as an italic sub-row beneath each transaction that has one.

---

### 5. Privacy enforcement — render layer

**Hard rules, not filterable:**

- If any transaction for a donor has `is_anonymous = true` OR `is_redacted = true`, the entire donor record is flagged anonymous. This propagates at grouping time, not render time.
- Anonymous donors display as "Anonymous donor" (italic, 🔒 icon). Email, phone, and company are hidden in every view — sorting, filtering, and exporting cannot reveal them.
- `donation_amount_is_hidden = true` suppresses the displayed gross/fees/net for that specific transaction row. The donor-level total is NOT suppressed (to avoid implicitly revealing the amount through subtraction would require suppressing the total too — deferred decision).
- A footer note reminds: "Tags and notes are internal only; they are never shown to or shared with donors."

---

### 6. Donor annotations — tags and notes

Internal annotation system. **Never contacts donors — internal use only.**

**Backend endpoints added to `main.py`:**

| Endpoint | Method | Description |
|---|---|---|
| `/donors/annotations` | GET | Returns all annotations as `{donor_id: {tags, note}}` |
| `/donors/{donor_id}/annotations` | POST | Saves tags + note for one donor |

Annotations stored in `backend/data/donor_annotations.json` (atomic write via tmp-file rename). The `donor_id` path parameter is validated with `r'^[a-zA-Z0-9_-]{1,80}$'` to prevent injection. Tags are deduplicated, stripped, and capped at 40 chars each / 20 tags max.

**Preset tags** (quick-add buttons in the editor):
- Major donor
- Board contact
- Do not list publicly
- Recurring
- Lapsed
- Foundation

Free-text custom tags also supported. Notes capped at 4,000 chars.

Annotations are bulk-loaded once on mount via `GET /donors/annotations` (one round-trip, not per-donor). Saves via POST trigger an optimistic local state update.

---

### 7. Filters and sort

**Sort columns:** Donor name, Total given, Gifts, First gift, Last gift, Campaigns, Recurring  
**Filters:**
- Text search (name / email / campaign) — respects privacy: never searches anonymous donors by name/email
- Tag filter (dropdown, only shows tags that exist in annotations)
- Campaign filter (dropdown of all distinct campaigns across all donors)
- Recurring only (checkbox)
- Show/hide anonymous (checkbox, default: show)
- "Clear filters" button appears when any filter is active

**Summary strip** above the table:
- Total donors (filtered count / total)
- Total raised (all-time gross sum)
- # recurring donors
- # anonymous donors
- # tagged donors (when > 0)

---

### 8. normalize.py — 8 new donor-centric fields

Added to every normalized transaction:

| Field | Classy source field | Purpose |
|---|---|---|
| `donor_supporter_id` | `member_supporter_id` / `supporter_id` | Primary grouping key |
| `is_anonymous` | `is_anonymous` | Privacy flag |
| `is_redacted` | `is_redacted` | Privacy flag |
| `donation_amount_is_hidden` | `donation_amount_is_hidden` | Amount suppression |
| `recurring_donation_plan_id` | `recurring_donation_plan_id` | Recurring detection |
| `donor_phone` | `member_phone` | Contact display |
| `company_name` | `company_name` | Contact display |
| `donor_comment` | `comment` | Donor message shown in expanded detail |

All use `tx.get()` with safe defaults — if a field name is wrong, the value is empty/False (no crash).

---

### 9. Cache auto-invalidation

`_cache_schema_valid()` in `main.py` now requires `donor_supporter_id` and `is_anonymous` in addition to the existing checks. The stale `transactions_cache.json` (missing the new fields) will auto-invalidate and trigger a fresh Classy API fetch on the next request to `/classy/transactions/all`.

---

### 10. Infrastructure changes

| File | Change |
|---|---|
| `frontend/src/App.jsx` | Added `DonorCRM` import; "Donors" tab added first, set as default |
| `frontend/src/index.css` | Root `max-width` widened 960px → 1440px for the wider donor table |
| `frontend/vite.config.js` | Added `/donors` proxy route; changed all proxy targets from `https://` to `http://` (backend was running in plain HTTP mode, causing EPROTO SSL mismatch) |
| `backend/main.py` | `import re`, `import List`; `ANNOTATIONS_FILE` path constant; `_SAFE_DONOR_ID` regex; `_read_annotations()`, `_write_annotations()`, `AnnotationBody`, two new endpoints |

---

## Open Items (updated from session 3)

- **Classy field names unverified** — `donor_supporter_id`, `donor_phone`, `company_name`, `donor_comment`, `is_anonymous`, `is_redacted`, `donation_amount_is_hidden` are best-guess names. If they come back empty when data is expected, inspect a raw transaction via `/classy/transactions/sample` and correct the field name in `normalize.py`, then delete `backend/tokens/transactions_cache.json`.
- **`PayPalCommerce` → `_PROCESSOR_MAP`** (from session 3): add `"paypalcommerce": "PayPal"` — still pending.
- **QB import format** still unverified with accountant — test in QBO sandbox first.
- **CLASS_NORMALIZATION shim** — 4 entries for Callie to fix in Classy `external_reference_id`.
- **QB OAuth token** expired 2026-05-24 — re-auth needed before any QB write operations.
- **`donation_amount_is_hidden` — donor total** — currently the donor-level `total_given` is NOT suppressed even when a transaction has this flag set. Decide: suppress the total too, or leave as-is (current behaviour).
- **Vite proxy protocol** — changed to `http://` this session; if backend is ever restarted with SSL (`--ssl-keyfile`/`--ssl-certfile`), change proxy targets back to `https://` and add `secure: false`.
