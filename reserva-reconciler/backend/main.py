from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from auth.quickbooks_oauth import router as qb_router
from auth.classy_oauth import router as classy_router
from connectors.classy import fetch_transactions
from connectors.normalize import normalize_transactions

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
