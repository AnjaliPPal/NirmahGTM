import os
import json
import anthropic
from .models import CompanyInput, ScoreResult
from .prompts import SCORING_SYSTEM_PROMPT, SCORING_PROMPT_V2, OPENER_PROMPT_V1, PROMPT_VERSION
from .slack import send_slack_alert
from .enrichment import enrich_company
from .signal_detector import detect_signals
from .crm import push_to_hubspot

_client: anthropic.Anthropic | None = None

SCORE_THRESHOLD      = int(os.environ.get("SCORE_THRESHOLD", "6"))
CONFIDENCE_THRESHOLD = int(os.environ.get("CONFIDENCE_THRESHOLD", "80"))
DEAL_ACV             = float(os.environ.get("DEAL_ACV", "45000"))
MODEL                = "claude-sonnet-4-6"


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _calculate_cost(usage) -> float:
    # claude-sonnet-4-6 (May 2026): write $3.75/1M | read $0.30/1M | in $3/1M | out $15/1M
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read  = getattr(usage, "cache_read_input_tokens", 0) or 0
    regular     = getattr(usage, "input_tokens", 0) or 0
    output      = getattr(usage, "output_tokens", 0) or 0
    return (
        cache_write * 0.00000375 +
        cache_read  * 0.0000003  +
        regular     * 0.000003   +
        output      * 0.000015
    )


