#!/usr/bin/env python3
"""
Re-runs the documentation scraper and explicitly writes all scraped
documentation JSON files to docs/ subdirectories using relative paths,
ensuring persistence in Zerve's filesystem.

Organized by source:
  docs/polymarket/    docs/kalshi/     docs/metaculus/
  docs/fred/          docs/alphavantage/  docs/sec/

Each crawled page is saved as a .json file.
A per-source _index.json and a master docs/master_index.json are also written.
"""

import os
import json
import time
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests
from datetime import datetime

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────
_MAX_DEPTH       = 2
_MAX_PAGES       = 40
_REQUEST_DELAY   = 0.4
_REQUEST_TIMEOUT = 12

_SOURCES = {
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
        "start_url": (
            "https://efts.sec.gov/LATEST/search-index"
            "?q=%22api%22&dateRange=custom&startdt=2020-01-01"
            "&enddt=2024-01-01&hits.hits.total.value=true"
        ),
        "allowed_domains": ["www.sec.gov", "efts.sec.gov"],
    },
}

# ─────────────────────────────────────────────────────────────
# HTTP session
# ─────────────────────────────────────────────────────────────
_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; DocBot/1.0; +https://zerve.ai)"
})


# ─────────────────────────────────────────────────────────────
# Helper utilities
# ─────────────────────────────────────────────────────────────
def _fetch(url: str) -> str | None:
    """Fetch URL; returns raw text or None on error."""
    try:
        resp = _session.get(url, timeout=_REQUEST_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"    [WARN] Could not fetch {url}: {e}")
        return None


def _clean_text(html: str) -> str:
    """Strip boilerplate; return readable plain text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "aside",
                     "noscript", "iframe", "header", "form"]):
        tag.decompose()
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_=re.compile(r"content|docs|markdown|prose", re.I))
        or soup.find("body")
        or soup
    )
    text = main.get_text(separator="\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _page_title(html: str) -> str:
    """Extract <title> or first <h1>."""
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else "Untitled"


def _internal_links(html: str, base_url: str, allowed_domains: list,
                    path_prefix: str = None) -> list:
    """Return list of internal links matching domain/prefix."""
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


def _url_to_filename(url: str) -> str:
    """Convert URL to a safe filesystem filename stem (max 120 chars)."""
    path = urlparse(url).path.strip("/").replace("/", "__") or "index"
    return re.sub(r"[^\w\-.]", "_", path)[:120]


# ─────────────────────────────────────────────────────────────
# Per-source crawler  (writes files using relative paths)
# ─────────────────────────────────────────────────────────────
def _crawl_and_write(source_name: str, config: dict, docs_root: str) -> dict:
    """
    Crawl one source, write each page as JSON, write _index.json.
    All file paths are relative (no leading /). Returns summary dict.
    """
    source_dir = os.path.join(docs_root, source_name)
    os.makedirs(source_dir, exist_ok=True)  # relative path → persists in Zerve

    start_url       = config["start_url"]
    allowed_domains = config["allowed_domains"]
    path_prefix     = config.get("path_prefix")

    visited      = set()
    queue        = [(start_url, 0)]   # (url, depth)
    pages_saved  = 0
    skipped      = 0
    records      = []

    print(f"\n{'='*60}")
    print(f"  Crawling: {source_name.upper()}  →  {source_dir}/")
    print(f"{'='*60}")

    while queue and pages_saved < _MAX_PAGES:
        url, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        html = _fetch(url)
        if not html:
            skipped += 1
            continue

        title   = _page_title(html)
        content = _clean_text(html)

        record = {
            "source":  source_name,
            "url":     url,
            "title":   title,
            "depth":   depth,
            "content": content,
        }

        # ── Write JSON file with relative path ──────────────────
        filename = _url_to_filename(url) + ".json"
        file_rel = os.path.join(source_dir, filename)   # e.g. docs/kalshi/foo.json
        with open(file_rel, "w", encoding="utf-8") as fh:
            json.dump(record, fh, ensure_ascii=False, indent=2)

        pages_saved += 1
        records.append({
            "url":   url,
            "title": title,
            "file":  file_rel,
        })
        print(f"    [WRITTEN] {file_rel}  ({len(content):,} chars)  \"{title[:55]}\"")

        # Follow links one level deeper
        if depth < _MAX_DEPTH:
            links = _internal_links(html, url, allowed_domains, path_prefix)
            for link in links:
                if link not in visited:
                    queue.append((link, depth + 1))

        time.sleep(_REQUEST_DELAY)

    # ── Per-source index ────────────────────────────────────────
    source_index = {
        "source":     source_name,
        "start_url":  start_url,
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "page_count": pages_saved,
        "skipped":    skipped,
        "pages":      records,
    }
    index_rel = os.path.join(source_dir, "_index.json")
    with open(index_rel, "w", encoding="utf-8") as fh:
        json.dump(source_index, fh, ensure_ascii=False, indent=2)

    print(f"    [INDEX  ] {index_rel}")
    print(f"    → {pages_saved} pages saved, {skipped} skipped")

    return source_index


# ─────────────────────────────────────────────────────────────
# Main: create root docs/ folder and crawl all sources
# ─────────────────────────────────────────────────────────────
_DOCS_ROOT = "docs"
os.makedirs(_DOCS_ROOT, exist_ok=True)
print(f"docs/ root created/verified at relative path: {_DOCS_ROOT}")

_run_summary = {}
for _src_name, _src_cfg in _SOURCES.items():
    _run_summary[_src_name] = _crawl_and_write(_src_name, _src_cfg, _DOCS_ROOT)

# ─────────────────────────────────────────────────────────────
# Master index
# ─────────────────────────────────────────────────────────────
_total_pages   = sum(v["page_count"] for v in _run_summary.values())
_total_skipped = sum(v["skipped"]    for v in _run_summary.values())

_master_index = {
    "scraped_at":    datetime.utcnow().isoformat() + "Z",
    "total_pages":   _total_pages,
    "total_skipped": _total_skipped,
    "sources":       _run_summary,
}
_master_path = os.path.join(_DOCS_ROOT, "master_index.json")
with open(_master_path, "w", encoding="utf-8") as fh:
    json.dump(_master_index, fh, ensure_ascii=False, indent=2)
print(f"\n[MASTER INDEX] Written → {_master_path}")

# ─────────────────────────────────────────────────────────────
# Final summary + os.listdir() verification
# ─────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("  SCRAPE COMPLETE — SUMMARY")
print(f"{'='*60}")
for _src, _info in _run_summary.items():
    print(f"  {_src:<18}  {_info['page_count']:3d} pages   {_info['skipped']:2d} skipped")
print(f"{'─'*60}")
print(f"  {'TOTAL':<18}  {_total_pages:3d} pages   {_total_skipped:2d} skipped")
print(f"{'='*60}")

print(f"\n── FILE VERIFICATION via os.listdir() ──────────────────────")
print(f"  docs/  → {sorted(os.listdir(_DOCS_ROOT))}")
for _src_name in _SOURCES:
    _src_dir = os.path.join(_DOCS_ROOT, _src_name)
    if os.path.isdir(_src_dir):
        _files = sorted(os.listdir(_src_dir))
        print(f"  docs/{_src_name}/ ({len(_files)} files) → {_files[:8]}{'...' if len(_files) > 8 else ''}")
    else:
        print(f"  docs/{_src_name}/ — NOT FOUND")

# Verify master index exists
_exists = os.path.isfile(_master_path)
_size   = os.path.getsize(_master_path) if _exists else 0
print(f"\n  master_index.json exists={_exists}, size={_size:,} bytes")
print("  All done ✓")
