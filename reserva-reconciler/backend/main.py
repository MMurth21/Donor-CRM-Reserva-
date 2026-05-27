import io
import os
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from auth.quickbooks_oauth import router as qb_router
from auth.classy_oauth import router as classy_router
from connectors.classy import (
    fetch_transactions, fetch_all_campaigns,
    fetch_campaign_totals, _gross, _txn_count,
)
from connectors.normalize import normalize_transactions, _load_mapping
from exporters.sales_receipt_csv import generate_sales_receipt_csv
from exporters.journal_entry_csv import generate_journal_entry_csv

logger = logging.getLogger(__name__)

MAPPING_FILE = Path(__file__).parent / "data" / "campaign_mapping.json"
TRANSACTIONS_CACHE_FILE = Path(__file__).parent / "tokens" / "transactions_cache.json"
CACHE_TTL = timedelta(hours=1)

app = FastAPI(title="Reserva Reconciler")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(qb_router, prefix="/auth/quickbooks", tags=["quickbooks-auth"])
app.include_router(classy_router, prefix="/auth/classy", tags=["classy-auth"])


# ── helpers ──────────────────────────────────────────────────────────────────

def _read_mapping_file() -> dict:
    return json.loads(MAPPING_FILE.read_text(encoding="utf-8"))


def _atomic_write_mapping(data: dict):
    tmp = MAPPING_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, MAPPING_FILE)


def _is_incomplete(entry: dict) -> bool:
    """Mapped but missing account or class (and not donor_selects)."""
    if entry.get("donor_selects"):
        return False
    return not entry.get("qbo_account") or not entry.get("qbo_class")


# ── health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


# ── Classy transactions ───────────────────────────────────────────────────────

@app.get("/classy/transactions/sample")
def transactions_sample():
    return fetch_transactions(per_page=3)


@app.get("/classy/transactions/normalized")
def transactions_normalized(page: int = 1):
    raw = fetch_transactions(page=page, per_page=20)
    rows = normalize_transactions(raw.get("data", []))
    summary = {
        "total_rows":           len(rows),
        "total_gross":          round(sum(r["gross_amount"]     for r in rows), 2),
        "total_platform_fee":   round(sum(r["platform_fee"]     for r in rows), 2),
        "total_processing_fee": round(sum(r["processing_fee"]   for r in rows), 2),
        "total_net":            round(sum(r["net_amount"]        for r in rows), 2),
        "unmapped_count":       sum(1 for r in rows if r["mapping_status"] == "needs_mapping"),
    }
    return {"summary": summary, "transactions": rows}


@app.get("/classy/transactions/all")
def transactions_all():
    """Full normalized transaction list with summary. Cached 1 hour. Filters gross > 0."""
    if TRANSACTIONS_CACHE_FILE.exists():
        cached = json.loads(TRANSACTIONS_CACHE_FILE.read_text(encoding="utf-8"))
        age_ok = datetime.now(timezone.utc) - datetime.fromisoformat(cached["fetched_at"]) < CACHE_TTL
        if age_ok:
            return cached["payload"]

    all_raw = []
    page, last_page = 1, None
    while True:
        body = fetch_transactions(page=page, per_page=100)
        if last_page is None:
            last_page = body.get("last_page", 1)
        all_raw.extend(body.get("data", []))
        if page >= last_page:
            break
        page += 1

    rows = normalize_transactions(all_raw)
    rows = [r for r in rows if r["gross_amount"] > 0]

    summary = {
        "total_rows":           len(rows),
        "total_gross":          round(sum(r["gross_amount"]     for r in rows), 2),
        "total_platform_fee":   round(sum(r["platform_fee"]     for r in rows), 2),
        "total_processing_fee": round(sum(r["processing_fee"]   for r in rows), 2),
        "total_net":            round(sum(r["net_amount"]        for r in rows), 2),
        "unmapped_count":       sum(1 for r in rows if r["mapping_status"] == "needs_mapping"),
    }
    payload = {"summary": summary, "transactions": rows}

    TRANSACTIONS_CACHE_FILE.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }, ensure_ascii=False), encoding="utf-8")
    return payload


