import os
import httpx
from auth.classy_oauth import get_valid_token

CLASSY_API_BASE = "https://api.classy.org/2.0"


def fetch_transactions(page: int = 1, per_page: int = 5) -> dict:
    org_id = os.environ["CLASSY_ORG_ID"]
    response = httpx.get(
        f"{CLASSY_API_BASE}/organizations/{org_id}/transactions",
        headers={"Authorization": f"Bearer {get_valid_token()}"},
        params={"page": page, "per_page": per_page},
    )
    response.raise_for_status()
    return response.json()
