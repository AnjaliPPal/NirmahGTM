from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid


class Signals(BaseModel):
    # ── Trigger 4: Funding & M&A ──────────────────────────────────────────
    funded_90d: bool = False
    funding_stage: Optional[str] = None          # "Series A", "Series B", etc.
    acquisition_activity: bool = False

    # ── Trigger 2: Hiring Signals ─────────────────────────────────────────
    hiring_gtm: bool = False
    open_gtm_roles: int = 0                      # count of open GTM/sales roles
    hiring_keywords: list[str] = []              # from actual JD text: ["SDR", "CRM"]

    # ── Trigger 1: Leadership Changes ─────────────────────────────────────
    new_exec_hire: bool = False
    new_exec_name: Optional[str] = None
    new_exec_title: Optional[str] = None         # "VP Sales", "CRO", etc.

    # ── Trigger 3: Tech Stack ─────────────────────────────────────────────
    tech_stack: list[str] = []
    crm: Optional[str] = None                    # "Salesforce", "HubSpot" — ruthless filter
    sales_engagement: Optional[str] = None       # "Outreach", "Salesloft"

    # ── Trigger 5: Hidden Intent ──────────────────────────────────────────
    growth_pct: float = 0.0                      # manual override if known
    news_keywords: list[str] = []               # expansion/growth signals from news
    intent_signals_count: int = 0               # total hidden intent signals found

    # web_intent: excluded — no free source. Bombora = paid. Added in v2.

    # ── Evidence strings (raw text behind each trigger) ────────────────────
    leadership_change_evidence: Optional[str] = None
    hiring_gtm_evidence: Optional[str] = None
    tech_stack_evidence: Optional[str] = None
    funded_90d_evidence: Optional[str] = None
    hidden_intent_evidence: Optional[str] = None


class CRMResult(BaseModel):
    pushed: bool = False
    contact_id: Optional[str] = None
    deal_id: Optional[str] = None
    error: Optional[str] = None


class EnrichmentData(BaseModel):
    decision_maker_name: Optional[str] = None
    decision_maker_title: Optional[str] = None
    decision_maker_email: Optional[str] = None
    employee_count: Optional[int] = None
    industry: Optional[str] = None
    enriched: bool = False


class CompanyInput(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=200)
    domain: str = Field(..., min_length=3, max_length=100)
    client_id: str = Field(..., description="Which client this company belongs to")
    signals: Optional[Signals] = None            # None = auto-detect all 5 triggers


class ScoreResult(BaseModel):
    company_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_name: str
    domain: str
    client_id: str
    signals: Signals
    enrichment: Optional[EnrichmentData] = None

    # Scoring
    score: Optional[int] = None
    confidence: Optional[int] = None
    reasoning: Optional[str] = None
    top_signal: Optional[str] = None
    contact_window: Optional[str] = None
    aha_moment: Optional[str] = None

    # Governance
    requires_human_review: bool = False

    # Output
    pitch_block: Optional[str] = None
    signal_scores: dict[str, int] = {}
    email_opener: Optional[str] = None
    pipeline_value_usd: Optional[float] = None
    alerted_slack: bool = False
    pushed_to_crm: bool = False
    hubspot_contact_id: Optional[str] = None
    hubspot_deal_id: Optional[str] = None
    cost_usd: Optional[float] = None
    scored: bool = False
    auto_detected: bool = False                  # True if signals were auto-detected
    prompt_version: Optional[str] = None        # which prompt produced this score
    suppressed: bool = False                    # True if cooldown prevented scoring
    suppression_reason: Optional[str] = None
    cached: bool = False
    error: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
