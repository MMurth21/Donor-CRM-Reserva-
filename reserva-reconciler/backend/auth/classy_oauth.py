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
CLASSY_TOKEN_FILE = TOKENS_DIR / "classy_tokens.json"

CLASSY_AUTH_URL = "https://api.classy.org/oauth2/auth"
CLASSY_TOKEN_URL = "https://api.classy.org/oauth2/token"


def build_auth_url() -> str:
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": os.environ["CLASSY_CLIENT_ID"],
        "redirect_uri": os.environ["CLASSY_REDIRECT_URI"],
        "response_type": "code",
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{CLASSY_AUTH_URL}?{query}"


def exchange_code(code: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": os.environ["CLASSY_REDIRECT_URI"],
        "client_id": os.environ["CLASSY_CLIENT_ID"],
        "client_secret": os.environ["CLASSY_CLIENT_SECRET"],
    }
    response = httpx.post(CLASSY_TOKEN_URL, data=data)
    response.raise_for_status()
    raw = response.json()
    expires_in = raw.get("expires_in", 3600)
    tokens = {
        "access_token": raw["access_token"],
        "refresh_token": raw.get("refresh_token", ""),
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
    }
    CLASSY_TOKEN_FILE.write_text(json.dumps(tokens, indent=2))
    return tokens


def refresh_if_needed() -> dict:
    tokens = json.loads(CLASSY_TOKEN_FILE.read_text())
    expires_at = datetime.fromisoformat(tokens["expires_at"])
    if datetime.now(timezone.utc) < expires_at:
        return tokens
    data = {
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "client_id": os.environ["CLASSY_CLIENT_ID"],
        "client_secret": os.environ["CLASSY_CLIENT_SECRET"],
    }
    response = httpx.post(CLASSY_TOKEN_URL, data=data)
    response.raise_for_status()
    raw = response.json()
    expires_in = raw.get("expires_in", 3600)
    tokens = {
        "access_token": raw["access_token"],
        "refresh_token": raw.get("refresh_token", tokens["refresh_token"]),
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
    }
    CLASSY_TOKEN_FILE.write_text(json.dumps(tokens, indent=2))
    return tokens


def get_valid_token() -> str:
    return refresh_if_needed()["access_token"]


@router.get("/login")
def login():
    return RedirectResponse(build_auth_url())


@router.get("/callback")
def callback(code: str, state: str = None):
    exchange_code(code)
    return PlainTextResponse("Classy connected.")


@router.get("/status")
def status():
    if not CLASSY_TOKEN_FILE.exists():
        return {"connected": False, "expires_at": None}
    tokens = json.loads(CLASSY_TOKEN_FILE.read_text())
    return {"connected": True, "expires_at": tokens.get("expires_at")}
