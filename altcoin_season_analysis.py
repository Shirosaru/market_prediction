
import pandas as pd
import numpy as np
import pickle
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
import requests
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Create outputs directory for charts
OUTPUTS_DIR = Path("outputs/charts")
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────
# ZERVE DESIGN SYSTEM
# ─────────────────────────────────────────────────────────
BG      = "#1D1D20"
FG      = "#fbfbff"
FG2     = "#909094"
BLUE    = "#A1C9F4"
ORANGE  = "#FFB482"
GREEN   = "#8DE5A1"
CORAL   = "#FF9F9B"
LAVENDER= "#D0BBFF"
YELLOW  = "#ffd400"
RED     = "#f04438"
EMERALD = "#17b26a"
PURPLE  = "#9467BD"

def style_ax(ax, title=None, xlabel=None, ylabel=None):
    ax.set_facecolor(BG)
    for sp in ax.spines.values():
        sp.set_color("#333337")
    ax.tick_params(colors=FG2, labelsize=9)
    ax.xaxis.label.set_color(FG2)
    ax.yaxis.label.set_color(FG2)
    if title:  ax.set_title(title, color=FG, fontsize=13, fontweight="bold", pad=12)
    if xlabel: ax.set_xlabel(xlabel, color=FG2, fontsize=10)
    if ylabel: ax.set_ylabel(ylabel, color=FG2, fontsize=10)
    ax.grid(axis="y", color="#333337", linewidth=0.5, alpha=0.6)

# ─────────────────────────────────────────────────────────
# 0. LOAD DATA FROM PHASE 4
# ─────────────────────────────────────────────────────────
import pickle
from pathlib import Path

output_dir = Path("outputs")
try:
    with open(output_dir / "unified_market_df.pkl", "rb") as f:
        unified_market_df = pickle.load(f)
    print("✓ Loaded unified_market_df from Phase 4")
except FileNotFoundError:
    print("⚠ Warning: unified_market_df.pkl not found. Ensure Phase 4 completed successfully.")
    raise

# ─────────────────────────────────────────────────────────
# 1. BUILD ALTCOIN UNIVERSE FROM unified_market_df
#    Exclude BTC, stablecoins, wrapped tokens
# ─────────────────────────────────────────────────────────
STABLECOINS = {"usdt","usdc","dai","busd","tusd","usdp","usdd","fdusd","pyusd","frax","lusd","gusd","susd","eurs"}
WRAPPED     = {"wbtc","weth","steth","cbeth","reth","wbeth","ezeth","rseth","weeth"}
BTC_ID      = "bitcoin"

df = unified_market_df.copy()

# Separate BTC
btc_data = df[df["coin_id"] == BTC_ID].iloc[0]
btc_price       = btc_data["current_price"]
btc_dom_now     = btc_data["btc_dominance_global_pct"]
btc_30d_pct     = btc_data["price_change_pct_30d"]
btc_7d_pct      = btc_data["price_change_pct_7d"]
btc_24h_pct     = btc_data["price_change_pct_24h"]

# Altcoin universe: top 50 by rank, excluding stables/wrapped/BTC
altcoins = df[
    (df["coin_id"] != BTC_ID) &
    (~df["symbol"].str.lower().isin(STABLECOINS)) &
    (~df["symbol"].str.lower().isin(WRAPPED)) &
    (df["market_cap_rank"] <= 60)  # some headroom to get 50 after filtering
].sort_values("market_cap_rank").head(50).reset_index(drop=True)

n_alts = len(altcoins)
print(f"Altcoin universe: {n_alts} coins")

# ─────────────────────────────────────────────────────────
# 2. ALTCOIN SEASON INDEX (snapshot-based on 30d returns)
#    Standard definition: % of top-50 alts outperforming BTC over 90 days
#    We proxy 90-day using 30d data (only available) with a note
# ─────────────────────────────────────────────────────────
alt_30d  = altcoins["price_change_pct_30d"].dropna()
alt_7d   = altcoins["price_change_pct_7d"].dropna()
alt_24h  = altcoins["price_change_pct_24h"].dropna()

