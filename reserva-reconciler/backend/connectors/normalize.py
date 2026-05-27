import json
import logging
from pathlib import Path
from connectors.classy import get_campaign_name, fetch_org_designations

logger = logging.getLogger(__name__)

MAPPING_FILE = Path(__file__).parent.parent / "data" / "campaign_mapping.json"

_PROCESSOR_MAP = {
    "stripe":      "Stripe",
    "stripe_ach":  "Stripe",
    "paypal":      "PayPal",
    "paypal_ec":   "PayPal",
    "paypal_rest": "PayPal",
}


def _load_mapping() -> dict:
    if not MAPPING_FILE.exists():
        return {}
    raw = json.loads(MAPPING_FILE.read_text())
    campaigns = raw.get("campaigns", raw)  # support both new nested and legacy flat format
    return {str(k): v for k, v in campaigns.items()}


def _f(value, default: float = 0.0) -> float:
    """Coerce a possibly-string or None value to float."""
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def _extract_processor(tx: dict) -> str:
    raw = (tx.get("payment_gateway") or "").lower().strip()
    return _PROCESSOR_MAP.get(raw, raw)


def normalize_transactions(raw_list: list) -> list:
    mapping     = _load_mapping()
    designations = fetch_org_designations()
    canonical   = []

    for tx in raw_list:
        campaign_id = str(tx.get("campaign_id", ""))

        gross          = round(_f(tx.get("total_gross_amount")), 2)
        total_fees     = round(_f(tx.get("fees_amount")), 2)
        processing_fee = round(_f(tx.get("pp_fees_amount")), 2)
        platform_fee   = round(max(total_fees - processing_fee, 0.0), 2)
        net            = round(_f(tx.get("donation_net_amount")), 2)

        recon = round(platform_fee + processing_fee + net, 2)
        if abs(recon - gross) > 0.01:
            logger.warning(
                "Reconciliation fail tx=%s: %.2f + %.2f + %.2f = %.2f != gross %.2f",
                tx.get("id"), platform_fee, processing_fee, net, recon, gross,
            )

        camp = mapping.get(campaign_id)
        if camp is None:
            qbo_account    = None
            qbo_class      = None
            mapping_status = "needs_mapping"
        elif camp.get("donor_selects"):
            qbo_account  = camp.get("qbo_account") or None
            desig        = designations.get(str(tx.get("designation_id", "")), {})
            ext_ref      = (desig.get("external_reference_id") or "").strip()
            if ext_ref:
                qbo_class      = ext_ref
                mapping_status = "mapped"
            else:
                qbo_class      = None
                mapping_status = "needs_mapping"
        else:
            qbo_account    = camp.get("qbo_account") or None
            qbo_class      = camp.get("qbo_class") or None
            mapping_status = "mapped"

        canonical.append({
            "transaction_id":   str(tx.get("id", "")),
            "transaction_date": tx.get("purchased_at") or "",
            "donor_name":       tx.get("member_name") or "",
            "donor_email":      tx.get("member_email_address") or "",
            "campaign_id":      campaign_id,
            "campaign_name":    get_campaign_name(campaign_id),
            "designation_id":   str(tx.get("designation_id", "") or ""),
            "platform":         "GoFundMe Pro",
            "processor":        _extract_processor(tx),
            "payment_method":   tx.get("payment_method") or "",
            "gross_amount":     gross,
            "total_fees":       total_fees,
            "processing_fee":   processing_fee,
            "platform_fee":     platform_fee,
            "net_amount":       net,
            "qbo_account":      qbo_account,
            "qbo_class":        qbo_class,
            "mapping_status":   mapping_status,
        })

    return canonical
