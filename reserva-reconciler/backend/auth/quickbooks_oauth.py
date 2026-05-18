import os
import json
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from intuitlib.client import AuthClient
from intuitlib.enums import Scopes

router = APIRouter()

TOKENS_DIR = Path(__file__).parent.parent / "tokens"
TOKENS_DIR.mkdir(exist_ok=True)
QB_TOKEN_FILE = TOKENS_DIR / "quickbooks.json"


def get_auth_client() -> AuthClient:
    return AuthClient(
        client_id=os.environ["QB_CLIENT_ID"],
        client_secret=os.environ["QB_CLIENT_SECRET"],
        redirect_uri=os.environ["QB_REDIRECT_URI"],
        environment=os.environ.get("QB_ENVIRONMENT", "sandbox"),
    )


@router.get("/login")
def login():
    client = get_auth_client()
    url = client.get_authorization_url([Scopes.ACCOUNTING])
    return RedirectResponse(url)


@router.get("/callback")
def callback(code: str, realmId: str, state: str = None):
    client = get_auth_client()
    client.get_bearer_token(code, realm_id=realmId)
    QB_TOKEN_FILE.write_text(json.dumps({
        "access_token": client.access_token,
        "refresh_token": client.refresh_token,
        "realm_id": realmId,
    }))
    return {"status": "connected", "realm_id": realmId}
