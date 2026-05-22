import os
import json
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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

MAPPING_FILE = Path(__file__).parent / "data" / "campaign_mapping.json"

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