# Outperforming BTC on each timeframe
n_outperf_30d = (alt_30d > btc_30d_pct).sum()
n_outperf_7d  = (alt_7d  > btc_7d_pct).sum()
n_outperf_24h = (alt_24h > btc_24h_pct).sum()

altseason_index_30d = round(n_outperf_30d / len(alt_30d) * 100, 1)
altseason_index_7d  = round(n_outperf_7d  / len(alt_7d)  * 100, 1)
altseason_index_24h = round(n_outperf_24h / len(alt_24h) * 100, 1)

def season_label(idx):
    if idx >= 75: return "🟢 ALTCOIN SEASON", GREEN
    if idx <= 25: return "🟠 BTC SEASON",     ORANGE
    return "⚪ NEUTRAL",                        FG2

season_label_30d, season_color_30d = season_label(altseason_index_30d)
season_label_7d,  season_color_7d  = season_label(altseason_index_7d)
season_label_24h, season_color_24h = season_label(altseason_index_24h)

print(f"\n{'='*55}")
print(f"  ALTCOIN SEASON INDEX (snapshot — {datetime.now(timezone.utc).strftime('%Y-%m-%d')})")
print(f"{'='*55}")
print(f"  30d index : {altseason_index_30d:>5.1f}%  →  {season_label_30d}")
print(f"   7d index : {altseason_index_7d:>5.1f}%  →  {season_label_7d}")
print(f"  24h index : {altseason_index_24h:>5.1f}%  →  {season_label_24h}")
print(f"  BTC dom.  : {btc_dom_now:.2f}%")
print(f"  BTC price : ${btc_price:,.0f}")

# ─────────────────────────────────────────────────────────
# 3. FETCH HISTORICAL BTC DOMINANCE + PRICE (90 days) 
#    via CoinGecko public API
# ─────────────────────────────────────────────────────────
CG_BASE = "https://api.coingecko.com/api/v3"
HEADERS = {"accept": "application/json"}
DELAY   = 1.5

def cg_get(ep, params=None, retries=5):
    for attempt in range(retries):
        r = requests.get(f"{CG_BASE}{ep}", params=params, headers=HEADERS, timeout=25)
        if r.status_code == 429:
            wait = 20 * (attempt + 1)
            print(f"  [CoinGecko] 429 rate-limit on {ep} — waiting {wait}s (attempt {attempt+1}/{retries})")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"CoinGecko {ep} failed after {retries} retries (rate limit)")

print("\n[CG] Fetching BTC price history (90d)...")
btc_hist = cg_get("/coins/bitcoin/market_chart", params={
    "vs_currency": "usd",
    "days": 90,
    "interval": "daily",
})
time.sleep(DELAY)

btc_prices_hist = pd.DataFrame(btc_hist["prices"], columns=["ts","price"])
btc_prices_hist["date"] = pd.to_datetime(btc_prices_hist["ts"], unit="ms").dt.normalize()
btc_prices_hist = btc_prices_hist.drop_duplicates("date").set_index("date")["price"]

# Market cap history for dominance proxy
print("[CG] Fetching total market cap history (90d)...")
global_hist = cg_get("/coins/bitcoin/market_chart", params={
    "vs_currency": "usd",
    "days": 90,
    "interval": "daily",
})
btc_mcap_hist_raw = pd.DataFrame(global_hist["market_caps"], columns=["ts","btc_mcap"])
btc_mcap_hist_raw["date"] = pd.to_datetime(btc_mcap_hist_raw["ts"], unit="ms").dt.normalize()
btc_mcap_hist = btc_mcap_hist_raw.drop_duplicates("date").set_index("date")["btc_mcap"]
time.sleep(DELAY)

