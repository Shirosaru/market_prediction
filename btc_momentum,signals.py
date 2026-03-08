"""
BTC & ETH Quantitative Market Direction Model — Standalone
Reads from disk CSVs + fresh CoinGecko API. No upstream variable deps.
"""
import requests, pandas as pd, numpy as np, json, re, time
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, matplotlib.ticker as mticker
from matplotlib.gridspec import GridSpec
from scipy import stats
from datetime import timedelta
from pathlib import Path

# Create outputs directory for charts
OUTPUTS_DIR = Path("outputs/charts")
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
from pathlib import Path

# ── Zerve Design System colors ──────────────────────────────────
BTC_BG, BTC_FG, BTC_FG2 = "#1D1D20", "#fbfbff", "#909094"
BTC_BLUE, BTC_ORANGE     = "#A1C9F4", "#FFB482"
BTC_GREEN, BTC_CORAL     = "#8DE5A1", "#FF9F9B"
BTC_LAV, BTC_GOLD        = "#D0BBFF", "#ffd400"
BTC_SUCC, BTC_WARN       = "#17b26a", "#f04438"
BTC_PURPLE               = "#9467BD"

plt.rcParams.update({"figure.facecolor": BTC_BG, "axes.facecolor": BTC_BG,
    "axes.edgecolor": BTC_FG2, "axes.labelcolor": BTC_FG,
    "xtick.color": BTC_FG2, "ytick.color": BTC_FG2,
    "text.color": BTC_FG, "grid.color": "#2d2d35", "grid.linewidth": 0.6,
    "font.family": "sans-serif", "font.size": 11})

# ── 1. FETCH 90-DAY OHLCV FROM COINGECKO ────────────────────────
CG_URL = "https://api.coingecko.com/api/v3"
HDR    = {"accept": "application/json"}

def fetch_ohlcv(coin_id):
    rr = requests.get(f"{CG_URL}/coins/{coin_id}/market_chart",
        params={"vs_currency": "usd", "days": 90, "interval": "daily"},
        headers=HDR, timeout=30)
    rr.raise_for_status()
    dd = rr.json()
    dfp = pd.DataFrame(dd["prices"],        columns=["ts", "close"])
    dfv = pd.DataFrame(dd["total_volumes"], columns=["ts", "volume"])
    dfc = pd.DataFrame(dd["market_caps"],   columns=["ts", "mktcap"])
    df  = dfp.merge(dfv, on="ts").merge(dfc, on="ts")
    df["date"] = pd.to_datetime(df["ts"], unit="ms").dt.normalize()
    df = df.drop_duplicates("date").sort_values("date").reset_index(drop=True)
    return df[["date", "close", "volume", "mktcap"]]

btc_ohlcv = fetch_ohlcv("bitcoin"); print(f"  BTC: {len(btc_ohlcv)} rows")
time.sleep(1.5)
eth_ohlcv = fetch_ohlcv("ethereum"); print(f"  ETH: {len(eth_ohlcv)} rows")

# ── 2. TECHNICAL INDICATORS ──────────────────────────────────────
def add_indicators(df):
    d = df.copy()
    d["sma20"] = d["close"].rolling(20).mean()
    d["sma50"] = d["close"].rolling(50).mean()
    delta = d["close"].diff()
    g = delta.clip(lower=0).ewm(com=13, min_periods=14).mean()
    l = (-delta).clip(lower=0).ewm(com=13, min_periods=14).mean()
    d["rsi14"] = 100 - 100 / (1 + g / l.replace(0, np.nan))
    ef = d["close"].ewm(span=12, adjust=False).mean()
    es = d["close"].ewm(span=26, adjust=False).mean()
    d["macd"]      = ef - es
    d["macd_sig"]  = d["macd"].ewm(span=9, adjust=False).mean()
    d["macd_hist"] = d["macd"] - d["macd_sig"]
    return d.dropna(subset=["rsi14"]).reset_index(drop=True)

btc_td = add_indicators(btc_ohlcv)
eth_td = add_indicators(eth_ohlcv)
print(f"  BTC RSI={btc_td['rsi14'].iloc[-1]:.1f}  SMA20=${btc_td['sma20'].iloc[-1]:,.0f}  SMA50=${btc_td['sma50'].iloc[-1]:,.0f}")
print(f"  ETH RSI={eth_td['rsi14'].iloc[-1]:.1f}")

