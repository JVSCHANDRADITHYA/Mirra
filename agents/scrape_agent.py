"""
agents/scrape_agent.py
─────────────────────
Scrapes the inspiration site. On total failure, falls back to
asking the user to describe the style they want manually.
"""

from rich.console import Console
from rich.prompt import Prompt, Confirm
from state import SiteBuilderState
from tools.scraper import scrape_site
from tools.css_parser import extract_design_tokens

console = Console()


def scrape_agent(state: SiteBuilderState) -> dict:
    console.rule("[bold cyan]🕷  SCRAPE AGENT")

    # ── If local HTML file was provided, use it directly ─────────────────────
    local_file = state.get("local_file")
    if local_file:
        try:
            with open(local_file, "r", encoding="utf-8", errors="replace") as f:
                raw_html = f.read()
            console.print(f"  [green]✓[/green] Loaded local file: {local_file}")
            tokens = extract_design_tokens("", raw_html)
            return _success(state, raw_html, "", None, tokens)
        except Exception as e:
            console.print(f"  [red]✗ Could not read local file: {e}[/red]")

    # ── Try live scraping ─────────────────────────────────────────────────────
    url = state["url"]
    console.print(f"  Scraping: {url}")

    try:
        result  = scrape_site(url, use_playwright=False)
        tokens  = extract_design_tokens(result["raw_css"], result["raw_html"])

        console.print(f"  [green]✓[/green] HTML fetched")
        console.print(f"  [green]✓[/green] Design tokens extracted")
        console.print(f"    Colors   : {tokens['colors'][:5]}")
        console.print(f"    Fonts    : {tokens['fonts']}")
        console.print(f"    Spacing  : {tokens['spacing_scale'][:5]}")
        return _success(state, result["raw_html"], result["raw_css"],
                        result["screenshot_b64"], tokens)

    except Exception as e:
        console.print(f"\n  [red bold]✗ Scraping failed: {e}[/red bold]")
        console.print("\n  [yellow]The site is blocking all automated access (Cloudflare / firewall).[/yellow]")
        console.print("  [dim]Options:[/dim]")
        console.print("  [dim]  1. Save the page manually (browser → Save As → Complete) and use --local[/dim]")
        console.print("  [dim]  2. Describe the style and we'll generate it from scratch[/dim]\n")

        use_manual = Confirm.ask("  Describe the style manually and continue?", default=True)
        if use_manual:
            tokens = _ask_manual_style()
            console.print("  [green]✓[/green] Manual style tokens collected")
            return _success(state, "", "", None, tokens,
                            error=f"scrape_agent: site blocked ({e})")
        else:
            console.print("  [red]Aborting. Try saving the page locally and using --local path/to/file.html[/red]")
            return {
                **_empty(state),
                "current_step": "done",
                "errors": state.get("errors", []) + [f"scrape_agent: site blocked, user aborted"],
            }


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _ask_manual_style() -> dict:
    """Ask user to describe the inspiration site's style when scraping fails."""
    console.print("\n  [bold]Describe the inspiration site's style:[/bold]")

    color_scheme = Prompt.ask(
        "  Color scheme",
        choices=["dark", "light", "colorful", "minimal", "gradient"],
        default="light"
    )
    primary_color = Prompt.ask("  Primary/brand color (hex or name, e.g. #1E90FF or navy)", default="#2563eb")
    accent_color  = Prompt.ask("  Accent color (e.g. #f59e0b)", default="#f59e0b")
    bg_color      = Prompt.ask("  Background color", default="#ffffff" if color_scheme == "light" else "#0f0f0f")
    font_style    = Prompt.ask(
        "  Font style",
        choices=["sans-serif modern", "serif elegant", "monospace tech", "geometric bold"],
        default="sans-serif modern"
    )
    aesthetic     = Prompt.ask(
        "  Overall aesthetic",
        choices=["minimal clean", "bold vibrant", "dark professional", "warm friendly", "glassmorphism"],
        default="minimal clean"
    )
    layout_type   = Prompt.ask(
        "  Layout type",
        choices=["landing page", "portfolio", "e-commerce", "blog", "saas"],
        default="landing page"
    )

    font_map = {
        "sans-serif modern":  "Inter",
        "serif elegant":      "Playfair Display",
        "monospace tech":     "JetBrains Mono",
        "geometric bold":     "Space Grotesk",
    }

    return {
        "colors":        [primary_color, accent_color, bg_color],
        "fonts":         [font_map.get(font_style, "Inter")],
        "spacing_scale": ["8px", "16px", "24px", "32px", "48px", "64px"],
        "css_variables": {
            "--primary":    primary_color,
            "--accent":     accent_color,
            "--background": bg_color,
        },
        "border_radius": ["8px", "12px"],
        "box_shadows":   ["0 4px 20px rgba(0,0,0,0.1)"],
        "_manual": True,
        "_aesthetic": aesthetic,
        "_layout_type": layout_type,
        "_color_scheme": color_scheme,
    }


def _success(state, raw_html, raw_css, screenshot_b64, tokens, error=None):
    errors = state.get("errors", [])
    if error:
        errors = errors + [error]
    return {
        "raw_html":       raw_html,
        "raw_css":        raw_css,
        "screenshot_b64": screenshot_b64,
        "design_tokens":  tokens,
        "current_step":   "styling",
        "errors":         errors,
    }


def _empty(state):
    return {
        "raw_html": "", "raw_css": "", "screenshot_b64": None,
        "design_tokens": {}, "current_step": "styling",
        "errors": state.get("errors", []),
    }