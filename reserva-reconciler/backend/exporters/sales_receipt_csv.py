"""
QuickBooks Online Sales Receipt CSV exporter.

Column format used (account-based, multi-line):
  *SalesReceiptNo | *Customer | *SalesReceiptDate | *DepositTo | Memo
  | NEEDS_REVIEW | *LineAccount | *LineAmount | LineClass | LineDescription

  * = required per QBO convention.

⚠  VERIFY BEFORE FIRST SANDBOX IMPORT:
   QBO's built-in CSV import for Sales Receipts is item-based (*ProductService).
   This file uses account names directly in *LineAccount. Confirm with your QBO
   accountant whether to: (a) use account names as-is via a compatible importer,
   (b) remap *LineAccount → *ProductService using matching QBO items, or
   (c) switch to a Deposit/Journal Entry format.
   Test in your QBO sandbox before touching the live company.
"""

import csv
import io
import logging
from datetime import date

logger = logging.getLogger(__name__)

# ── CONFIGURE THESE BEFORE FIRST IMPORT ──────────────────────────────────────
# Set to the exact account names as they appear in your QuickBooks chart of accounts.
PLATFORM_FEE_ACCOUNT   = "Service Fee"                 # Classy platform cut
PROCESSING_FEE_ACCOUNT = "Payment Processing Fee"      # processor cut
DEPOSIT_TO_ACCOUNT     = "Undeposited Funds"           # standard QBO clearing account
# ─────────────────────────────────────────────────────────────────────────────

# ── TEMPORARY: class-name shim ────────────────────────────────────────────────
# Corrects typos/mismatches in Classy's external_reference_id values while Callie
# fixes them at the source. Remove each entry once the Classy record is updated.
CLASS_NORMALIZATION = {
    "Conservation: Dracula Reserve":   "Conservation:Dracula Reserve",
    "Aldabra":                         "Conservation:Friends of Aldabra",
    "Conservation:Community Projects": "Conservation:DYR Community Projects",
    "Conservation:Columbia":           "Conservation:Colombia",           # typo in Classy ext_ref_id
}

# Known-good QB class list — anything outside this set is logged as a warning.
KNOWN_GOOD_QB_CLASSES = {
    "Conservation",
    "Conservation:Colombia",
    "Conservation:Conservation Match Fund",
    "Conservation:Dracula Reserve",
    "Conservation:DYR Community Projects",
    "Conservation:Friends of Aldabra",
    "Conservation:Pearl Islands",
    "Education",
    "General Administration",
    "Storytelling",
    "Unrestricted Revenue",
}
# ─────────────────────────────────────────────────────────────────────────────

INCOME_LINE_DESC       = "Donation"
PLATFORM_FEE_DESC      = "GoFundMe Pro platform fee"
PROCESSING_FEE_DESC    = "Payment processing fee"

ELIGIBLE_STATUSES = {"mapped", "donor_selects"}

# Column headers — see module docstring for verification notes.
HEADERS = [
    "*SalesReceiptNo",
    "*Customer",
    "*SalesReceiptDate",
    "*DepositTo",
    "Memo",
    "NEEDS_REVIEW",
    "*LineAccount",
    "*LineAmount",
    "LineClass",
    "LineDescription",
]


def _fmt_date(iso_str: str) -> str:
    """ISO timestamp → MM/DD/YYYY (QBO's expected date format)."""
    if not iso_str:
        return ""
    try:
        d = date.fromisoformat(iso_str[:10])
        return f"{d.month:02d}/{d.day:02d}/{d.year}"
    except (ValueError, TypeError):
        return iso_str[:10]


