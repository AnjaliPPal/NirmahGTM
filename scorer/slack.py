"""
Slack alerts with Block Kit ROI receipt.

Routing:
  confidence >= CONFIDENCE_THRESHOLD → SLACK_WEBHOOK_URL  (main sales channel)
  confidence <  CONFIDENCE_THRESHOLD → SLACK_REVIEW_WEBHOOK_URL  (#human-review-required)

ROI receipt format (main channel):
  🚨 High Intent Signal: Acme Corp
  Score + aha moment
  Pipeline: $45,000 | Signal Cost: $0.004 | ROI: 11,250,000x
  [Push to HubSpot] [View Domain]
"""
import os
import requests
from .models import ScoreResult

SLACK_WEBHOOK_URL        = os.environ.get("SLACK_WEBHOOK_URL", "")
SLACK_REVIEW_WEBHOOK_URL = os.environ.get("SLACK_REVIEW_WEBHOOK_URL", "")  # #human-review-required
HUBSPOT_PORTAL_ID        = os.environ.get("HUBSPOT_PORTAL_ID", "")


def _hubspot_url(result: ScoreResult) -> str | None:
    if not HUBSPOT_PORTAL_ID:
        return None
    # Link to the auto-created deal if CRM push already happened
    if result.hubspot_deal_id:
        return f"https://app.hubspot.com/contacts/{HUBSPOT_PORTAL_ID}/deal/{result.hubspot_deal_id}"
    # Fall back to pre-filled create-contact form
    email   = (result.enrichment.decision_maker_email or "") if result.enrichment else ""
    name    = (result.enrichment.decision_maker_name or "")  if result.enrichment else ""
    first   = name.split()[0] if name else ""
    return (
        f"https://app.hubspot.com/contacts/{HUBSPOT_PORTAL_ID}/contact/new"
        f"?email={email}&firstname={first}&company={result.company_name}&website={result.domain}"
    )


def _contact_text(result: ScoreResult) -> str:
    if not result.enrichment or not result.enrichment.enriched:
        return ""
    parts = []
    if result.enrichment.decision_maker_name:
        parts.append(result.enrichment.decision_maker_name)
    if result.enrichment.decision_maker_title:
        parts.append(f"({result.enrichment.decision_maker_title})")
    if result.enrichment.decision_maker_email:
        parts.append(f"`{result.enrichment.decision_maker_email}`")
    return " ".join(parts)


def _roi_blocks(result: ScoreResult) -> list:
    pipeline = f"${result.pipeline_value_usd:,.0f}" if result.pipeline_value_usd else "N/A"
    cost     = f"${result.cost_usd:.4f}" if result.cost_usd else "N/A"
    roi      = (
        f"{result.pipeline_value_usd / result.cost_usd:,.0f}x"
        if result.pipeline_value_usd and result.cost_usd
        else "∞"
    )
    contact  = _contact_text(result)
    opener   = f"\n*Opening line:* _{result.email_opener}_" if result.email_opener else ""

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🚨 High Intent Signal: {result.company_name}"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{result.score}/10 (confidence: {result.confidence}%):* {result.aha_moment}"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Signal:* {result.top_signal}"},
                {"type": "mrkdwn", "text": f"*Window:* {result.contact_window}"},
                {"type": "mrkdwn", "text": f"*Est. Pipeline Value:* {pipeline}"},
                {"type": "mrkdwn", "text": f"*Cost to Acquire Signal:* {cost}  _(ROI: {roi})_"},
            ],
        },
    ]

    if contact or opener:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Contact:* {contact}{opener}" if contact else opener},
        })

    action_elements = []
    hs_url = _hubspot_url(result)
    if hs_url:
        hs_label = "View in HubSpot" if result.hubspot_deal_id else "Push to HubSpot"
        action_elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": hs_label},
            "url": hs_url,
            "style": "primary",
        })
    action_elements.append({
        "type": "button",
        "text": {"type": "plain_text", "text": f"View {result.domain}"},
        "url": f"https://{result.domain}",
    })
    blocks.append({"type": "actions", "elements": action_elements})

    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": f"Client: `{result.client_id}` | Scored by SignalOS"}],
    })
    return blocks


def _review_blocks(result: ScoreResult) -> list:
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"⚠️ Human Review Required: {result.company_name}"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Score:* {result.score}/10 | *Confidence:* {result.confidence}% _(below {os.environ.get('CONFIDENCE_THRESHOLD', '80')}% threshold)_\n"
                    f"*Aha Moment:* {result.aha_moment}\n"
                    f"*Why low confidence:* {result.reasoning}\n"
                    f"_Review manually before any outreach._"
                ),
            },
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Domain: `{result.domain}` | Client: `{result.client_id}`"}],
        },
    ]


def _post(webhook_url: str, blocks: list) -> bool:
    if not webhook_url:
        return False
    try:
        r = requests.post(webhook_url, json={"blocks": blocks}, timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def send_slack_alert(result: ScoreResult) -> bool:
    """Route to correct Slack channel based on confidence. Never raises."""
    if result.requires_human_review:
        webhook = SLACK_REVIEW_WEBHOOK_URL or SLACK_WEBHOOK_URL  # fallback if review channel not set
        return _post(webhook, _review_blocks(result))

    return _post(SLACK_WEBHOOK_URL, _roi_blocks(result))