# ── 3. LOG-LINEAR REGRESSION + 30-DAY FORECAST (95% CI) ─────────
xs     = np.arange(len(btc_td))
lp     = np.log(btc_td["close"].values)
sl, ic, rv, _, _ = stats.linregress(xs, lp)
resid  = (lp - (sl * xs + ic)).std()
n      = len(btc_td)
fi     = np.arange(n, n + 30)
ld     = btc_td["date"].iloc[-1]
fdates = [ld + timedelta(days=d) for d in range(1, 31)]
lf     = sl * fi + ic
fwd_mean = np.exp(lf)
tc     = stats.t.ppf(0.975, df=n - 2)
se     = resid * np.sqrt(1 + 1/n + (fi - xs.mean())**2 / np.sum((xs - xs.mean())**2))
fwd_hi = np.exp(lf + tc * se)
fwd_lo = np.exp(lf - tc * se)

btc_price  = float(btc_td["close"].iloc[-1])
btc_fc30   = float(fwd_mean[-1])
btc_dir    = "BULLISH" if btc_fc30 > btc_price else "BEARISH"
btc_fc_pct = (btc_fc30 / btc_price - 1) * 100

print(f"\n{'='*55}")
print(f"BTC Regression R²={rv**2:.3f}  slope={sl:.5f}/day")
print(f"Current: ${btc_price:,.0f}  →  30d: ${btc_fc30:,.0f} ({btc_fc_pct:+.1f}%)  [{btc_dir}]")
print(f"95% CI: ${fwd_lo[-1]:,.0f} – ${fwd_hi[-1]:,.0f}")

# ── 4. REGIME CLASSIFICATION ─────────────────────────────────────
def regime(df, sym):
    r  = df.iloc[-1]
    rsi, macd, sig = float(r["rsi14"]), float(r["macd"]), float(r["macd_sig"])
    s20, s50, cl   = float(r["sma20"]),  float(r["sma50"]),  float(r["close"])
    s_rsi  = "bullish" if rsi > 55 else ("bearish" if rsi < 45 else "neutral")
    s_ma   = "bullish" if cl > s20 > s50 else ("bearish" if cl < s20 < s50 else "neutral")
    s_macd = "bullish" if macd > sig else "bearish"
    inds   = [("RSI", s_rsi), ("MA", s_ma), ("MACD", s_macd)]
    nb, nr = sum(1 for _, v in inds if v == "bullish"), sum(1 for _, v in inds if v == "bearish")
    reg    = "BULLISH" if nb >= 2 else ("BEARISH" if nr >= 2 else "NEUTRAL")
    return dict(sym=sym, regime=reg, rsi14=rsi, close=cl, sma20=s20, sma50=s50,
                macd=macd, macd_sig=sig, inds=inds)

btc_reg = regime(btc_td, "BTC")
eth_reg = regime(eth_td, "ETH")

# ── 5. SUPPORT / RESISTANCE ──────────────────────────────────────
def sr_levels(df, w=14):
    hi  = df["close"].rolling(w, center=True).max()
    lo  = df["close"].rolling(w, center=True).min()
    now = float(df["close"].iloc[-1])
    lv  = sorted(set([round(float(v), -2) for v in hi.dropna()] +
                     [round(float(v), -2) for v in lo.dropna()]))
    return sorted([l for l in lv if l < now * 0.995])[-3:], \
           sorted([l for l in lv if l > now * 1.005])[:3]

btc_sup, btc_res = sr_levels(btc_td)

# ── 6. KALSHI PROBS (disk CSV) ────────────────────────────────────
TARGETS = [80000, 90000, 100000, 110000, 120000]