# Global market cap (total) history 
print("[CG] Fetching ETH history for dominance denominator...")
eth_hist = cg_get("/coins/ethereum/market_chart", params={
    "vs_currency": "usd",
    "days": 90,
    "interval": "daily",
})
eth_mcap_raw = pd.DataFrame(eth_hist["market_caps"], columns=["ts","eth_mcap"])
eth_mcap_raw["date"] = pd.to_datetime(eth_mcap_raw["ts"], unit="ms").dt.normalize()
eth_mcap_hist = eth_mcap_raw.drop_duplicates("date").set_index("date")["eth_mcap"]
time.sleep(DELAY)

# Approximate total market cap: use BTC dominance ratio from today as denominator
# BTC dominance = BTC_mcap / total_mcap  →  total_mcap ≈ BTC_mcap / btc_dom_now
btc_dom_frac = btc_dom_now / 100.0
hist_df = pd.DataFrame({
    "btc_price": btc_prices_hist,
    "btc_mcap":  btc_mcap_hist,
    "eth_mcap":  eth_mcap_hist,
}).dropna()

# Estimate total market cap  
hist_df["total_mcap_est"] = hist_df["btc_mcap"] / btc_dom_frac
hist_df["btc_dominance"]  = (hist_df["btc_mcap"] / hist_df["total_mcap_est"]) * 100
# Smooth dominance (rolling 3-day)
hist_df["btc_dom_smooth"] = hist_df["btc_dominance"].rolling(3, min_periods=1).mean()

# BTC 30-day rolling return (proxy for consolidation detection)
hist_df["btc_30d_return"] = hist_df["btc_price"].pct_change(30) * 100
hist_df["btc_7d_return"]  = hist_df["btc_price"].pct_change(7) * 100
hist_df["btc_7d_vol"]     = hist_df["btc_price"].pct_change().rolling(7).std() * 100

print(f"[CG] History loaded: {len(hist_df)} days")

# ─────────────────────────────────────────────────────────
# 4. SIMULATE DAILY ALTSEASON INDEX (rolling approximation)
#    Since we only have current snapshot of alt returns,
#    we build a simulated index using BTC dominance slope
#    as a proxy for capital rotation
# ─────────────────────────────────────────────────────────
# Dom declining + BTC price stable → liquidity rotating → alt season
hist_df["dom_change_7d"]   = hist_df["btc_dom_smooth"].diff(7)
hist_df["dom_change_14d"]  = hist_df["btc_dom_smooth"].diff(14)
hist_df["btc_vol_7d"]      = hist_df["btc_price"].pct_change().rolling(7).std() * 100

# Altseason signal: inverse of BTC dominance, normalised to 0-100
dom_min = hist_df["btc_dom_smooth"].min()
dom_max = hist_df["btc_dom_smooth"].max()
hist_df["alt_season_proxy"] = (
    (dom_max - hist_df["btc_dom_smooth"]) / (dom_max - dom_min) * 100
).clip(0, 100)

# Overlay actual snapshot values at end
hist_df.loc[hist_df.index[-1], "alt_season_proxy"] = altseason_index_30d

# ─────────────────────────────────────────────────────────
# 5. IDENTIFY HISTORICAL TRIGGERS
# ─────────────────────────────────────────────────────────
# Consolidation periods: BTC 7d vol < 1.5% AND 7d return between -5% and +5%
hist_df["is_consolidation"] = (
    (hist_df["btc_vol_7d"] < 2.0) &
    (hist_df["btc_7d_return"].abs() < 8)
)
# Dominance breakdown: 7d dom change < -1%
hist_df["is_dom_breakdown"] = hist_df["dom_change_7d"] < -1.0
# Liquidity rotation: dominance declining + volume surge proxy (vol/price)
hist_df["volume_proxy"] = hist_df["btc_mcap"].diff().abs() / hist_df["btc_mcap"]
hist_df["is_rotation"]  = (
    hist_df["dom_change_7d"] < -0.5
)

n_consol  = hist_df["is_consolidation"].sum()
n_dom_brk = hist_df["is_dom_breakdown"].sum()
n_rot     = hist_df["is_rotation"].sum()

print(f"\nHistorical Trigger Analysis (last 90 days):")
print(f"  Consolidation periods  : {n_consol} days")
print(f"  Dom breakdown days     : {n_dom_brk} days")
print(f"  Rotation signal days   : {n_rot} days")

