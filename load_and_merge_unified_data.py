
import pandas as pd
import requests
import time
import json
import re
from pathlib import Path

# ─────────────────────────────────────────────
# 1. LOAD KALSHI DATA FROM data/ FOLDER
# ─────────────────────────────────────────────
kalshi_markets_path     = Path("data/kalshi/crypto_markets.csv")
kalshi_summary_path     = Path("data/kalshi/crypto_markets_summary.csv")

kalshi_markets_raw  = pd.read_csv(kalshi_markets_path)
kalshi_summary_raw  = pd.read_csv(kalshi_summary_path)

print(f"[Kalshi] crypto_markets.csv       : {kalshi_markets_raw.shape}")
print(f"[Kalshi] crypto_markets_summary.csv: {kalshi_summary_raw.shape}")

# ─────────────────────────────────────────────
# 2. LOAD POLYMARKET DATA FROM data/ FOLDER
# ─────────────────────────────────────────────
poly_events_path  = Path("data/polymarket/crypto_events.csv")
poly_markets_path = Path("data/polymarket/crypto_markets.csv")

poly_events_raw  = pd.read_csv(poly_events_path)
poly_markets_raw = pd.read_csv(poly_markets_path)

print(f"[Polymarket] crypto_events.csv : {poly_events_raw.shape}")
print(f"[Polymarket] crypto_markets.csv: {poly_markets_raw.shape}")

# ─────────────────────────────────────────────
# 3. FETCH LIVE COINGECKO DATA (top 100, no API key)
# ─────────────────────────────────────────────
CG_BASE  = "https://api.coingecko.com/api/v3"
HEADERS  = {"accept": "application/json"}
DELAY    = 1.2   # polite rate-limit pause

