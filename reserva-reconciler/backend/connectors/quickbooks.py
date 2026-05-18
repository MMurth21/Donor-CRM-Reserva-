import os
import json
from pathlib import Path
from intuitlib.client import AuthClient
from quickbooks import QuickBooks
from quickbooks.objects.customer import Customer

TOKENS_DIR = Path(__file__).parent.parent / "tokens"
QB_TOKEN_FILE = TOKENS_DIR / "quickbooks.json"


def get_client() -> QuickBooks:
    tokens = json.loads(QB_TOKEN_FILE.read_text())
    auth_client = AuthClient(
        client_id=os.environ["QB_CLIENT_ID"],
        client_secret=os.environ["QB_CLIENT_SECRET"],
        redirect_uri=os.environ["QB_REDIRECT_URI"],
        environment=os.environ.get("QB_ENVIRONMENT", "sandbox"),
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        realm_id=tokens["realm_id"],
    )
    return QuickBooks(auth_client=auth_client, company_id=tokens["realm_id"])


def get_customers():
    client = get_client()
    return Customer.all(qb=client)
