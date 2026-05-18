import json
import httpx
from pathlib import Path

TOKENS_DIR = Path(__file__).parent.parent / "tokens"
CLASSY_TOKEN_FILE = TOKENS_DIR / "classy.json"

CLASSY_API_BASE = "https://api.classy.org/2.0"


def get_headers() -> dict:
    tokens = json.loads(CLASSY_TOKEN_FILE.read_text())
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def get_donations(campaign_id: int):
    url = f"{CLASSY_API_BASE}/campaigns/{campaign_id}/transactions"
    response = httpx.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json()


def get_members(organization_id: int):
    url = f"{CLASSY_API_BASE}/organizations/{organization_id}/members"
    response = httpx.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json()
