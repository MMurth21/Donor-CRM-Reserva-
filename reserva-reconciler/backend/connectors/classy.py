import os
import json
import httpx
from datetime import datetime, timezone, timedelta
from pathlib import Path
from auth.classy_oauth import get_valid_token

CLASSY_API_BASE = "https://api.classy.org/2.0"

TOKENS_DIR = Path(__file__).parent.parent / "tokens"
CAMPAIGN_CACHE_FILE = TOKENS_DIR / "campaign_cache.json"
CACHE_TTL = timedelta(hours=1)


def _headers() -> dict:
    return {"Authorization": f"Bearer {get_valid_token()}"}


def fetch_all_campaigns(force_refresh: bool = False) -> dict:
    """Returns {str(campaign_id): campaign_name}. Caches for 1 hour."""
    if not force_refresh and CAMPAIGN_CACHE_FILE.exists():
        cached = json.loads(CAMPAIGN_CACHE_FILE.read_text())
        fetched_at = datetime.fromisoformat(cached["fetched_at"])
        if datetime.now(timezone.utc) - fetched_at < CACHE_TTL:
            return cached["campaigns"]

    campaigns = {}
    page = 1
    while True:
        resp = httpx.get(
            f"{CLASSY_API_BASE}/organizations/{os.environ['CLASSY_ORG_ID']}/campaigns",
            headers=_headers(),
            params={"page": page, "per_page": 100},
        )
        resp.raise_for_status()
        body = resp.json()
        for c in body.get("data", []):
            campaigns[str(c["id"])] = c.get("name") or ""
        if page >= body.get("last_page", 1):
            break
        page += 1

    CAMPAIGN_CACHE_FILE.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "campaigns": campaigns,
    }, indent=2))
    return campaigns


def get_campaign_name(campaign_id: str):
    return fetch_all_campaigns().get(str(campaign_id))


def fetch_transactions(page: int = 1, per_page: int = 5) -> dict:
    org_id = os.environ["CLASSY_ORG_ID"]
    response = httpx.get(
        f"{CLASSY_API_BASE}/organizations/{org_id}/transactions",
        headers=_headers(),
        params={"page": page, "per_page": per_page},
    )
    response.raise_for_status()
    return response.json()
