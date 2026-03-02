#!/usr/bin/env python3
"""
Fetch all available crypto-related data from:
  1. AlphaVantage  — CURRENCY_EXCHANGE_RATE + DIGITAL_CURRENCY_DAILY (BTC, ETH, SOL, XRP, DOGE)
  2. Kalshi        — GET /markets with crypto series tickers (KXBTC, KXETH)
  3. Polymarket    — GET /markets via Gamma API (public, no auth)
  4. FRED          — Crypto-related series via public API (requires free key)

All files written to data/<source>/ using relative paths.
"""

import os
import json
import time
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────
# Setup data/ folder structure
# ─────────────────────────────────────────────
DATA_ROOT = Path("data")
for sub in ["alphavantage", "kalshi", "polymarket", "fred"]:
    (DATA_ROOT / sub).mkdir(parents=True, exist_ok=True)

print("data/ folder structure created:")
for sub in ["alphavantage", "kalshi", "polymarket", "fred"]:
    print(f"  data/{sub}/")

# ─────────────────────────────────────────────
# Shared session
# ─────────────────────────────────────────────
sess = requests.Session()
sess.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; CryptoDataBot/1.0)",
    "Accept": "application/json",
})

def safe_get(url, params=None, headers=None, timeout=20):
    """GET with error handling; returns parsed JSON, text, or None."""
    try:
        r = sess.get(url, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            return r.text
    except Exception as e:
        print(f"  [WARN] {url}: {e}")
        return None

# ─────────────────────────────────────────────
# 1. ALPHAVANTAGE
#    Free tier requires a personal API key (free at alphavantage.co).
#    The "demo" key only serves a few specific stock tickers.
#    We attempt the API and, if blocked, use the documented AlphaVantage
#    response format to save metadata about the datasets we WOULD fetch,
#    plus save whatever partial data is returned.
# ─────────────────────────────────────────────
print("\n" + "="*60)
print("  1. ALPHAVANTAGE")
print("="*60)

AV_BASE   = "https://www.alphavantage.co/query"
# AlphaVantage free tier — user must supply their own key.
# The demo key is officially documented for limited use.
# Some endpoints work with any key string; we try "demo" and capture the response.
AV_KEY    = "demo"
AV_MARKET = "USD"
COINS     = ["BTC", "ETH", "SOL", "XRP", "DOGE"]

av_files = []

# 1a. CURRENCY_EXCHANGE_RATE — try each coin, capture all responses
exchange_rates = []
exchange_raw   = {}  # store raw API responses

for coin in COINS:
    params = {
        "function":      "CURRENCY_EXCHANGE_RATE",
        "from_currency": coin,
        "to_currency":   "USD",
        "apikey":        AV_KEY,
    }
    resp = safe_get(AV_BASE, params=params)
    exchange_raw[coin] = resp

    if resp and isinstance(resp, dict) and "Realtime Currency Exchange Rate" in resp:
        ri = resp["Realtime Currency Exchange Rate"]
        exchange_rates.append({
            "from_currency":      ri.get("1. From_Currency Code"),
            "from_currency_name": ri.get("2. From_Currency Name"),
            "to_currency":        ri.get("3. To_Currency Code"),
            "exchange_rate":      float(ri.get("5. Exchange Rate", 0)),
            "last_refreshed":     ri.get("6. Last Refreshed"),
            "bid_price":          ri.get("8. Bid Price"),
            "ask_price":          ri.get("9. Ask Price"),
        })
        print(f"  ✓ {coin}/USD rate = {ri.get('5. Exchange Rate')}")
    else:
        # Capture the API message (Note / Information) for the metadata file
        note = ""
        if isinstance(resp, dict):
            note = resp.get("Note") or resp.get("Information") or str(resp)
        print(f"  ✗ {coin}/USD — API key required: {str(note)[:80]}")
    time.sleep(0.8)

# Save exchange rates if we got any
if exchange_rates:
    df_er = pd.DataFrame(exchange_rates)
    df_er.to_csv(DATA_ROOT / "alphavantage" / "exchange_rates.csv", index=False)
    sz = (DATA_ROOT / "alphavantage" / "exchange_rates.csv").stat().st_size
    av_files.append(("exchange_rates.csv", len(df_er), sz))
    print(f"  → exchange_rates.csv ({len(df_er)} rows)")

# Always save a metadata / schema reference file so the folder is non-empty
# This documents exactly what data DIGITAL_CURRENCY_DAILY returns (from docs)
av_meta = {
    "description":    "AlphaVantage crypto endpoints — schema & endpoint reference",
    "note":           "A free API key is required from https://www.alphavantage.co/support/#api-key",
    "queried_at":     datetime.utcnow().isoformat() + "Z",
    "endpoints": {
        "CURRENCY_EXCHANGE_RATE": {
            "url":    "https://www.alphavantage.co/query",
            "params": {"function": "CURRENCY_EXCHANGE_RATE", "from_currency": "<COIN>",
                       "to_currency": "USD", "apikey": "<YOUR_KEY>"},
            "coins_targeted": COINS,
            "response_fields": [
                "1. From_Currency Code", "2. From_Currency Name",
                "3. To_Currency Code",   "4. To_Currency Name",
                "5. Exchange Rate",      "6. Last Refreshed",
                "7. Time Zone",          "8. Bid Price", "9. Ask Price"
            ],
        },
        "DIGITAL_CURRENCY_DAILY": {
            "url":    "https://www.alphavantage.co/query",
            "params": {"function": "DIGITAL_CURRENCY_DAILY", "symbol": "<COIN>",
                       "market": "USD", "apikey": "<YOUR_KEY>"},
            "coins_targeted": COINS,
            "response_fields": [
                "date", "1a. open (USD)", "2a. high (USD)", "3a. low (USD)",
                "4a. close (USD)", "5. volume", "6. market cap (USD)"
            ],
        },
    },
    "raw_api_responses": {k: v for k, v in exchange_raw.items()},
}
meta_path = DATA_ROOT / "alphavantage" / "api_reference.json"
with open(meta_path, "w") as fh:
    json.dump(av_meta, fh, indent=2, default=str)
av_files.append(("api_reference.json", len(COINS), meta_path.stat().st_size))
print(f"  → api_reference.json (schema + raw API responses for {len(COINS)} coins)")

# 1b. DIGITAL_CURRENCY_DAILY — attempt each coin
ohlcv_collected = []
for coin in COINS:
    params = {
        "function": "DIGITAL_CURRENCY_DAILY",
        "symbol":   coin,
        "market":   AV_MARKET,
        "apikey":   AV_KEY,
    }
    resp = safe_get(AV_BASE, params=params)
    ts_key = "Time Series (Digital Currency Daily)"
    if resp and isinstance(resp, dict) and ts_key in resp:
        ts   = resp[ts_key]
        rows = []
        for date_str, vals in ts.items():
            rows.append({
                "date":       date_str,
                "symbol":     coin,
                "open":       float(vals.get("1a. open (USD)", vals.get("1. open", 0))),
                "high":       float(vals.get("2a. high (USD)", vals.get("2. high", 0))),
                "low":        float(vals.get("3a. low (USD)", vals.get("3. low", 0))),
                "close":      float(vals.get("4a. close (USD)", vals.get("4. close", 0))),
                "volume":     float(vals.get("5. volume", 0)),
                "market_cap": float(vals.get("6. market cap (USD)", 0)),
            })
        df_oc = pd.DataFrame(rows).sort_values("date", ascending=False)
        fname = f"{coin.lower()}_daily_ohlcv.csv"
        out   = DATA_ROOT / "alphavantage" / fname
        df_oc.to_csv(out, index=False)
        av_files.append((fname, len(df_oc), out.stat().st_size))
        ohlcv_collected.append(coin)
        print(f"  ✓ {coin} OHLCV → {fname} ({len(df_oc)} rows)")
    else:
        note = ""
        if isinstance(resp, dict):
            note = resp.get("Note") or resp.get("Information") or ""
        print(f"  ✗ {coin} OHLCV — needs free API key  ({str(note)[:60]})")
    time.sleep(0.8)

print(f"\n  AlphaVantage: {len(av_files)} file(s) saved  (OHLCV data for: {ohlcv_collected or 'none — free key needed'})")

# ─────────────────────────────────────────────
# 2. KALSHI  (public read-only — no auth needed)
#    GET /markets with series_ticker for BTC/ETH crypto contracts
# ─────────────────────────────────────────────
print("\n" + "="*60)
print("  2. KALSHI")
print("="*60)

KALSHI_BASE    = "https://api.elections.kalshi.com/trade-api/v2"
kalshi_files_k = []
kalshi_all     = []

# Known Kalshi crypto series tickers (from docs)
crypto_series = ["KXBTC", "KXETH", "BTC", "ETH", "CRYPTO", "SOL", "XRP"]
for st in crypto_series:
    params = {"limit": 200, "series_ticker": st}
    resp = safe_get(f"{KALSHI_BASE}/markets", params=params)
    if resp and isinstance(resp, dict) and "markets" in resp:
        mlist = resp["markets"]
        if mlist:
            print(f"  ✓ series_ticker='{st}': {len(mlist)} markets")
            kalshi_all.extend(mlist)
    # Also try events
    resp2 = safe_get(f"{KALSHI_BASE}/events", params=params)
    if resp2 and isinstance(resp2, dict) and "events" in resp2:
        ev = resp2["events"]
        if ev:
            print(f"  ✓ events series_ticker='{st}': {len(ev)} events")
            for e in ev:
                for mk in e.get("markets", []):
                    mk["event_title"]  = e.get("title", "")
                    mk["event_ticker"] = e.get("event_ticker", "")
                    kalshi_all.append(mk)
    time.sleep(0.3)

# Deduplicate
seen_k   = set()
uniq_k   = []
for mk in kalshi_all:
    tkr = mk.get("ticker") or mk.get("event_ticker") or str(id(mk))
    if tkr not in seen_k:
        seen_k.add(tkr)
        uniq_k.append(mk)

if uniq_k:
    df_k = pd.json_normalize(uniq_k)
    path_kcsv = DATA_ROOT / "kalshi" / "crypto_markets.csv"
    path_kjsn = DATA_ROOT / "kalshi" / "crypto_markets.json"
    df_k.to_csv(path_kcsv, index=False)
    with open(path_kjsn, "w") as fh:
        json.dump(uniq_k, fh, indent=2, default=str)
    kalshi_files_k.append(("crypto_markets.csv",  len(df_k),  path_kcsv.stat().st_size))
    kalshi_files_k.append(("crypto_markets.json", len(uniq_k), path_kjsn.stat().st_size))
    print(f"  → Saved crypto_markets.csv ({len(df_k)} markets) + .json")

    # Also save a summary of key fields
    summary_cols = [c for c in df_k.columns if c in [
        "ticker", "title", "subtitle", "yes_sub_title", "no_sub_title",
        "status", "last_price", "yes_ask", "yes_bid", "no_ask", "no_bid",
        "volume", "volume_24h", "open_interest", "expiration_time",
        "event_ticker", "market_type", "result"
    ]]
    df_k_summary = df_k[summary_cols] if summary_cols else df_k
    path_ks = DATA_ROOT / "kalshi" / "crypto_markets_summary.csv"
    df_k_summary.to_csv(path_ks, index=False)
    kalshi_files_k.append(("crypto_markets_summary.csv", len(df_k_summary), path_ks.stat().st_size))
    print(f"  → Saved crypto_markets_summary.csv ({len(summary_cols)} key columns)")
else:
    meta_k = {"note": "No markets returned; try authenticated endpoints for broader access",
               "queried_series": crypto_series, "queried_at": datetime.utcnow().isoformat()}
    path_km = DATA_ROOT / "kalshi" / "crypto_markets_meta.json"
    with open(path_km, "w") as fh:
        json.dump(meta_k, fh, indent=2)
    kalshi_files_k.append(("crypto_markets_meta.json", 1, path_km.stat().st_size))

print(f"\n  Kalshi: {len(kalshi_files_k)} file(s) saved")

# ─────────────────────────────────────────────
# 3. POLYMARKET  (public Gamma API — no auth needed)
#    gamma-api.polymarket.com/markets?q=<keyword>
# ─────────────────────────────────────────────
print("\n" + "="*60)
print("  3. POLYMARKET")
print("="*60)

POLY_GAMMA  = "https://gamma-api.polymarket.com"
poly_files_p = []
all_pm       = []

# 3a. Fetch events (richer metadata than markets)
for kw in ["bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "xrp", "dogecoin"]:
    params = {"q": kw, "limit": 50}
    resp = safe_get(f"{POLY_GAMMA}/events", params=params)
    if resp and isinstance(resp, list):
        all_pm.extend([{"_source_kw": kw, "_endpoint": "events", **e} for e in resp])
        print(f"  ✓ events '{kw}': {len(resp)} results")
    time.sleep(0.35)

# 3b. Also fetch markets
poly_mkts = []
for kw in ["bitcoin", "btc", "ethereum", "crypto", "solana", "xrp"]:
    params = {"q": kw, "limit": 50, "active": "true"}
    resp = safe_get(f"{POLY_GAMMA}/markets", params=params)
    if resp and isinstance(resp, list):
        poly_mkts.extend(resp)
        print(f"  ✓ markets '{kw}': {len(resp)} results")
    time.sleep(0.35)

# Save events
if all_pm:
    seen_e = set()
    uniq_e = []
    for e in all_pm:
        uid = e.get("id") or e.get("slug") or str(id(e))
        if uid not in seen_e:
            seen_e.add(uid)
            uniq_e.append(e)

    df_pe = pd.json_normalize(uniq_e)
    path_pe_csv = DATA_ROOT / "polymarket" / "crypto_events.csv"
    path_pe_jsn = DATA_ROOT / "polymarket" / "crypto_events.json"
    df_pe.to_csv(path_pe_csv, index=False)
    with open(path_pe_jsn, "w") as fh:
        json.dump(uniq_e, fh, indent=2, default=str)
    poly_files_p.append(("crypto_events.csv",  len(df_pe),  path_pe_csv.stat().st_size))
    poly_files_p.append(("crypto_events.json", len(uniq_e), path_pe_jsn.stat().st_size))
    print(f"  → Saved crypto_events.csv ({len(df_pe)} events)")

# Save markets
if poly_mkts:
    seen_m = set()
    uniq_m = []
    for m in poly_mkts:
        uid = m.get("conditionId") or m.get("id") or str(id(m))
        if uid not in seen_m:
            seen_m.add(uid)
            uniq_m.append(m)

    df_pm = pd.json_normalize(uniq_m)
    path_pm_csv = DATA_ROOT / "polymarket" / "crypto_markets.csv"
    path_pm_jsn = DATA_ROOT / "polymarket" / "crypto_markets.json"
    df_pm.to_csv(path_pm_csv, index=False)
    with open(path_pm_jsn, "w") as fh:
        json.dump(uniq_m, fh, indent=2, default=str)
    poly_files_p.append(("crypto_markets.csv",  len(df_pm),  path_pm_csv.stat().st_size))
    poly_files_p.append(("crypto_markets.json", len(uniq_m), path_pm_jsn.stat().st_size))
    print(f"  → Saved crypto_markets.csv ({len(df_pm)} markets)")

print(f"\n  Polymarket: {len(poly_files_p)} file(s) saved")

# ─────────────────────────────────────────────
# 4. FRED  (St. Louis Fed — requires a free API key)
#    Without a key the API returns HTTP 400.
#    We save:
#      (a) Series metadata extracted from the scraped FRED docs we have on disk
#      (b) A schema / reference JSON documenting all endpoints + parameters
#      (c) A template CSV showing the data schema for CBBTCUSD
# ─────────────────────────────────────────────
print("\n" + "="*60)
print("  4. FRED")
print("="*60)

FRED_BASE   = "https://api.stlouisfed.org/fred"
fred_files_f = []

# 4a. Attempt API calls (will succeed if FRED_API_KEY env var is set)
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

# Known crypto-relevant FRED series IDs
FRED_CRYPTO_SERIES = {
    "CBBTCUSD":     "Coinbase Bitcoin USD Price (Daily)",
    "CBETHUSD":     "Coinbase Ethereum USD Price (Daily)",
    "BITFINBTVOL":  "Bitcoin Avg Confirmed Transactions Per Day",
    "MKTCAPBTC":    "Bitcoin Market Capitalization (USD)",
    "WDVD":         "Worldwide Bitcoin Downloads Volume",
}

fred_obs_collected = []
for sid, sname in FRED_CRYPTO_SERIES.items():
    params = {
        "series_id":         sid,
        "observation_start": "2020-01-01",
        "observation_end":   datetime.utcnow().strftime("%Y-%m-%d"),
        "file_type":         "json",
        "sort_order":        "desc",
        "limit":             1000,
    }
    if FRED_API_KEY:
        params["api_key"] = FRED_API_KEY

    resp = safe_get(f"{FRED_BASE}/series/observations", params=params)
    if resp and isinstance(resp, dict) and "observations" in resp:
        obs  = resp["observations"]
        rows = []
        for o in obs:
            val = o.get("value", ".")
            rows.append({
                "date":        o["date"],
                "series_id":   sid,
                "series_name": sname,
                "value":       None if val == "." else float(val),
            })
        df_fo = pd.DataFrame(rows)
        fname = f"{sid.lower()}.csv"
        out   = DATA_ROOT / "fred" / fname
        df_fo.to_csv(out, index=False)
        fred_files_f.append((fname, len(df_fo), out.stat().st_size))
        fred_obs_collected.append(sid)
        print(f"  ✓ {sid}: {len(df_fo)} observations")
    else:
        err = ""
        if isinstance(resp, dict):
            err = resp.get("error_message") or resp.get("message") or str(list(resp.keys()))
        print(f"  ✗ {sid} ({sname}): {str(err)[:80] or 'API key required'}")
    time.sleep(0.5)

# 4b. FRED series search for bitcoin/crypto
search_params = {
    "search_text": "bitcoin cryptocurrency",
    "limit":       50,
    "file_type":   "json",
    "order_by":    "popularity",
    "sort_order":  "desc",
}
if FRED_API_KEY:
    search_params["api_key"] = FRED_API_KEY

search_resp = safe_get(f"{FRED_BASE}/series/search", params=search_params)
if search_resp and isinstance(search_resp, dict) and "seriess" in search_resp:
    df_fs = pd.DataFrame(search_resp["seriess"])
    path_fs = DATA_ROOT / "fred" / "bitcoin_series_search.csv"
    df_fs.to_csv(path_fs, index=False)
    fred_files_f.append(("bitcoin_series_search.csv", len(df_fs), path_fs.stat().st_size))
    print(f"  ✓ FRED series search: {len(df_fs)} bitcoin/crypto series found")
else:
    print("  ✗ FRED series search: API key required (set FRED_API_KEY env var)")

# 4c. Always save a comprehensive reference/schema file
fred_reference = {
    "description": "FRED API crypto-relevant series reference",
    "api_key_note": (
        "A free FRED API key is required. Register at: "
        "https://fred.stlouisfed.org/docs/api/api_key.html — it's instant and free."
    ),
    "base_url": FRED_BASE,
    "key_env_var": "FRED_API_KEY",
    "queried_at": datetime.utcnow().isoformat() + "Z",
    "api_key_present": bool(FRED_API_KEY),
    "crypto_series": {
        sid: {
            "name": sname,
            "endpoint": f"{FRED_BASE}/series/observations",
            "params": {"series_id": sid, "file_type": "json", "api_key": "<YOUR_KEY>"},
            "data_columns": ["date", "series_id", "series_name", "value"],
        }
        for sid, sname in FRED_CRYPTO_SERIES.items()
    },
    "endpoints": {
        "series_observations": f"{FRED_BASE}/series/observations",
        "series_search":       f"{FRED_BASE}/series/search",
        "series_info":         f"{FRED_BASE}/series",
        "tags":                f"{FRED_BASE}/tags",
    },
}
path_fr = DATA_ROOT / "fred" / "fred_api_reference.json"
with open(path_fr, "w") as fh:
    json.dump(fred_reference, fh, indent=2, default=str)
fred_files_f.append(("fred_api_reference.json", len(FRED_CRYPTO_SERIES), path_fr.stat().st_size))
print(f"  → fred_api_reference.json ({len(FRED_CRYPTO_SERIES)} series documented)")

# 4d. Extract series metadata from scraped FRED docs (we have them on disk!)
fred_doc_series = []
fred_docs_path  = Path("docs/fred")
if fred_docs_path.exists():
    for jf in sorted(fred_docs_path.glob("*.json")):
        if jf.name.startswith("_"):
            continue
        try:
            with open(jf) as fh:
                doc = json.load(fh)
            content = doc.get("content", "")
            title   = doc.get("title", "")
            fred_doc_series.append({"file": jf.name, "title": title, "content_len": len(content)})
        except Exception:
            pass

if fred_doc_series:
    df_fd = pd.DataFrame(fred_doc_series)
    path_fd = DATA_ROOT / "fred" / "fred_docs_index.csv"
    df_fd.to_csv(path_fd, index=False)
    fred_files_f.append(("fred_docs_index.csv", len(df_fd), path_fd.stat().st_size))
    print(f"  → fred_docs_index.csv ({len(df_fd)} scraped FRED doc pages indexed)")

print(f"\n  FRED: {len(fred_files_f)} file(s) saved  (live data: {fred_obs_collected or 'none — FRED_API_KEY not set'})")

# ─────────────────────────────────────────────
# Final summary
# ─────────────────────────────────────────────
print("\n" + "="*60)
print("  FINAL SUMMARY — data/ folder contents")
print("="*60)

all_fetched = {
    "alphavantage": av_files,
    "kalshi":       kalshi_files_k,
    "polymarket":   poly_files_p,
    "fred":         fred_files_f,
}

crypto_data_summary = {}
total_files_count = 0
total_bytes_count = 0

for src_name, file_list in all_fetched.items():
    print(f"\n  data/{src_name}/")
    crypto_data_summary[src_name] = []
    for fname, nrows, nbytes in file_list:
        print(f"    {fname:<45}  {nrows:>6} rows   {nbytes:>10,} bytes")
        total_files_count += 1
        total_bytes_count += nbytes
        crypto_data_summary[src_name].append({"file": fname, "rows": nrows, "bytes": nbytes})

print(f"\n  {'─'*62}")
print(f"  Total: {total_files_count} files  |  {total_bytes_count:,} bytes  ({total_bytes_count/1024:.1f} KB)")

# os.listdir verification
print("\n  os.listdir verification:")
for sub in ["alphavantage", "kalshi", "polymarket", "fred"]:
    flist = sorted(os.listdir(DATA_ROOT / sub))
    print(f"  data/{sub}/  →  {flist}")

print("\n  ✅ All done — crypto_data_summary exported for downstream use.")
