from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from auth.quickbooks_oauth import router as qb_router
from auth.classy_oauth import router as classy_router
from connectors.classy import fetch_transactions, fetch_all_campaigns, fetch_campaign_totals
from connectors.normalize import normalize_transactions, _load_mapping

app = FastAPI(title="Reserva Reconciler")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(qb_router, prefix="/auth/quickbooks", tags=["quickbooks-auth"])
app.include_router(classy_router, prefix="/auth/classy", tags=["classy-auth"])


@app.get("/health")
def health():
    return {"status": "ok"}


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


@app.get("/mapping/unmapped")
def mapping_unmapped():
    """Campaigns that move money and have no QBO mapping yet."""
    campaigns = fetch_all_campaigns()
    mapping = _load_mapping()
    totals = fetch_campaign_totals()
    result = sorted(
        [
            {"id": cid, "name": name, "total_gross": totals.get(cid, 0.0)}
            for cid, name in campaigns.items()
            if cid not in mapping and totals.get(cid, 0.0) > 0
        ],
        key=lambda r: r["total_gross"],
        reverse=True,
    )
    return {"unmapped_count": len(result), "campaigns": result}


@app.get("/mapping/all-campaigns")
def mapping_all_campaigns():
    """All Classy campaigns with mapping status and gross total."""
    campaigns = fetch_all_campaigns()
    mapping = _load_mapping()
    totals = fetch_campaign_totals()
    result = sorted(
        [
            {
                "id": cid,
                "name": name,
                "total_gross": totals.get(cid, 0.0),
                "mapping_status": (
                    "mapped" if cid in mapping else
                    ("no_transactions" if totals.get(cid, 0.0) == 0 else "needs_mapping")
                ),
            }
            for cid, name in campaigns.items()
        ],
        key=lambda r: r["total_gross"],
        reverse=True,
    )
    return {"total_campaigns": len(result), "campaigns": result}


@app.get("/debug/mapping-join")
def debug_mapping_join():
    import json
    from pathlib import Path

    # 1. Simulate how campaign_id comes off a raw Classy transaction
    raw_campaign_id = 719401  # integer, as Classy returns it
    as_str = str(raw_campaign_id)

    # 2. Load mapping exactly as normalize.py does
    mapping = _load_mapping()
    sample_keys = list(mapping.keys())[:3]

    return {
        "raw_campaign_id": {
            "value": raw_campaign_id,
            "type": type(raw_campaign_id).__name__,
            "repr": repr(raw_campaign_id),
        },
        "after_str_cast": {
            "value": as_str,
            "type": type(as_str).__name__,
            "repr": repr(as_str),
        },
        "mapping_sample_keys": [
            {"key": k, "type": type(k).__name__, "repr": repr(k)}
            for k in sample_keys
        ],
        "total_keys_loaded": len(mapping),
        "str_strip_found_in_mapping": as_str.strip() in mapping,
        "mapping_file_path": str(Path(__file__).parent / "data" / "campaign_mapping.json"),
    }
