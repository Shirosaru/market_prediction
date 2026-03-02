#!/usr/bin/env python3
"""
Documentation scraper: recursively crawls all 6 sources, extracts clean text,
saves structured JSON files to docs/<source>/ directories.
"""

import os
import json
import time
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
MAX_DEPTH      = 2          # Recursive link depth
MAX_PAGES      = 40         # Max pages per source
REQUEST_DELAY  = 0.4        # Seconds between requests
REQUEST_TIMEOUT = 12

SOURCES = {
    "polymarket": {
        "start_url": "https://docs.polymarket.com/",
        "allowed_domains": ["docs.polymarket.com"],
    },
    "kalshi": {
        "start_url": "https://docs.kalshi.com/",
        "allowed_domains": ["docs.kalshi.com"],
    },
    "metaculus": {
        "start_url": "https://www.metaculus.com/api/",
        "allowed_domains": ["www.metaculus.com"],
        "path_prefix": "/api",
    },
    "fred": {
        "start_url": "https://fred.stlouisfed.org/docs/api/fred/",
        "allowed_domains": ["fred.stlouisfed.org"],
        "path_prefix": "/docs/api",
    },
    "alphavantage": {
        "start_url": "https://www.alphavantage.co/documentation/",
        "allowed_domains": ["www.alphavantage.co"],
        "path_prefix": "/documentation",
    },
    "sec": {
        "start_url": "https://efts.sec.gov/LATEST/search-index?q=%22api%22&dateRange=custom&startdt=2020-01-01&enddt=2024-01-01&hits.hits.total.value=true",
        "allowed_domains": ["www.sec.gov", "efts.sec.gov"],
    },
}

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; DocBot/1.0; +https://zerve.ai)"
})

def fetch(url: str) -> str | None:
    """Fetch URL text content; returns None on failure."""
    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  [WARN] Could not fetch {url}: {e}")
        return None


def extract_clean_text(html: str) -> str:
    """Strip boilerplate, scripts, styles and return readable plain text."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove noise elements
    for tag in soup(["script", "style", "nav", "footer", "aside",
                     "noscript", "iframe", "header", "form"]):
        tag.decompose()

    # Try content-rich containers first
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_=re.compile(r"content|docs|markdown|prose", re.I))
        or soup.find("body")
        or soup
    )

    text = main.get_text(separator="\n", strip=True)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_page_title(html: str) -> str:
    """Extract <title> or first h1 from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return "Untitled"


def extract_internal_links(html: str, base_url: str, allowed_domains: list,
                            path_prefix: str = None) -> list:
    """Extract internal links matching domain and optional path prefix."""
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].split("#")[0].split("?")[0]
        if not href:
            continue
        abs_url = urljoin(base_url, href)
        parsed = urlparse(abs_url)
        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.netloc not in allowed_domains:
            continue
        if path_prefix and not parsed.path.startswith(path_prefix):
            continue
        links.add(abs_url.rstrip("/") or abs_url)
    return list(links)


def url_to_filename(url: str) -> str:
    """Convert a URL to a safe filename (without extension)."""
    parsed = urlparse(url)
    path = parsed.path.strip("/").replace("/", "__") or "index"
    # Sanitize
    path = re.sub(r"[^\w\-.]", "_", path)
    return path[:120]  # cap length


# ─────────────────────────────────────────────
# Core crawler
# ─────────────────────────────────────────────
def crawl_source(name: str, config: dict, docs_root: Path) -> dict:
    """
    Recursively crawl a source up to MAX_DEPTH / MAX_PAGES.
    Returns a summary dict.
    """
    folder = docs_root / name
    folder.mkdir(parents=True, exist_ok=True)

    start_url       = config["start_url"]
    allowed_domains = config["allowed_domains"]
    path_prefix     = config.get("path_prefix", None)

    visited   = set()
    queue     = [(start_url, 0)]   # (url, depth)
    pages_saved = 0
    skipped   = 0
    records   = []

    print(f"\n{'='*60}")
    print(f"  Crawling: {name.upper()}  (start: {start_url})")
    print(f"{'='*60}")

    while queue and pages_saved < MAX_PAGES:
        url, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        html = fetch(url)
        if not html:
            skipped += 1
            continue

        title = get_page_title(html)
        text  = extract_clean_text(html)

        # Build structured record
        record = {
            "source":  name,
            "url":     url,
            "title":   title,
            "depth":   depth,
            "content": text,
        }

        # Save as JSON
        filename  = url_to_filename(url) + ".json"
        out_path  = folder / filename
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        records.append({"url": url, "title": title, "file": str(out_path.relative_to(docs_root))})
        pages_saved += 1
        print(f"  [{pages_saved:02d}] depth={depth}  {title[:60]}")

        # Follow links at next depth
        if depth < MAX_DEPTH:
            links = extract_internal_links(html, url, allowed_domains, path_prefix)
            for link in links:
                if link not in visited:
                    queue.append((link, depth + 1))

        time.sleep(REQUEST_DELAY)

    # Save a source-level index
    source_index = {
        "source":     name,
        "start_url":  start_url,
        "pages":      records,
        "page_count": pages_saved,
        "skipped":    skipped,
    }
    index_path = folder / "_index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(source_index, f, ensure_ascii=False, indent=2)

    print(f"  → {pages_saved} pages saved, {skipped} skipped  |  index: {index_path}")
    return source_index


# ─────────────────────────────────────────────
# Main execution
# ─────────────────────────────────────────────
docs_root = Path("docs")
docs_root.mkdir(exist_ok=True)

scrape_summary = {}
for source_name, source_config in SOURCES.items():
    result = crawl_source(source_name, source_config, docs_root)
    scrape_summary[source_name] = result

# ─────────────────────────────────────────────
# Print final summary
# ─────────────────────────────────────────────
print(f"\n{'='*60}")
print("  SCRAPE COMPLETE — SUMMARY")
print(f"{'='*60}")
total_pages  = 0
total_skipped = 0
for src, info in scrape_summary.items():
    pc = info["page_count"]
    sk = info["skipped"]
    total_pages  += pc
    total_skipped += sk
    print(f"  {src:<18}  {pc:3d} pages saved   {sk:2d} skipped")

print(f"{'─'*60}")
print(f"  {'TOTAL':<18}  {total_pages:3d} pages saved   {total_skipped:2d} skipped")
print(f"{'='*60}")

# Save master index
master_index = {
    "sources": scrape_summary,
    "total_pages": total_pages,
}
with open(docs_root / "master_index.json", "w") as f:
    json.dump(master_index, f, ensure_ascii=False, indent=2)

print(f"\n  Master index → docs/master_index.json")
print(f"  docs/ folder → {docs_root.resolve()}")
