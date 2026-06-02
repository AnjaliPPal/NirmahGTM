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

OPENER_PROMPT_V1 = """Write a cold outreach opening for this B2B prospect using the DATA → ASSUMPTION → CTA framework.

{contact_context}Company: {company_name}

Verified signal evidence — use ONLY these facts, never invent:
{evidence_block}

FRAMEWORK (follow in order):
1. DATA — state ONE specific verifiable fact from the evidence above (exact role title, funding amount, headline date, stack gap)
2. ASSUMPTION — draw a UNIQUE, non-obvious conclusion that only fits this company. Ask: what internal pressure does this fact create RIGHT NOW? Never write "you're scaling fast" or "you must be busy" — those fit 10,000 companies.
3. CTA — knee-jerk CTA only: never "hop on a 15-min call". Lead-magnet style: "Would you be opposed to me sending over [specific thing]?"

HARD RULES:
- Do NOT start with: "I", "Hi", "Hey", "Congrats", "Hope", "Reaching out", "Just"
- FORBIDDEN words: leverage, synergy, streamline, pain points, excited, resonate, empower, scale your team
- If first name is known, address them by first name only (no last name)
- DATA+ASSUMPTION block: under 25 words
- Full message: under 45 words total
- Sound like a human wrote this at 9am, not a template

BAD (never write like this):
"Hi Sarah, I noticed Acme just raised a Series B. Would love to hop on a quick 15-min call to see if we can help you scale your sales team. Let me know!"
Why it fails: generic DATA (raising = everyone does it), lazy ASSUMPTION (scale your team = fits any company), bad CTA (hop on a call = high commitment = no reply).

GOOD (write like this):
"Sarah — Acme closing $80M with Salesforce but no engagement tool means your new SDRs have no sequencing layer. Would you be opposed to me sending over what three similar-stage teams plugged in first?"
Why it works: specific DATA (exact gap), sharp ASSUMPTION (SDRs without sequences = known risk), knee-jerk CTA (send something over = zero commitment).

Return ONLY the message. No quotes. No preamble."""

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
- M&A activity: {acquisition_activity}{funding_evidence_line}{funding_date_line}{funding_url_line}

TRIGGER 5 — Hidden Intent (expansion signals before they post a job):
- News keywords: {news_keywords}
- Intent signals found: {intent_signals_count}{intent_evidence_line}
{rag_context}
Scoring rules:
- 8-10: THREE OR MORE triggers firing simultaneously. Real urgency. Be skeptical.
- 5-7: One or two triggers. Timing unclear.
- 1-4: Weak signals or noise.

Confidence (50-100): rate evidence quality using the bands in your system instructions — not your certainty about the score.

pitch_block: 3-5 sentences. Write like a sales intelligence analyst. Name the SPECIFIC signals, explain WHY they create a buying window right now, and what changes for the buyer in the next 30-60 days if they don't act. No marketing language.

signal_scores: score each trigger 0-10 independently. Use 0 when data is absent for that trigger.

Return ONLY valid JSON:
{{"score": <1-10>, "confidence": <50-100>, "reasoning": "<specific, max 15 words>", "top_signal": "<single strongest trigger>", "contact_window": "<now|2-4 weeks|not yet>", "aha_moment": "<RULE: use ONLY facts from the Real headline above. If a Real headline exists: sentence 1 = exact amount + stage + date from headline (e.g. 'Exaforce raised $125M Series B on May 12 2026'). Sentence 2 = specific internal pressure this creates (board mandate, headcount unlocked, tool budgets approved). NEVER say 'may miss the opportunity' or 'creates internal pressure to scale'. If no Real headline: write exactly 'Funding flagged — no public announcement confirmed. Verify amount and date directly before outreach.'>", "signal_scores": {{"leadership_change": <0-10>, "hiring": <0-10>, "tech_stack": <0-10>, "funding": <0-10>, "hidden_intent": <0-10>}}, "pitch_block": "<3-5 sentences domain-specific sales insight>"}}\
"""
