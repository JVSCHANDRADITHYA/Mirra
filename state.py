"""
state.py — Shared state object passed between all agents.
Think of this as the single source of truth for the entire pipeline.
"""

from typing import TypedDict, Optional, List, Any


class SiteBuilderState(TypedDict):
    # ── Input ────────────────────────────────────────────────────────────
    url: str                          # The inspiration site URL
    local_file: Optional[str]         # path to a locally saved HTML file (bypass scraping)

    # ── Scrape Agent outputs ─────────────────────────────────────────────
    raw_html: Optional[str]           # Full HTML of the target site
    raw_css: Optional[str]            # Extracted CSS text
    screenshot_b64: Optional[str]     # Base64 screenshot (if playwright used)

    # ── Design Extractor outputs ─────────────────────────────────────────
    design_tokens: Optional[dict]     # { colors, fonts, spacing, shadows, radius }

    # ── Styling Agent outputs ────────────────────────────────────────────
    style_json: Optional[dict]        # Full CSS strategy as structured JSON

    # ── Structure Agent outputs ──────────────────────────────────────────
    structure_json: Optional[dict]    # Section map + component hierarchy

    # ── HIL: Content Agent ──────────────────────────────────────────────
    user_content: Optional[dict]      # { brand, tagline, products, images, nav }
    hil_approvals: List[dict]         # Audit trail of all human approvals

    # ── Assembly Agent outputs ───────────────────────────────────────────
    final_output: Optional[str]       # Final HTML string

    # ── Verification Agent outputs ───────────────────────────────────────
    verification_report: Optional[dict]
    verified: Optional[bool]

    # ── Internal plumbing ────────────────────────────────────────────────
    messages: List[Any]               # LangChain message history
    current_step: str                 # Tracks where we are
    errors: List[str]                 # Accumulated errors
    retry_count: int                  # Retry counter for verification loops