"""
QuickBooks Online Journal Entry CSV exporter — FORWARD-ONLY, per-month.

Usage: pass a single target month ("YYYY-MM"). Only transactions for that month
are included (gross > 0, mapping_status == "mapped").

Structure per JE:
  DEBIT  Classy Pay Clearing Account   sum(net)            [one line per processor present]
  DEBIT  Service Fee                   sum(platform_fee)   [one per (processor, campaign_id, designation_id)]
  DEBIT  Payment Processing Fee        sum(processing_fee) [one per (processor, campaign_id, designation_id)]
  CREDIT (qbo_account)                 sum(gross)          [one per (qbo_account, qbo_class), with Class]

Descriptions:
  Clearing: "{Mon YYYY} Total - {Processor} - NET"
  Fee:      "{Mon YYYY} {Processor} - Campaign {campaign_id} / Designation ID {designation_id}"
  Credit:   "{Mon YYYY} Donations"

JournalDate = last calendar day of the month (MM/DD/YYYY).

Callie's invariants enforced here:
  1. PayPalCommerce is handled in normalize.py (_PROCESSOR_MAP). This exporter
     only sees resolved processor names ("Stripe", "PayPal").
  2. CLEARING ZERO-OUT: sum(clearing debits) must equal sum(net_amount for all
     included transactions). Fails loudly if there's a gap > $0.01.
  3. UNKNOWN PROCESSOR = HARD ERROR: any mapped, non-$0, non-offline,
     non-null-gateway transaction whose processor is not in KNOWN_PROCESSORS
     raises ValueError. Do not emit a JE with a dropped payout processor.
  4. MONTH WITHHOLD: if any campaign has a needs_mapping transaction in the
     target month, the entire JE is withheld (raises ValueError listing blockers).

Import via: QBO → Import Data → Journal Entries. DO NOT import without reviewing report first.
"""

import csv
import io
import logging
from calendar import monthrange
from collections import defaultdict
from datetime import date

from exporters.sales_receipt_csv import CLASS_NORMALIZATION, KNOWN_GOOD_QB_CLASSES

logger = logging.getLogger(__name__)

CLEARING_ACCOUNT    = "Classy Pay Clearing Account"
SERVICE_FEE_ACCOUNT = "Service Fee"
PROCESSING_FEE_ACCT = "Payment Processing Fee"

KNOWN_PROCESSORS = {"Stripe", "PayPal"}

HEADERS = [
    "JournalNo",
    "JournalDate",
    "Account",
    "Debits",
    "Credits",
    "Description",
    "Name",
    "Class",
]

_MONTH_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


def _last_day(year: int, month: int) -> str:
    last = monthrange(year, month)[1]
    return f"{month:02d}/{last:02d}/{year}"


