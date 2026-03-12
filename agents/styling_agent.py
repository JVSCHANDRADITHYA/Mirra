"""
agents/styling_agent.py
───────────────────────
Responsible for:
  Taking design_tokens (colors, fonts, spacing) and asking the LLM
  to produce a structured style.json — the CSS strategy for the new site.

Single focused prompt. One job. JSON output forced.
"""

import json
from rich.console import Console
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from state import SiteBuilderState

console = Console()

# ── LLM (JSON mode forced) ────────────────────────────────────────────────────
llm = ChatOllama(
    model="gpt-oss:20b",
    base_url="http://localhost:11434",
    format="json",
    temperature=0,
)

SYSTEM_PROMPT = """You are a CSS design system expert. 
Given design tokens from an inspiration website, produce a style.json config 
for building a NEW website inspired by the same aesthetic.

You MUST respond with ONLY valid JSON — no markdown, no explanation, no backticks.

Output this exact structure:
{
  "primary_color": "#hex",
  "secondary_color": "#hex",
  "accent_color": "#hex",
  "background_color": "#hex",
  "text_color": "#hex",
  "heading_font": "Font Name",
  "body_font": "Font Name",
  "base_font_size": "16px",
  "heading_sizes": {"h1": "3rem", "h2": "2rem", "h3": "1.5rem"},
  "spacing": {"sm": "8px", "md": "16px", "lg": "32px", "xl": "64px"},
  "border_radius": "8px",
  "box_shadow": "0 4px 20px rgba(0,0,0,0.1)",
  "button_style": {"padding": "12px 28px", "border_radius": "6px", "font_weight": "600"},
  "card_style": {"padding": "24px", "border_radius": "12px", "shadow": "0 2px 12px rgba(0,0,0,0.08)"},
  "nav_style": {"background": "#hex", "text_color": "#hex", "height": "64px"},
  "aesthetic_notes": "Brief description of the visual style (e.g. minimal dark SaaS, warm e-commerce)"
}"""


def styling_agent(state: SiteBuilderState) -> dict:
    console.rule("[bold magenta]🎨  STYLING AGENT")

    tokens = state.get("design_tokens", {})

    user_prompt = f"""Here are the design tokens extracted from the inspiration site:

Colors: {tokens.get('colors', [])[:10]}
Fonts: {tokens.get('fonts', [])}
Spacing scale: {tokens.get('spacing_scale', [])[:8]}
Border radius values: {tokens.get('border_radius', [])}
Box shadows: {tokens.get('box_shadows', [])}
CSS variables: {dict(list(tokens.get('css_variables', {}).items())[:15])}

Produce the style.json for the new website now."""

    try:
        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])

        raw = response.content.strip()
        # Strip any accidental markdown fences
        raw = raw.replace("```json", "").replace("```", "").strip()
        style_json = json.loads(raw)

        console.print(f"  [green]✓[/green] style.json generated")
        console.print(f"    Aesthetic : {style_json.get('aesthetic_notes', '')}")
        console.print(f"    Primary   : {style_json.get('primary_color')}")
        console.print(f"    Fonts     : {style_json.get('heading_font')} / {style_json.get('body_font')}")

        return {
            "style_json": style_json,
            "current_step": "structure",
            "errors": state.get("errors", []),
        }

    except Exception as e:
        console.print(f"  [red]✗ Styling agent failed: {e}[/red]")
        # Provide a safe fallback style_json
        return {
            "style_json": _fallback_style(),
            "current_step": "structure",
            "errors": state.get("errors", []) + [f"styling_agent: {str(e)}"],
        }


def _fallback_style() -> dict:
    return {
        "primary_color": "#2563eb",
        "secondary_color": "#1e40af",
        "accent_color": "#f59e0b",
        "background_color": "#ffffff",
        "text_color": "#111827",
        "heading_font": "Inter",
        "body_font": "Inter",
        "base_font_size": "16px",
        "heading_sizes": {"h1": "3rem", "h2": "2rem", "h3": "1.5rem"},
        "spacing": {"sm": "8px", "md": "16px", "lg": "32px", "xl": "64px"},
        "border_radius": "8px",
        "box_shadow": "0 4px 20px rgba(0,0,0,0.1)",
        "button_style": {"padding": "12px 28px", "border_radius": "6px", "font_weight": "600"},
        "card_style": {"padding": "24px", "border_radius": "12px", "shadow": "0 2px 12px rgba(0,0,0,0.08)"},
        "nav_style": {"background": "#ffffff", "text_color": "#111827", "height": "64px"},
        "aesthetic_notes": "Clean modern SaaS (fallback defaults)",
    }