# ── mapping endpoints ─────────────────────────────────────────────────────────

@app.get("/mapping/unmapped")
def mapping_unmapped():
    """Campaigns that move money and are missing or incomplete in the mapping."""
    campaigns = fetch_all_campaigns()
    mapping = _load_mapping()
    totals = fetch_campaign_totals()
    full = _read_mapping_file()["campaigns"]

    result = []
    for cid, name in campaigns.items():
        gross = _gross(totals, cid)
        if gross <= 0:
            continue
        entry = full.get(cid)
        if entry is None or _is_incomplete(entry):
            result.append({
                "campaign_id":   cid,
                "campaign_name": name,
                "txn_count":     _txn_count(totals, cid),
                "total_gross":   gross,
            })

    result.sort(key=lambda r: r["total_gross"], reverse=True)
    return {"unmapped_count": len(result), "campaigns": result}


@app.get("/mapping/options")
def mapping_options():
    """Distinct qbo_account and qbo_class values already in the mapping file."""
    campaigns = _read_mapping_file()["campaigns"]
    accounts = sorted({v["qbo_account"] for v in campaigns.values() if v.get("qbo_account")})
    classes  = sorted({v["qbo_class"]   for v in campaigns.values() if v.get("qbo_class")})
    return {"qbo_accounts": accounts, "qbo_classes": classes}


@app.get("/mapping/all-campaigns")
def mapping_all_campaigns():
    """All Classy campaigns with mapping status and gross total."""
    campaigns = fetch_all_campaigns()
    mapping = _load_mapping()
    totals = fetch_campaign_totals()
    result = sorted(
        [
            {
                "id":             cid,
                "name":           name,
                "total_gross":    _gross(totals, cid),
                "txn_count":      _txn_count(totals, cid),
                "mapping_status": (
                    "mapped"          if cid in mapping else
                    "no_transactions" if _gross(totals, cid) == 0
                    else "needs_mapping"
                ),
            }
            for cid, name in campaigns.items()
        ],
        key=lambda r: r["total_gross"],
        reverse=True,
    )
    return {"total_campaigns": len(result), "campaigns": result}


class AssignBody(BaseModel):
    campaign_id:    str
    qbo_account:    str
    qbo_class:      str
    designation_id: Optional[str] = None
    donor_selects:  bool = False


@app.post("/mapping/assign")
def mapping_assign(body: AssignBody):
    campaigns = fetch_all_campaigns()
    if body.campaign_id not in campaigns:
        raise HTTPException(status_code=404, detail=f"campaign_id {body.campaign_id} not in Classy campaign cache")

    file_data = _read_mapping_file()
    existing = file_data["campaigns"].get(body.campaign_id, {})

    entry = {
        "campaign_id":            body.campaign_id,
        "campaign_name":          campaigns[body.campaign_id],
        "qbo_account":            body.qbo_account,
        "qbo_class":              body.qbo_class,
        "designation_id":         body.designation_id or existing.get("designation_id"),
        "internal_campaign_name": existing.get("internal_campaign_name"),
        "donor_selects":          body.donor_selects,
    }

    file_data["campaigns"][body.campaign_id] = entry
    _atomic_write_mapping(file_data)
    return {"status": "saved", "entry": entry}


# ── debug ─────────────────────────────────────────────────────────────────────

@app.get("/classy/campaigns/unmapped")
def campaigns_unmapped():
    campaigns = fetch_all_campaigns()
    mapping = _load_mapping()
    unmapped = [
        {"id": cid, "name": name}
        for cid, name in sorted(campaigns.items())
        if cid not in mapping
    ]
    return {"unmapped_count": len(unmapped), "campaigns": unmapped}


@app.get("/debug/mapping-join")
def debug_mapping_join():
    raw_campaign_id = 719401
    as_str = str(raw_campaign_id)
    mapping = _load_mapping()
    sample_keys = list(mapping.keys())[:3]
    return {
        "raw_campaign_id":        {"value": raw_campaign_id, "type": type(raw_campaign_id).__name__, "repr": repr(raw_campaign_id)},
        "after_str_cast":         {"value": as_str,          "type": type(as_str).__name__,          "repr": repr(as_str)},
        "mapping_sample_keys":    [{"key": k, "type": type(k).__name__, "repr": repr(k)} for k in sample_keys],
        "total_keys_loaded":      len(mapping),
        "str_strip_found_in_mapping": as_str.strip() in mapping,
        "mapping_file_path":      str(MAPPING_FILE),
    }


