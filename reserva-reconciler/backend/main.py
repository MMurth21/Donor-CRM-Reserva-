from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from auth.quickbooks_oauth import router as qb_router
from auth.classy_oauth import router as classy_router

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