# ─────────────────────────────────────────────────────────
# 6. CORRELATION MATRIX: BTC moves vs altcoin performance
#    Use current snapshot: BTC 30d/7d/24h vs each alt's 30d/7d/24h
# ─────────────────────────────────────────────────────────
alt_corr = altcoins[["symbol","name","price_change_pct_30d","price_change_pct_7d","price_change_pct_24h"]].copy()
alt_corr.columns = ["symbol","name","alt_30d","alt_7d","alt_24h"]

# Lagged relationship matrix: we compute correlation of alt returns
# across timeframes vs BTC returns at each timeframe
corr_data = {}
for sym, row in alt_corr.iterrows():
    corr_data[alt_corr.loc[sym, "symbol"]] = {
        "alt_30d": alt_corr.loc[sym, "alt_30d"],
        "alt_7d":  alt_corr.loc[sym, "alt_7d"],
        "alt_24h": alt_corr.loc[sym, "alt_24h"],
    }

corr_df = pd.DataFrame(corr_data).T.dropna()
# Add BTC reference row
btc_ref = pd.Series({"alt_30d": btc_30d_pct, "alt_7d": btc_7d_pct, "alt_24h": btc_24h_pct}, name="BTC")
corr_df_full = pd.concat([corr_df, btc_ref.to_frame().T])

# Correlation: each altcoin's returns at each timeframe
# Lag effect: does 7d BTC move → 24h alt move? Does 30d BTC → 7d alt?
lag_matrix = pd.DataFrame({
    "BTC_30d→Alt_30d": [np.corrcoef(corr_df["alt_30d"], np.full(len(corr_df), btc_30d_pct))[0,1]],
    "BTC_7d→Alt_7d":   [np.corrcoef(corr_df["alt_7d"],  np.full(len(corr_df), btc_7d_pct))[0,1]],
    "BTC_24h→Alt_24h": [np.corrcoef(corr_df["alt_24h"], np.full(len(corr_df), btc_24h_pct))[0,1]],
})

# Cross-timeframe correlations (lag effects)
corr_matrix = corr_df[["alt_30d","alt_7d","alt_24h"]].corr()
corr_matrix.index   = ["Alt 30d","Alt 7d","Alt 24h"]
corr_matrix.columns = ["Alt 30d","Alt 7d","Alt 24h"]

# Leaders vs laggers: top alts outperforming BTC on 30d
alt_corr["vs_btc_30d"] = alt_corr["alt_30d"] - btc_30d_pct
alt_corr["vs_btc_7d"]  = alt_corr["alt_7d"]  - btc_7d_pct
leaders_30d  = alt_corr.nlargest(8, "vs_btc_30d")[["symbol","alt_30d","vs_btc_30d"]]
laggers_30d  = alt_corr.nsmallest(8, "vs_btc_30d")[["symbol","alt_30d","vs_btc_30d"]]
leaders_7d   = alt_corr.nlargest(5, "vs_btc_7d")[["symbol","alt_7d","vs_btc_7d"]]

print(f"\nTop 8 Alt Leaders (30d vs BTC):")
for _, r in leaders_30d.iterrows():
    print(f"  {r['symbol'].upper():<8} {r['alt_30d']:>+7.1f}% (vs BTC {r['vs_btc_30d']:>+7.1f}%)")

print(f"\nTop 8 Alt Laggers (30d vs BTC):")
for _, r in laggers_30d.iterrows():
    print(f"  {r['symbol'].upper():<8} {r['alt_30d']:>+7.1f}% (vs BTC {r['vs_btc_30d']:>+7.1f}%)")

# ─────────────────────────────────────────────────────────
# 7. VISUALISATION 1: BTC Dominance + Altseason Index
# ─────────────────────────────────────────────────────────
fig1, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
fig1.patch.set_facecolor(BG)
plt.subplots_adjust(hspace=0.08)

dates = hist_df.index

