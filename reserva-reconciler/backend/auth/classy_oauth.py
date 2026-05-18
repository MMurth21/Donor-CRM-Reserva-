import os
import json
import httpx
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()

TOKENS_DIR = Path(__file__).parent.parent / "tokens"
TOKENS_DIR.mkdir(exist_ok=True)
CLASSY_TOKEN_FILE = TOKENS_DIR / "classy.json"

CLASSY_AUTH_URL = "https://www.classy.org/oauth2/auth"
CLASSY_TOKEN_URL = "https://www.classy.org/oauth2/token"


@router.get("/login")
def login():
    params = {
        "client_id": os.environ["CLASSY_CLIENT_ID"],
        "redirect_uri": os.environ["CLASSY_REDIRECT_URI"],
        "response_type": "code",
        "scope": "read write",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(f"{CLASSY_AUTH_URL}?{query}")


@router.get("/callback")
def callback(code: str):
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": os.environ["CLASSY_REDIRECT_URI"],
        "client_id": os.environ["CLASSY_CLIENT_ID"],
        "client_secret": os.environ["CLASSY_CLIENT_SECRET"],
    }
    response = httpx.post(CLASSY_TOKEN_URL, data=data)
    response.raise_for_status()
    tokens = response.json()
    CLASSY_TOKEN_FILE.write_text(json.dumps(tokens))
    return {"status": "connected"}
