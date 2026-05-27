# Reserva Reconciler — Donor CRM
**Org:** Reserva: The Youth Land Trust  
**Stack:** FastAPI (Python 3.9) + React/Vite + QuickBooks Online + Classy (GoFundMe Pro)  
**Status:** Deployed to GitHub Pages — backend runs locally or via tunnel

---

## What This Is

A donor CRM and accounting reconciler for Reserva YLT. The org collects donations through Classy (GoFundMe Pro) and books them in QuickBooks Online. Before this tool, reconciliation was manual — exporting a Classy CSV and hand-matching it to QBO entries, a process prone to missed transactions and mislabeled payment processors.

This tool pulls all Classy transactions via API, normalizes them, maps each campaign to the correct QBO account and class, and generates a QBO-importable monthly Journal Entry CSV. No QB API writes. Read-only Classy data. File-only export. One month at a time.

---

## Project 3 Accountability Questions

These questions come from the AI 201 design accountability framework. The answers below are written in the first person because these are my answers, not a template.

---

### Can I defend this?
*Can you explain every design decision by pointing back to your research and your person's needs?*

Yes, and the defense is specific.

**Callie** (Reserva's bookkeeper) is my person. Every structural decision in the JE exporter traces back either to a conversation with her or to direct inspection of Reserva's live data.

- **Three-bucket exclusion logic** (offline / zero-dollar / null-gateway) — Callie confirmed that offline donations are booked manually by the bookkeeper and must not appear in the clearing-account JE. The $0 rows are free event registrations, not donations — I confirmed this by pulling the raw Classy JSON and seeing all fee fields were genuinely $0. They get filtered before they can create noise.

- **PayPalCommerce as a second payout rail** — I discovered this by auditing all 3,745 transactions' `payment_gateway` field in session 3. Classy's GoFundMe Pro integration routes some donations through PayPal Commerce, not Stripe. Before the fix, these 212 transactions ($15,042.08) were silently excluded from the JE. Callie confirmed in session 4 that PayPal Commerce donations settle to the same PayPal payout account and must be included.

- **Month withhold on unmapped campaigns** — Callie's explicit rule: if any campaign in a target month hasn't been mapped to a QBO account and class, withhold the entire month's JE rather than emit a partial one. A partial JE would leave the clearing account unbalanced in a way that's harder to find and fix than just waiting.

- **Clearing zero-out invariant** — The clearing account is zero-sum: every debit that hits "Classy Pay Clearing Account" must be matched by a deposit from the payment processor. The validation check (`sum(clearing debits) == sum(net_amount for all included transactions)`) enforces this before the file is written, not after it's imported.

- **Hard error on unknown processor** — Callie's specific instruction. Silently dropping an unknown processor leaves the clearing account non-zero in a way that isn't immediately visible in QBO. The system refuses to emit a JE rather than emit one that won't zero out.

The one thing I can't fully defend yet: the QB import format (specifically the `*LineAccount` column in the Sales Receipt CSV) hasn't been verified against a live QBO sandbox. That's documented as an open item.

---

### Is this mine?
*Did you direct AI based on your Design Argument, or did you accept AI's suggestions because they looked good?*

The design decisions are mine. The implementation was AI-assisted.

I came to each session with a specific problem to solve, grounded in either Callie's accounting workflow or data I'd already inspected. The session logs show this: in session 1, I brought the Classy OAuth credential error (angle brackets in the secret value) to Claude after I'd already observed the `invalid_client` response. In session 3, I brought the PayPalCommerce discovery — 212 transactions silently falling into `legacy_unknown` — after I'd already audited the payment gateway distribution myself. In session 4, I brought Callie's five confirmed rules with specific behaviors attached to each.

Where I accepted AI suggestions rather than directing: the initial FastAPI + Vite scaffold structure, and the cent-adjustment logic on the largest credit line when the JE is off by a fraction of a cent. I accepted the scaffold because the technical stack was a pragmatic choice (not a design argument), and I accepted the cent-adjustment because it matched how bookkeepers actually handle floating-point rounding in practice — which I verified makes sense.

What I didn't do: I didn't look at an AI-generated UI and say "that looks good" and ship it. The frontend exists purely as an operational tool for me and Callie to use. It has no visual design argument because it doesn't need one — it needs to be readable and functional.

---

### Did I verify?
*Does the product actually work the way your person needs it to? Did you test with them, not just in your browser?*

Partially yes, with a specific gap.

**Verified with real data:** Every rule in the JE exporter was validated against Reserva's live Classy transactions — not mock data, not a sandbox. The April and May 2026 JE runs both produced balanced entries ($1,050.28 and $2,997.32 respectively) with confirmed processor splits and a clearing gap of $0.00. The PayPalCommerce transactions were verified by pulling their raw JSON directly from the Classy API and confirming the `pp_reference_id` and `agreementId` fields are real PayPal Billing Agreement IDs.

**Verified with Callie:** The exclusion rules (offline donations, month withhold, hard error on unknown processor) came from Callie's explicit direction in session 4. She confirmed how each category should be treated.

**Not yet verified with Callie:** The generated CSV file has not yet been imported into a live or sandbox QBO environment and confirmed to post correctly. The column names (`*LineAccount`, `*Class`, etc.) are based on the QBO import template documentation, but the actual sandbox test hasn't happened. This is the most significant open item.

---

### Would I teach this?
*Could you explain the system architecture, the research process, and the design rationale to another designer?*

Yes. Here's the short version I would use:

**Architecture:** The backend is a FastAPI server with two read-only API integrations (Classy for transactions, QuickBooks for OAuth only — no writes). It normalizes raw Classy transaction JSON into a canonical format that separates platform fee, processor fee, and net for each transaction. A campaign mapping file links Classy campaign IDs to QBO account names and class names. The JE exporter groups mapped transactions by processor and campaign, builds the debit/credit structure, validates balance, and writes a CSV.

**Research process:** The design started from Callie's existing workflow — a manual Classy export matched to QBO entries. Every structural choice was an answer to a specific failure mode in that manual process: missed payment processors (PayPalCommerce), mislabeled transactions (offline vs. online), and partial-month imports that leave clearing accounts unbalanced.

**Design rationale:** The tool is built to fail loudly rather than silently. An unknown processor stops the export entirely. An unmapped campaign withholds the whole month. A clearing imbalance above a penny raises an error. This is intentional — the cost of a bad JE import is harder to fix than the cost of a failed export.

---

### Is my disclosure honest?
*Does your AI Direction Log accurately reflect what happened? When you're presenting a case study with real evidence, fabrication is not just academic dishonesty — it's professional fraud.*

Yes, and the session logs exist as the primary record.

Four session logs are in `/session-logs/` and cover every working session from initial scaffold to the final accounting rules. They document the resistance points (OAuth credential bugs, Python 3.9 type annotation incompatibilities, wrong cache formats, the PayPalCommerce discovery), the riffs (pivoting from `auth_code` to `client_credentials` when the Classy endpoint returned 405), and the decisions that were deferred vs. shipped.

The AI Direction Log accurately reflects that I directed the work based on Callie's needs and real data inspection, and that Claude handled implementation — writing the Python, the React components, and the GitHub Actions workflow. I wrote none of the code myself. What I did write: the problem definition, the data audit, the accounting rules, and the validation criteria for each.

The one thing I want to be precise about: the session logs were written *by Claude* as a record of the session, not by me after the fact. They're accurate but they're not written in my voice. The answers in this README are.

---

## System Architecture

```
Classy API (read-only)
    ↓ OAuth2 client_credentials
    ↓ /organizations/83147/transactions (paginated, 100/page)
    ↓
connectors/normalize.py
    → _PROCESSOR_MAP: Stripe / PayPal / PayPalCommerce / legacy-Classy-Pay
    → campaign_mapping.json: campaign_id → {qbo_account, qbo_class}
    → designation lookup for donor-selects campaigns
    → canonical fields: gross, platform_fee, processing_fee, net
    ↓
exporters/journal_entry_csv.py
    → Rule 3: unknown processor → hard error (no silent drops)
    → Rule 4: unmapped campaign in month → withhold entire JE
    → clearing debits: one line per processor, sum(net)
    → fee debits: one line per (processor, campaign_id, designation_id)
    → income credits: one line per (qbo_account, qbo_class)
    → Rule 2: clearing zero-out validation (gap must be ≤ $0.01)
    → balance check: debits == credits (cent-adjust if needed)
    → output: QBO Journal Entry CSV, UTF-8 BOM
    ↓
QBO → Import Data → Journal Entries
    (manual review required before import)
```

---

## Open Items

- **QBO sandbox import test** — the SR and JE CSV column names need verification against a live QBO sandbox before the first real import
- **PayPal payout reconciliation** — the $14,334 PayPal net in the JE needs to be cross-checked against the actual PayPal payout statement
- **Mobile access** — currently requires a running backend; GitHub Pages deployment works with an ngrok tunnel for remote access

---

## Sessions

| Session | Date | What Was Built |
|---|---|---|
| 1 | 2026-05-22–23 | FastAPI + React scaffold, QB OAuth, Classy OAuth, normalization layer, campaign mapping |
| 2 | 2026-05-23–24 | Sales Receipt CSV exporter, campaign mapping UI, designation lookup, donor CRM view |
| 3 | 2026-05-26–27 | JE exporter (forward-only, per-month), three-bucket exclusion logic, PayPalCommerce audit |
| 4 | 2026-05-27 | Callie's 5 accounting rules, PayPalCommerce fix, clearing zero-out validation, GitHub Pages |
