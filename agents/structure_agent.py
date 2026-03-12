"""
agents/structure_agent.py
─────────────────────────
Responsible for:
  Analyzing the inspiration site's HTML and producing a structure.json —
  the section map and component hierarchy for the new site.

Outputs a skeleton the Assembly Agent will flesh out with real content.
"""

import json
import re
from bs4 import BeautifulSoup
from rich.console import Console
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from state import SiteBuilderState

console = Console()

llm = ChatOllama(
    model="gpt-oss:20b",
    base_url="http://localhost:11434",
    format="json",
    temperature=0,
)

SYSTEM_PROMPT = """You are a web architect. Analyze a website's structure and produce 
a section map for recreating it with fresh content.

Respond ONLY with valid JSON — no markdown, no explanation.

Output this exact structure:
{
  "sections": [
    {
      "id": "navbar",
      "type": "navbar",
      "description": "Top navigation bar with logo and links",
      "components": ["logo", "nav_links", "cta_button"]
    },
    {
      "id": "hero",
      "type": "hero",
      "description": "Full-width hero with headline, subtext, and CTA",
      "components": ["headline", "subheadline", "cta_button", "hero_image"]
    }
  ],
  "layout_notes": "Brief notes on the overall layout pattern",
  "color_scheme": "light|dark|mixed"
}

Common section types: navbar, hero, features, pricing, testimonials, 
cta_banner, footer, gallery, about, team, faq, contact"""


def _summarize_html(html: str) -> str:
    """Extract structural signals from HTML without sending 100k chars to the LLM."""
    soup = BeautifulSoup(html, "html.parser")

    # Get tag counts as structure signal
    structural_tags = ["nav", "header", "main", "section", "article", "aside", "footer"]
    tag_summary = {t: len(soup.find_all(t)) for t in structural_tags}

    # Get class names as semantic signal (top 40 most common)
    all_classes = []
    for tag in soup.find_all(class_=True):
        all_classes.extend(tag.get("class", []))
    from collections import Counter
    top_classes = [c for c, _ in Counter(all_classes).most_common(40)]

    # Get H1-H3 headings
    headings = [h.get_text(strip=True)[:80] for h in soup.find_all(["h1", "h2", "h3"])[:10]]

    return f"""
Tag counts: {tag_summary}
Top CSS classes: {top_classes}
Headings found: {headings}
"""


def structure_agent(state: SiteBuilderState) -> dict:
    console.rule("[bold yellow]🏗  STRUCTURE AGENT")

    html_summary = _summarize_html(state.get("raw_html", ""))

    user_prompt = f"""Inspiration site structure signals:

{html_summary}

Style notes: {state.get('style_json', {}).get('aesthetic_notes', 'unknown')}

Produce the structure.json for the new website now."""

    try:
        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])

        raw = response.content.strip().replace("```json", "").replace("```", "").strip()
        structure_json = json.loads(raw)

        sections = structure_json.get("sections", [])
        console.print(f"  [green]✓[/green] Structure defined — {len(sections)} sections:")
        for s in sections:
            console.print(f"    [{s['type']}] {s['description'][:60]}")

        return {
            "structure_json": structure_json,
            "current_step": "hil_structure_approval",
            "errors": state.get("errors", []),
        }

    except Exception as e:
        console.print(f"  [red]✗ Structure agent failed: {e}[/red]")
        return {
            "structure_json": _fallback_structure(),
            "current_step": "hil_structure_approval",
            "errors": state.get("errors", []) + [f"structure_agent: {str(e)}"],
        }


def _fallback_structure() -> dict:
    return {
        "sections": [
            {"id": "navbar",     "type": "navbar",       "description": "Navigation bar with logo and links", "components": ["logo", "nav_links", "cta_button"]},
            {"id": "hero",       "type": "hero",         "description": "Hero section with headline and CTA",  "components": ["headline", "subheadline", "cta_button"]},
            {"id": "features",   "type": "features",     "description": "3-column feature highlights",        "components": ["feature_card"]},
            {"id": "cta",        "type": "cta_banner",   "description": "Call to action banner",              "components": ["headline", "cta_button"]},
            {"id": "footer",     "type": "footer",       "description": "Footer with links and copyright",    "components": ["logo", "links", "copyright"]},
        ],
        "layout_notes": "Standard SaaS landing page layout",
        "color_scheme": "light",
    }
