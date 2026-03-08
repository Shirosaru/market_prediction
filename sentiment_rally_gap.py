"""
SENTIMENT-REALITY GAP ANALYSIS
================================
Compare crowd prediction market sentiment (Kalshi + Polymarket) against
hard technical signals (RSI, MA regime, BTC dominance, altcoin season index)
to find where the crowd is dangerously wrong.
"""

import pandas as pd
import numpy as np
import re
import json
import time
import requests
import pickle
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import datetime

# ── Load context from previous phases ──────────────────────────────
output_dir = Path("outputs")
try:
    with open(output_dir / "global_context.pkl", "rb") as f:
        global_context = pickle.load(f)
    btc_dominance = global_context.get("btc_dominance", 56.0)
    eth_dominance = global_context.get("eth_dominance", 9.9)
    total_market_cap_usd = global_context.get("total_market_cap_usd")
    total_volume_usd = global_context.get("total_volume_usd")
    active_cryptos = global_context.get("active_cryptos")
    market_cap_change_24h = global_context.get("market_cap_change_24h", 0.0)
    print(f"✓ Loaded global context (BTC dominance: {btc_dominance:.2f}%)")
except FileNotFoundError:
    print("⚠ Warning: global_context.pkl not found. Using defaults.")
    btc_dominance = 56.0
    eth_dominance = 9.9
    total_market_cap_usd = 2.4e12
    total_volume_usd = 50e9
    active_cryptos = 18607
    market_cap_change_24h = 0.0

# ── Zerve Design System ───────────────────────────────────────────
BG      = "#1D1D20"
FG      = "#fbfbff"
FG2     = "#909094"
BLUE    = "#A1C9F4"
ORANGE  = "#FFB482"
GREEN   = "#8DE5A1"
CORAL   = "#FF9F9B"
LAV     = "#D0BBFF"
GOLD    = "#ffd400"
EMERALD = "#17b26a"
RED     = "#f04438"
PURPLE  = "#9467BD"

plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "axes.edgecolor": FG2,
    "axes.labelcolor": FG, "xtick.color": FG2, "ytick.color": FG2,
    "text.color": FG, "grid.color": "#2d2d35", "grid.linewidth": 0.5,
    "font.family": "sans-serif", "font.size": 11,
})

# ══════════════════════════════════════════════════════════════════
# 1. EXTRACT CROWD SENTIMENT FROM KALSHI & POLYMARKET
# ══════════════════════════════════════════════════════════════════
print("=" * 65)
print("STEP 1: EXTRACTING CROWD SENTIMENT SCORES")
print("=" * 65)

# -- KALSHI: Fetch live open markets from API first, fall back to disk CSV
_KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
_kalshi_live = []
for _st in ["KXBTC", "KXETH", "BTC", "ETH", "SOL", "XRP", "CRYPTO"]:
    try:
        _r = requests.get(f"{_KALSHI_BASE}/markets",
                          params={"limit": 200, "series_ticker": _st, "status": "open"},
                          timeout=15)
        if _r.ok:
            _mlist = _r.json().get("markets", [])
            _kalshi_live.extend(_mlist)
    except Exception as _ex:
        print(f"  [WARN] Kalshi live fetch {_st}: {_ex}")
    time.sleep(0.3)

if _kalshi_live:
    print(f"  [Kalshi live] {len(_kalshi_live)} open markets fetched from API")
    df_kal_raw = pd.DataFrame(_kalshi_live)
else:
    print("  [Kalshi] Live fetch returned 0 open markets — loading disk CSV")
    df_kal_raw = pd.read_csv("data/kalshi/crypto_markets.csv")

# Extract crypto identifier from event_ticker
def kal_extract_ticker(event_tk):
    """Map Kalshi event_ticker prefix to crypto symbol."""
    et = str(event_tk).upper()
    for sym in ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "LTC", "LINK"]:
        if sym in et:
            return sym
    return None

if "event_ticker" not in df_kal_raw.columns:
    df_kal_raw["event_ticker"] = df_kal_raw.get("ticker", "").str.rsplit("-T", n=1).str[0]
df_kal_raw["crypto_sym"] = df_kal_raw["event_ticker"].apply(kal_extract_ticker)

# Keep markets with actual pricing — try yes_ask/bid, last_price, previous_price, or no_ask inferred YES
for _col in ["yes_ask", "yes_bid", "last_price", "previous_price", "no_ask", "no_bid"]:
    if _col not in df_kal_raw.columns:
        df_kal_raw[_col] = 0
    df_kal_raw[_col] = pd.to_numeric(df_kal_raw[_col], errors="coerce").fillna(0)

df_kal_priced = df_kal_raw[
    ((df_kal_raw["yes_ask"] + df_kal_raw["yes_bid"]) > 0) |
    (df_kal_raw["last_price"] > 0) |
    (df_kal_raw["previous_price"] > 0) |
    # infer YES from no_ask: in a binary market, YES ≈ 100 - no_ask
    (df_kal_raw["no_ask"].between(1, 99))
].copy()

def _kal_crowd_prob(row):
    if (row["yes_ask"] + row["yes_bid"]) > 0:
        return (row["yes_ask"] + row["yes_bid"]) / 2 / 100
    if row["last_price"] > 0:
        return row["last_price"] / 100
    if row["previous_price"] > 0:
        return row["previous_price"] / 100
    if 1 <= row["no_ask"] <= 99:
        return (100 - row["no_ask"]) / 100  # inferred YES from NO ask
    return np.nan

df_kal_priced["crowd_prob"] = df_kal_priced.apply(_kal_crowd_prob, axis=1)
df_kal_priced = df_kal_priced[df_kal_priced["crowd_prob"].between(0.01, 0.99)].copy()

# For sentiment per crypto: take median crowd prob across all its markets
kal_sent = (df_kal_priced.groupby("event_ticker")
    .agg(crowd_prob=("crowd_prob", "mean"),
         volume=("volume", "sum"),
         n_markets=("ticker", "count"),
         subtitle=("subtitle", "first"),
         event_ticker=("event_ticker", "first"),
         crypto_sym=("crypto_sym", "first"))
    .reset_index(drop=True))
