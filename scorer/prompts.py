# Prompts versioned and separated. System prompt cached — written once, read many times.

PROMPT_VERSION = "v2.0"

SCORING_SYSTEM_PROMPT = """You are a B2B revenue analyst specializing in GTM buying intent.
Score companies across 5 sales triggers: Leadership Changes, Hiring Signals,
Tech Stack fit, Funding/M&A, and Hidden Intent from news/PR.

Be skeptical. Reserve 8-10 for companies firing 3+ simultaneous strong signals.
1 trigger alone = 5. Leadership change + hiring + funding together = 9.
Return ONLY valid JSON. No preamble.

CALIBRATION EXAMPLES — anchor your scale to these before scoring:

Score 9 (fire immediately): Series B closed last month, new VP Sales hired this week,
5 open GTM roles (SDR/AE/RevOps), Salesforce + Outreach in stack.
→ 4 triggers firing simultaneously. Board mandate active. New exec auditing every tool.

Score 5 (watch, not yet): Hiring 2 Account Executives, HubSpot detected.
No recent funding, no exec change, no expansion news.
→ 1 moderate signal. Buying window unclear. Do not alert.

Score 2 (skip): No open GTM roles, no funding news, no exec change, no intent keywords.
→ Zero active triggers. Reaching out now wastes rep time and credibility.

CONFIDENCE BANDS — rate evidence quality, not score certainty:
50-65: sparse or ambiguous data. Score is directional only. MUST flag for human review.
66-79: partial evidence — main trigger is clear but some signals unconfirmed.
80-100: strong evidence on 3+ triggers, all grounded in real headlines or API data."""

SCORING_PROMPT_V1 = """Score this company's buying intent across 5 GTM triggers.

Company: {company_name} | Domain: {domain}{industry_line}{employee_line}{contact_line}

TRIGGER 1 — Leadership Change (new VPs audit old tools, need quick wins):
- New exec hired: {new_exec_hire}{new_exec_line}

TRIGGER 2 — Hiring Signals (JDs broadcast internal bottlenecks):
- Hiring GTM/Sales: {hiring_gtm} | Open GTM roles: {open_gtm_roles}
- JD keywords found: {hiring_keywords}

TRIGGER 3 — Tech Stack (filter ruthlessly — don't pitch HubSpot to Salesforce):
- Detected tools: {tech_stack}
- CRM: {crm} | Sales engagement: {sales_engagement}

TRIGGER 4 — Funding & M&A (new capital = board mandate to scale fast):
- Recently funded: {funded_90d} | Stage: {funding_stage}
- M&A activity: {acquisition_activity}

TRIGGER 5 — Hidden Intent (expansion signals before they post a job):
- News keywords: {news_keywords}
- Intent signals found: {intent_signals_count}

Scoring:
- 8-10: THREE OR MORE triggers firing simultaneously. Real urgency. Be skeptical.
- 5-7: One or two triggers. Timing unclear.
- 1-4: Weak signals or noise.

Confidence (50-100): rate evidence quality using the bands in your system instructions — not your certainty about the score.

Return ONLY valid JSON:
{{"score": <1-10>, "confidence": <50-100>, "reasoning": "<specific, max 15 words>", "top_signal": "<single strongest trigger>", "contact_window": "<now|2-4 weeks|not yet>", "aha_moment": "<1-2 sentences: name the specific triggers firing + what it means for buying urgency>"}}\
"""

OPENER_PROMPT_V1 = """Write ONE cold outreach opening sentence for this B2B prospect.

{contact_context}Company: {company_name}

Raw signal evidence — use these exact facts, not your own paraphrase:
{evidence_block}

Hard rules:
- Maximum 20 words
- Do NOT start with "I noticed" or "I came across" or any compliment
- Reference a SPECIFIC fact from the evidence above (exact role title, funding amount, headline)
- Sound like a human wrote this at 9am after reading TechCrunch
- No em-dashes, no corporate speak

Return ONLY the sentence. Nothing else. No quotes."""

SCORING_PROMPT_V2 = """Score this company's buying intent across 5 GTM triggers.

Company: {company_name} | Domain: {domain}{industry_line}{employee_line}{contact_line}

TRIGGER 1 — Leadership Change (new VPs audit old tools, need quick wins):
- New exec hired: {new_exec_hire}{new_exec_line}{leadership_evidence_line}

TRIGGER 2 — Hiring Signals (JDs broadcast internal bottlenecks):
- Hiring GTM/Sales: {hiring_gtm} | Open GTM roles: {open_gtm_roles}
- JD keywords found: {hiring_keywords}{hiring_evidence_line}

TRIGGER 3 — Tech Stack (filter ruthlessly — don't pitch HubSpot to Salesforce):
- Detected tools: {tech_stack}
- CRM: {crm} | Sales engagement: {sales_engagement}{tech_evidence_line}

TRIGGER 4 — Funding & M&A (new capital = board mandate to scale fast):
- Recently funded: {funded_90d} | Stage: {funding_stage}
- M&A activity: {acquisition_activity}{funding_evidence_line}

TRIGGER 5 — Hidden Intent (expansion signals before they post a job):
- News keywords: {news_keywords}
- Intent signals found: {intent_signals_count}{intent_evidence_line}

Scoring rules:
- 8-10: THREE OR MORE triggers firing simultaneously. Real urgency. Be skeptical.
- 5-7: One or two triggers. Timing unclear.
- 1-4: Weak signals or noise.

Confidence (50-100): rate evidence quality using the bands in your system instructions — not your certainty about the score.

pitch_block: 3-5 sentences. Write like a sales intelligence analyst. Name the SPECIFIC signals, explain WHY they create a buying window right now, and what changes for the buyer in the next 30-60 days if they don't act. No marketing language.

signal_scores: score each trigger 0-10 independently. Use 0 when data is absent for that trigger.

Return ONLY valid JSON:
{{"score": <1-10>, "confidence": <50-100>, "reasoning": "<specific, max 15 words>", "top_signal": "<single strongest trigger>", "contact_window": "<now|2-4 weeks|not yet>", "aha_moment": "<1-2 sentences: specific triggers + buying urgency>", "signal_scores": {{"leadership_change": <0-10>, "hiring": <0-10>, "tech_stack": <0-10>, "funding": <0-10>, "hidden_intent": <0-10>}}, "pitch_block": "<3-5 sentences domain-specific sales insight>"}}\
"""
