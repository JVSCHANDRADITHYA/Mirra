"""
tools/css_parser.py — Extracts design tokens from raw CSS without an LLM.
Handles colors, fonts, spacing scale, border radius, shadows.
"""

import re
from collections import Counter
from typing import Optional


# ─── Color extraction ─────────────────────────────────────────────────────────

HEX_RE     = re.compile(r'#(?:[0-9a-fA-F]{3,4}){1,2}\b')
RGB_RE     = re.compile(r'rgba?\(\s*[\d.]+\s*,\s*[\d.]+\s*,\s*[\d.]+(?:\s*,\s*[\d.]+)?\s*\)')
HSL_RE     = re.compile(r'hsla?\(\s*[\d.]+\s*,\s*[\d.%]+\s*,\s*[\d.%]+(?:\s*,\s*[\d.]+)?\s*\)')
CSS_VAR_RE = re.compile(r'--[\w-]+\s*:\s*([^;]+);')


def extract_colors(css: str) -> list[str]:
    colors: list[str] = []
    colors += HEX_RE.findall(css)
    colors += RGB_RE.findall(css)
    colors += HSL_RE.findall(css)

    # Deduplicate, keep most frequent first
    freq = Counter(c.lower() for c in colors)
    return [c for c, _ in freq.most_common(20)]


# ─── Font extraction ──────────────────────────────────────────────────────────

FONT_FAMILY_RE = re.compile(r'font-family\s*:\s*([^;{]+)')
GOOGLE_FONT_RE = re.compile(r'fonts\.googleapis\.com/css[^"\']+family=([^&"\']+)')


def extract_fonts(css: str, html: str) -> list[str]:
    families: list[str] = []

    for match in FONT_FAMILY_RE.finditer(css):
        raw = match.group(1).strip().rstrip(",")
        for font in raw.split(","):
            f = font.strip().strip('"\'')
            if f and f.lower() not in ("inherit", "initial", "unset", "sans-serif",
                                        "serif", "monospace", "system-ui", "cursive"):
                families.append(f)

    # Also sniff Google Fonts from HTML
    for match in GOOGLE_FONT_RE.finditer(html):
        raw = match.group(1).replace("+", " ").replace("|", ",")
        for part in raw.split(","):
            name = re.sub(r':\d+', '', part).strip()
            if name:
                families.append(name)

    freq = Counter(f.lower() for f in families)
    return list(dict.fromkeys(f for f, _ in freq.most_common(5)))  # top 5 unique


# ─── Spacing extraction ───────────────────────────────────────────────────────

SPACING_RE = re.compile(r'\b(\d+(?:\.\d+)?)(px|rem|em)\b')


def extract_spacing_scale(css: str) -> list[str]:
    matches = SPACING_RE.findall(css)
    values = [f"{v}{u}" for v, u in matches if float(v) > 0]
    freq = Counter(values)
    # Return top 10 most common spacing values
    return [v for v, _ in freq.most_common(10)]


# ─── CSS variable extraction ──────────────────────────────────────────────────

def extract_css_variables(css: str) -> dict[str, str]:
    """Pull out all CSS custom properties (--var: value)."""
    vars_dict: dict[str, str] = {}
    for match in re.finditer(r'(--[\w-]+)\s*:\s*([^;]+);', css):
        vars_dict[match.group(1).strip()] = match.group(2).strip()
    return vars_dict


# ─── Border radius + shadows ─────────────────────────────────────────────────

RADIUS_RE = re.compile(r'border-radius\s*:\s*([^;]+)')
SHADOW_RE  = re.compile(r'box-shadow\s*:\s*([^;]+)')


def extract_radius_and_shadows(css: str) -> dict:
    radii   = list(dict.fromkeys(m.group(1).strip() for m in RADIUS_RE.finditer(css)))[:5]
    shadows = list(dict.fromkeys(m.group(1).strip() for m in SHADOW_RE.finditer(css)))[:3]
    return {"border_radius": radii, "box_shadows": shadows}


# ─── Master extractor ─────────────────────────────────────────────────────────

def extract_design_tokens(css: str, html: str = "") -> dict:
    """Returns a full design_tokens dict from raw CSS + optional HTML."""
    rs = extract_radius_and_shadows(css)
    return {
        "colors":         extract_colors(css),
        "fonts":          extract_fonts(css, html),
        "spacing_scale":  extract_spacing_scale(css),
        "css_variables":  extract_css_variables(css),
        "border_radius":  rs["border_radius"],
        "box_shadows":    rs["box_shadows"],
    }
