"""
agents/assembly_agent.py
────────────────────────
Responsible for:
  Taking style.json + structure.json + user_content and generating
  the final, complete HTML/CSS/JS website.

Uses the LLM to write the actual code. Provides rich context
in small, focused chunks to stay within 20B model limits.
"""

import json
from rich.console import Console
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from state import SiteBuilderState

console = Console()

# Assembly uses a bigger context but still JSON-free (returns HTML)
llm = ChatOllama(
    model="gpt-oss:20b",
    base_url="http://localhost:11434",
    temperature=0.1,
    num_ctx=8192,
)

SYSTEM_PROMPT = """You are an expert frontend developer. 
Build a complete, single-file HTML website from the provided style, structure, and content data.

RULES:
- Return ONLY the HTML. No explanation. No markdown fences. Start with <!DOCTYPE html>
- All CSS must be inline in a <style> block in <head>
- Use Google Fonts import for the specified fonts
- Mobile responsive using CSS Grid and Flexbox
- Smooth scroll, hover transitions
- Every section from the structure must appear
- Use the EXACT colors, fonts, spacing from style.json
- Fill content from user_content exactly as given
- Use semantic HTML5 tags (nav, main, section, footer, article)
- The result must look professional and polished"""


def assembly_agent(state: SiteBuilderState) -> dict:
    console.rule("[bold blue]🔧  ASSEMBLY AGENT")

    style   = state.get("style_json", {})
    struct  = state.get("structure_json", {})
    content = state.get("user_content", {})

    # Build a compact but rich prompt
    user_prompt = f"""Build the website with these exact specifications:

## STYLE CONFIG
{json.dumps(style, indent=2)}

## SITE STRUCTURE
{json.dumps(struct, indent=2)}

## USER CONTENT
Brand: {content.get('brand_name', 'My Brand')}
Tagline: {content.get('tagline', '')}
Description: {content.get('description', '')}
CTA: {content.get('cta_text', 'Get Started')} → {content.get('cta_url', '#')}
Nav links: {content.get('nav_links', [])}
Footer: {content.get('footer_copy', '')}

Section content:
{json.dumps(content.get('sections', []), indent=2)}

Generate the complete HTML file now."""

    console.print("  Generating HTML... [dim](this may take 30–60s on 20B)[/dim]")

    try:
        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])

        html = response.content.strip()

        # Clean up any accidental markdown wrapping
        if html.startswith("```"):
            html = html.split("\n", 1)[1]
            html = html.rsplit("```", 1)[0]

        # Ensure it starts with doctype
        if "<!DOCTYPE" not in html and "<html" not in html:
            html = _wrap_partial_html(html, style, content)

        console.print(f"  [green]✓[/green] HTML generated — {len(html):,} characters")

        return {
            "final_output": html,
            "current_step": "verification",
            "errors": state.get("errors", []),
        }

    except Exception as e:
        console.print(f"  [red]✗ Assembly failed: {e}[/red]")
        fallback = _minimal_fallback_html(content, style)
        return {
            "final_output": fallback,
            "current_step": "verification",
            "errors": state.get("errors", []) + [f"assembly_agent: {str(e)}"],
        }


def _wrap_partial_html(partial: str, style: dict, content: dict) -> str:
    """Wrap partial HTML output in a proper document shell."""
    brand = content.get("brand_name", "My Site")
    primary = style.get("primary_color", "#2563eb")
    bg = style.get("background_color", "#ffffff")
    text = style.get("text_color", "#111827")
    font = style.get("body_font", "Inter")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{brand}</title>
<link href="https://fonts.googleapis.com/css2?family={font.replace(' ', '+')}:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: '{font}', sans-serif; background:{bg}; color:{text}; }}
  :root {{ --primary:{primary}; }}
</style>
</head>
<body>
{partial}
</body>
</html>"""


def _minimal_fallback_html(content: dict, style: dict) -> str:
    brand = content.get("brand_name", "My Site")
    tagline = content.get("tagline", "Welcome")
    primary = style.get("primary_color", "#2563eb")
    font = style.get("body_font", "Inter")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{brand}</title>
<link href="https://fonts.googleapis.com/css2?family={font.replace(' ', '+')}:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: '{font}', sans-serif; background:#fff; color:#111; }}
  nav {{ background:{primary}; padding:1rem 2rem; display:flex; justify-content:space-between; align-items:center; }}
  nav a {{ color:#fff; text-decoration:none; font-weight:600; font-size:1.2rem; }}
  .hero {{ padding:6rem 2rem; text-align:center; }}
  .hero h1 {{ font-size:3rem; margin-bottom:1rem; color:#111; }}
  .hero p {{ font-size:1.2rem; color:#555; margin-bottom:2rem; }}
  .btn {{ background:{primary}; color:#fff; padding:14px 32px; border:none; border-radius:8px; font-size:1rem; font-weight:600; cursor:pointer; text-decoration:none; }}
  footer {{ background:#111; color:#aaa; text-align:center; padding:2rem; margin-top:4rem; }}
</style>
</head>
<body>
<nav><a href="#">{brand}</a></nav>
<main>
  <section class="hero">
    <h1>{tagline}</h1>
    <p>{content.get('description', '')}</p>
    <a href="{content.get('cta_url','#')}" class="btn">{content.get('cta_text','Get Started')}</a>
  </section>
</main>
<footer><p>{content.get('footer_copy', f'© 2025 {brand}')}</p></footer>
</body>
</html>"""
