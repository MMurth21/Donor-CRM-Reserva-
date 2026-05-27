import os
import json
import httpx
from datetime import datetime, timezone, timedelta
from pathlib import Path
from auth.classy_oauth import get_valid_token

CLASSY_API_BASE = "https://api.classy.org/2.0"

TOKENS_DIR = Path(__file__).parent.parent / "tokens"
CAMPAIGN_CACHE_FILE    = TOKENS_DIR / "campaign_cache.json"
CAMPAIGN_TOTALS_FILE   = TOKENS_DIR / "campaign_totals_cache.json"
DESIGNATIONS_CACHE_FILE = TOKENS_DIR / "designations_cache.json"
CACHE_TTL = timedelta(hours=1)


def _headers() -> dict:
    return {"Authorization": f"Bearer {get_valid_token()}"}


def fetch_org_designations(force_refresh: bool = False) -> dict:
    """Return {str(designation_id): designation_record} for org 83147. File-cached 1 hour."""
    if not force_refresh and DESIGNATIONS_CACHE_FILE.exists():
        cached = json.loads(DESIGNATIONS_CACHE_FILE.read_text())
        age_ok = datetime.now(timezone.utc) - datetime.fromisoformat(cached["fetched_at"]) < CACHE_TTL
        if age_ok:
            return cached["designations"]

    org_id = os.environ["CLASSY_ORG_ID"]
    designations = {}
    page, last_page = 1, None
    while True:
        resp = httpx.get(
            f"{CLASSY_API_BASE}/organizations/{org_id}/designations",
            headers=_headers(),
            params={"page": page, "per_page": 100},
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        if last_page is None:
            last_page = body.get("last_page", 1)
        for d in body.get("data", []):
            designations[str(d["id"])] = d
        if page >= last_page:
            break
        page += 1

    DESIGNATIONS_CACHE_FILE.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "designations": designations,
    }, indent=2))
    return designations


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


def fetch_campaign_totals(force_refresh: bool = False) -> dict:
    """Returns {str(campaign_id): {"total_gross": float, "txn_count": int}}. Cached 1 hour."""
    if not force_refresh and CAMPAIGN_TOTALS_FILE.exists():
        cached = json.loads(CAMPAIGN_TOTALS_FILE.read_text())
        age_ok = datetime.now(timezone.utc) - datetime.fromisoformat(cached["fetched_at"]) < CACHE_TTL
        sample = next(iter(cached.get("totals", {}).values()), None)
        if age_ok and isinstance(sample, dict):  # reject old float-value format
            return cached["totals"]

    totals = {}
    org_id = os.environ["CLASSY_ORG_ID"]
    page, last_page = 1, None
    while True:
        resp = httpx.get(
            f"{CLASSY_API_BASE}/organizations/{org_id}/transactions",
            headers=_headers(),
            params={"page": page, "per_page": 100},
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        if last_page is None:
            last_page = body["last_page"]
        for tx in body["data"]:
            cid = str(tx.get("campaign_id", ""))
            try:
                gross = float(tx.get("total_gross_amount") or 0)
            except (ValueError, TypeError):
                gross = 0.0
            if cid not in totals:
                totals[cid] = {"total_gross": 0.0, "txn_count": 0}
            totals[cid]["total_gross"] = round(totals[cid]["total_gross"] + gross, 2)
            totals[cid]["txn_count"] += 1
        if page >= last_page:
            break
        page += 1

    CAMPAIGN_TOTALS_FILE.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "totals": totals,
    }, indent=2))
    return totals


def _gross(totals: dict, cid: str) -> float:
    v = totals.get(cid, {})
    return v.get("total_gross", 0.0) if isinstance(v, dict) else float(v)


def _txn_count(totals: dict, cid: str) -> int:
    v = totals.get(cid, {})
    return v.get("txn_count", 0) if isinstance(v, dict) else 0


def fetch_transactions(page: int = 1, per_page: int = 5) -> dict:
    org_id = os.environ["CLASSY_ORG_ID"]
    response = httpx.get(
        f"{CLASSY_API_BASE}/organizations/{org_id}/transactions",
        headers=_headers(),
        params={"page": page, "per_page": per_page},
    )
    response.raise_for_status()
    return response.json()
