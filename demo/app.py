"""
SignalOS Gradio Demo — type a domain, get a scored lead with pitch block.
Run: python demo/app.py
Requires: SIGNALOS_API_URL env var (default http://localhost:8000)
"""
import os
import json
import gradio as gr
import httpx

API_URL = os.environ.get("SIGNALOS_API_URL", "http://localhost:8000")

SCORE_COLOR = {
    range(1, 4): "🔴",
    range(4, 7): "🟡",
    range(7, 11): "🟢",
}


def _score_badge(score) -> str:
    if score is None:
        return "—"
    for r, badge in SCORE_COLOR.items():
        if score in r:
            return f"{badge} {score}/10"
    return f"{score}/10"


def score_company(
    api_url: str,
    company_name: str,
    domain: str,
    client_id: str,
    funded_90d: bool,
    hiring_gtm: bool,
    growth_pct: float,
    tech_stack_raw: str,
) -> tuple:
    tech_stack = [t.strip() for t in tech_stack_raw.split(",") if t.strip()]

    payload = {
        "company_name": company_name.strip(),
        "domain": domain.strip().lstrip("https://").lstrip("http://").rstrip("/"),
        "client_id": client_id.strip() or "demo",
        "signals": {
            "funded_90d": funded_90d,
            "hiring_gtm": hiring_gtm,
            "growth_pct": growth_pct,
            "tech_stack": tech_stack,
        },
    }

    try:
        resp = httpx.post(f"{api_url.rstrip('/')}/score-company", json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        err = f"API error {e.response.status_code}: {e.response.text}"
        return err, "—", "—", "—", "—", "—", "—", "{}"
    except Exception as e:
        return str(e), "—", "—", "—", "—", "—", "—", "{}"

    if data.get("error"):
        return data["error"], "—", "—", "—", "—", "—", "—", json.dumps(data, indent=2)

    if data.get("suppressed"):
        note = f"Suppressed — {data.get('suppression_reason', 'cooldown active')}"
        return note, "—", "—", "—", "—", "—", "—", json.dumps(data, indent=2)

    score_str      = _score_badge(data.get("score"))
    contact_window = data.get("contact_window") or "—"
    top_signal     = data.get("top_signal") or "—"
    aha_moment     = data.get("aha_moment") or "—"
    email_opener   = data.get("email_opener") or "—"
    reasoning      = data.get("reasoning") or "—"
    cost           = f"${data.get('cost_usd', 0):.4f}" if data.get("cost_usd") else "—"

    status_parts = []
    if data.get("cached"):
        status_parts.append("cached")
    if data.get("alerted_slack"):
        status_parts.append("Slack alerted")
    if data.get("pushed_to_crm"):
        status_parts.append("CRM pushed")
    if data.get("requires_human_review"):
        status_parts.append("human review required")
    status = " · ".join(status_parts) if status_parts else "scored"

    return status, score_str, contact_window, top_signal, aha_moment, email_opener, reasoning, cost, json.dumps(data, indent=2)


def build_ui():
    with gr.Blocks(title="SignalOS — GTM Signal Intelligence", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            """
# SignalOS — GTM Signal Intelligence
Score any company's buying intent using Claude Sonnet. Detects funding, hiring, leadership change, tech stack & growth signals.
"""
        )

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### Company Details")
                api_url_box   = gr.Textbox(label="API URL", value=API_URL, placeholder="http://localhost:8000")
                company_input = gr.Textbox(label="Company Name", placeholder="Acme Corp")
                domain_input  = gr.Textbox(label="Domain", placeholder="acme.com")
                client_input  = gr.Textbox(label="Client ID", value="demo", placeholder="demo")

                gr.Markdown("### Known Signals (optional — leave blank for auto-detect)")
                funded_check  = gr.Checkbox(label="Funded in last 90 days")
                hiring_check  = gr.Checkbox(label="Hiring GTM roles")
                growth_slider = gr.Slider(minimum=0, maximum=200, step=5, label="Growth % (headcount)", value=0)
                tech_input    = gr.Textbox(label="Tech Stack (comma-separated)", placeholder="Salesforce, Outreach")

                score_btn = gr.Button("Score Company", variant="primary", size="lg")

            with gr.Column(scale=2):
                gr.Markdown("### Results")
                with gr.Row():
                    status_out  = gr.Textbox(label="Status", interactive=False)
                    score_out   = gr.Textbox(label="Score", interactive=False)
                    window_out  = gr.Textbox(label="Contact Window", interactive=False)
                    cost_out    = gr.Textbox(label="Claude Cost", interactive=False)

                top_signal_out  = gr.Textbox(label="Top Signal", interactive=False)
                aha_out         = gr.Textbox(label="Aha Moment", interactive=False, lines=2)
                opener_out      = gr.Textbox(label="Email Opener", interactive=False, lines=2)
                reasoning_out   = gr.Textbox(label="Claude Reasoning", interactive=False, lines=4)

                with gr.Accordion("Full JSON Response", open=False):
                    json_out = gr.Code(language="json", label="Raw API Response")

        score_btn.click(
            fn=score_company,
            inputs=[
                api_url_box, company_input, domain_input, client_input,
                funded_check, hiring_check, growth_slider, tech_input,
            ],
            outputs=[
                status_out, score_out, window_out, top_signal_out,
                aha_out, opener_out, reasoning_out, cost_out, json_out,
            ],
        )

        gr.Examples(
            examples=[
                [API_URL, "Notion", "notion.so", "demo", False, True, 40, "Salesforce, Slack"],
                [API_URL, "Rippling", "rippling.com", "demo", True, True, 80, "Workday, Greenhouse"],
                [API_URL, "Acme Corp", "acme.com", "demo", True, False, 0, "HubSpot"],
            ],
            inputs=[api_url_box, company_input, domain_input, client_input, funded_check, hiring_check, growth_slider, tech_input],
            label="Example Companies",
        )

    return demo


if __name__ == "__main__":
    ui = build_ui()
    ui.launch(server_name="0.0.0.0", server_port=7860, share=False)