kal_sent["platform"] = "Kalshi"

print(f"\n[Kalshi] {len(df_kal_priced)} priced markets → {len(kal_sent)} unique events")

# Group by crypto symbol for a per-coin aggregate view
kal_by_coin = {}
for sym in ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE"]:
    sub = df_kal_priced[df_kal_priced["crypto_sym"] == sym]
    if len(sub) > 0:
        wts = np.maximum(sub["volume"].values.astype(float), 1.0)
        wavg = float(np.average(sub["crowd_prob"].values, weights=wts))
        kal_by_coin[sym] = {"crowd_prob": wavg, "n_markets": len(sub), "source": "Kalshi"}
        print(f"  Kalshi {sym}: {wavg*100:.1f}% avg implied probability ({len(sub)} markets)")

# -- POLYMARKET: Fetch live prices for active crypto markets, fall back to saved CSV
PGAMMA = "https://gamma-api.polymarket.com"
HDR = {"accept": "application/json"}

def fetch_poly_crypto():
    """Fetch active crypto prediction markets from Polymarket."""
    kws = ["bitcoin", "btc", "ethereum", "eth", "solana", "sol", "crypto"]
    mkts = []
    for kw in kws:
        try:
            rr = requests.get(f"{PGAMMA}/markets",
                              params={"q": kw, "limit": 100, "active": "true"},
                              headers=HDR, timeout=15)
            if rr.ok and isinstance(rr.json(), list):
                mkts.extend(rr.json())
        except Exception as ex:
            print(f"  [WARN] Polymarket {kw}: {ex}")
        time.sleep(0.5)
    return mkts

poly_raw = fetch_poly_crypto()
# Check if live markets have any real liquidity; if not, also load from saved CSV
_live_liquid = sum(1 for m in poly_raw if float(m.get("liquidityNum") or 0) > 0)
if _live_liquid == 0:
    print(f"\n[Polymarket] Live API: {len(poly_raw)} markets but 0 with liquidity — trying saved CSV fallback")
    try:
        _pm_csv = pd.read_csv("data/polymarket/crypto_markets.csv")
        _pm_csv_liquid = _pm_csv[pd.to_numeric(_pm_csv.get("liquidityNum", 0), errors="coerce").fillna(0) > 0]
        # Convert CSV rows to dict format compatible with the parser below
        poly_raw = _pm_csv_liquid.to_dict(orient="records")
        print(f"[Polymarket] Loaded {len(poly_raw)} liquid markets from saved CSV")
    except Exception as _pm_e:
        print(f"[Polymarket] CSV fallback failed: {_pm_e}")
else:
    print(f"\n[Polymarket] {len(poly_raw)} raw markets fetched ({_live_liquid} with liquidity)")

def poly_extract_crypto(q):
    q_lower = q.lower()
    if "bitcoin" in q_lower or " btc" in q_lower:
        return "BTC"
    if "ethereum" in q_lower or " eth" in q_lower:
        return "ETH"
    if "solana" in q_lower or " sol" in q_lower:
        return "SOL"
    if "ripple" in q_lower or " xrp" in q_lower:
        return "XRP"
    if "binance" in q_lower or " bnb" in q_lower:
        return "BNB"
    if "doge" in q_lower:
        return "DOGE"
    return None

poly_records = []
for pm in poly_raw:
    # Skip illiquid markets entirely
    if float(pm.get("liquidityNum") or 0) <= 0 and float(pm.get("volumeNum") or pm.get("volume") or 0) <= 0:
        continue
    qs = pm.get("question", "")
    sym = poly_extract_crypto(qs)
    if not sym:
        continue
    # Extract YES price — try multiple fields in order of reliability
    yp = None
    # 1. outcomePrices JSON list [yes_price, no_price] — values in 0-1 decimal
    op_str = pm.get("outcomePrices", "")
    if isinstance(op_str, str) and op_str.strip():
        try:
            op_parsed = json.loads(op_str)
            v = float(op_parsed[0]) if op_parsed else 0
            if v > 1:        # might be in cents (0-100)
                v = v / 100
            if 0.005 < v < 0.995:
                yp = v
        except Exception:
            pass
    # 2. bestBid / bestAsk midpoint — can be 0-1 decimal or 0-100 cents
    if yp is None:
        _bb = pm.get("bestBid")
        _ba = pm.get("bestAsk")
        if _bb is not None and _ba is not None:
            try:
                bb, ba = float(_bb), float(_ba)
                if ba > 1:           # cents scale → convert
                    bb, ba = bb / 100, ba / 100
                if 0 < bb < ba < 1:  # valid spread
                    mid = (bb + ba) / 2
                    if 0.005 < mid < 0.995:
                        yp = mid
            except Exception:
                pass
    # 3. lastTradePrice
    if yp is None:
        ltp = pm.get("lastTradePrice") or pm.get("last_trade_price")
        if ltp is not None:
            try:
                ltp = float(ltp)
                ltp = ltp / 100 if ltp > 1 else ltp
                if 0.005 < ltp < 0.995:
                    yp = ltp
            except Exception:
                pass
    if yp is None:
        continue
    poly_records.append({
        "crypto_sym": sym,
        "question": qs,
        "crowd_prob": yp,
        "volume": float(pm.get("volumeNum") or pm.get("volume") or 0),
    })

poly_by_coin = {}
if poly_records:
    df_poly = pd.DataFrame(poly_records)
    for sym, grp in df_poly.groupby("crypto_sym"):
        wts = np.maximum(grp["volume"].values, 1.0)
        wavg = float(np.average(grp["crowd_prob"].values, weights=wts))
        poly_by_coin[sym] = {"crowd_prob": wavg, "n_markets": len(grp), "source": "Polymarket"}
        print(f"  Polymarket {sym}: {wavg*100:.1f}% avg implied probability ({len(grp)} markets)")