# ── export ─────────────────────────────────────────────────────────────────────

def _cache_schema_valid(cached: dict) -> bool:
    """Return False when the cached transactions are missing fields added after initial build."""
    txns = cached.get("payload", {}).get("transactions", [])
    if not txns:
        return True
    sample = txns[0]
    return "processor" in sample and "designation_id" in sample and "payment_method" in sample


def _get_all_transactions() -> list:
    """Return the full normalized transaction list (uses /classy/transactions/all cache)."""
    if TRANSACTIONS_CACHE_FILE.exists():
        cached = json.loads(TRANSACTIONS_CACHE_FILE.read_text(encoding="utf-8"))
        age_ok = datetime.now(timezone.utc) - datetime.fromisoformat(cached["fetched_at"]) < CACHE_TTL
        if age_ok and _cache_schema_valid(cached):
            return cached["payload"]["transactions"]
        if age_ok and not _cache_schema_valid(cached):
            logger.info("Cache schema stale (missing processor/designation_id) — forcing refresh")

    # cache miss or stale schema: re-run the full fetch
    return transactions_all()["transactions"]


@app.get("/export/sales-receipts/report")
def export_sales_receipts_report():
    """Validation report — call this first to review before downloading the CSV."""
    txns = _get_all_transactions()
    _, report = generate_sales_receipt_csv(txns)

    if report["recon_failures"]:
        for f in report["recon_failures"]:
            logger.warning("Recon failure: %s", f)

    logger.info(
        "Sales receipt report: %d written, %d skipped, %d recon failures",
        report["written"], report["skipped_unmapped"], len(report["recon_failures"]),
    )
    return report


@app.get("/export/sales-receipts/download")
def export_sales_receipts_download():
    """Stream the QBO Sales Receipt CSV file as a download. FILE ONLY — does not post to QuickBooks."""
    txns = _get_all_transactions()
    csv_bytes, report = generate_sales_receipt_csv(txns)

    logger.info(
        "Sales receipt download: %d receipts, %d skipped, %d recon failures",
        report["written"], report["skipped_unmapped"], len(report["recon_failures"]),
    )

    filename = f"sales_receipts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/export/journal-entries/report")
def export_journal_entries_report(month: str):
    """
    Validation report for a single monthly JE.

    month: YYYY-MM (e.g. 2026-05) — required.

    Reviews balance, processor splits, class normalization, and unknown entries.
    Call this first; download only after confirming the report looks correct.
    """
    try:
        txns = _get_all_transactions()
        _, report = generate_journal_entry_csv(txns, month)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not report.get("balanced"):
        logger.error("JE %s: IMBALANCED  delta=%s", report["journal_no"], report["delta"])
    if report.get("cent_adjustment") is not None:
        logger.info("JE %s: cent adjustment %.4f applied", report["journal_no"], report["cent_adjustment"])
    if report.get("unknown_processors"):
        logger.warning("JE %s: %d unknown-processor transactions excluded",
                       report["journal_no"], len(report["unknown_processors"]))

    logger.info(
        "Journal entry report: %s  txns=%d  balanced=%s  lines=%d",
        report["journal_no"], report["transactions_count"],
        report["balanced"], report["line_count"],
    )
    return report


@app.get("/export/journal-entries/download")
def export_journal_entries_download(month: str):
    """
    Stream a single monthly QBO Journal Entry CSV.

    month: YYYY-MM (e.g. 2026-05) — required.

    FILE ONLY — does not post to QuickBooks. Review /report first.
    """
    try:
        txns = _get_all_transactions()
        csv_bytes, report = generate_journal_entry_csv(txns, month)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    logger.info(
        "Journal entry download: %s  txns=%d  balanced=%s",
        report["journal_no"], report["transactions_count"], report["balanced"],
    )

    filename = f"journal_entry_{month}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
