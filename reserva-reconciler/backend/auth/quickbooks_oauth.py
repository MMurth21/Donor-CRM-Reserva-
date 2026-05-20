import os
import json
import secrets
import httpx
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import RedirectResponse, PlainTextResponse

router = APIRouter()

TOKENS_DIR = Path(__file__).parent.parent / "tokens"
TOKENS_DIR.mkdir(exist_ok=True)
QB_TOKEN_FILE = TOKENS_DIR / "quickbooks.json"

QB_AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
QB_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
QB_SCOPES = "com.intuit.quickbooks.accounting"


def build_auth_url() -> str:
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": os.environ["QB_CLIENT_ID"],
        "redirect_uri": os.environ["QB_REDIRECT_URI"],
        "response_type": "code",
        "scope": QB_SCOPES,
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{QB_AUTH_URL}?{query}"


def exchange_code(code: str, realm_id: str) -> dict:
    response = httpx.post(
        QB_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": os.environ["QB_REDIRECT_URI"],
        },
        auth=(os.environ["QB_CLIENT_ID"], os.environ["QB_CLIENT_SECRET"]),
    )
    response.raise_for_status()
    raw = response.json()
    expires_in = raw.get("expires_in", 3600)
    tokens = {
        "access_token": raw["access_token"],
        "refresh_token": raw.get("refresh_token", ""),
        "realm_id": realm_id,
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
    }
    QB_TOKEN_FILE.write_text(json.dumps(tokens, indent=2))
    return tokens


def refresh_if_needed() -> dict:
    tokens = json.loads(QB_TOKEN_FILE.read_text())
    expires_at = datetime.fromisoformat(tokens["expires_at"])
    if datetime.now(timezone.utc) < expires_at:
        return tokens
    response = httpx.post(
        QB_TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]},
        auth=(os.environ["QB_CLIENT_ID"], os.environ["QB_CLIENT_SECRET"]),
    )
    response.raise_for_status()
    raw = response.json()
    expires_in = raw.get("expires_in", 3600)
    tokens = {
        "access_token": raw["access_token"],
        "refresh_token": raw.get("refresh_token", tokens["refresh_token"]),
        "realm_id": tokens["realm_id"],
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
    }
    QB_TOKEN_FILE.write_text(json.dumps(tokens, indent=2))
    return tokens


def get_valid_token() -> str:
    return refresh_if_needed()["access_token"]


@router.get("/login")
def login():
    return RedirectResponse(build_auth_url())


@router.get("/callback")
def callback(code: str, realmId: str, state: str = None):
    exchange_code(code, realmId)
    return PlainTextResponse("QuickBooks connected.")


@router.get("/status")
def status():
    if not QB_TOKEN_FILE.exists():
        return {"connected": False, "expires_at": None}
    tokens = json.loads(QB_TOKEN_FILE.read_text())
    return {"connected": True, "expires_at": tokens.get("expires_at"), "realm_id": tokens.get("realm_id")}