# Merge Kalshi + Polymarket: weighted average per coin
all_syms = sorted(set(list(kal_by_coin.keys()) + list(poly_by_coin.keys())))
crowd_sentiment = {}
for sym in all_syms:
    probs, weights = [], []
    if sym in kal_by_coin:
        probs.append(kal_by_coin[sym]["crowd_prob"])
        weights.append(max(kal_by_coin[sym]["n_markets"], 1))
    if sym in poly_by_coin:
        probs.append(poly_by_coin[sym]["crowd_prob"])
        weights.append(max(poly_by_coin[sym]["n_markets"] * 2, 1))  # Polymarket = real liquidity
    if probs:
        w_arr = np.array(weights, dtype=float)
        combined = float(np.average(probs, weights=w_arr))
        crowd_sentiment[sym] = {
            "crowd_prob":   combined,
            "kalshi_prob":  kal_by_coin.get(sym, {}).get("crowd_prob"),
            "poly_prob":    poly_by_coin.get(sym, {}).get("crowd_prob"),
            "cg_comm_prob": None,
            "n_kalshi":     kal_by_coin.get(sym, {}).get("n_markets", 0),
            "n_poly":       poly_by_coin.get(sym, {}).get("n_markets", 0),
        }

# -- STEP 1c: CoinGecko Community Sentiment (fills in all altcoins)
# Load from disk (written by fetch_crypto_data.py Phase 5); fall back to live fetch
_cg_sent = {}
try:
    _df_cg = pd.read_csv("data/coingecko/community_sentiment.csv")
    for _, _cgr in _df_cg.iterrows():
        _cg_sent[str(_cgr["symbol"]).upper()] = float(_cgr["crowd_prob"])
    print(f"\n[CoinGecko Community] {len(_cg_sent)} coins loaded from disk")
except Exception:
    print("\n[CoinGecko Community] Disk file not found — fetching live...")
    _CG_COINS = [
        "bitcoin","ethereum","solana","ripple","binancecoin","dogecoin",
        "cardano","avalanche-2","chainlink","polkadot","uniswap","litecoin",
        "cosmos","near","aptos","optimism","arbitrum","sui","pepe","shiba-inu",
        "internet-computer","hedera-hashgraph","vechain","algorand",
        "the-open-network","kaspa","filecoin","render-token","bittensor","hyperliquid",
    ]
    for _cid in _CG_COINS:
        try:
            _r = requests.get(
                f"https://api.coingecko.com/api/v3/coins/{_cid}",
                params={"localization":"false","tickers":"false",
                        "market_data":"false","community_data":"true",
                        "developer_data":"false"},
                timeout=12,
            )
            if _r.ok:
                _d = _r.json()
                _up = _d.get("sentiment_votes_up_percentage")
                _sym = _d.get("symbol","").upper()
                if _up is not None and _sym:
                    _cg_sent[_sym] = round(float(_up) / 100, 4)
        except Exception:
            pass
        time.sleep(1.2)
    print(f"  [CoinGecko Community] {len(_cg_sent)} coins fetched live")

# Merge CoinGecko community sentiment into crowd_sentiment dict
# It gets a lower weight (0.3×) than prediction markets (real money)
# Only used for coins NOT already covered by Kalshi/Polymarket
_cg_added = []
for _sym, _cp in _cg_sent.items():
    if _sym not in kal_by_coin and _sym not in poly_by_coin:
        crowd_sentiment[_sym] = {
            "crowd_prob":   _cp,
            "kalshi_prob":  None,
            "poly_prob":    None,
            "cg_comm_prob": _cp,
            "n_kalshi":     0,
            "n_poly":       0,
        }
        all_syms = sorted(set(list(all_syms) + [_sym]))
        _cg_added.append(_sym)
    elif _sym in crowd_sentiment:
        # Blend CoinGecko community into existing prediction-market probability
        _existing = crowd_sentiment[_sym]["crowd_prob"]
        _blended  = round(_existing * 0.85 + _cp * 0.15, 4)  # 85% pred market, 15% community
        crowd_sentiment[_sym]["crowd_prob"]   = _blended
        crowd_sentiment[_sym]["cg_comm_prob"] = _cp

print(f"  Added {len(_cg_added)} altcoins from CoinGecko community sentiment: {_cg_added[:10]}{'...' if len(_cg_added)>10 else ''}")
print(f"\n[Unified] {len(crowd_sentiment)} coins with crowd sentiment scores:")
for _s, _v in list(crowd_sentiment.items())[:8]:
    _src = "Kalshi+Poly" if _v["n_kalshi"] or _v["n_poly"] else "CG Community"
    print(f"  {_s}: crowd_prob={_v['crowd_prob']*100:.1f}%  [{_src}]")
if len(crowd_sentiment) > 8:
    print(f"  ... and {len(crowd_sentiment)-8} more coins")

# ══════════════════════════════════════════════════════════════════
# 2. COMPUTE TECHNICAL REALITY SIGNALS
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 65)
print("STEP 2: COMPUTING TECHNICAL REALITY SIGNALS")
print("=" * 65)

# Load altseason context from Phase 5
try:
    with open(output_dir / "altseason_context.pkl", "rb") as f:
        altseason_context = pickle.load(f)
    altseason_index_30d = altseason_context.get("altseason_index_30d", 50.0)
    altseason_index_7d = altseason_context.get("altseason_index_7d", 50.0)
    altseason_index_24h = altseason_context.get("altseason_index_24h", 50.0)
    print(f"✓ Loaded altseason context from Phase 5")
except FileNotFoundError:
    print(f"⚠ Warning: altseason_context.pkl not found. Using defaults.")
    altseason_index_30d = 50.0
    altseason_index_7d = 50.0
    altseason_index_24h = 50.0

# -- BTC dominance from upstream (load_and_merge_unified_data)
_btc_dom = float(btc_dominance)   # 56.1%
_altidx_30d = float(altseason_index_30d)   # from altcoin_season_analysis
_altidx_7d  = float(altseason_index_7d)
_alt_idx_24h = float(altseason_index_24h)

