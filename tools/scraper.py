"""
tools/scraper.py — Fetches raw HTML + CSS from the inspiration site.

Strategy (auto-cascading):
  1. requests with full browser headers + session warmup + UA rotation
  2. playwright headless (if installed)
  3. urllib last-resort  ← also used for CSS fetching when requests is blocked

CSS extraction handles:
  - Traditional <style> blocks + linked .css files
  - Next.js / Vite / CRA bundled CSS (/_next/static/css/, /assets/, /dist/)
  - Inline style="" attributes on elements
  - CSS vars sniffed from <script> blocks
"""

import base64
import random
import re
import time
import urllib.request
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

def _make_headers(ua: str = None) -> dict:
    return {
        "User-Agent":                ua or random.choice(USER_AGENTS),
        "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language":           "en-US,en;q=0.9",
        "Accept-Encoding":           "gzip, deflate, br",
        "Connection":                "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest":            "document",
        "Sec-Fetch-Mode":            "navigate",
        "Sec-Fetch-Site":            "none",
        "Sec-Fetch-User":            "?1",
        "Cache-Control":             "max-age=0",
        "DNT":                       "1",
    }


# ─── Fetch a single URL as text (tries urllib, falls back quietly) ────────────

def _fetch_text(url: str) -> str:
    """Fetch a URL as text using urllib (works even when requests is blocked)."""
    try:
        req = urllib.request.Request(url, headers=_make_headers())
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


# ─── CSS collector ────────────────────────────────────────────────────────────

def _collect_css(soup: BeautifulSoup, base_url: str) -> str:
    """
    Extract CSS from all sources: <style> tags, linked .css files,
    Next.js/Vite bundles, inline style attrs, and <script> token sniffing.
    Uses urllib for all sub-fetches so it works even when requests is blocked.
    """
    css_chunks = []

    # 1. Inline <style> blocks
    for tag in soup.find_all("style"):
        text = tag.get_text()
        if text.strip():
            css_chunks.append(text)

    # 2. <link rel="stylesheet"> — linked CSS files
    for link in soup.find_all("link", rel=lambda r: r and "stylesheet" in r):
        href = link.get("href", "").strip()
        if not href or href.startswith("data:"):
            continue
        css_url = href if href.startswith("http") else urljoin(base_url, href)
        text = _fetch_text(css_url)
        if text:
            css_chunks.append(text)

    # 3. Next.js / Vite / CRA bundled CSS
    #    These show up as href="/_next/static/css/xxx.css" etc. in the raw HTML
    found_bundles = set()
    for pat in [
        r'href=["\']?((?:/_next/static/css|/assets|/static/css|/dist)[^"\'>\s]+\.css)',
    ]:
        for m in re.findall(pat, str(soup)):
            found_bundles.add(m)

    for href in found_bundles:
        css_url = urljoin(base_url, href)
        text = _fetch_text(css_url)
        if text:
            css_chunks.append(text)
            print(f"  [scraper] ✓ bundle CSS: {href[:60]}")

    # 4. Inline style="" attributes → reconstruct as CSS rules
    inline_rules = []
    for tag in soup.find_all(style=True):
        val = tag.get("style", "").strip()
        if val:
            classes = ".".join(tag.get("class", []))
            sel = tag.name + (f".{classes}" if classes else "")
            inline_rules.append(f"{sel} {{ {val} }}")
    if inline_rules:
        css_chunks.append("/* inline styles */\n" + "\n".join(inline_rules[:150]))

    # 5. CSS vars / theme tokens from <script> (Next.js inlines these)
    script_props = []
    for script in soup.find_all("script"):
        text = script.get_text()
        if any(k in text for k in ("--tw-", "var(--", "color:", "font-family:")):
            found = re.findall(
                r'(?:--[\w-]+\s*:[^;,"\']{2,60}|'
                r'(?:color|font-family|background(?:-color)?|border-radius|font-size)'
                r'\s*:\s*[^;,"\'<>]{3,40})',
                text
            )
            script_props.extend(found[:40])
    if script_props:
        css_chunks.append("/* script tokens */\n:root {\n  " +
                          ";\n  ".join(script_props) + "\n}")

    combined = "\n\n".join(filter(None, css_chunks))
    if not combined.strip():
        print("  [scraper] ⚠  No CSS extracted — site may use CSS-in-JS or Tailwind JIT")
        print("            Tip: install Playwright for full JS-rendered CSS extraction")
    return combined


# ─── Strategy 1: requests + session warmup ───────────────────────────────────

def scrape_with_requests(url: str) -> dict:
    session = requests.Session()
    last_err = None

    for attempt, ua in enumerate(USER_AGENTS[:3]):
        try:
            headers = _make_headers(ua)
            warmup = "/".join(url.split("/")[:3])
            try:
                session.get(warmup, headers=headers, timeout=8)
                time.sleep(0.4)
            except Exception:
                pass

            resp = session.get(url, headers=headers, timeout=20, allow_redirects=True)
            resp.raise_for_status()

            soup    = BeautifulSoup(resp.text, "html.parser")
            raw_css = _collect_css(soup, url)
            return {"raw_html": resp.text, "raw_css": raw_css, "screenshot_b64": None}

        except requests.exceptions.ConnectionError as e:
            last_err = e
            print(f"  [scraper] Attempt {attempt+1} blocked, retrying...")
            time.sleep(1 + attempt)
        except requests.exceptions.HTTPError as e:
            last_err = e
            break

    raise ConnectionError(f"requests failed: {last_err}")


# ─── Strategy 2: Playwright (full browser) ───────────────────────────────────

def scrape_with_playwright(url: str) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("playwright not installed — pip install playwright && playwright install chromium")

    print("  [scraper] Using Playwright...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-blink-features=AutomationControlled",
        ])
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=random.choice(USER_AGENTS),
            locale="en-US",
        )
        page = ctx.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass

        raw_html = page.content()
        raw_css  = page.evaluate("""
            () => Array.from(document.styleSheets)
                .map(s => { try { return Array.from(s.cssRules).map(r=>r.cssText).join('\\n'); } catch{return '';} })
                .join('\\n\\n')
        """)
        screenshot_b64 = base64.b64encode(page.screenshot(full_page=True)).decode()
        browser.close()

    # Also run soup-based collector for anything playwright missed
    soup      = BeautifulSoup(raw_html, "html.parser")
    extra_css = _collect_css(soup, url)
    return {"raw_html": raw_html, "raw_css": raw_css + "\n\n" + extra_css, "screenshot_b64": screenshot_b64}


# ─── Strategy 3: urllib (last resort) ────────────────────────────────────────

def _scrape_urllib_fallback(url: str) -> dict:
    print("  [scraper] Using urllib...")
    req = urllib.request.Request(url, headers=_make_headers())
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw_html = resp.read().decode("utf-8", errors="replace")

    soup    = BeautifulSoup(raw_html, "html.parser")
    # _collect_css uses urllib internally — works even when requests is blocked
    raw_css = _collect_css(soup, url)
    return {"raw_html": raw_html, "raw_css": raw_css, "screenshot_b64": None}


# ─── Master entry point ───────────────────────────────────────────────────────

def scrape_site(url: str, use_playwright: bool = False) -> dict:
    if use_playwright:
        return scrape_with_playwright(url)
    try:
        return scrape_with_requests(url)
    except Exception as e:
        print(f"  [scraper] requests blocked: {e}")
        try:
            return scrape_with_playwright(url)
        except Exception as e2:
            print(f"  [scraper] playwright failed: {e2}")
            return _scrape_urllib_fallback(url)