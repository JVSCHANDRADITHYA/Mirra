"""
agents/content_agent.py
────────────────────────
HIL agent.

Key design: interrupt() pauses the graph. main.py then calls
collect_content_from_user() DIRECTLY (outside the graph stream)
to gather all content via CLI prompts. Then resumes the graph
with Command(resume={"user_content": {...}}).

This avoids rich prompts running inside LangGraph's stream loop
which can swallow output.
"""

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from langgraph.types import interrupt
from state import SiteBuilderState

console = Console()


def content_agent(state: SiteBuilderState) -> dict:
    console.rule("[bold green]👤  CONTENT AGENT  [HIL]")

    structure = state.get("structure_json", {})
    sections  = structure.get("sections", [])
    style     = state.get("style_json", {})

    # Show structure preview
    _show_structure_preview(sections, style)

    # Pause graph — main.py will collect content and resume with it
    resume_data = interrupt({
        "type":     "structure_approval",
        "sections": [{"id": s["id"], "type": s["type"], "description": s["description"]}
                     for s in sections],
        "style":    style,
    })

    # resume_data contains user_content collected by main.py
    user_content = resume_data.get("user_content") if isinstance(resume_data, dict) else None

    if not user_content:
        # Fallback: if somehow content wasn't passed in, collect inline
        console.print("  [yellow]No content in resume payload — collecting inline[/yellow]")
        user_content = collect_content_from_user(sections)

    _show_content_summary(user_content)
    console.print("\n  [green]✓[/green] Content collected — generating site...\n")

    return {
        "user_content":  user_content,
        "hil_approvals": state.get("hil_approvals", []) + [{"step": "content", "sections": len(sections)}],
        "current_step":  "assembly",
        "errors":        state.get("errors", []),
    }


# ─── Standalone content collector (called from main.py, OUTSIDE the graph) ───

def collect_content_from_user(sections: list) -> dict:
    """
    Called directly by main.py after interrupt() pauses the graph.
    Runs in normal terminal context — rich prompts work fine here.
    """
    content: dict = {}

    console.print(Panel("[bold]BRAND BASICS[/bold]", style="green"))
    content["brand_name"]  = Prompt.ask("  Brand / business name")
    content["tagline"]     = Prompt.ask("  Tagline or main headline")
    content["description"] = Prompt.ask("  One sentence about what you do")
    content["cta_text"]    = Prompt.ask("  Main CTA button text", default="Get Started")
    content["cta_url"]     = Prompt.ask("  CTA URL", default="#")

    console.print(Panel("[bold]NAVIGATION[/bold]", style="green"))
    nav_raw = Prompt.ask("  Nav links (comma-separated, e.g. Home, About, Work, Contact)")
    content["nav_links"] = [n.strip() for n in nav_raw.split(",") if n.strip()]

    section_content: list = []
    for s in sections:
        t = s["type"]
        if t in ("navbar", "footer"):
            continue

        console.print(Panel(f"[bold]{t.upper()}[/bold] — {s['description']}", style="blue"))
        sc: dict = {"section_id": s["id"], "type": t, "label": s.get("id", t)}

        if t == "hero":
            sc["headline"]    = Prompt.ask("  Hero headline", default=content.get("tagline", ""))
            sc["subheadline"] = Prompt.ask("  Hero subtext")
            sc["cta_text"]    = Prompt.ask("  CTA button", default=content.get("cta_text", "Get Started"))

        elif t == "features":
            num = int(Prompt.ask("  How many items?", default="3"))
            sc["features"] = []
            for i in range(num):
                console.print(f"  [dim]Item {i+1}[/dim]")
                sc["features"].append({
                    "icon":        Prompt.ask("    Icon (emoji)", default="⚡"),
                    "title":       Prompt.ask("    Title"),
                    "description": Prompt.ask("    Description"),
                })

        elif t == "pricing":
            num = int(Prompt.ask("  How many tiers?", default="3"))
            sc["tiers"] = []
            for i in range(num):
                console.print(f"  [dim]Tier {i+1}[/dim]")
                sc["tiers"].append({
                    "name":     Prompt.ask("    Name"),
                    "price":    Prompt.ask("    Price"),
                    "features": Prompt.ask("    Features (comma-separated)").split(","),
                    "cta":      Prompt.ask("    CTA", default="Get Started"),
                })

        elif t == "testimonials":
            num = int(Prompt.ask("  How many testimonials?", default="2"))
            sc["testimonials"] = []
            for i in range(num):
                sc["testimonials"].append({
                    "quote":  Prompt.ask(f"  Quote {i+1}"),
                    "author": Prompt.ask(f"  Author"),
                    "role":   Prompt.ask(f"  Role"),
                })

        elif t in ("cta_banner", "cta"):
            sc["headline"] = Prompt.ask("  Banner headline")
            sc["cta_text"] = Prompt.ask("  CTA text", default="Get Started")

        elif t == "faq":
            num = int(Prompt.ask("  How many FAQs?", default="3"))
            sc["faqs"] = []
            for i in range(num):
                sc["faqs"].append({
                    "question": Prompt.ask(f"  Q{i+1}"),
                    "answer":   Prompt.ask(f"  A{i+1}"),
                })

        elif t in ("about", "gallery", "contact", "team"):
            sc["headline"] = Prompt.ask(f"  {t.capitalize()} section headline")
            sc["body"]     = Prompt.ask(f"  {t.capitalize()} body text")

        else:
            sc["content"] = Prompt.ask(f"  Content for '{s['id']}'")

        section_content.append(sc)

    content["sections"]     = section_content
    content["footer_links"] = content.get("nav_links", [])
    content["footer_copy"]  = Prompt.ask(
        "\n  Footer copyright",
        default=f"© 2025 {content.get('brand_name', 'Your Company')}. All rights reserved."
    )
    return content


# ─── Display helpers ──────────────────────────────────────────────────────────

def _show_structure_preview(sections: list, style: dict):
    console.print()
    table = Table(title="📐 Proposed Site Structure", show_header=True, header_style="bold cyan")
    table.add_column("#",    style="dim", width=4)
    table.add_column("ID",   style="bold")
    table.add_column("Type", style="cyan")
    table.add_column("Description")
    for i, s in enumerate(sections, 1):
        table.add_row(str(i), s["id"], s["type"], s["description"])
    console.print(table)
    console.print(f"\n  [dim]Aesthetic : {style.get('aesthetic_notes', '')}[/dim]")
    console.print(f"  [dim]Colors    : primary={style.get('primary_color')} · accent={style.get('accent_color')}[/dim]\n")


def _show_content_summary(content: dict):
    console.print()
    console.print(Panel(
        f"[bold]{content.get('brand_name')}[/bold]\n"
        f"[italic]{content.get('tagline')}[/italic]\n\n"
        f"{content.get('description')}\n\n"
        f"Sections filled : {len(content.get('sections', []))}\n"
        f"Nav             : {', '.join(content.get('nav_links', []))}",
        title="📋 Content Summary", style="green",
    ))