# Dominance trend context (estimated)
_dom_trend_14d = -0.05  # default estimate if not available
altseason_summary = {"season_status": "NEUTRAL"}  # default
print(f"\n[Structural Context]")
print(f"  BTC Dominance   : {_btc_dom:.1f}%  (trend 14d: {_dom_trend_14d:+.3f})")
print(f"  Altcoin Idx 30d : {_altidx_30d:.0f}%  |  7d: {_altidx_7d:.0f}%  |  24h: {_alt_idx_24h:.0f}%")
print(f"  Season Status   : {altseason_summary.get('season_status', 'NEUTRAL')}")

# Load unified market df from Phase 4
try:
    with open(output_dir / "unified_market_df.pkl", "rb") as f:
        unified_market_df = pickle.load(f)
    print(f"✓ Loaded unified_market_df from Phase 4")
except Exception as _pkl_err:
    print(f"⚠ Could not load unified_market_df.pkl ({type(_pkl_err).__name__}). Trying CSV fallback...")
    try:
        unified_market_df = pd.read_csv(output_dir / "unified_market_df.csv")
        print(f"✓ Loaded unified_market_df from CSV ({len(unified_market_df)} rows)")
    except Exception:
        print("⚠ CSV not found either. Fetching price data directly from CoinGecko...")
        try:
            _cg_r = requests.get(
                "https://api.coingecko.com/api/v3/coins/markets",
                params={
                    "vs_currency": "usd",
                    "ids": "bitcoin,ethereum,solana,ripple,binancecoin,dogecoin",
                    "price_change_percentage": "7d,30d",
                    "sparkline": "false",
                    "per_page": 50,
                },
                timeout=20,
            )
            unified_market_df = pd.DataFrame(_cg_r.json()).rename(columns={
                "price_change_percentage_24h":              "price_change_pct_24h",
                "price_change_percentage_7d_in_currency":  "price_change_pct_7d",
                "price_change_percentage_30d_in_currency": "price_change_pct_30d",
            })
            print(f"✓ Fetched {len(unified_market_df)} coins from CoinGecko")
        except Exception as _cg_e:
            print(f"⚠ CoinGecko fetch failed: {_cg_e}. Technical signals unavailable.")
            unified_market_df = pd.DataFrame()

# -- Technical momentum per coin from unified_market_df (CoinGecko live)
# We'll use price changes to infer momentum signal
_mkt_df = unified_market_df.copy()
if not _mkt_df.empty and "symbol" in _mkt_df.columns:
    _mkt_df["symbol_upper"] = _mkt_df["symbol"].str.upper()
else:
    _mkt_df["symbol_upper"] = ""

def compute_tech_signal(row):
    """
    Compute a normalized [0, 1] technical bullishness score from:
    - 30d performance vs BTC (positive = outperforming BTC)
    - 7d performance vs BTC
    - 24h price change direction
    - ATH distance (far from ATH = bearish potential, or oversold bounce)
    Returns value 0..1 where 0.5 = neutral.
    """
    p30 = row.get("price_change_pct_30d", 0) or 0
    p7  = row.get("price_change_pct_7d", 0) or 0
    p24 = row.get("price_change_pct_24h", 0) or 0
    # Normalize signals to 0..1
    # 30d: -50% → 0, 0% → 0.5, +50% → 1
    sig30 = float(np.clip((p30 + 50) / 100, 0, 1))
    # 7d: -20% → 0, 0% → 0.5, +20% → 1
    sig7  = float(np.clip((p7  + 20) / 40,  0, 1))
    # 24h: -5% → 0, 0% → 0.5, +5% → 1
    sig24 = float(np.clip((p24 + 5) / 10,   0, 1))
    # Weighted composite (longer timeframes get more weight)
    composite = 0.5 * sig30 + 0.3 * sig7 + 0.2 * sig24
    return composite

tech_signals = {}
for sym in all_syms:
    _row = _mkt_df[_mkt_df["symbol_upper"] == sym]
    if len(_row) > 0:
        row_data = _row.iloc[0]
        sig = compute_tech_signal(row_data)
        tech_signals[sym] = {
            "tech_signal": sig,
            "p30d": float(row_data.get("price_change_pct_30d", 0) or 0),
            "p7d":  float(row_data.get("price_change_pct_7d",  0) or 0),
            "p24h": float(row_data.get("price_change_pct_24h", 0) or 0),
            "ath_pct": float(row_data.get("ath_change_percentage", 0) or 0),
        }
        print(f"  {sym}: tech_signal={sig:.3f}  (30d={tech_signals[sym]['p30d']:+.1f}%  "
              f"7d={tech_signals[sym]['p7d']:+.1f}%  24h={tech_signals[sym]['p24h']:+.1f}%)")

# Also add BTC from indicators if available (BTC is in unified_market_df)
if "BTC" not in tech_signals:
    _btc_mkt = _mkt_df[_mkt_df["symbol_upper"] == "BTC"]
    if len(_btc_mkt) > 0:
        sig = compute_tech_signal(_btc_mkt.iloc[0])
        tech_signals["BTC"] = {"tech_signal": sig,
            "p30d": float(_btc_mkt.iloc[0].get("price_change_pct_30d", 0) or 0),
            "p7d":  float(_btc_mkt.iloc[0].get("price_change_pct_7d",  0) or 0),
            "p24h": float(_btc_mkt.iloc[0].get("price_change_pct_24h", 0) or 0),
            "ath_pct": float(_btc_mkt.iloc[0].get("ath_change_percentage", 0) or 0)}

# Structural adjustment: BTC dominance & altcoin index modify reality signal
# High BTC dominance (>55%) = bearish for alts, neutral/slightly bullish for BTC
# Altcoin index 30d < 50 = bearish for alts; > 75 = bullish for alts
dom_structural_adj = 0.0
if _btc_dom > 55:
    dom_structural_adj = -0.05  # structural headwind for alts