kal_df = pd.read_csv("data/kalshi/crypto_markets.csv")
kal_btc = kal_df[
    kal_df["event_ticker"].astype(str).str.startswith("KXBTC", na=False) &
    (kal_df["strike_type"].astype(str) == "greater")
].copy()
kal_btc["sv"] = pd.to_numeric(kal_btc["floor_strike"], errors="coerce").fillna(0)
kal_btc["ya"] = pd.to_numeric(kal_btc["yes_ask"],      errors="coerce").fillna(0)
kal_btc["yb"] = pd.to_numeric(kal_btc["yes_bid"],      errors="coerce").fillna(0)
kal_btc["lp"] = pd.to_numeric(kal_btc["last_price"],   errors="coerce").fillna(0)
kal_btc["ip"] = (kal_btc["ya"] + kal_btc["yb"]) / 2 / 100
mask0 = kal_btc["ip"] == 0
kal_btc.loc[mask0, "ip"] = kal_btc.loc[mask0, "lp"] / 100
kal_v = kal_btc[(kal_btc["sv"] > 50000) & (kal_btc["ip"] > 0)].sort_values("sv").reset_index(drop=True)

def interp_p(tgt, df_v, pc="ip", sc="sv"):
    if df_v.empty: return None
    lo = df_v[df_v[sc] <= tgt]; hi = df_v[df_v[sc] >= tgt]
    if lo.empty: return float(hi.iloc[0][pc])
    if hi.empty: return float(lo.iloc[-1][pc])
    lr, hr = lo.iloc[-1], hi.iloc[0]
    dn = float(hr[sc]) - float(lr[sc])
    if dn == 0: return float(lr[pc])
    t = (tgt - float(lr[sc])) / dn
    return float(lr[pc]) * (1 - t) + float(hr[pc]) * t

kal_probs = {}
for tgt in TARGETS:
    p = interp_p(tgt, kal_v)
    kal_probs[tgt] = p
    print(f"  Kalshi P(BTC>${tgt//1000}k) = {f'{p*100:.1f}%' if p else 'N/A'}")

# ── 7. POLYMARKET PROBS (fresh API + disk supplement) ───────────
PGAMMA = "https://gamma-api.polymarket.com"

def price_from_q(txt):
    tu = str(txt).upper()
    m1 = re.search(r"\$(\d+)K\b", tu)
    if m1: return float(m1.group(1)) * 1000
    m2 = re.search(r"\$([\d,]+)", tu)
    if m2: return float(m2.group(1).replace(",", ""))
    return None

poly_raw = []
for kw in ["bitcoin above", "btc above", "bitcoin price", "bitcoin hits"]:
    rr2 = requests.get(f"{PGAMMA}/markets", params={"q": kw, "limit": 100, "active": "true"}, headers=HDR, timeout=15)
    if rr2.ok and isinstance(rr2.json(), list): poly_raw.extend(rr2.json())
    time.sleep(0.6)
print(f"\n  Polymarket: {len(poly_raw)} raw markets")

parsed = []
for mkt in poly_raw:
    q = str(mkt.get("question", "") or "")
    if not any(w in q.lower() for w in ["bitcoin", "btc"]): continue
    if not any(w in q.lower() for w in ["above", "reach", "hit", "exceed", "end", ">"]): continue
    tgt2 = price_from_q(q)
    if tgt2 is None or tgt2 < 50000: continue
    yp = None
    opr = mkt.get("outcomePrices", "")
    opl = opr if isinstance(opr, list) else (json.loads(opr) if isinstance(opr, str) and opr.strip() else [])
    if opl:
        fp = float(opl[0])
        yp = fp / 100.0 if fp > 1.0 else fp
    if yp is None:
        ltp = mkt.get("lastTradePrice", 0) or 0
        if isinstance(ltp, (int, float)): yp = float(ltp) / 100.0 if float(ltp) > 1 else float(ltp)
    if yp and yp > 0:
        parsed.append({"target": tgt2, "prob": float(yp),
                        "volume": float(mkt.get("volumeNum", 0) or mkt.get("volume", 0) or 0)})

poly_probs = {}
if parsed:
    ppdf = pd.DataFrame(parsed)
    ppdf["rt"] = (ppdf["target"] / 1000).round() * 1000
    for rtg, grp in ppdf.groupby("rt"):
        w = np.maximum(grp["volume"].values, 1.0)
        poly_probs[int(rtg)] = float(np.average(grp["prob"].values, weights=w))
        print(f"  Poly P(BTC>${int(rtg)//1000}k) = {poly_probs[int(rtg)]*100:.1f}%")