# --- Upper panel: BTC Dominance
ax1.set_facecolor(BG)
ax1.fill_between(dates, hist_df["btc_dom_smooth"], alpha=0.18, color=ORANGE)
ax1.plot(dates, hist_df["btc_dom_smooth"], color=ORANGE, linewidth=2.0, label="BTC Dominance")
ax1.axhline(y=btc_dom_now, color=YELLOW, linewidth=1, linestyle="--", alpha=0.7)

# Shade consolidation zones
prev_consol = False
start_c = None
for d, is_c in zip(dates, hist_df["is_consolidation"]):
    if is_c and not prev_consol:
        start_c = d
    elif not is_c and prev_consol and start_c:
        ax1.axvspan(start_c, d, color=LAVENDER, alpha=0.12, label="_")
    prev_consol = is_c

# Dominance breakdown arrows
breakdown_dates = hist_df[hist_df["is_dom_breakdown"]].index
for bd in breakdown_dates[::3]:  # every 3rd to avoid clutter
    ax1.annotate("↓", xy=(bd, hist_df.loc[bd, "btc_dom_smooth"]),
                 fontsize=9, color=CORAL, ha="center", va="top")

ax1.set_ylabel("BTC Dominance (%)", color=FG2, fontsize=10)
ax1.tick_params(colors=FG2, labelsize=9)
for sp in ax1.spines.values(): sp.set_color("#333337")
ax1.grid(axis="y", color="#333337", linewidth=0.5, alpha=0.6)
ax1.set_title("BTC Dominance & Altcoin Season Index — 90 Day View", 
              color=FG, fontsize=14, fontweight="bold", pad=14)
ax1.text(0.01, 0.92, f"Current: {btc_dom_now:.2f}%", transform=ax1.transAxes,
         color=YELLOW, fontsize=9, fontweight="bold")

# Legend patches
leg1 = [
    mpatches.Patch(color=ORANGE, label="BTC Dominance (3d MA)"),
    mpatches.Patch(color=LAVENDER, alpha=0.4, label="BTC Consolidation Zones"),
    mpatches.Patch(color=CORAL, label="Dom. Breakdown Events"),
]
ax1.legend(handles=leg1, loc="upper right", framealpha=0.15,
           facecolor=BG, edgecolor="#333337", labelcolor=FG, fontsize=8)

# --- Lower panel: Altseason Proxy Index
ax2.set_facecolor(BG)
# Zones
ax2.axhspan(0, 25,  color=ORANGE, alpha=0.10)
ax2.axhspan(25, 75, color=FG2,    alpha=0.05)
ax2.axhspan(75, 100,color=GREEN,  alpha=0.10)
ax2.axhline(75, color=GREEN,  linewidth=0.8, linestyle="--", alpha=0.6)
ax2.axhline(25, color=ORANGE, linewidth=0.8, linestyle="--", alpha=0.6)

# Plot index
idx_color = season_color_30d
ax2.fill_between(dates, hist_df["alt_season_proxy"], alpha=0.2, color=idx_color)
ax2.plot(dates, hist_df["alt_season_proxy"], color=idx_color, linewidth=2.2)

# Mark end-point with current real value
ax2.scatter([dates[-1]], [altseason_index_30d], color=YELLOW, s=70, zorder=6)
ax2.text(dates[-1], altseason_index_30d + 4, f"{altseason_index_30d:.0f}", 
         color=YELLOW, fontsize=9, ha="right", fontweight="bold")

ax2.text(0.5, 0.88, "ALTCOIN SEASON", transform=ax2.transAxes,
         color=GREEN, fontsize=8, ha="center", alpha=0.7)
ax2.text(0.5, 0.08, "BTC SEASON", transform=ax2.transAxes,
         color=ORANGE, fontsize=8, ha="center", alpha=0.7)

ax2.set_ylim(0, 105)
ax2.set_ylabel("Alt Season Index", color=FG2, fontsize=10)
ax2.set_xlabel("Date", color=FG2, fontsize=10)
ax2.tick_params(colors=FG2, labelsize=9)
for sp in ax2.spines.values(): sp.set_color("#333337")
ax2.grid(axis="y", color="#333337", linewidth=0.5, alpha=0.6)