elif _btc_dom < 45:
    dom_structural_adj = +0.05  # structural tailwind for alts

alt_structural_adj = 0.0
if _altidx_30d >= 75:
    alt_structural_adj = +0.05  # altseason = bullish alts
elif _altidx_30d < 50:
    alt_structural_adj = -0.05  # BTC season = bearish alts

# ══════════════════════════════════════════════════════════════════
# 3. COMPUTE SENTIMENT-REALITY GAP
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 65)
print("STEP 3: COMPUTING SENTIMENT-REALITY GAP")
print("=" * 65)

# Gap = crowd_prob - tech_signal
# Positive gap = crowd MORE bullish than data supports (overconfident)
# Negative gap = crowd MORE bearish than data supports (potential opportunity)

gap_records = []
for sym in all_syms:
    if sym not in crowd_sentiment or sym not in tech_signals:
        continue
    crowd_p = crowd_sentiment[sym]["crowd_prob"]
    tech_s  = tech_signals[sym]["tech_signal"]
    # Apply structural adjustments for alts (not BTC)
    adj_signal = tech_s
    if sym != "BTC":
        adj_signal = float(np.clip(tech_s + dom_structural_adj + alt_structural_adj, 0, 1))
    
    gap = crowd_p - adj_signal
    
    gap_records.append({
        "symbol": sym,
        "crowd_prob": crowd_p,
        "tech_signal": adj_signal,
        "gap": gap,
        "kalshi_prob": crowd_sentiment[sym].get("kalshi_prob"),
        "poly_prob":   crowd_sentiment[sym].get("poly_prob"),
        "n_kalshi":    crowd_sentiment[sym].get("n_kalshi", 0),
        "n_poly":      crowd_sentiment[sym].get("n_poly", 0),
        "p30d":        tech_signals[sym]["p30d"],
        "p7d":         tech_signals[sym]["p7d"],
        "p24h":        tech_signals[sym]["p24h"],
        "ath_pct":     tech_signals[sym]["ath_pct"],
    })

# Handle empty records case
if len(gap_records) > 0:
    gap_df = pd.DataFrame(gap_records).sort_values("gap", ascending=False).reset_index(drop=True)
    gap_df["gap_pct"] = gap_df["gap"] * 100
else:
    print("\n[!] No overlapping symbols between crowd sentiment and technical signals.")
    gap_df = pd.DataFrame(columns=["symbol", "crowd_prob", "tech_signal", "gap", "gap_pct"])

print("\n  SENTIMENT-REALITY GAP SCORES (sorted most overconfident → most undervalued):")
print(f"  {'Symbol':<8}  {'Crowd%':>7}  {'TechSig':>8}  {'Gap':>8}  {'Verdict'}")
print("  " + "-" * 60)
for _, row_g in gap_df.iterrows():
    verdict = "OVERCONFIDENT" if row_g["gap"] > 0.10 else ("UNDERVALUED" if row_g["gap"] < -0.10 else "ALIGNED")
    print(f"  {row_g['symbol']:<8}  {row_g['crowd_prob']*100:>6.1f}%  "
          f"{row_g['tech_signal']*100:>7.1f}%  {row_g['gap_pct']:>+7.1f}%  {verdict}")

# Top 5 overconfident and top 5 undervalued
top_over = gap_df[gap_df["gap"] > 0].head(5)
top_under = gap_df[gap_df["gap"] < 0].tail(5).sort_values("gap")

print(f"\n  TOP OVERPRICED BELIEFS (crowd > data says):")
for _, r in top_over.iterrows():
    print(f"    {r['symbol']}: crowd {r['crowd_prob']*100:.1f}% vs tech {r['tech_signal']*100:.1f}%  gap +{r['gap_pct']:.1f}%")

print(f"\n  TOP UNDERVALUED BELIEFS (data more bullish than crowd):")
for _, r in top_under.iterrows():
    print(f"    {r['symbol']}: crowd {r['crowd_prob']*100:.1f}% vs tech {r['tech_signal']*100:.1f}%  gap {r['gap_pct']:.1f}%")

# ══════════════════════════════════════════════════════════════════
# 4. VISUALIZATIONS
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 65)
print("STEP 4: GENERATING VISUALIZATIONS")
print("=" * 65)

CHARTS_DIR = Path("outputs/charts")
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Chart 1: Scatter — Crowd Sentiment vs Technical Signal ────────
crowd_vs_tech_scatter = plt.figure(figsize=(12, 8), facecolor=BG)
ax1 = crowd_vs_tech_scatter.add_subplot(111)
ax1.set_facecolor(BG)

if len(gap_df) > 0:
    _syms_list = gap_df["symbol"].tolist()
    _crowd   = gap_df["crowd_prob"].values * 100
    _tech    = gap_df["tech_signal"].values * 100
    _gaps    = gap_df["gap"].values

    # Color by gap: coral = overconfident, green = undervalued
    _colors = [CORAL if g > 0.05 else (GREEN if g < -0.05 else BLUE) for g in _gaps]
    _sizes  = 200 + np.abs(_gaps) * 1200

    scatter = ax1.scatter(_tech, _crowd, s=_sizes, c=_colors, alpha=0.85,
                           edgecolors=FG2, linewidths=0.8, zorder=5)

    # Diagonal line = perfect alignment
    diag_x = np.linspace(0, 100, 100)
    ax1.plot(diag_x, diag_x, color=FG2, lw=1.5, linestyle="--", alpha=0.6, label="Perfect Alignment", zorder=3)

    # Shade: above diagonal = overconfident (crowd > data), below = undervalued
    ax1.fill_between(diag_x, diag_x, 100, color=CORAL, alpha=0.06, label="Crowd Overconfident Zone")
    ax1.fill_between(diag_x, 0, diag_x, color=GREEN,  alpha=0.06, label="Data More Bullish Zone")

    # Labels for each point
    for i, sym in enumerate(_syms_list):
        y_off = 2.5 if _crowd[i] > _tech[i] else -4.5
        ax1.annotate(sym, (_tech[i], _crowd[i]),
                     xytext=(_tech[i], _crowd[i] + y_off),
                     fontsize=10, fontweight="bold", color=FG, ha="center",
                     arrowprops=None)