# Supplement from disk
poly_disk = pd.read_csv("data/polymarket/crypto_markets.csv", low_memory=False)
btc_disk  = poly_disk[
    poly_disk["question"].astype(str).str.lower().str.contains("bitcoin|btc", na=False) &
    poly_disk["question"].astype(str).str.lower().str.contains("above|reach|hit|exceed|end|>", na=False)
]
for idx2 in range(len(btc_disk)):
    row2 = btc_disk.iloc[idx2]
    tg3  = price_from_q(str(row2["question"]))
    if tg3 is None or tg3 < 50000: continue
    tk3  = int(round(tg3 / 1000) * 1000)
    if tk3 in poly_probs: continue
    op3  = row2.get("outcomePrices", "")
    p3   = None
    if isinstance(op3, str) and op3.strip():
        ol3 = json.loads(op3)
        if isinstance(ol3, list) and ol3:
            fp3 = float(ol3[0])
            p3  = fp3 / 100.0 if fp3 > 1.0 else fp3
    if p3 is None:
        lt3 = row2.get("lastTradePrice", 0)
        if isinstance(lt3, (int, float)) and not pd.isna(lt3):
            p3 = float(lt3) / 100.0 if float(lt3) > 1 else float(lt3)
    if p3 and p3 > 0:
        poly_probs[tk3] = p3
        print(f"  Poly(disk) P(BTC>${tk3//1000}k) = {p3*100:.1f}%")

# ── 8. REGIME REPORT ─────────────────────────────────────────────
print(f"\n{'='*55}")
print("MOMENTUM REGIME REPORT")
print(f"{'='*55}")
for rg in [btc_reg, eth_reg]:
    em = "🟢" if rg["regime"]=="BULLISH" else ("🔴" if rg["regime"]=="BEARISH" else "🟡")
    rl = "overbought" if rg["rsi14"]>70 else ("oversold" if rg["rsi14"]<30 else "neutral")
    ml = "bullish ✚" if rg["macd"]>rg["macd_sig"] else "bearish ✖"
    print(f"\n  {em} {rg['sym']} — {rg['regime']}")
    print(f"     Price ${rg['close']:,.2f} | SMA20 ${rg['sma20']:,.0f} | SMA50 ${rg['sma50']:,.0f}")
    print(f"     RSI(14)={rg['rsi14']:.1f} ({rl}) | MACD {ml}")
    for nm, sv in rg["inds"]: print(f"       {nm}: {sv}")

print(f"\n{'='*55}")
print(f"BTC 30-DAY FORECAST")
print(f"{'='*55}")
print(f"  Current    : ${btc_price:,.0f}")
print(f"  Forecast   : ${btc_fc30:,.0f}  ({btc_fc_pct:+.1f}%)  → {btc_dir}")
print(f"  95% CI     : ${fwd_lo[-1]:,.0f} – ${fwd_hi[-1]:,.0f}")
print(f"  Support    : {['${:,.0f}'.format(s) for s in btc_sup]}")
print(f"  Resistance : {['${:,.0f}'.format(r) for r in btc_res]}")

# ── 9. 4-PANEL CHART ─────────────────────────────────────────────
btc_momentum_chart = plt.figure(figsize=(18, 16), facecolor=BTC_BG)
btc_momentum_chart.suptitle("BTC Market Direction Model  |  CoinGecko OHLCV · Kalshi & Polymarket",
                              fontsize=15, color=BTC_FG, fontweight="bold", y=0.985)
gs = GridSpec(4, 1, figure=btc_momentum_chart, height_ratios=[3, 1, 1, 1.4],
              hspace=0.12, top=0.96, bottom=0.06, left=0.09, right=0.97)
ap = btc_momentum_chart.add_subplot(gs[0])
ar = btc_momentum_chart.add_subplot(gs[1], sharex=ap)
am = btc_momentum_chart.add_subplot(gs[2], sharex=ap)
ab = btc_momentum_chart.add_subplot(gs[3])
for ax in [ap, ar, am, ab]: ax.set_facecolor(BTC_BG)