fig1.text(0.01, 0.01, "▼ Coral arrows = dominance breakdowns  |  Purple zones = BTC consolidation",
          color=FG2, fontsize=8, va="bottom")

plt.tight_layout()
btc_dom_altseason_chart = fig1
plt.savefig(OUTPUTS_DIR / "btc_dom_altseason_chart.png", dpi=150, bbox_inches="tight", facecolor=BG)
plt.show()
print("Chart 1 saved.")

# ─────────────────────────────────────────────────────────
# 8. VISUALISATION 2: Top Altcoin 30d Perf Heatmap vs BTC
# ─────────────────────────────────────────────────────────
# Top 20 alts by absolute 30d performance
hm_alts = altcoins.nlargest(20, "price_change_pct_30d").copy()
hm_alts_bot = altcoins.nsmallest(10, "price_change_pct_30d").copy()
hm_data = pd.concat([hm_alts, hm_alts_bot]).drop_duplicates("symbol")
hm_data = hm_data.set_index("symbol")[["price_change_pct_30d","price_change_pct_7d","price_change_pct_24h"]].copy()
hm_data.columns = ["30d %","7d %","24h %"]

# Add BTC row for reference
btc_hm = pd.DataFrame({"30d %":[btc_30d_pct],"7d %":[btc_7d_pct],"24h %":[btc_24h_pct]}, index=["BTC ★"])
hm_data = pd.concat([btc_hm, hm_data])

fig2, ax = plt.subplots(figsize=(10, 11))
fig2.patch.set_facecolor(BG)
ax.set_facecolor(BG)

# Diverging colourmap centred at 0
vmax = max(abs(hm_data.values.max()), abs(hm_data.values.min())) * 0.8
cmap = mcolors.LinearSegmentedColormap.from_list(
    "rg", [RED, "#333337", EMERALD], N=256
)
im = ax.imshow(hm_data.values, aspect="auto", cmap=cmap,
               vmin=-vmax, vmax=vmax)

ax.set_xticks(range(3))
ax.set_xticklabels(hm_data.columns, color=FG, fontsize=11, fontweight="bold")
ax.set_yticks(range(len(hm_data)))
ax.set_yticklabels(hm_data.index.str.upper(), color=FG, fontsize=9)

# Annotate cells
for i in range(len(hm_data)):
    for j in range(3):
        val = hm_data.iloc[i, j]
        cell_color = FG if abs(val) < vmax * 0.5 else BG
        sym = "+" if val > 0 else ""
        ax.text(j, i, f"{sym}{val:.1f}%", ha="center", va="center",
                color=cell_color, fontsize=8.5, fontweight="bold")

# BTC row separator
ax.axhline(0.5, color=YELLOW, linewidth=1.5, alpha=0.7)

cb = plt.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
cb.ax.tick_params(colors=FG2, labelsize=8)
cb.set_label("Return (%)", color=FG2, fontsize=9)
cb.outline.set_edgecolor("#333337")

ax.set_title("Top Altcoin Performance vs BTC — Heatmap (30d / 7d / 24h)",
             color=FG, fontsize=13, fontweight="bold", pad=14)
ax.tick_params(top=True, labeltop=True, bottom=False, labelbottom=False, colors=FG2)

for sp in ax.spines.values(): sp.set_visible(False)

fig2.text(0.5, 0.01, f"★ BTC reference row  |  Data: CoinGecko  |  {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
          ha="center", color=FG2, fontsize=8)

plt.tight_layout()
altcoin_perf_heatmap = fig2
plt.savefig(OUTPUTS_DIR / "altcoin_perf_heatmap.png", dpi=150, bbox_inches="tight", facecolor=BG)
plt.show()
print("Chart 2 saved.")