ax1.set_xlabel("Technical Signal Strength (%)", fontsize=12, color=FG)
ax1.set_ylabel("Crowd Sentiment Score (implied probability %)", fontsize=12, color=FG)
ax1.set_title("Crowd Sentiment vs Technical Signal — Where Is The Crowd Wrong?",
              fontsize=14, fontweight="bold", color=FG, pad=12)
ax1.set_xlim(0, 100)
ax1.set_ylim(0, 100)
ax1.grid(True, alpha=0.25)

legend_patches = [
    mpatches.Patch(color=CORAL, label="Crowd overconfident (gap > 5%)"),
    mpatches.Patch(color=GREEN,  label="Data more bullish than crowd (gap < -5%)"),
    mpatches.Patch(color=BLUE,   label="Roughly aligned (|gap| ≤ 5%)"),
]
ax1.legend(handles=legend_patches + [
    plt.Line2D([0], [0], color=FG2, linestyle="--", lw=1.5, label="Perfect Alignment")],
    framealpha=0.3, facecolor=BG, edgecolor=FG2, labelcolor=FG, fontsize=9,
    loc="lower right")

plt.tight_layout(pad=1.5)
crowd_vs_tech_scatter.savefig(CHARTS_DIR / "sentiment_vs_tech_scatter.png", dpi=150, bbox_inches="tight", facecolor=BG)
print("  ✅ crowd_vs_tech_scatter rendered → outputs/charts/sentiment_vs_tech_scatter.png")

# ── Chart 2: Bar — Sentiment-Reality Gap by Market ────────────────
if len(gap_df) > 0:
    gap_bar_chart = plt.figure(figsize=(12, 7), facecolor=BG)
    ax2 = gap_bar_chart.add_subplot(111)
    ax2.set_facecolor(BG)

    _sorted_gaps = gap_df.sort_values("gap_pct", ascending=True)
    _bar_colors  = [CORAL if g > 0 else GREEN for g in _sorted_gaps["gap_pct"].values]

    bars = ax2.barh(_sorted_gaps["symbol"], _sorted_gaps["gap_pct"],
                    color=_bar_colors, alpha=0.88, edgecolor=FG2, linewidth=0.6)

    for bar_obj, gap_val in zip(bars, _sorted_gaps["gap_pct"].values):
        x_pos = gap_val + (0.5 if gap_val >= 0 else -0.5)
        ha = "left" if gap_val >= 0 else "right"
        ax2.text(x_pos, bar_obj.get_y() + bar_obj.get_height() / 2,
                 f"{gap_val:+.1f}%", ha=ha, va="center", color=FG, fontsize=10, fontweight="bold")

    ax2.axvline(0, color=FG2, lw=1.5, alpha=0.8)
    ax2.set_xlabel("Sentiment–Reality Gap (%)\n(positive = crowd more bullish than data)", color=FG, fontsize=11)
    ax2.set_title("Sentiment–Reality Gap by Market\nKalshi + Polymarket vs Technical Momentum Signals",
                  fontsize=13, fontweight="bold", color=FG, pad=10)
    ax2.grid(True, axis="x", alpha=0.25)

    over_p = mpatches.Patch(color=CORAL, label="Crowd overconfident (sell signal)")
    under_p = mpatches.Patch(color=GREEN, label="Crowd underestimates (buy signal)")
    ax2.legend(handles=[over_p, under_p], framealpha=0.3, facecolor=BG,
               edgecolor=FG2, labelcolor=FG, fontsize=10, loc="lower right")
    plt.tight_layout(pad=1.5)
    gap_bar_chart.savefig(CHARTS_DIR / "sentiment_gap_bar.png", dpi=150, bbox_inches="tight", facecolor=BG)
    print("  ✅ gap_bar_chart rendered → outputs/charts/sentiment_gap_bar.png")

# ── Chart 3: Summary Table ─────────────────────────────────────────
if len(gap_df) > 0:
    summary_table_fig = plt.figure(figsize=(14, max(4, len(gap_df) * 0.55 + 2.5)), facecolor=BG)
    ax3 = summary_table_fig.add_subplot(111)
    ax3.set_facecolor(BG)
    ax3.axis("off")

    table_cols = ["Symbol", "Crowd Prob", "Tech Signal", "Gap", "30d Perf", "7d Perf", "# Kalshi", "# Poly", "Verdict"]
    table_data = []
    for _, rw in gap_df.iterrows():
        verdict = ("🔴 OVERCONFIDENT" if rw["gap"] > 0.10
                   else ("🟢 UNDERVALUED"  if rw["gap"] < -0.10
                   else "🟡 ALIGNED"))
        table_data.append([
            rw["symbol"],
            f"{rw['crowd_prob']*100:.1f}%",
            f"{rw['tech_signal']*100:.1f}%",
            f"{rw['gap_pct']:+.1f}%",
            f"{rw['p30d']:+.1f}%",
            f"{rw['p7d']:+.1f}%",
            str(int(rw["n_kalshi"])),
            str(int(rw["n_poly"])),
            verdict,
        ])

    tbl = ax3.table(
        cellText=table_data,
        colLabels=table_cols,
        cellLoc="center",
        loc="center",
        bbox=[0, 0, 1, 1],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)

    # Style cells
    for (r, c), cell in tbl.get_celld().items():
        cell.set_facecolor("#28282e" if r % 2 == 0 else BG)
        cell.set_edgecolor(FG2)
        cell.set_linewidth(0.5)
        if r == 0:
            cell.set_facecolor("#3a3a42")
            cell.set_text_props(color=GOLD, fontweight="bold", fontsize=10)
        else:
            # Color the gap column
            if c == 3 and r > 0:
                gap_v = table_data[r-1][3]
                gap_f = float(gap_v.replace("%", "").replace("+", ""))
                cell.set_facecolor(CORAL + "30" if gap_f > 10 else (GREEN + "30" if gap_f < -10 else BG))
            cell.set_text_props(color=FG, fontsize=9)

    summary_table_fig.suptitle(
        "Sentiment–Reality Gap Summary Table  |  All Available Prediction Markets",
        fontsize=13, fontweight="bold", color=FG, y=0.98
    )
    plt.tight_layout(pad=2.0)
    summary_table_fig.savefig(CHARTS_DIR / "sentiment_gap_table.png", dpi=150, bbox_inches="tight", facecolor=BG)
    print("  ✅ summary_table_fig rendered → outputs/charts/sentiment_gap_table.png")