# Panel 1: Price + MAs + Forecast
hd = btc_td["date"].values
ap.plot(hd, btc_td["close"], color=BTC_BLUE,   lw=2,   label="BTC Close", zorder=5)
ap.plot(hd, btc_td["sma20"], color=BTC_ORANGE, lw=1.5, ls="--", alpha=0.9, label="SMA 20")
ap.plot(hd, btc_td["sma50"], color=BTC_GREEN,  lw=1.5, ls="-.", alpha=0.9, label="SMA 50")
fc = BTC_SUCC if btc_dir == "BULLISH" else BTC_WARN
ap.plot(fdates, fwd_mean, color=fc, lw=2, ls="--", label=f"30d Forecast ({btc_dir})", zorder=4)
ap.fill_between(fdates, fwd_lo, fwd_hi, color=fc, alpha=0.15, label="95% CI")
ap.plot([ld, fdates[0]], [btc_price, fwd_mean[0]], color=fc, lw=2, ls="--", zorder=4)
for sl2 in btc_sup:
    ap.axhline(sl2, color=BTC_SUCC, lw=0.8, ls=":", alpha=0.7)
    ap.text(hd[3], sl2*1.003, f"S ${sl2/1e3:.0f}k", color=BTC_SUCC, fontsize=8.5, va="bottom")
for rl2 in btc_res:
    ap.axhline(rl2, color=BTC_WARN, lw=0.8, ls=":", alpha=0.7)
    ap.text(hd[3], rl2*1.003, f"R ${rl2/1e3:.0f}k", color=BTC_WARN, fontsize=8.5, va="bottom")
ap.set_ylabel("Price (USD)", color=BTC_FG, fontsize=11)
ap.yaxis.set_major_formatter(mticker.StrMethodFormatter("${x:,.0f}"))
ap.legend(loc="upper left", framealpha=0.3, facecolor=BTC_BG, edgecolor=BTC_FG2, labelcolor=BTC_FG, fontsize=9)
ap.grid(True, alpha=0.4)
rc2 = btc_reg["regime"]
rc2c = BTC_SUCC if rc2=="BULLISH" else (BTC_WARN if rc2=="BEARISH" else BTC_GOLD)
ap.text(0.99, 0.97, f"Regime: {rc2}", transform=ap.transAxes, ha="right", va="top",
        fontsize=12, fontweight="bold", color=rc2c,
        bbox=dict(boxstyle="round,pad=0.3", facecolor=BTC_BG, edgecolor=rc2c, alpha=0.9))
ap.set_title("BTC / USD  —  Price, Moving Averages & 30-Day Forecast Cone (95% CI)", color=BTC_FG, fontsize=12, pad=6)

# Panel 2: RSI
ar.plot(hd, btc_td["rsi14"], color=BTC_LAV, lw=1.8)
ar.axhline(70, color=BTC_WARN, lw=1, ls="--", alpha=0.8)
ar.axhline(30, color=BTC_SUCC, lw=1, ls="--", alpha=0.8)
ar.axhline(50, color=BTC_FG2,  lw=0.8, ls=":", alpha=0.5)
ar.fill_between(hd, 70, btc_td["rsi14"].clip(lower=70), color=BTC_WARN, alpha=0.15)
ar.fill_between(hd, btc_td["rsi14"].clip(upper=30), 30, color=BTC_SUCC, alpha=0.15)
ar.set_ylim(10, 90); ar.set_ylabel("RSI (14)", color=BTC_FG, fontsize=10)
ar.text(0.01, 0.88, "Overbought 70", transform=ar.transAxes, color=BTC_WARN, fontsize=8)
ar.text(0.01, 0.07, "Oversold 30",   transform=ar.transAxes, color=BTC_SUCC, fontsize=8)
ar.text(0.99, 0.88, f"RSI: {btc_td['rsi14'].iloc[-1]:.1f}", transform=ar.transAxes,
        ha="right", color=BTC_LAV, fontsize=10, fontweight="bold")
ar.grid(True, alpha=0.3)