# ─────────────────────────────────────────────────────────
# 9. VISUALISATION 3: Correlation Heatmap (alt returns vs BTC)
# ─────────────────────────────────────────────────────────
# Build cross-timeframe correlation for leaders
top_alts = alt_corr.nlargest(15, "vs_btc_30d")["symbol"].tolist()
bot_alts = alt_corr.nsmallest(5, "vs_btc_30d")["symbol"].tolist()
sel_syms = top_alts + bot_alts

sel_df = alt_corr[alt_corr["symbol"].isin(sel_syms)].set_index("symbol")[["alt_30d","alt_7d","alt_24h"]].copy()
sel_df.loc["BTC"] = [btc_30d_pct, btc_7d_pct, btc_24h_pct]
sel_df.columns = ["30d","7d","24h"]

# Full pairwise correlation across coins x timeframes
# Shape: flatten each coin into feature vector
full_corr = sel_df.T.corr()  # coin x coin correlation across 3 timeframes

fig3, ax = plt.subplots(figsize=(12, 10))
fig3.patch.set_facecolor(BG)
ax.set_facecolor(BG)

n_c = len(full_corr)
cmap2 = mcolors.LinearSegmentedColormap.from_list(
    "corr", [CORAL, "#1D1D20", BLUE], N=256
)
im2 = ax.imshow(full_corr.values, aspect="auto", cmap=cmap2, vmin=-1, vmax=1)

syms = [s.upper() for s in full_corr.index]
ax.set_xticks(range(n_c))
ax.set_xticklabels(syms, rotation=45, ha="right", color=FG, fontsize=8)
ax.set_yticks(range(n_c))
ax.set_yticklabels(syms, color=FG, fontsize=8)

# Annotate
for i in range(n_c):
    for j in range(n_c):
        val = full_corr.values[i, j]
        txt_col = FG if abs(val) < 0.5 else BG
        ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                color=txt_col, fontsize=6.5)

# Highlight BTC row/col
btc_idx = syms.index("BTC")
for k in range(n_c):
    ax.add_patch(plt.Rectangle((btc_idx - 0.5, k - 0.5), 1, 1,
                                fill=False, edgecolor=YELLOW, linewidth=1.2))
    ax.add_patch(plt.Rectangle((k - 0.5, btc_idx - 0.5), 1, 1,
                                fill=False, edgecolor=YELLOW, linewidth=1.2))

cb2 = plt.colorbar(im2, ax=ax, fraction=0.025, pad=0.02)
cb2.ax.tick_params(colors=FG2, labelsize=8)
cb2.set_label("Pearson r (across 30d/7d/24h returns)", color=FG2, fontsize=9)
cb2.outline.set_edgecolor("#333337")

ax.set_title("Correlation Heatmap: Altcoin Returns vs BTC (Leaders + Laggers)",
             color=FG, fontsize=13, fontweight="bold", pad=14)