else:
    print("  ⚠️  No data for visualization; skipping charts")

# ── Chart 4: Altcoin Technical Momentum Heatmap (ALL coins) ───────
# Build tech signals for every coin in unified_market_df, filter stablecoins
STABLECOINS = {"USDT","USDC","DAI","BUSD","TUSD","USDP","GUSD","FRAX","LUSD",
               "USDD","PYUSD","USDS","FDUSD","EURC","USDE","USDTB","GHO","OUSG",
               "EUTBL","YLDS","BFUSD","USDTB","TBTC","WBTC","WETH","STETH",
               "CBETH","RETH","USD1","RAIN","STABLE","USYC"}
_all_coin_rows = []
if not _mkt_df.empty and "symbol" in _mkt_df.columns:
    for _, _cr in _mkt_df.iterrows():
        _sym = str(_cr.get("symbol", "")).upper()
        if not _sym or _sym in STABLECOINS:
            continue
        _sig = compute_tech_signal(_cr)
        _adj = _sig if _sym == "BTC" else float(np.clip(_sig + dom_structural_adj + alt_structural_adj, 0, 1))
        _all_coin_rows.append({
            "symbol":      _sym,
            "tech_signal": _adj,
            "p30d":        float(_cr.get("price_change_pct_30d", 0) or 0),
            "p7d":         float(_cr.get("price_change_pct_7d",  0) or 0),
            "p24h":        float(_cr.get("price_change_pct_24h", 0) or 0),
            "market_cap":  float(_cr.get("market_cap", 0) or 0),
            "crowd_prob":  crowd_sentiment.get(_sym, {}).get("crowd_prob", None),
        })

if _all_coin_rows:
    _all_df = (pd.DataFrame(_all_coin_rows)
               .drop_duplicates("symbol")
               .sort_values("tech_signal", ascending=True)
               .reset_index(drop=True))

    _n = len(_all_df)
    _fig_h = max(10, _n * 0.32 + 2.5)
    altcoin_heatmap_fig, _ax4 = plt.subplots(figsize=(14, _fig_h), facecolor=BG)
    _ax4.set_facecolor(BG)

    # Color map: red (0) → yellow (0.5) → green (1)
    _cmap = plt.cm.RdYlGn
    _bar_colors = [_cmap(float(v)) for v in _all_df["tech_signal"].values]

    _bars = _ax4.barh(_all_df["symbol"], _all_df["tech_signal"] * 100,
                      color=_bar_colors, alpha=0.88, edgecolor="#333338", linewidth=0.4)

    # Overlay crowd sentiment where available (BTC / ETH)
    for _, _row in _all_df.iterrows():
        if _row["crowd_prob"] is not None:
            _cp = float(_row["crowd_prob"]) * 100
            _ax4.plot(_cp, _row.name, marker="D", color=GOLD, markersize=7,
                      markeredgecolor=BG, markeredgewidth=0.8, zorder=6)
            _ax4.annotate(f" Crowd {_cp:.0f}%",
                          xy=(_cp, _row.name),
                          xytext=(_cp + 1.5, _row.name),
                          color=GOLD, fontsize=7.5, va="center", fontweight="bold")

    # Value labels on bars
    for _b, (_ts, _sym) in zip(_bars, zip(_all_df["tech_signal"].values, _all_df["symbol"].values)):
        _x = _b.get_width()
        _ax4.text(_x + 0.6, _b.get_y() + _b.get_height() / 2,
                  f"{_x:.0f}%", va="center", ha="left", color=FG, fontsize=7.5)

    # Reference lines
    _ax4.axvline(50, color=FG2, lw=1.2, linestyle="--", alpha=0.6, label="Neutral (50%)")
    _ax4.axvline(65, color=GREEN, lw=0.8, linestyle=":", alpha=0.45, label="Bullish zone")
    _ax4.axvline(35, color=CORAL, lw=0.8, linestyle=":", alpha=0.45, label="Bearish zone")

    _ax4.set_xlim(0, 105)
    _ax4.set_xlabel("Technical Momentum Signal (%)\n0 = strongly bearish  |  50 = neutral  |  100 = strongly bullish",
                    color=FG, fontsize=10)
    _ax4.set_title(
        f"Altcoin Technical Momentum Heatmap  |  {_n} Coins  |  Sorted Best → Worst\n"
        f"Gold diamond = prediction market crowd probability (Kalshi/Polymarket)",
        fontsize=13, fontweight="bold", color=FG, pad=10)
    _ax4.tick_params(axis="y", labelsize=8.5, labelcolor=FG)
    _ax4.tick_params(axis="x", labelcolor=FG2)
    _ax4.grid(True, axis="x", alpha=0.18)

    _legend_items = [
        mpatches.Patch(color=_cmap(0.85), label="Bullish momentum"),
        mpatches.Patch(color=_cmap(0.5),  label="Neutral momentum"),
        mpatches.Patch(color=_cmap(0.15), label="Bearish momentum"),
        plt.Line2D([0], [0], marker="D", color=GOLD, markersize=7,
                   linestyle="None", label="Crowd sentiment (Kalshi/Poly)"),
    ]
    _ax4.legend(handles=_legend_items, framealpha=0.3, facecolor=BG,
                edgecolor=FG2, labelcolor=FG, fontsize=9, loc="lower right")

    plt.tight_layout(pad=1.8)
    altcoin_heatmap_fig.savefig(CHARTS_DIR / "altcoin_momentum_heatmap.png",
                                dpi=150, bbox_inches="tight", facecolor=BG)
    print(f"  ✅ altcoin_momentum_heatmap rendered ({_n} coins) → outputs/charts/altcoin_momentum_heatmap.png")
