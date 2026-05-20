import os
import json
import httpx
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import APIRouter, HTTPException

router = APIRouter()

TOKENS_DIR = Path(__file__).parent.parent / "tokens"
TOKENS_DIR.mkdir(exist_ok=True)
CLASSY_TOKEN_FILE = TOKENS_DIR / "classy_tokens.json"

CLASSY_TOKEN_URL = "https://api.classy.org/oauth2/auth"
CLASSY_API_BASE = "https://api.classy.org/2.0"


def get_token() -> dict:
    response = httpx.post(
        CLASSY_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": os.environ["CLASSY_CLIENT_ID"],
            "client_secret": os.environ["CLASSY_CLIENT_SECRET"],
        },
    )
    response.raise_for_status()
    raw = response.json()
    tokens = {
        "access_token": raw["access_token"],
        "token_type": raw.get("token_type", "bearer"),
        "expires_at": (
            datetime.now(timezone.utc) + timedelta(seconds=raw.get("expires_in", 3600))
        ).isoformat(),
    }
    CLASSY_TOKEN_FILE.write_text(json.dumps(tokens, indent=2))
    return tokens


def get_valid_token() -> str:
    if CLASSY_TOKEN_FILE.exists():
        tokens = json.loads(CLASSY_TOKEN_FILE.read_text())
        if datetime.now(timezone.utc) < datetime.fromisoformat(tokens["expires_at"]):
            return tokens["access_token"]
    return get_token()["access_token"]


@router.get("/status")
def status():
    if not CLASSY_TOKEN_FILE.exists():
        return {"connected": False, "expires_at": None}
    tokens = json.loads(CLASSY_TOKEN_FILE.read_text())
    return {"connected": True, "expires_at": tokens.get("expires_at")}


@router.get("/test")
def test():
    org_id = os.environ["CLASSY_ORG_ID"]
    token = get_valid_token()
    response = httpx.get(
        f"{CLASSY_API_BASE}/organizations/{org_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    if not response.is_success:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    data = response.json()
    return {"status_code": response.status_code, "org_name": data.get("name")}
