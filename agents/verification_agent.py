"""
agents/verification_agent.py
────────────────────────────
Responsible for:
  Rule-based checks on the final HTML. No LLM needed here.
  Checks: style fidelity, required sections present, responsive tags,
          broken internal refs, accessibility basics.

On FAIL → routes back to assembly_agent (up to 2 retries).
On PASS → marks verified=True and ends the graph.
"""

import re
from rich.console import Console
from rich.table import Table
from state import SiteBuilderState

console = Console()

MAX_RETRIES = 2


def verification_agent(state: SiteBuilderState) -> dict:
    console.rule("[bold red]✅  VERIFICATION AGENT")

    html    = state.get("final_output", "")
    style   = state.get("style_json", {})
    struct  = state.get("structure_json", {})
    retries = state.get("retry_count", 0)

    checks, failures = _run_all_checks(html, style, struct)
    _print_report(checks)

    passed = len(failures) == 0
    report = {
        "checks":   checks,
        "failures": failures,
        "passed":   passed,
        "retry":    retries,
    }

    if passed:
        console.print("\n  [bold green]✓ VERIFICATION PASSED — site is ready![/bold green]")
        return {
            "verification_report": report,
            "verified": True,
            "current_step": "done",
            "errors": state.get("errors", []),
        }
    elif retries >= MAX_RETRIES:
        console.print(f"\n  [yellow]⚠ Max retries reached. Delivering with warnings.[/yellow]")
        return {
            "verification_report": report,
            "verified": False,
            "current_step": "done",
            "errors": state.get("errors", []) + [f"verification: {failures}"],
        }
    else:
        console.print(f"\n  [red]✗ {len(failures)} checks failed. Routing back to assembly.[/red]")
        # Inject failure context into errors so assembly_agent can fix
        fix_hint = f"Please fix these issues: {'; '.join(failures)}"
        return {
            "verification_report": report,
            "verified": False,
            "current_step": "assembly",  # loop back
            "retry_count": retries + 1,
            "errors": state.get("errors", []) + [fix_hint],
        }


# ─── Individual checks ────────────────────────────────────────────────────────

def _run_all_checks(html: str, style: dict, struct: dict) -> tuple[list[dict], list[str]]:
    checks = []
    failures = []

    def check(name: str, fn, *args) -> bool:
        passed, detail = fn(*args)
        checks.append({"name": name, "passed": passed, "detail": detail})
        if not passed:
            failures.append(f"{name}: {detail}")
        return passed

    check("DOCTYPE present",          _check_doctype,    html)
    check("Viewport meta tag",        _check_viewport,   html)
    check("Primary color used",       _check_color,      html, style)
    check("Font referenced",          _check_font,       html, style)
    check("All sections present",     _check_sections,   html, struct)
    check("No broken href anchors",   _check_anchors,    html)
    check("Has navigation",           _check_nav,        html)
    check("Has footer",               _check_footer,     html)
    check("Reasonable size",          _check_size,       html)
    check("No empty <body>",          _check_body,       html)

    return checks, failures


def _check_doctype(html: str) -> tuple[bool, str]:
    ok = "<!DOCTYPE" in html or "<!doctype" in html
    return ok, "OK" if ok else "Missing DOCTYPE declaration"

def _check_viewport(html: str) -> tuple[bool, str]:
    ok = 'viewport' in html and 'width=device-width' in html
    return ok, "OK" if ok else "Missing viewport meta tag"

def _check_color(html: str, style: dict) -> tuple[bool, str]:
    color = style.get("primary_color", "")
    if not color:
        return True, "No primary color in style (skipped)"
    ok = color.lower() in html.lower()
    return ok, "OK" if ok else f"Primary color {color} not found in HTML"

def _check_font(html: str, style: dict) -> tuple[bool, str]:
    font = style.get("body_font") or style.get("heading_font", "")
    if not font:
        return True, "No font in style (skipped)"
    ok = font.replace(" ", "+") in html or font in html
    return ok, "OK" if ok else f"Font '{font}' not referenced in HTML"

def _check_sections(html: str, struct: dict) -> tuple[bool, str]:
    sections = struct.get("sections", [])
    missing = []
    for s in sections:
        sid = s["id"]
        if sid not in html and s["type"] not in html:
            missing.append(sid)
    ok = len(missing) == 0
    return ok, "OK" if ok else f"Sections possibly missing: {missing}"

def _check_anchors(html: str) -> tuple[bool, str]:
    broken = re.findall(r'href="(?!http|mailto|#|/)([^"]+)"', html)
    ok = len(broken) == 0
    return ok, "OK" if ok else f"Possibly broken hrefs: {broken[:3]}"

def _check_nav(html: str) -> tuple[bool, str]:
    ok = "<nav" in html
    return ok, "OK" if ok else "No <nav> element found"

def _check_footer(html: str) -> tuple[bool, str]:
    ok = "<footer" in html
    return ok, "OK" if ok else "No <footer> element found"

def _check_size(html: str) -> tuple[bool, str]:
    size = len(html)
    ok = 500 < size < 500_000
    return ok, f"{size:,} chars — OK" if ok else f"{size:,} chars — suspiciously small/large"

def _check_body(html: str) -> tuple[bool, str]:
    body_content = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    if not body_content:
        return False, "No <body> tag found"
    ok = len(body_content.group(1).strip()) > 100
    return ok, "OK" if ok else "<body> content is empty or near-empty"


# ─── Pretty printer ───────────────────────────────────────────────────────────

def _print_report(checks: list[dict]):
    table = Table(show_header=True, header_style="bold")
    table.add_column("Check",  width=28)
    table.add_column("Status", width=8)
    table.add_column("Detail")

    for c in checks:
        status  = "[green]PASS[/green]" if c["passed"] else "[red]FAIL[/red]"
        detail  = c["detail"] if not c["passed"] else "[dim]" + c["detail"] + "[/dim]"
        table.add_row(c["name"], status, detail)

    console.print(table)
