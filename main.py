"""
main.py

Flow:
  Phase 1 → graph runs scrape/style/structure → content_agent hits interrupt()
           → graph pauses, returns interrupt payload to us
  Phase 2 → we collect content in terminal (outside graph)
           → resume graph with Command(resume={"user_content": ...})
           → content_agent picks it up, assembly + verification run
           → HTML saved
"""

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from langgraph.types import Command

from graph import create_app

console = Console()


def initial_state(url: str, local_file: str = None) -> dict:
    return {
        "url":                 url,
        "local_file":          local_file,
        "raw_html":            None,
        "raw_css":             None,
        "screenshot_b64":      None,
        "design_tokens":       None,
        "style_json":          None,
        "structure_json":      None,
        "user_content":        None,
        "hil_approvals":       [],
        "final_output":        None,
        "verification_report": None,
        "verified":            None,
        "messages":            [],
        "current_step":        "scrape",
        "errors":              [],
        "retry_count":         0,
    }


def run(url: str, out_file: str = "output/site.html",
        thread_id: str = None, local_file: str = None):

    app       = create_app()
    thread_id = thread_id or str(uuid.uuid4())
    config    = {"configurable": {"thread_id": thread_id}}

    console.print(Panel(
        f"[bold]🚀 Site Builder[/bold]\n\n"
        f"URL        : [link]{url}[/link]\n"
        f"Local file : [dim]{local_file or 'none'}[/dim]\n"
        f"Thread ID  : [dim]{thread_id}[/dim]\n"
        f"Output     : [dim]{out_file}[/dim]",
        style="bold cyan",
    ))

    # ── Phase 1: scrape → style → structure → interrupt() in content_agent ───
    console.print("\n[bold]Phase 1[/bold]: Analysing site...\n")

    state = initial_state(url, local_file=local_file)

    try:
        for _ in app.stream(state, config=config):
            pass
    except Exception as e:
        console.print(f"[red]Phase 1 error: {e}[/red]")
        import traceback; traceback.print_exc()
        sys.exit(1)

    # Verify we're paused at content_agent's interrupt()
    graph_state = app.get_state(config)
    if not graph_state.next:
        # Graph finished without pausing — check if it errored out
        final = graph_state.values
        if not final.get("final_output"):
            console.print("\n[red]Graph finished early with no output.[/red]")
            _print_errors(final.get("errors", []))
        else:
            _save_and_report(final, out_file, thread_id, url)
        return

    console.print(f"\n[yellow]⏸  Paused at: {graph_state.next}[/yellow]")

    # ── Collect content directly in terminal (outside graph stream) ───────────
    console.print("\n[bold]Phase 2[/bold]: Your content\n")

    structure = graph_state.values.get("structure_json", {})
    sections  = structure.get("sections", [])

    from agents.content_agent import collect_content_from_user
    try:
        user_content = collect_content_from_user(sections)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(0)

    # ── Resume graph with collected content ───────────────────────────────────
    console.print("\n[bold]Phase 3[/bold]: Generating site...\n")

    try:
        for _ in app.stream(
            Command(resume={"user_content": user_content}),
            config=config
        ):
            pass
    except Exception as e:
        console.print(f"[red]Phase 3 error: {e}[/red]")
        import traceback; traceback.print_exc()
        sys.exit(1)

    final = app.get_state(config).values
    _save_and_report(final, out_file, thread_id, url)


def _save_and_report(final: dict, out_file: str, thread_id: str, url: str):
    html     = final.get("final_output", "")
    verified = final.get("verified")
    report   = final.get("verification_report", {})
    errors   = final.get("errors", [])

    if errors:
        console.print("\n[yellow]Warnings:[/yellow]")
        for e in errors:
            console.print(f"  [dim]• {e}[/dim]")

    if not html:
        console.print("\n[red bold]✗ No HTML generated.[/red bold]")
        console.print("[dim]The LLM (Ollama) returned empty output. This can happen when:[/dim]")
        console.print("[dim]  • The model is still loading (try running again)[/dim]")
        console.print("[dim]  • Context window exceeded (site too complex)[/dim]")
        console.print("[dim]  • Ollama process died mid-generation[/dim]")
        _print_errors(errors)
        sys.exit(1)

    os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
    Path(out_file).write_text(html, encoding="utf-8")

    report_file = out_file.replace(".html", "_report.json")
    Path(report_file).write_text(json.dumps({
        "thread_id": thread_id, "url": url, "verified": verified,
        "errors": errors, "checks": report.get("checks", []),
    }, indent=2), encoding="utf-8")

    status = "[green]✓ VERIFIED[/green]" if verified else "[yellow]⚠ WITH WARNINGS[/yellow]"
    console.print()
    console.print(Panel(
        f"Status  : {status}\n"
        f"Output  : [bold]{out_file}[/bold]  ({len(html):,} chars)\n"
        f"Report  : [dim]{report_file}[/dim]",
        title="🎉 Done!", style="green" if verified else "yellow",
    ))
    console.print(f"\n  [bold]start {out_file}[/bold]  ← open in browser\n")


def _print_errors(errors: list):
    if errors:
        console.print("[red]Errors:[/red]")
        for e in errors:
            console.print(f"  • {e}")


def main():
    parser = argparse.ArgumentParser(description="Site Builder — LangGraph + Ollama")
    parser.add_argument("url",     nargs="?", help="Inspiration URL")
    parser.add_argument("--out",   default="output/site.html")
    parser.add_argument("--local", help="Path to locally saved HTML file")
    parser.add_argument("--resume",help="Resume by thread_id (note: MemorySaver resets on restart)")
    args = parser.parse_args()

    if args.resume:
        app    = create_app()
        config = {"configurable": {"thread_id": args.resume}}
        gs     = app.get_state(config)
        if not gs.values:
            console.print("[red]Thread not found — MemorySaver resets when process restarts.[/red]")
            sys.exit(1)
        for _ in app.stream(Command(resume={}), config=config):
            pass
        _save_and_report(app.get_state(config).values, args.out, args.resume, "resumed")
        return

    if args.local and not args.url:
        url = f"local://{Path(args.local).name}"
    elif args.url:
        url = args.url if args.url.startswith("http") else "https://" + args.url
    else:
        console.print(Panel(
            "[bold]🌐 Site Builder[/bold]\n\nUsage:\n"
            "  python main.py https://example.com\n"
            "  python main.py --local path/to/page.html",
            style="cyan"
        ))
        url = console.input("\n  Inspiration URL: ").strip()
        if not url.startswith("http"):
            url = "https://" + url

    run(url=url, out_file=args.out, local_file=args.local)


if __name__ == "__main__":
    main()