# Panel 3: MACD
am.plot(hd, btc_td["macd"],     color=BTC_BLUE,   lw=1.5, label="MACD")
am.plot(hd, btc_td["macd_sig"], color=BTC_ORANGE, lw=1.5, label="Signal")
am.bar(hd, btc_td["macd_hist"].clip(lower=0), color=BTC_SUCC, alpha=0.5, width=1.0)
am.bar(hd, btc_td["macd_hist"].clip(upper=0), color=BTC_WARN, alpha=0.5, width=1.0)
am.axhline(0, color=BTC_FG2, lw=0.8)
am.set_ylabel("MACD", color=BTC_FG, fontsize=10)
am.legend(loc="upper left", framealpha=0.2, facecolor=BTC_BG, edgecolor=BTC_FG2, labelcolor=BTC_FG, fontsize=8, ncol=2)
am.grid(True, alpha=0.3)

# Panel 4: Probability bars
bp2  = np.arange(len(TARGETS)); bw2 = 0.35
kv2  = [float(kal_probs.get(t) or 0) for t in TARGETS]
pv2  = [float(poly_probs.get(t) or 0) for t in TARGETS]
bk2  = ab.bar(bp2 - bw2/2, [v*100 for v in kv2], bw2, color=BTC_PURPLE, alpha=0.85, label="Kalshi")
bp22 = ab.bar(bp2 + bw2/2, [v*100 for v in pv2], bw2, color=BTC_CORAL,  alpha=0.85, label="Polymarket")
for br in list(bk2) + list(bp22):
    bh = br.get_height()
    if bh > 0.5:
        ab.text(br.get_x() + br.get_width()/2, bh + 0.5, f"{bh:.1f}%",
                ha="center", va="bottom", color=BTC_FG, fontsize=8.5)
ab.set_xticks(bp2)
ab.set_xticklabels([f"BTC > ${t//1000}k" for t in TARGETS], color=BTC_FG, fontsize=10)
ab.set_ylabel("Implied Probability (%)", color=BTC_FG, fontsize=10)
ab.set_title("Kalshi & Polymarket  —  BTC Price Target Implied Probabilities", color=BTC_FG, fontsize=11, pad=6)
ab.legend(framealpha=0.3, facecolor=BTC_BG, edgecolor=BTC_FG2, labelcolor=BTC_FG, fontsize=10)
ab.grid(True, axis="y", alpha=0.3)
mp2 = max(max(kv2 + pv2, default=0) * 100 + 12, 20)
ab.set_ylim(0, mp2)
ab.text(0.99, 0.97, f"BTC Now: ${btc_price:,.0f}", transform=ab.transAxes, ha="right", va="top",
        color=BTC_GOLD, fontsize=10, fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", facecolor=BTC_BG, edgecolor=BTC_GOLD, alpha=0.9))

plt.setp(ap.get_xticklabels(), visible=False)
plt.setp(ar.get_xticklabels(), visible=False)
plt.setp(am.get_xticklabels(), visible=False)
btc_momentum_chart.align_ylabels([ap, ar, am])
print("\n  ✅ btc_momentum_chart rendered")
btc_momentum_chart.savefig(OUTPUTS_DIR / "btc_momentum_chart.png", dpi=150, bbox_inches="tight", facecolor=BTC_BG)
print(f"  ✅ Saved to {OUTPUTS_DIR / 'btc_momentum_chart.png'}")

# ── 10. EXPORT VARIABLES ─────────────────────────────────────────
btc_indicators_df  = btc_td
eth_indicators_df  = eth_td
btc_forecast_df    = pd.DataFrame({"date": fdates, "forecast": fwd_mean.tolist(),
                                    "lower_95": fwd_lo.tolist(), "upper_95": fwd_hi.tolist()})
btc_regime_summary = {**btc_reg, "forecast_30d": btc_fc30, "forecast_pct": btc_fc_pct,
                       "direction": btc_dir, "current": btc_price,
                       "support": btc_sup, "resistance": btc_res, "r2": rv**2}
btc_prediction_probs = {"kalshi": {k: round(v*100,1) for k,v in kal_probs.items() if v},
                         "poly":   {k: round(v*100,1) for k,v in poly_probs.items() if v}}

print(f"\n  BTC={btc_reg['regime']}  ETH={eth_reg['regime']}  Direction={btc_dir} ({btc_fc_pct:+.1f}%)")
print(f"  Kalshi: {btc_prediction_probs['kalshi']}")
print(f"  Poly:   {btc_prediction_probs['poly']}")
print("  ✅ All indicators computed, chart rendered, forecast printed.")