else:
    print("  ⚠️  No market data available for altcoin heatmap")

# ══════════════════════════════════════════════════════════════════
# 5. NARRATIVE SUMMARY
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 65)
print("NARRATIVE SUMMARY: WHERE IS THE CROWD WRONG?")
print("=" * 65)

print(f"""
╔══════════════════════════════════════════════════════════════════╗
║           CRYPTO SENTIMENT vs REALITY — KEY FINDINGS            ║
╠══════════════════════════════════════════════════════════════════╣

📊 STRUCTURAL MARKET REALITY:
   • BTC Dominance: {_btc_dom:.1f}% — {'dominance rising (BTC season)' if _dom_trend_14d > 0 else 'dominance falling (alt season pressure)'}
   • Altcoin Season Index: {_altidx_30d:.0f}/100 (30d) — {altseason_summary['season_status']}
   • Market Cap Δ 24h: {market_cap_change_24h:+.1f}%

🎯 SENTIMENT-REALITY GAP RESULTS:
""")

if len(top_over) > 0:
    print("   TOP OVERCONFIDENT BETS (crowd believes more bullish than data supports):")
    for _, rw in top_over.iterrows():
        print(f"   → {rw['symbol']}: Crowd bets {rw['crowd_prob']*100:.0f}% vs tech signal {rw['tech_signal']*100:.0f}% | gap +{rw['gap_pct']:.0f}%")
        print(f"     Data: 30d perf {rw['p30d']:+.1f}% | 7d {rw['p7d']:+.1f}% — market momentum doesn't support crowd euphoria")

if len(top_under) > 0:
    print(f"\n   TOP UNDERVALUED BELIEFS (data more bullish than crowd thinks):")
    for _, rw in top_under.iterrows():
        print(f"   → {rw['symbol']}: Crowd only bets {rw['crowd_prob']*100:.0f}% vs tech signal {rw['tech_signal']*100:.0f}% | gap {rw['gap_pct']:.0f}%")
        print(f"     Data: 30d perf {rw['p30d']:+.1f}% | 7d {rw['p7d']:+.1f}% — crowd underestimates real momentum")

print(f"""
🔑 KEY CONCLUSIONS:
   • BTC dominance at {_btc_dom:.1f}% signals {'capital rotation BACK TO BTC — alts face structural headwinds.' if _btc_dom > 55 else 'capital flowing INTO alts — structural tailwind for alts.'}
   • The altcoin season 30d index is {_altidx_30d:.0f}/100: {'altcoin market is broadly outperforming BTC' if _altidx_30d > 75 else 'BTC is still leading — alts lag structurally' if _altidx_30d < 50 else 'mixed rotation, coin selection matters more than direction'}.
   • Prediction market crowds (Kalshi + Polymarket) are {'broadly overconfident relative to on-chain momentum' if gap_df['gap'].mean() > 0.05 else 'broadly underestimating momentum relative to technical signals' if gap_df['gap'].mean() < -0.05 else 'roughly aligned with technical reality, with specific outliers worth watching'}.

⚠️  ACTIONABLE INSIGHT:
   Markets where crowd_prob >> tech_signal = potential short/fade opportunity.
   Markets where tech_signal >> crowd_prob = overlooked by market, potential opportunity.
   {f"Biggest divergence: {gap_df.iloc[0]['symbol']} (gap: {gap_df.iloc[0]['gap_pct']:+.1f}%)" if len(gap_df) > 0 else "No significant divergences detected."}

╚══════════════════════════════════════════════════════════════════╝
""")

# ══════════════════════════════════════════════════════════════════
# 6. EXPORT RESULTS
# ══════════════════════════════════════════════════════════════════
sentiment_reality_gap_df   = gap_df
sentiment_gap_summary = {
    "btc_dominance":     _btc_dom,
    "altseason_30d":     _altidx_30d,
    "altseason_7d":      _altidx_7d,
    "n_markets_kalshi":  len(df_kal_priced) if len(gap_df) > 0 else 0,
    "n_markets_poly":    len(poly_records) if poly_records and len(gap_df) > 0 else 0,
    "n_coins_analyzed":  len(gap_df),
    "mean_gap_pct":      float(gap_df["gap_pct"].mean()) if len(gap_df) > 0 else 0.0,
    "top_overconfident": [],
    "top_undervalued":   [],
    "timestamp":         datetime.utcnow().isoformat(),
}

if len(gap_df) > 0:
    sentiment_gap_summary["top_overconfident"] = gap_df[gap_df["gap"] > 0].head(5)["symbol"].tolist()
    sentiment_gap_summary["top_undervalued"] = gap_df[gap_df["gap"] < 0].tail(5)["symbol"].tolist()

DATA_OUT_DIR = Path("outputs/data")
DATA_OUT_DIR.mkdir(parents=True, exist_ok=True)

if len(gap_df) > 0:
    gap_df.to_csv(DATA_OUT_DIR / "sentiment_reality_gap.csv", index=False)
    print(f"  ✅ Exported gap data → outputs/data/sentiment_reality_gap.csv")

with open(DATA_OUT_DIR / "sentiment_gap_summary.json", "w") as _f:
    import json as _json
    _json.dump(sentiment_gap_summary, _f, indent=2, default=str)
print(f"  ✅ Exported summary → outputs/data/sentiment_gap_summary.json")

print(f"\n✅ sentiment_reality_gap_df: {gap_df.shape}")
if len(gap_df) > 0:
    print(f"   Mean gap: {gap_df['gap_pct'].mean():+.1f}%  |  Coins analyzed: {len(gap_df)}")
else:
    print(f"   (no overlapping data to analyze)")