def _flt(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


def _mon_label(year: int, month: int) -> str:
    return f"{_MONTH_ABBR[month - 1]} {year}"


def generate_journal_entry_csv(transactions: list, target_month: str) -> tuple[bytes, dict]:
    """
    Returns (csv_bytes, report).

    target_month: "YYYY-MM" (e.g. "2026-05")

    Raises ValueError for hard errors:
      - Invalid target_month format
      - Any unmapped campaigns in the target month (Rule 4 — month withheld)
      - Any GoFundMe Pro transaction with an unknown processor (Rule 3 — hard error)
      - Clearing zero-out validation failure > $0.01 (Rule 2)

    report keys:
      journal_no          – "JE-YYYYMM"
      je_date             – last day of month (MM/DD/YYYY)
      transactions_count  – transactions included in the JE
      je_gross            – float total gross of included transactions
      balanced            – bool: debits == credits to the penny
      total_debits        – float
      total_credits       – float
      delta               – float (0.00 when balanced)
      cent_adjustment     – float or None
      processor_nets      – {processor: net_sum}
      total_fees          – {service_fee: float, processing_fee: float}
      clearing_validation – {net_sum: float, clearing_sum: float, gap: float, ok: bool}
      excluded            – {
            offline:      {count, total_gross, items: [{id, date, gross}]}
            zero_dollar:  count
            null_gateway: count   # null/empty gateway — not a GoFundMe Pro payout
          }
      unknown_classes     – [str]
      line_count          – CSV data rows written (excl. header)
    """
    try:
        year_str, month_str = target_month.split("-")
        target_year, target_month_num = int(year_str), int(month_str)
        if not (1 <= target_month_num <= 12):
            raise ValueError
    except (ValueError, AttributeError):
        raise ValueError(f"target_month must be 'YYYY-MM', got: {target_month!r}")

    mon_label  = _mon_label(target_year, target_month_num)
    journal_no = f"JE-{target_year}{target_month_num:02d}"
    je_date    = _last_day(target_year, target_month_num)

    # ── RULE 4: MONTH WITHHELD if any campaign in this month is unmapped ─────
    # Check ALL transactions in the target month (not just mapped ones).
    all_month_txns: list[dict] = []
    for t in transactions:
        raw_date = (t.get("transaction_date") or "")[:10]
        try:
            d = date.fromisoformat(raw_date)
        except (ValueError, TypeError):
            continue
        if d.year == target_year and d.month == target_month_num:
            all_month_txns.append(t)

    blocking_campaigns: dict[str, dict] = {}
    for t in all_month_txns:
        if t.get("mapping_status") == "needs_mapping":
            cid   = t.get("campaign_id") or "unknown"
            cname = t.get("campaign_name") or cid
            if cid not in blocking_campaigns:
                blocking_campaigns[cid] = {
                    "campaign_id":   cid,
                    "campaign_name": cname,
                    "txn_count":     0,
                    "gross":         0.0,
                }
            blocking_campaigns[cid]["txn_count"] += 1
            blocking_campaigns[cid]["gross"] = round(
                blocking_campaigns[cid]["gross"] + _flt(t.get("gross_amount")), 2
            )

    if blocking_campaigns:
        camps_sorted = sorted(blocking_campaigns.values(), key=lambda x: -x["gross"])
        lines = "\n".join(
            f"  [{c['campaign_id']}] {c['campaign_name']!r}: "
            f"{c['txn_count']} txn(s), ${c['gross']:.2f} gross"
            for c in camps_sorted
        )
        raise ValueError(
            f"JE {journal_no}: WITHHELD — {len(blocking_campaigns)} unmapped campaign(s) "
            f"in {mon_label}. Map them all before generating the JE.\n"
            f"Blocking campaigns:\n{lines}"
        )

    # ── Collect mapped transactions for the target month ─────────────────────
    month_mapped: list[dict] = [
        t for t in all_month_txns
        if t.get("mapping_status") == "mapped"
    ]

    # ── Bucket every mapped transaction exactly once ──────────────────────────
    #
    # Exclusion tiers (in priority order):
    #   zero_dollar   – gross <= 0 ($0 registrations, voids)
    #   offline       – null/empty gateway + method=="offline"  (booked separately)
    #   null_gateway  – null/empty gateway, non-offline (legacy Classy Pay, no payout)
    #   known_txns    – processor in KNOWN_PROCESSORS → goes in JE
    #   HARD ERROR    – non-empty processor NOT in KNOWN_PROCESSORS
    #
    zero_dollar:    list[dict] = []
    offline:        list[dict] = []
    null_gateway:   list[dict] = []   # no processor → not a GoFundMe Pro payout
    known_txns:     list[dict] = []
    unknown_proc:   list[dict] = []   # → RULE 3: hard error

    for t in month_mapped:
        gross  = _flt(t.get("gross_amount"))
        proc   = t.get("processor", "")          # "" when payment_gateway was null/empty
        method = (t.get("payment_method") or "").lower().strip()

        if gross <= 0:
            zero_dollar.append(t)
        elif not proc and method == "offline":
            offline.append(t)
        elif not proc:
            null_gateway.append(t)              # no payout, correctly excluded
        elif proc in KNOWN_PROCESSORS:
            known_txns.append(t)
        else:
            unknown_proc.append(t)              # HARD ERROR: unknown processor

    # ── RULE 3: Unknown processor = HARD ERROR ───────────────────────────────
    if unknown_proc:
        by_proc: dict[str, list] = defaultdict(list)
        for t in unknown_proc:
            by_proc[t.get("processor", "(empty)")].append(t)

        detail_lines = []
        for proc_name, txns in sorted(by_proc.items()):
            total = round(sum(_flt(t.get("gross_amount")) for t in txns), 2)
            detail_lines.append(
                f"  processor={proc_name!r}: {len(txns)} txn(s), "
                f"${total:.2f} gross, "
                f"ids=[{', '.join(str(t.get('transaction_id','?')) for t in txns[:5])}]"
                + (" …" if len(txns) > 5 else "")
            )

        raise ValueError(
            f"JE {journal_no}: HARD ERROR — {len(unknown_proc)} transaction(s) in "
            f"{mon_label} have a non-empty payment processor that is NOT in the processor "
            f"map. A dropped payout would leave the clearing account non-zero. "
            f"Add the missing processor to _PROCESSOR_MAP in connectors/normalize.py "
            f"and regenerate the cache before exporting.\n"
            + "\n".join(detail_lines)
        )

    offline_gross = round(sum(_flt(t.get("gross_amount")) for t in offline), 2)
    je_gross      = round(sum(_flt(t.get("gross_amount")) for t in known_txns), 2)

    if not known_txns:
        buf = io.StringIO()
        csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n").writerow(HEADERS)
        report = {
            "journal_no": journal_no, "je_date": je_date,
            "transactions_count": 0, "je_gross": 0.0,
            "balanced": True, "total_debits": 0.0, "total_credits": 0.0,
            "delta": 0.0, "cent_adjustment": None, "processor_nets": {},
            "total_fees": {"service_fee": 0.0, "processing_fee": 0.0},
            "clearing_validation": {"net_sum": 0.0, "clearing_sum": 0.0, "gap": 0.0, "ok": True},
            "excluded": {
                "offline":      {"count": len(offline), "total_gross": offline_gross,
                                 "items": [_offline_item(t) for t in offline]},
                "zero_dollar":  len(zero_dollar),
                "null_gateway": len(null_gateway),
            },
            "unknown_classes": [], "line_count": 0,
            "warning": f"No Stripe/PayPal mapped transactions found for {target_month}",
        }
        _print_validation_empty(journal_no, mon_label, report)
        return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8"), report

    # 1. Clearing lines — sum(net) per processor
    clearing: dict[str, float] = defaultdict(float)
    for t in known_txns:
        p = t["processor"]
        clearing[p] = round(clearing[p] + _flt(t.get("net_amount")), 2)

    # ── RULE 2: Clearing zero-out invariant ──────────────────────────────────
    # sum(clearing debits) MUST equal sum(net_amount of all included transactions).
    # Floating-point rounding at intermediate steps can create tiny differences;
    # a gap > $0.01 indicates a real accounting error.
    net_sum      = round(sum(_flt(t.get("net_amount")) for t in known_txns), 2)
    clearing_sum = round(sum(clearing.values()), 2)
    clearing_gap = round(clearing_sum - net_sum, 2)
    clearing_ok  = abs(clearing_gap) <= 0.01

    if not clearing_ok:
        raise ValueError(
            f"JE {journal_no}: CLEARING ZERO-OUT FAILED — "
            f"clearing debits ${clearing_sum:.2f} ≠ sum of transaction nets ${net_sum:.2f} "
            f"(gap ${clearing_gap:+.2f}). This JE would leave the clearing account "
            f"non-zero. Do not import. Investigate the gap before retrying."
        )

    clearing_validation = {
        "net_sum":      net_sum,
        "clearing_sum": clearing_sum,
        "gap":          clearing_gap,
        "ok":           clearing_ok,
    }

    # 2. Fee lines — per (processor, campaign_id, designation_id)
    svc_lines:  dict[tuple, float] = defaultdict(float)
    proc_lines: dict[tuple, float] = defaultdict(float)
    for t in known_txns:
        key = (t.get("processor", ""), t.get("campaign_id", ""), t.get("designation_id", ""))
        svc_lines[key]  = round(svc_lines[key]  + _flt(t.get("platform_fee")),   2)
        proc_lines[key] = round(proc_lines[key] + _flt(t.get("processing_fee")), 2)

    # 3. Credit lines — per (qbo_account, qbo_class), sum(gross)
    unknown_classes: list[str] = []
    credit_map: dict[tuple, float] = defaultdict(float)
    for t in known_txns:
        acct = t.get("qbo_account") or ""
        cls  = CLASS_NORMALIZATION.get(
            (t.get("qbo_class") or "").strip(),
            (t.get("qbo_class") or "").strip(),
        )
        if cls and cls not in KNOWN_GOOD_QB_CLASSES:
            if cls not in unknown_classes:
                unknown_classes.append(cls)
            logger.warning("JE %s: class %r not in KNOWN_GOOD_QB_CLASSES", journal_no, cls)
        credit_map[(acct, cls)] = round(
            credit_map[(acct, cls)] + _flt(t.get("gross_amount")), 2
        )

    # Compute totals
    total_clearing = round(sum(clearing.values()), 2)
    total_svc_fee  = round(sum(svc_lines.values()),  2)
    total_proc_fee = round(sum(proc_lines.values()),  2)
    total_debits   = round(total_clearing + total_svc_fee + total_proc_fee, 2)
    total_credits  = round(sum(credit_map.values()), 2)
    delta          = round(total_debits - total_credits, 2)

    # Cent adjustment: if imbalance <= $0.01, nudge the largest credit line
    cent_adjustment = None
    if delta != 0.0:
        if abs(delta) <= 0.01:
            largest = max(credit_map, key=credit_map.__getitem__)
            credit_map[largest] = round(credit_map[largest] + delta, 2)
            cent_adjustment = delta
            total_credits   = round(sum(credit_map.values()), 2)
            delta           = round(total_debits - total_credits, 2)
        else:
            logger.error(
                "JE %s: imbalance $%.4f exceeds cent threshold — REVIEW REQUIRED "
                "(debits=%.2f credits=%.2f)",
                journal_no, delta, total_debits, total_credits,
            )

    balanced = abs(delta) < 0.005

    # Write CSV
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(HEADERS)
    line_count = 0

    def row(account, debit, credit, description, cls=""):
        nonlocal line_count
        writer.writerow([
            journal_no, je_date, account,
            f"{debit:.2f}" if debit else "",
            f"{credit:.2f}" if credit else "",
            description, "", cls,
        ])
        line_count += 1

    # Clearing debit lines
    for proc in sorted(clearing):
        amt = clearing[proc]
        if amt:
            row(CLEARING_ACCOUNT, amt, 0, f"{mon_label} Total - {proc} - NET")

    # Service Fee debit lines
    for key in sorted(svc_lines):
        proc, camp_id, desig_id = key
        amt = svc_lines[key]
        if amt:
            row(SERVICE_FEE_ACCOUNT, amt, 0,
                f"{mon_label} {proc} - Campaign {camp_id} / Designation ID {desig_id}")

    # Payment Processing Fee debit lines
    for key in sorted(proc_lines):
        proc, camp_id, desig_id = key
        amt = proc_lines[key]
        if amt:
            row(PROCESSING_FEE_ACCT, amt, 0,
                f"{mon_label} {proc} - Campaign {camp_id} / Designation ID {desig_id}")

    # Credit (income) lines
    credit_desc = f"{mon_label} Donations"
    for (acct, cls) in sorted(credit_map):
        amt = credit_map[(acct, cls)]
        if amt:
            row(acct, 0, amt, credit_desc, cls)

    report = {
        "journal_no":         journal_no,
        "je_date":            je_date,
        "transactions_count": len(known_txns),
        "je_gross":           je_gross,
        "balanced":           balanced,
        "total_debits":       total_debits,
        "total_credits":      total_credits,
        "delta":              delta,
        "cent_adjustment":    cent_adjustment,
        "processor_nets":     dict(clearing),
        "total_fees": {
            "service_fee":    total_svc_fee,
            "processing_fee": total_proc_fee,
        },
        "clearing_validation": clearing_validation,
        "excluded": {
            "offline":      {"count": len(offline), "total_gross": offline_gross,
                             "items": [_offline_item(t) for t in offline]},
            "zero_dollar":  len(zero_dollar),
            "null_gateway": len(null_gateway),
        },
        "unknown_classes":    sorted(unknown_classes),
        "line_count":         line_count,
    }

    _print_validation(report, clearing, total_clearing, total_svc_fee, total_proc_fee,
                      clearing_validation)
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8"), report


def _offline_item(t: dict) -> dict:
    return {
        "transaction_id": t.get("transaction_id"),
        "date":           (t.get("transaction_date") or "")[:10],
        "gross_amount":   _flt(t.get("gross_amount")),
        "payment_method": t.get("payment_method"),
    }


def _print_validation(report: dict, clearing: dict, total_clearing: float,
                      total_svc_fee: float, total_proc_fee: float,
                      clearing_validation: dict):
    sep = "=" * 66
    excl      = report["excluded"]
    n_offline = excl["offline"]["count"]
    g_offline = excl["offline"]["total_gross"]
    n_zero    = excl["zero_dollar"]
    n_null    = excl["null_gateway"]
    cv        = clearing_validation

    print(f"\n{sep}")
    print(f"JE VALIDATION — {report['journal_no']}  ({_mon_label_from_no(report['journal_no'])})")
    print(sep)

    print(f"  JE includes {report['transactions_count']} transactions "
          f"(${report['je_gross']:.2f}).")
    print(f"  Excluded: {n_offline} offline (${g_offline:.2f}, booked separately), "
          f"{n_zero} zero-dollar, "
          f"{n_null} null-gateway (legacy/no-payout).")

    if n_offline:
        print(f"\n  Offline donations excluded (handled separately by bookkeeper):")
        for item in excl["offline"]["items"]:
            print(f"    txn {item['transaction_id']}  {item['date']}  "
                  f"${item['gross_amount']:.2f}  method={item['payment_method']!r}")

    if report["transactions_count"]:
        print(f"\n  Per-processor NET subtotals:")
        for proc in sorted(clearing):
            print(f"    {proc:<8}  ${clearing[proc]:.2f}")

        # Rule 2: Clearing zero-out result
        cv_ok = "✓ PASS" if cv["ok"] else "✗ FAIL"
        print(f"\n  Clearing zero-out check ({cv_ok}):")
        print(f"    sum(clearing debits) = ${cv['clearing_sum']:.2f}")
        print(f"    sum(txn net_amounts) = ${cv['net_sum']:.2f}")
        if cv["gap"] != 0.0:
            print(f"    gap                 = ${cv['gap']:+.4f}")

        print(f"\n  Total gross   = ${report['total_credits']:.2f}")
        print(f"  Total debits  = ${report['total_debits']:.2f}")
        print(f"    Clearing    = ${total_clearing:.2f}")
        print(f"    Service fee = ${total_svc_fee:.2f}")
        print(f"    Proc fee    = ${total_proc_fee:.2f}")

        bal_str = "BALANCED ✓" if report["balanced"] else f"IMBALANCED ✗  delta=${report['delta']:.4f}"
        print(f"\n  Balance check : {bal_str}")
        if report["cent_adjustment"] is not None:
            print(f"  Cent adj applied: ${report['cent_adjustment']:.4f} on largest credit line")

    if report["unknown_classes"]:
        print(f"\n  *** UNKNOWN QB CLASSES — REVIEW BEFORE IMPORT ***")
        for cls in sorted(report["unknown_classes"]):
            print(f"    {cls!r}")

    print(sep + "\n")


def _print_validation_empty(journal_no: str, mon_label: str, report: dict):
    excl = report["excluded"]
    sep  = "=" * 66
    print(f"\n{sep}")
    print(f"JE VALIDATION — {journal_no}  ({mon_label})")
    print(sep)
    print(f"  JE includes 0 transactions ($0.00).")
    print(f"  Excluded: {excl['offline']['count']} offline "
          f"(${excl['offline']['total_gross']:.2f}, booked separately), "
          f"{excl['zero_dollar']} zero-dollar, "
          f"{excl['null_gateway']} null-gateway.")
    print(f"  WARNING: {report['warning']}")
    print(sep + "\n")


def _mon_label_from_no(journal_no: str) -> str:
    """'JE-202605' → 'May 2026'"""
    try:
        year  = int(journal_no[3:7])
        month = int(journal_no[7:9])
        return _mon_label(year, month)
    except (ValueError, IndexError):
        return journal_no
