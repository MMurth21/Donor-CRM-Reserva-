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
      excluded            – {
            offline:        {count, total_gross, items: [{id, date, gross}]}
            zero_dollar:    count
            legacy_unknown: [{transaction_id, processor, gross_amount}]
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

    # Collect all mapped transactions in target month (any gross)
    month_mapped: list[dict] = []
    for t in transactions:
        if t.get("mapping_status") != "mapped":
            continue
        raw_date = (t.get("transaction_date") or "")[:10]
        try:
            d = date.fromisoformat(raw_date)
        except (ValueError, TypeError):
            logger.warning("Unparseable date for txn %s: %r", t.get("transaction_id"), raw_date)
            continue
        if d.year == target_year and d.month == target_month_num:
            month_mapped.append(t)

    # Bucket every transaction exactly once
    zero_dollar:    list[dict] = []   # gross <= 0 — silently excluded
    offline:        list[dict] = []   # offline gift, no processor — excluded intentionally
    known_txns:     list[dict] = []   # Stripe / PayPal — goes into the JE
    legacy_unknown: list[dict] = []   # non-empty gateway not in _PROCESSOR_MAP — flag loudly

    for t in month_mapped:
        gross  = _flt(t.get("gross_amount"))
        proc   = t.get("processor", "")              # "" when payment_gateway was null/empty
        method = (t.get("payment_method") or "").lower().strip()

        if gross <= 0:
            zero_dollar.append(t)
        elif not proc and method == "offline":
            offline.append(t)
        elif proc in KNOWN_PROCESSORS:
            known_txns.append(t)
        else:
            legacy_unknown.append(t)

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
            "excluded": {
                "offline":        {"count": len(offline), "total_gross": offline_gross,
                                   "items": [_offline_item(t) for t in offline]},
                "zero_dollar":    len(zero_dollar),
                "legacy_unknown": [_unknown_item(t) for t in legacy_unknown],
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
        "excluded": {
            "offline":        {"count": len(offline), "total_gross": offline_gross,
                               "items": [_offline_item(t) for t in offline]},
            "zero_dollar":    len(zero_dollar),
            "legacy_unknown": [_unknown_item(t) for t in legacy_unknown],
        },
        "unknown_classes":    sorted(unknown_classes),
        "line_count":         line_count,
    }

    _print_validation(report, clearing, total_clearing, total_svc_fee, total_proc_fee)
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8"), report


def _offline_item(t: dict) -> dict:
    return {
        "transaction_id": t.get("transaction_id"),
        "date":           (t.get("transaction_date") or "")[:10],
        "gross_amount":   _flt(t.get("gross_amount")),
        "payment_method": t.get("payment_method"),
    }


def _unknown_item(t: dict) -> dict:
    return {
        "transaction_id": t.get("transaction_id"),
        "processor":      t.get("processor"),
        "gross_amount":   _flt(t.get("gross_amount")),
    }


def _print_validation(report: dict, clearing: dict, total_clearing: float,
                      total_svc_fee: float, total_proc_fee: float):
    sep = "=" * 62
    excl      = report["excluded"]
    n_offline = excl["offline"]["count"]
    g_offline = excl["offline"]["total_gross"]
    n_zero    = excl["zero_dollar"]
    n_unknown = len(excl["legacy_unknown"])

    print(f"\n{sep}")
    print(f"JE VALIDATION — {report['journal_no']}  ({_mon_label_from_no(report['journal_no'])})")
    print(sep)

    print(f"  JE includes {report['transactions_count']} transactions "
          f"(${report['je_gross']:.2f}).")
    print(f"  Excluded: {n_offline} offline (${g_offline:.2f}, booked separately), "
          f"{n_zero} zero-dollar, "
          f"{n_unknown} unknown {'(investigate if >0)' if n_unknown == 0 else '— INVESTIGATE'}.")

    if n_offline:
        print(f"\n  Offline donations excluded (handled separately by bookkeeper):")
        for item in excl["offline"]["items"]:
            print(f"    txn {item['transaction_id']}  {item['date']}  "
                  f"${item['gross_amount']:.2f}  method={item['payment_method']!r}")

    if n_unknown:
        print(f"\n  *** LEGACY/UNKNOWN PROCESSORS — INVESTIGATE ({n_unknown}) ***")
        for u in excl["legacy_unknown"]:
            print(f"    txn {u['transaction_id']}  gateway={u['processor']!r}  "
                  f"gross=${u['gross_amount']:.2f}")

    if report["transactions_count"]:
        print(f"\n  Per-processor NET subtotals:")
        for proc in sorted(clearing):
            print(f"    {proc:<8}  ${clearing[proc]:.2f}")

        print(f"\n  Total gross   = ${report['total_credits']:.2f}")
        print(f"  Total debits  = ${report['total_debits']:.2f}")
        print(f"    Clearing    = ${total_clearing:.2f}")
        print(f"    Service fee = ${total_svc_fee:.2f}")
        print(f"    Proc fee    = ${total_proc_fee:.2f}")

        bal_str = "BALANCED" if report["balanced"] else f"IMBALANCED  delta=${report['delta']:.4f}"
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
    sep  = "=" * 62
    print(f"\n{sep}")
    print(f"JE VALIDATION — {journal_no}  ({mon_label})")
    print(sep)
    print(f"  JE includes 0 transactions ($0.00).")
    print(f"  Excluded: {excl['offline']['count']} offline "
          f"(${excl['offline']['total_gross']:.2f}, booked separately), "
          f"{excl['zero_dollar']} zero-dollar, "
          f"{len(excl['legacy_unknown'])} unknown.")
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
