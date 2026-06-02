import re
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


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
    leadership_hire_date: Optional[str] = None        # RFC 2822 pubDate from RSS e.g. "Mon, 12 May 2026 ..."
    leadership_change_evidence: Optional[str] = None
    hiring_gtm_evidence: Optional[str] = None
    tech_stack_evidence: Optional[str] = None
    funded_90d_evidence: Optional[str] = None
    funded_90d_url: Optional[str] = None           # direct link to the funding news article
    funded_90d_date: Optional[str] = None          # pub date from RSS e.g. "Mon, 12 May 2026"
    funded_90d_headline: Optional[str] = None      # raw RSS headline — contains amount + stage
    hidden_intent_evidence: Optional[str] = None


class EvalOutcome(BaseModel):
    domain: str
    client_id: str
    outcome: str = Field(..., pattern="^(replied|closed|no_reply|bounced)$")
    hubspot_deal_id: Optional[str] = None
    days_to_outcome: Optional[int] = None


class EvalReport(BaseModel):
    client_id: str
    prompt_version: str
    total: int
    replied: int
    closed: int
    no_reply: int
    bounced: int
    reply_rate: float
    close_rate: float


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
    contacts: list[dict] = []          # up to 3 GTM contacts from Hunter [{name, title, email}]
    enriched: bool = False


class CompanyInput(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=200)
    domain: str = Field(..., min_length=3, max_length=100)
    client_id: str = Field(..., description="Which client this company belongs to")
    signals: Optional[Signals] = None            # None = auto-detect all 5 triggers
    scoring_context: Optional[str] = None       # extra enrichment from Clay Sculptor columns

    @field_validator("domain")
    @classmethod
    def clean_domain(cls, v: str) -> str:
        """Strip protocol, www, and trailing slash so callers can paste full URLs."""
        v = v.strip().lower()
        v = re.sub(r"^https?://", "", v)
        v = re.sub(r"^www\.", "", v)
        v = v.rstrip("/")
        if "." not in v:
            raise ValueError(f"Invalid domain: '{v}' — must contain a dot (e.g. acme.com)")
        return v


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
    situation: Optional[str] = None  # human-research paragraph combining all 5 signals
    talking_points: list[str] = []   # 3-5 BDR hooks for cold calls, one sharp sentence each

    # Governance
    requires_human_review: bool = False

    # Output
    pitch_block: Optional[str] = None
    signal_scores: dict[str, int] = {}
    email_opener: Optional[str] = None
    secondary_contact: Optional[dict] = None   # {name, title, email} for rollout sequence
    pipeline_value_usd: Optional[float] = None
    alerted_slack: bool = False
    pushed_to_crm: bool = False
    hubspot_contact_id: Optional[str] = None
    hubspot_deal_id: Optional[str] = None
    cost_usd: Optional[float] = None
    model_costs: dict[str, float] = {}        # per-model breakdown: {"gpt-4o-mini": 0.0001, "claude-sonnet-4-6": 0.003}
    pre_filter_passed: bool = True            # False when pre-filter rejected (zero signals)
    pre_filter_reason: Optional[str] = None  # why pre-filter passed or failed
    scored: bool = False
    auto_detected: bool = False                  # True if signals were auto-detected
    prompt_version: Optional[str] = None        # which prompt produced this score
    suppressed: bool = False                    # True if cooldown prevented scoring
    suppression_reason: Optional[str] = None
    cached: bool = False
    db_persisted: bool = False                  # True if Supabase insert succeeded
    error: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class BatchScoreRequest(BaseModel):
    companies: list[CompanyInput] = Field(..., min_length=1, max_length=50)
    min_score: int = Field(default=6, ge=1, le=10)


class BatchScoreResult(BaseModel):
    total_scored: int
    hot_leads_count: int
    ranked: list[ScoreResult]
    summary: str