def _flt(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


def generate_sales_receipt_csv(transactions: list) -> tuple[bytes, dict]:
    """
    Returns (csv_bytes, report).

    csv_bytes: UTF-8 with BOM (Excel-safe), QBO Sales Receipt multi-line format.
    report keys:
      written           – receipts included in the file
      skipped_unmapped  – rows excluded (mapping_status == needs_mapping)
      recon_failures    – list of dicts for receipts where gross - fees != net (> $0.01)
      totals            – {gross, platform_fee, processing_fee, net} for written rows
      columns_used      – the header list, so caller can surface it to the user
    """
    eligible = [t for t in transactions if t.get("mapping_status") in ELIGIBLE_STATUSES]
    skipped  = len(transactions) - len(eligible)

    recon_failures = []
    totals = {"gross": 0.0, "platform_fee": 0.0, "processing_fee": 0.0, "net": 0.0}
    unexpected_classes: set[str] = set()

    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(HEADERS)

    for txn in eligible:
        gross  = round(_flt(txn.get("gross_amount")),     2)
        pf     = round(_flt(txn.get("platform_fee")),     2)
        procf  = round(_flt(txn.get("processing_fee")),   2)
        net    = round(_flt(txn.get("net_amount")),        2)

        recon = round(gross - pf - procf, 2)
        if abs(recon - net) > 0.01:
            recon_failures.append({
                "transaction_id":  txn.get("transaction_id"),
                "donor_name":      txn.get("donor_name"),
                "gross":           gross,
                "platform_fee":    pf,
                "processing_fee":  procf,
                "net":             net,
                "computed_net":    recon,
                "delta":           round(recon - net, 4),
            })

        totals["gross"]          = round(totals["gross"]          + gross, 2)
        totals["platform_fee"]   = round(totals["platform_fee"]   + pf,    2)
        totals["processing_fee"] = round(totals["processing_fee"] + procf, 2)
        totals["net"]            = round(totals["net"]            + net,   2)

        receipt_no    = txn.get("transaction_id", "")
        donor         = txn.get("donor_name") or "Unknown Donor"
        txn_date      = _fmt_date(txn.get("transaction_date", ""))
        qbo_account   = txn.get("qbo_account") or ""
        qbo_class     = txn.get("qbo_class") or ""
        qbo_class     = CLASS_NORMALIZATION.get(qbo_class, qbo_class)  # TEMPORARY shim
        if qbo_class and qbo_class not in KNOWN_GOOD_QB_CLASSES:
            unexpected_classes.add(qbo_class)
        needs_review  = "Y" if txn.get("mapping_status") == "donor_selects" else ""
        memo          = txn.get("campaign_name") or ""

        # ── Row 1: receipt header + income line ──────────────────────────────
        writer.writerow([
            receipt_no,
            donor,
            txn_date,
            DEPOSIT_TO_ACCOUNT,
            memo,
            needs_review,
            qbo_account,
            f"{gross:.2f}",
            qbo_class,
            INCOME_LINE_DESC,
        ])

        # ── Row 2: platform fee line (omit if zero) ───────────────────────────
        if pf > 0:
            writer.writerow([
                receipt_no,     # ties back to the receipt
                "", "", "", "", "",
                PLATFORM_FEE_ACCOUNT,
                f"{-pf:.2f}",   # negative = deduction from receipt total
                qbo_class,
                PLATFORM_FEE_DESC,
            ])

        # ── Row 3: processing fee line (omit if zero) ─────────────────────────
        if procf > 0:
            writer.writerow([
                receipt_no,
                "", "", "", "", "",
                PROCESSING_FEE_ACCOUNT,
                f"{-procf:.2f}",
                qbo_class,
                PROCESSING_FEE_DESC,
            ])

    if unexpected_classes:
        logger.warning(
            "LineClass values not in KNOWN_GOOD_QB_CLASSES: %s",
            sorted(unexpected_classes),
        )

    report = {
        "written":          len(eligible),
        "skipped_unmapped": skipped,
        "recon_failures":   recon_failures,
        "totals":           totals,
        "columns_used":     HEADERS,
        "config": {
            "platform_fee_account":   PLATFORM_FEE_ACCOUNT,
            "processing_fee_account": PROCESSING_FEE_ACCOUNT,
            "deposit_to_account":     DEPOSIT_TO_ACCOUNT,
        },
    }

    # UTF-8 BOM so Excel opens without encoding issues
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8"), report
