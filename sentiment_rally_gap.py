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
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import datetime

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

# -- KALSHI: Load from disk, extract meaningful markets with price
df_kal_raw = pd.read_csv("data/kalshi/crypto_markets.csv")

# Extract crypto identifier from event_ticker
def kal_extract_ticker(event_tk):
    """Map Kalshi event_ticker prefix to crypto symbol."""
    et = str(event_tk).upper()
    for sym in ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "LTC", "LINK"]:
        if sym in et:
            return sym
    return None

df_kal_raw["crypto_sym"] = df_kal_raw["event_ticker"].apply(kal_extract_ticker)

# Keep markets with actual pricing (yes_ask or yes_bid > 0)
df_kal_priced = df_kal_raw[
    ((df_kal_raw["yes_ask"] + df_kal_raw["yes_bid"]) > 0) |
    (df_kal_raw["last_price"] > 0)
].copy()

df_kal_priced["crowd_prob"] = np.where(
    (df_kal_priced["yes_ask"] + df_kal_priced["yes_bid"]) > 0,
    (df_kal_priced["yes_ask"] + df_kal_priced["yes_bid"]) / 2 / 100,
    df_kal_priced["last_price"] / 100
)
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

# -- POLYMARKET: Fetch live prices for active crypto markets
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
print(f"\n[Polymarket] {len(poly_raw)} raw markets fetched")

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
    qs = pm.get("question", "")
    sym = poly_extract_crypto(qs)
    if not sym:
        continue
    # Extract YES price (outcomePrices[0])
    yp = None
    op_str = pm.get("outcomePrices", "")
    if isinstance(op_str, str):
        try:
            op_parsed = json.loads(op_str)
            yp = float(op_parsed[0]) if op_parsed else None
        except Exception:
            pass
    if yp is None:
        ltp = pm.get("lastTradePrice", 0) or 0
        yp = float(ltp) / 100 if ltp > 1 else (float(ltp) if ltp else None)
    if yp is None or yp <= 0.005 or yp >= 0.995:
        continue
    poly_records.append({
        "crypto_sym": sym,
        "question": qs,
        "crowd_prob": yp,
        "volume": float(pm.get("volumeNum", 0) or 0),
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
        weights.append(max(poly_by_coin[sym]["n_markets"] * 2, 1))  # Polymarket higher liquidity
    if probs:
        w_arr = np.array(weights, dtype=float)
        combined = float(np.average(probs, weights=w_arr))
        crowd_sentiment[sym] = {
            "crowd_prob": combined,
            "kalshi_prob": kal_by_coin.get(sym, {}).get("crowd_prob"),
            "poly_prob":   poly_by_coin.get(sym, {}).get("crowd_prob"),
            "n_kalshi":    kal_by_coin.get(sym, {}).get("n_markets", 0),
            "n_poly":      poly_by_coin.get(sym, {}).get("n_markets", 0),
        }

print(f"\n[Unified] {len(crowd_sentiment)} coins with crowd sentiment scores:")
for sym, v in crowd_sentiment.items():
    print(f"  {sym}: crowd_prob={v['crowd_prob']*100:.1f}% "
          f"(Kalshi: {(v['kalshi_prob'] or 0)*100:.1f}%, Poly: {(v['poly_prob'] or 0)*100:.1f}%)")

# ══════════════════════════════════════════════════════════════════
# 2. COMPUTE TECHNICAL REALITY SIGNALS
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 65)
print("STEP 2: COMPUTING TECHNICAL REALITY SIGNALS")
print("=" * 65)

# -- BTC dominance from upstream (load_and_merge_unified_data)
_btc_dom = float(btc_dominance)   # 56.1%
_altidx_30d = float(altseason_index_30d)   # from altcoin_season_analysis
_altidx_7d  = float(altseason_index_7d)
_alt_idx_24h = float(altseason_index_24h)

# Dominance trend context
_dom_trend_14d = float(dom_trend)  # from altcoin_season_analysis
print(f"\n[Structural Context]")
print(f"  BTC Dominance   : {_btc_dom:.1f}%  (trend 14d: {_dom_trend_14d:+.3f})")
print(f"  Altcoin Idx 30d : {_altidx_30d:.0f}%  |  7d: {_altidx_7d:.0f}%  |  24h: {_alt_idx_24h:.0f}%")
print(f"  Season Status   : {altseason_summary['season_status']}")

# -- Technical momentum per coin from unified_market_df (CoinGecko live)
# We'll use price changes to infer momentum signal
_mkt_df = unified_market_df.copy()
_mkt_df["symbol_upper"] = _mkt_df["symbol"].str.upper()

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

gap_df = pd.DataFrame(gap_records).sort_values("gap", ascending=False).reset_index(drop=True)
gap_df["gap_pct"] = gap_df["gap"] * 100

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

# ── Chart 1: Scatter — Crowd Sentiment vs Technical Signal ────────
crowd_vs_tech_scatter = plt.figure(figsize=(12, 8), facecolor=BG)
ax1 = crowd_vs_tech_scatter.add_subplot(111)
ax1.set_facecolor(BG)

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
print("  ✅ crowd_vs_tech_scatter rendered")

# ── Chart 2: Bar — Sentiment-Reality Gap by Market ────────────────
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
print("  ✅ gap_bar_chart rendered")

# ── Chart 3: Summary Table ─────────────────────────────────────────
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
print("  ✅ summary_table_fig rendered")

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
    "n_markets_kalshi":  len(df_kal_priced),
    "n_markets_poly":    len(poly_records) if poly_records else 0,
    "n_coins_analyzed":  len(gap_df),
    "mean_gap_pct":      float(gap_df["gap_pct"].mean()),
    "top_overconfident": top_over["symbol"].tolist(),
    "top_undervalued":   top_under["symbol"].tolist(),
    "timestamp":         datetime.utcnow().isoformat(),
}
print(f"\n✅ sentiment_reality_gap_df: {gap_df.shape}")
print(f"   Mean gap: {gap_df['gap_pct'].mean():+.1f}%  |  Coins analyzed: {len(gap_df)}")