# Prompt caching gives 90% discount on cached input tokens. Blended real-world reduction is approximately 80% depending on cache hit rate.
_SYSTEM = [{"type": "text", "text": SCORING_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]


def score_company(company: CompanyInput) -> ScoreResult:
    # ── Auto-detect signals if not manually provided ───────────────────────
    auto_detected = company.signals is None
    signals = company.signals or detect_signals(company.domain, company.company_name)

    enrichment = enrich_company(company.domain)

    result = ScoreResult(
        company_name=company.company_name,
        domain=company.domain,
        client_id=company.client_id,
        signals=signals,
        enrichment=enrichment,
        auto_detected=auto_detected,
        prompt_version=PROMPT_VERSION,
    )
    total_cost = 0.0

    # ── Step 1: Build richer scoring prompt from all 5 triggers ───────────
    industry_line  = f" | Industry: {enrichment.industry}" if enrichment.industry else ""
    employee_line  = f" | Employees: ~{enrichment.employee_count}" if enrichment.employee_count else ""
    contact_line   = f" | Decision maker: {enrichment.decision_maker_title}" if enrichment.decision_maker_title else ""
    new_exec_line  = f" — {signals.new_exec_name} ({signals.new_exec_title})" if signals.new_exec_name else ""

    leadership_evidence_line = f"\n- Evidence: {signals.leadership_change_evidence}" if signals.leadership_change_evidence else ""
    hiring_evidence_line     = f"\n- Evidence: {signals.hiring_gtm_evidence}" if signals.hiring_gtm_evidence else ""
    tech_evidence_line       = f"\n- Evidence: {signals.tech_stack_evidence}" if signals.tech_stack_evidence else ""
    funding_evidence_line    = f"\n- Evidence: {signals.funded_90d_evidence}" if signals.funded_90d_evidence else ""
    intent_evidence_line     = f"\n- Evidence: {signals.hidden_intent_evidence}" if signals.hidden_intent_evidence else ""

    scoring_prompt = SCORING_PROMPT_V2.format(
        company_name=company.company_name,
        domain=company.domain,
        industry_line=industry_line,
        employee_line=employee_line,
        contact_line=contact_line,
        new_exec_hire=signals.new_exec_hire,
        new_exec_line=new_exec_line,
        leadership_evidence_line=leadership_evidence_line,
        hiring_gtm=signals.hiring_gtm,
        open_gtm_roles=signals.open_gtm_roles,
        hiring_keywords=", ".join(signals.hiring_keywords) or "none detected",
        hiring_evidence_line=hiring_evidence_line,
        tech_stack=", ".join(signals.tech_stack) or "unknown",
        crm=signals.crm or "unknown",
        sales_engagement=signals.sales_engagement or "unknown",
        tech_evidence_line=tech_evidence_line,
        funded_90d=signals.funded_90d,
        funding_stage=signals.funding_stage or "unknown",
        acquisition_activity=signals.acquisition_activity,
        funding_evidence_line=funding_evidence_line,
        news_keywords=", ".join(signals.news_keywords) or "none",
        intent_signals_count=signals.intent_signals_count,
        intent_evidence_line=intent_evidence_line,
    )

    raw = ""
    try:
        response = _get_client().messages.create(
            model=MODEL,
            max_tokens=250,
            system=_SYSTEM,
            messages=[{"role": "user", "content": scoring_prompt}],
        )
        raw = response.content[0].text.strip()
        total_cost += _calculate_cost(response.usage)

        parsed = json.loads(raw)
        result.score          = int(parsed["score"])
        result.confidence     = int(parsed.get("confidence", 100))
        result.reasoning      = parsed["reasoning"]
        result.top_signal     = parsed["top_signal"]
        result.contact_window = parsed["contact_window"]
        result.aha_moment     = parsed.get("aha_moment", result.reasoning)
        result.signal_scores  = parsed.get("signal_scores", {})
        result.pitch_block    = parsed.get("pitch_block")
        result.scored         = True

        result.requires_human_review = result.confidence < CONFIDENCE_THRESHOLD

    except json.JSONDecodeError as e:
        result.error = f"JSON parse failed: {e} | raw: {raw[:200]}"
        result.cost_usd = round(total_cost, 6)
        return result
    except Exception as e:
        result.error = f"Scoring failed: {str(e)}"
        result.cost_usd = round(total_cost, 6)
        return result

    # ── Step 2: Opener — high-confidence, above-threshold leads only ──────
    if result.score >= SCORE_THRESHOLD and not result.requires_human_review:
        contact_context = ""
        if enrichment.decision_maker_name and enrichment.decision_maker_title:
            contact_context = f"Contact: {enrichment.decision_maker_name}, {enrichment.decision_maker_title}\n"
        elif enrichment.decision_maker_name:
            contact_context = f"Contact: {enrichment.decision_maker_name}\n"

        evidence_parts = [
            ev for ev in [
                signals.funded_90d_evidence,
                signals.hiring_gtm_evidence,
                signals.leadership_change_evidence,
                signals.hidden_intent_evidence,
                signals.tech_stack_evidence,
            ] if ev
        ]
        evidence_block = "\n".join(f"- {e}" for e in evidence_parts) if evidence_parts else "- No specific evidence captured"

        opener_prompt = OPENER_PROMPT_V1.format(
            company_name=company.company_name,
            contact_context=contact_context,
            evidence_block=evidence_block,
        )
        try:
            opener_response = _get_client().messages.create(
                model=MODEL,
                max_tokens=60,
                system=_SYSTEM,
                messages=[{"role": "user", "content": opener_prompt}],
            )
            result.email_opener = opener_response.content[0].text.strip()
            total_cost += _calculate_cost(opener_response.usage)
        except Exception:
            result.email_opener = None

    # ── Step 3: ROI + cost ────────────────────────────────────────────────
    if result.score >= SCORE_THRESHOLD:
        result.pipeline_value_usd = DEAL_ACV

    result.cost_usd = round(total_cost, 6)

    # ── Step 4: Alert — main channel or #human-review-required ───────────
    if result.score >= SCORE_THRESHOLD:
        result.alerted_slack = send_slack_alert(result)

    # ── Step 5: CRM push — high-confidence leads only, auto into HubSpot ─
    if result.score >= SCORE_THRESHOLD and not result.requires_human_review:
        crm = push_to_hubspot(result)
        if crm.pushed:
            result.pushed_to_crm      = True
            result.hubspot_contact_id = crm.contact_id
            result.hubspot_deal_id    = crm.deal_id

    return result