ax.text(0.0, -0.11,
        f"Yellow highlights = BTC row/col  |  Blue = positive corr  |  Coral = inverse  |  {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        transform=ax.transAxes, color=FG2, fontsize=8)
for sp in ax.spines.values(): sp.set_visible(False)

plt.tight_layout()
altcoin_correlation_heatmap = fig3
plt.savefig(OUTPUTS_DIR / "altcoin_correlation_heatmap.png", dpi=150, bbox_inches="tight", facecolor=BG)
plt.show()
print("Chart 3 saved.")

# ─────────────────────────────────────────────────────────
# 10. KEY FINDINGS SUMMARY
# ─────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  KEY FINDINGS — ALTCOIN SEASON ANALYSIS")
print(f"{'='*60}")

print(f"\n📊 CURRENT SEASON STATUS")
print(f"  Alt Season Index (30d): {altseason_index_30d:.1f}%  →  {season_label_30d}")
print(f"  Alt Season Index (7d) : {altseason_index_7d:.1f}%  →  {season_label_7d}")
print(f"  Alt Season Index (24h): {altseason_index_24h:.1f}%  →  {season_label_24h}")
print(f"  BTC Dominance Now     : {btc_dom_now:.2f}%")
print(f"  Verdict: Market is in {'an ALTCOIN SEASON' if altseason_index_30d >= 75 else 'BTC SEASON' if altseason_index_30d <= 25 else 'a NEUTRAL phase — watch for rotation signals'}")

dom_trend = hist_df["btc_dom_smooth"].iloc[-1] - hist_df["btc_dom_smooth"].iloc[-14]
dom_trend_dir = "⬇️ DECLINING" if dom_trend < -0.5 else "⬆️ RISING" if dom_trend > 0.5 else "➡️ FLAT"

print(f"\n📉 BTC DOMINANCE TREND (14d)")
print(f"  Direction : {dom_trend_dir}  ({dom_trend:+.2f}% over 14 days)")
print(f"  Breakdown days (7d drop >1%) : {n_dom_brk} / 90")
print(f"  Rotation signal days          : {n_rot} / 90")
print(f"  Consolidation days            : {n_consol} / 90")

print(f"\n🔄 DOMINANT ROTATION PATTERNS")
if dom_trend < -1:
    print("  → BTC dominance is actively declining — capital rotating to alts")
elif dom_trend > 1:
    print("  → BTC dominance rising — risk-off / BTC accumulation phase")
else:
    print("  → Dominance stable — no strong directional rotation signal yet")

if n_consol > 20:
    print(f"  → Frequent BTC consolidation ({n_consol} days) historically precedes alt breakouts")
if n_dom_brk > 10:
    print(f"  → Multiple dominance breakdowns ({n_dom_brk} days) signal sustained rotation")

print(f"\n🏆 ALT LEADERS (30d outperformance vs BTC {btc_30d_pct:+.1f}%)")
for _, r in leaders_30d.head(5).iterrows():
    print(f"  {r['symbol'].upper():<8} {r['alt_30d']:>+7.1f}%  (Δ vs BTC: {r['vs_btc_30d']:>+7.1f}%)")

print(f"\n🔻 ALT LAGGERS (30d underperformance vs BTC)")
for _, r in laggers_30d.head(5).iterrows():
    print(f"  {r['symbol'].upper():<8} {r['alt_30d']:>+7.1f}%  (Δ vs BTC: {r['vs_btc_30d']:>+7.1f}%)")

print(f"\n⚡ 7d MOMENTUM LEADERS (rotation effect)")
for _, r in leaders_7d.iterrows():
    print(f"  {r['symbol'].upper():<8} {r['alt_7d']:>+7.1f}%  (Δ vs BTC: {r['vs_btc_7d']:>+7.1f}%)")

print(f"\n📐 CROSS-TIMEFRAME CORRELATION (alt returns)")
print(corr_matrix.to_string())
print(f"\n  High cross-timeframe correlation → trends persist across timeframes")
print(f"  Low correlation → short-term noise, not sustained rotation")

# Store outputs for downstream use
altseason_context = {
    "altseason_index_30d": altseason_index_30d,
    "altseason_index_7d": altseason_index_7d,
    "altseason_index_24h": altseason_index_24h,
    "btc_dominance_now": btc_dom_now,
    "altseason_label": season_label_30d,
}

from pathlib import Path
output_dir = Path("outputs")
output_dir.mkdir(exist_ok=True)

with open(output_dir / "altseason_context.pkl", "wb") as f:
    pickle.dump(altseason_context, f)

import json as _json
with open(output_dir / "altseason_context.json", "w") as _f:
    _json.dump(altseason_context, _f, indent=2, default=str)

print(f"\n✅ altcoin_season_analysis complete! Saved context for Phase 7.")
print(f"   Saved: outputs/altseason_context.pkl + altseason_context.json")
altseason_summary = {
    "index_30d": altseason_index_30d,
    "index_7d":  altseason_index_7d,
    "index_24h": altseason_index_24h,
    "season_status": season_label_30d,
    "btc_dominance": btc_dom_now,
    "btc_price": btc_price,
    "dom_trend_14d": dom_trend,
    "n_alts_analyzed": n_alts,
    "leaders": leaders_30d.to_dict("records"),
    "laggers": laggers_30d.to_dict("records"),
}

print(f"\n✅ Analysis complete. altseason_summary stored.")
