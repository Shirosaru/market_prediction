
import json
import os
import re
from pathlib import Path

docs_root = Path("docs")

# ─────────────────────────────────────────────
# Helper: load a JSON file safely
# ─────────────────────────────────────────────
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ─────────────────────────────────────────────
# Helper: recursively search text for crypto signals
# ─────────────────────────────────────────────
CRYPTO_KEYWORDS = re.compile(
    r'\b(bitcoin|btc|ethereum|eth|crypto(?:currency)?|blockchain|token|'
    r'defi|nft|usdc|usdt|stablecoin|coinbase|binance|polygon|matic|'
    r'solana|sol|cardano|ada|ripple|xrp|litecoin|ltc|polkadot|dot|'
    r'avalanche|avax|chainlink|link|uniswap|uni|web3|dex|'
    r'digital.?asset|virtual.?currency|on.?chain)\b',
    re.IGNORECASE
)

def crypto_hits(text: str) -> list:
    return list({m.group(0).lower() for m in CRYPTO_KEYWORDS.finditer(text)})

def text_from_doc(doc: dict) -> str:
    """Pull all string values from a nested dict into one blob."""
    parts = []
    if isinstance(doc, dict):
        for v in doc.values():
            parts.append(text_from_doc(v))
    elif isinstance(doc, list):
        for item in doc:
            parts.append(text_from_doc(item))
    elif isinstance(doc, str):
        parts.append(doc)
    return " ".join(parts)

# ─────────────────────────────────────────────
# Load master index
# ─────────────────────────────────────────────
master_index_path = docs_root / "master_index.json"
if not master_index_path.exists():
    print(f"[!] Creating default master_index.json...")
    master_index = {
        "description": "Master index of API documentation sources",
        "sources": ["polymarket", "kalshi", "metaculus", "fred", "alphavantage", "sec"],
        "collected_at": "auto-generated",
        "status": "auto-indexed"
    }
else:
    master_index = load_json(master_index_path)

print("=" * 70)
print("CRYPTO API ANALYSIS — ALL SOURCES")
print("=" * 70)

# ─────────────────────────────────────────────
# Per-source analysis
# ─────────────────────────────────────────────
sources = ["polymarket", "kalshi", "metaculus", "fred", "alphavantage", "sec"]

crypto_api_summary = {}   # exported for downstream blocks

for source in sources:
    src_dir = docs_root / source
    idx_path = src_dir / "_index.json"

    print(f"\n{'─'*70}")
    print(f"  SOURCE: {source.upper()}")
    print(f"{'─'*70}")

    if not src_dir.exists():
        print("  [!] Source directory not found — skipping")
        continue
    
    if not idx_path.exists():
        # Try to auto-index HTML files in the directory
        html_files = list(src_dir.glob("*.html"))
        if not html_files:
            print("  [!] No documentation files found — skipping")
            continue
        print(f"  [i] Auto-indexing {len(html_files)} HTML files...")
        src_index = {"files": [f.name for f in html_files], "auto_indexed": True}
    else:
        src_index = load_json(idx_path)

    # Collect all doc files for this source
    doc_files = sorted(src_dir.glob("*.json"))
    doc_files = [f for f in doc_files if f.name != "_index.json"]

    crypto_pages = []           # pages with crypto content
    endpoints = []              # (method, path, description)
    auth_methods = set()
    base_urls = set()
    param_patterns = {}         # endpoint → params

    for doc_file in doc_files:
        doc = load_json(doc_file)
        full_text = text_from_doc(doc)
        hits = crypto_hits(full_text)

        # ── extract base URLs ──────────────────────────────────────────
        for url in re.findall(r'https?://[a-zA-Z0-9._/%-]+', full_text):
            # keep only root base URLs (not deep paths)
            m = re.match(r'(https?://[a-zA-Z0-9._-]+(?:/[a-zA-Z0-9._-]{0,20})?)', url)
            if m:
                base_urls.add(m.group(1))

        # ── extract auth patterns ──────────────────────────────────────
        for auth_pat in re.findall(
            r'\b(api.?key|bearer.?token|oauth|hmac|jwt|l1.?header|'
            r'private.?key|signature|authorization)\b',
            full_text, re.IGNORECASE
        ):
            auth_methods.add(auth_pat.lower())

        # ── look for endpoint patterns ─────────────────────────────────
        # Match patterns like GET /v1/markets or POST /api/v2/orders
        for ep in re.findall(
            r'\b(GET|POST|PUT|PATCH|DELETE)\s+(/[a-zA-Z0-9/_{}.-]+)',
            full_text
        ):
            endpoints.append(ep)

        # ── flag crypto-relevant pages ─────────────────────────────────
        if hits:
            crypto_pages.append({
                "file": doc_file.name,
                "crypto_terms": hits[:8],   # cap to 8 for readability
            })

    # Deduplicate endpoints
    unique_endpoints = list(dict.fromkeys(endpoints))

    # Filter base_urls to meaningful ones (strip overly generic)
    meaningful_urls = sorted({
        u for u in base_urls
        if any(kw in u for kw in [
            "api", "fred", "kalshi", "polymarket", "alphavantage",
            "metaculus", "sec.gov", "edgar"
        ])
    })

    # Summarize auth
    auth_summary = sorted(auth_methods)

    print(f"  Total doc files scanned : {len(doc_files)}")
    print(f"  Crypto-relevant pages   : {len(crypto_pages)}")
    print(f"  Unique endpoints found  : {len(unique_endpoints)}")

    if meaningful_urls:
        print(f"\n  Base URLs:")
        for u in meaningful_urls[:8]:
            print(f"    • {u}")

    if auth_summary:
        print(f"\n  Authentication methods detected:")
        for a in auth_summary[:6]:
            print(f"    • {a}")

    if unique_endpoints:
        print(f"\n  Endpoints (sample, up to 20):")
        for method, path in unique_endpoints[:20]:
            print(f"    {method:<7} {path}")
        if len(unique_endpoints) > 20:
            print(f"    ... and {len(unique_endpoints)-20} more")

    if crypto_pages:
        print(f"\n  Crypto-relevant pages:")
        for p in crypto_pages[:10]:
            terms_str = ", ".join(p["crypto_terms"])
            print(f"    [{p['file']}]  terms: {terms_str}")
        if len(crypto_pages) > 10:
            print(f"    ... and {len(crypto_pages)-10} more pages")
    else:
        print("\n  ⚠  No explicit crypto keywords found in docs.")

    crypto_api_summary[source] = {
        "total_docs": len(doc_files),
        "crypto_pages": crypto_pages,
        "base_urls": meaningful_urls,
        "auth_methods": auth_summary,
        "endpoints": unique_endpoints,
    }

# ─────────────────────────────────────────────
# Cross-source summary table
# ─────────────────────────────────────────────
print(f"\n\n{'='*70}")
print("EXECUTIVE SUMMARY — CRYPTO DATA AVAILABILITY BY SOURCE")
print(f"{'='*70}")
print(f"{'Source':<15} {'Docs':>5} {'Crypto Pages':>13} {'Endpoints':>10}")
print(f"{'─'*15} {'─'*5} {'─'*13} {'─'*10}")
for src, info in crypto_api_summary.items():
    print(f"{src:<15} {info['total_docs']:>5} {len(info['crypto_pages']):>13} {len(info['endpoints']):>10}")

print(f"\nDone — crypto API analysis complete.")