def cg_get(endpoint, params=None):
    resp = requests.get(f"{CG_BASE}{endpoint}", params=params,
                        headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()

# 3a. Top-100 coins by market cap with 7d/30d price change
coins_page1 = cg_get("/coins/markets", params={
    "vs_currency": "usd",
    "order": "market_cap_desc",
    "per_page": 100,
    "page": 1,
    "sparkline": "false",
    "price_change_percentage": "7d,30d",
})
time.sleep(DELAY)

cg_coins_df = pd.DataFrame(coins_page1)
print(f"\n[CoinGecko] /coins/markets top-100 : {cg_coins_df.shape}")

# 3b. Global market data — BTC dominance, total market cap, altcoin context
global_data = cg_get("/global")
time.sleep(DELAY)
gd = global_data.get("data", {})

btc_dominance   = gd.get("market_cap_percentage", {}).get("btc", None)
eth_dominance   = gd.get("market_cap_percentage", {}).get("eth", None)
total_market_cap_usd = gd.get("total_market_cap", {}).get("usd", None)
total_volume_usd     = gd.get("total_volume", {}).get("usd", None)
active_cryptos       = gd.get("active_cryptocurrencies", None)
market_cap_change_24h = gd.get("market_cap_change_percentage_24h_usd", None)

print(f"[CoinGecko] BTC dominance       : {btc_dominance:.2f}%")
print(f"[CoinGecko] ETH dominance       : {eth_dominance:.2f}%")
print(f"[CoinGecko] Total mkt cap (USD) : ${total_market_cap_usd:,.0f}")
print(f"[CoinGecko] Active cryptos      : {active_cryptos}")

# ─────────────────────────────────────────────
# 4. BUILD UNIFIED SENTIMENT/PREDICTION MARKET DF
# ─────────────────────────────────────────────

# ── 4a. Normalise Kalshi full markets
kalshi_sentiment_cols = [
    "ticker", "event_ticker", "title", "subtitle", "status",
    "market_type", "strike_type", "expiration_time", "close_time",
    "last_price", "last_price_dollars",
    "yes_ask", "yes_bid", "yes_ask_dollars", "yes_bid_dollars",
    "no_ask",  "no_bid",  "no_ask_dollars",  "no_bid_dollars",
    "open_interest", "volume", "volume_24h",
    "liquidity", "liquidity_dollars",
    "notional_value", "notional_value_dollars",
    "floor_strike", "cap_strike", "result",
]
# keep only columns that actually exist
kalshi_keep = [c for c in kalshi_sentiment_cols if c in kalshi_markets_raw.columns]
kalshi_norm = kalshi_markets_raw[kalshi_keep].copy()
kalshi_norm["source"]     = "kalshi"
kalshi_norm["platform"]   = "Kalshi"
# Rename to common schema
kalshi_norm = kalshi_norm.rename(columns={
    "ticker":           "market_id",
    "event_ticker":     "event_id",
    "title":            "market_title",
    "subtitle":         "market_subtitle",
    "expiration_time":  "end_date",
    "close_time":       "close_date",
    "last_price":       "last_price_cents",   # 0-100 cents scale
    "last_price_dollars": "last_price_usd",
    "yes_ask_dollars":  "yes_ask_usd",
    "yes_bid_dollars":  "yes_bid_usd",
    "no_ask_dollars":   "no_ask_usd",
    "no_bid_dollars":   "no_bid_usd",
    "volume_24h":       "volume_24h_raw",
    "open_interest":    "open_interest_raw",
})
# Derive implied probability from yes_ask/yes_bid midpoint (0-100 scale)
if "yes_ask" in kalshi_norm.columns and "yes_bid" in kalshi_norm.columns:
    kalshi_norm["implied_prob"] = (kalshi_norm["yes_ask"] + kalshi_norm["yes_bid"]) / 2 / 100
else:
    kalshi_norm["implied_prob"] = None

# ── 4b. Normalise Polymarket markets
poly_markets_cols = [
    "id", "question", "category", "endDate", "startDate",
    "liquidity", "volume", "openInterest",
    "volume24hr", "volume1wk", "volume1mo",
    "lastTradePrice", "bestBid", "bestAsk",
    "oneDayPriceChange", "oneWeekPriceChange", "oneMonthPriceChange",
    "active", "closed", "archived", "restricted",
    "competitive",
]
poly_keep = [c for c in poly_markets_cols if c in poly_markets_raw.columns]
poly_norm = poly_markets_raw[poly_keep].copy()
poly_norm["source"]   = "polymarket"
poly_norm["platform"] = "Polymarket"
poly_norm = poly_norm.rename(columns={
    "id":               "market_id",
    "question":         "market_title",
    "endDate":          "end_date",
    "startDate":        "close_date",   # closest equivalent
    "openInterest":     "open_interest_raw",
    "volume24hr":       "volume_24h_raw",
    "lastTradePrice":   "last_price_usd",
    "bestBid":          "yes_bid_usd",
    "bestAsk":          "yes_ask_usd",
    "oneDayPriceChange":  "price_change_1d",
    "oneWeekPriceChange": "price_change_7d",
    "oneMonthPriceChange":"price_change_30d",
})
# Implied probability from midpoint of bid/ask
if "yes_ask_usd" in poly_norm.columns and "yes_bid_usd" in poly_norm.columns:
    poly_norm["implied_prob"] = (poly_norm["yes_ask_usd"] + poly_norm["yes_bid_usd"]) / 2
else:
    poly_norm["implied_prob"] = None

poly_norm["market_subtitle"] = poly_norm.get("category", None) if "category" in poly_norm.columns else None
if "category" in poly_norm.columns:
    poly_norm["market_subtitle"] = poly_norm["category"]

# ── 4c. Align columns and concatenate
common_cols = [
    "source", "platform", "market_id", "event_id" if "event_id" in kalshi_norm.columns else "market_id",
    "market_title", "market_subtitle", "status", "market_type", "strike_type",
    "end_date", "close_date", "implied_prob",
    "last_price_usd", "yes_ask_usd", "yes_bid_usd", "no_ask_usd", "no_bid_usd",
    "volume", "volume_24h_raw", "open_interest_raw", "liquidity",
    "result", "active", "closed", "restricted",
]

def safe_concat_df(df, cols):
    """Keep only existing cols, add missing as NaN."""
    existing = [c for c in cols if c in df.columns]
    missing  = [c for c in cols if c not in df.columns]
    out = df[existing].copy()
    for mc in missing:
        out[mc] = None
    return out[cols]

all_common = list(dict.fromkeys(common_cols))   # deduplicate, preserve order
kalshi_aligned = safe_concat_df(kalshi_norm, all_common)
poly_aligned   = safe_concat_df(poly_norm,   all_common)

unified_sentiment_df = pd.concat([kalshi_aligned, poly_aligned], ignore_index=True)

print(f"\n{'='*60}")
print("UNIFIED SENTIMENT / PREDICTION MARKET DATAFRAME")
print(f"{'='*60}")
print(f"Shape  : {unified_sentiment_df.shape}")
print(f"Columns ({len(unified_sentiment_df.columns)}):")
for col in unified_sentiment_df.columns:
    nn = unified_sentiment_df[col].notna().sum()
    print(f"  {col:<30} | non-null: {nn}/{len(unified_sentiment_df)}")

# ─────────────────────────────────────────────
# 5. BUILD UNIFIED MARKET STRUCTURE DF
# ─────────────────────────────────────────────

# 5a. CoinGecko coins — select & rename key columns
cg_keep = [
    "id", "symbol", "name", "current_price",
    "market_cap", "market_cap_rank",
    "fully_diluted_valuation",
    "total_volume",
    "high_24h", "low_24h",
    "price_change_24h", "price_change_percentage_24h",
    "price_change_percentage_7d_in_currency",
    "price_change_percentage_30d_in_currency",
    "market_cap_change_24h", "market_cap_change_percentage_24h",
    "circulating_supply", "total_supply", "max_supply",
    "ath", "ath_change_percentage",
    "atl", "atl_change_percentage",
    "last_updated",
]
cg_existing = [c for c in cg_keep if c in cg_coins_df.columns]
cg_norm = cg_coins_df[cg_existing].copy()
cg_norm = cg_norm.rename(columns={
    "id":                                   "coin_id",
    "price_change_percentage_7d_in_currency":  "price_change_pct_7d",
    "price_change_percentage_30d_in_currency": "price_change_pct_30d",
    "price_change_percentage_24h":             "price_change_pct_24h",
})
cg_norm["source"] = "coingecko"
cg_norm["data_type"] = "spot_market"

# 5b. Compute BTC dominance index per coin
#   dominance_ratio = coin_market_cap / total_market_cap_usd
if total_market_cap_usd and total_market_cap_usd > 0:
    cg_norm["dominance_pct"] = (cg_norm["market_cap"] / total_market_cap_usd) * 100
else:
    cg_norm["dominance_pct"] = None

# 5c. Altcoin vs BTC performance ratio (7d)
#   ratio > 1 → outperformed BTC; < 1 → underperformed
btc_row = cg_norm[cg_norm["symbol"].str.upper() == "BTC"]
btc_7d_change = btc_row["price_change_pct_7d"].iloc[0] if not btc_row.empty else None

if btc_7d_change is not None and btc_7d_change != 0:
    cg_norm["alt_vs_btc_perf_7d"] = cg_norm["price_change_pct_7d"] / btc_7d_change
else:
    cg_norm["alt_vs_btc_perf_7d"] = None

# 5d. Attach global context columns
cg_norm["btc_dominance_global_pct"]  = btc_dominance
cg_norm["eth_dominance_global_pct"]  = eth_dominance
cg_norm["total_crypto_market_cap"]   = total_market_cap_usd
cg_norm["total_crypto_volume_24h"]   = total_volume_usd
cg_norm["global_mktcap_change_24h_pct"] = market_cap_change_24h

unified_market_df = cg_norm.reset_index(drop=True)

print(f"\n{'='*60}")
print("UNIFIED MARKET STRUCTURE DATAFRAME")
print(f"{'='*60}")
print(f"Shape  : {unified_market_df.shape}")
print(f"Columns ({len(unified_market_df.columns)}):")
for col in unified_market_df.columns:
    nn = unified_market_df[col].notna().sum()
    print(f"  {col:<40} | non-null: {nn}/{len(unified_market_df)}")

# ─────────────────────────────────────────────
# 6. QUICK INTEGRITY CHECKS
# ─────────────────────────────────────────────
print(f"\n{'='*60}")
print("DATA INTEGRITY SUMMARY")
print(f"{'='*60}")

# Sources breakdown in sentiment df
src_counts = unified_sentiment_df["source"].value_counts()
print(f"\nSentiment DF — records by source:")
for src, cnt in src_counts.items():
    print(f"  {src:<15}: {cnt} rows")

print(f"\nSentiment DF — null % per key column:")
key_sent_cols = ["implied_prob", "volume", "last_price_usd"]
for c in key_sent_cols:
    if c in unified_sentiment_df.columns:
        pct = unified_sentiment_df[c].isna().mean() * 100
        print(f"  {c:<30}: {pct:.1f}% null")

print(f"\nMarket Structure DF — sample (top 5 coins):")
preview_cols = ["coin_id", "symbol", "current_price", "market_cap",
                "dominance_pct", "price_change_pct_7d", "price_change_pct_30d",
                "alt_vs_btc_perf_7d", "btc_dominance_global_pct"]
avail_prev = [c for c in preview_cols if c in unified_market_df.columns]
print(unified_market_df[avail_prev].head(5).to_string(index=False))

print(f"\n✅ All sources loaded and merged successfully.")
print(f"   unified_sentiment_df : {unified_sentiment_df.shape}")
print(f"   unified_market_df    : {unified_market_df.shape}")

# ─────────────────────────────────────────────────────────
# Save dataframes as pickle for downstream phases
# ─────────────────────────────────────────────────────────
import pickle

output_dir = Path("outputs")
output_dir.mkdir(exist_ok=True)

# Save unified dataframes
with open(output_dir / "unified_market_df.pkl", "wb") as f:
    pickle.dump(unified_market_df, f)
with open(output_dir / "unified_sentiment_df.pkl", "wb") as f:
    pickle.dump(unified_sentiment_df, f)

# Save global context variables for Phase 7
global_context = {
    "btc_dominance": btc_dominance,
    "eth_dominance": eth_dominance,
    "total_market_cap_usd": total_market_cap_usd,
    "total_volume_usd": total_volume_usd,
    "active_cryptos": active_cryptos,
    "market_cap_change_24h": market_cap_change_24h,
}
with open(output_dir / "global_context.pkl", "wb") as f:
    pickle.dump(global_context, f)

# ── Also write human-readable versions ──────────────────────────────
import json as _json

unified_market_df.to_csv(output_dir / "unified_market_df.csv", index=False)
unified_sentiment_df.to_csv(output_dir / "unified_sentiment_df.csv", index=False)

with open(output_dir / "global_context.json", "w") as _f:
    _json.dump(global_context, _f, indent=2, default=str)

print(f"   Saved to outputs/: unified_market_df.pkl/.csv, unified_sentiment_df.pkl/.csv, global_context.pkl/.json")
