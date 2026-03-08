# Crypto Market Prediction Pipeline

> **Find where the crowd is wrong.** A 7-phase automated system that cross-references prediction market sentiment against technical momentum signals — ranking divergences across 29 cryptocurrencies in real time.

Built for the Zerve Hackathon. Runs in under 2 minutes on a single command.

---

## ⚡ Quick Start

```bash
conda activate market-analysis
python MAIN.py
```

Charts → `outputs/charts/` · Data → `outputs/data/`

---

## 🔍 What It Does

The pipeline identifies **Sentiment–Reality Gaps**: situations where crowd belief (Kalshi/Polymarket implied probability, or CoinGecko community votes) diverges significantly from on-chain technical momentum.

##Disclaim

---

## 🔄 Pipeline Phases

| Phase | Script | What it does |
|-------|--------|-------------|
| 1 | `docs_collector.py` | Scrapes 100+ API documentation pages |
| 2 | `doc_scraper_indexing.py` | Indexes + analyzes doc capabilities |
| 3 | `fetch_crypto_data.py` | Fetches live data — Kalshi (136 markets), CoinGecko, AlphaVantage, FRED, CG community sentiment |
| 4 | `load_and_merge_unified_data.py` | Merges all sources into unified DataFrames |
| 5 | `altcoin_season_analysis.py` | Computes altcoin season index + BTC dominance charts |
| 6 | `btc_momentum_signals.py` | Multi-factor technical analysis + BTC momentum forecast |
| 7 | `sentiment_rally_gap.py` | Crowd vs reality gap — 29 coins, 8 charts |

---

## 📊 Outputs

| File | Description |
|------|-------------|
| `outputs/charts/sentiment_vs_tech_scatter.png` | Scatter: Prediction Markets vs CG Community (dual panel) |
| `outputs/charts/sentiment_gap_bar.png` | Gap bar chart — ranked by divergence (dual panel) |
| `outputs/charts/sentiment_gap_table.png` | Full table: all 29 coins, source-labelled |
| `outputs/charts/altcoin_momentum_heatmap.png` | 82-coin momentum heatmap with crowd overlays |
| `outputs/charts/btc_momentum_chart.png` | BTC multi-factor momentum + forecast |
| `outputs/charts/btc_dom_altseason_chart.png` | BTC dominance trend + altcoin season index |
| `outputs/charts/altcoin_perf_heatmap.png` | 30d / 7d / 24h performance heatmap |
| `outputs/charts/altcoin_correlation_heatmap.png` | Cross-coin correlation matrix |
| `outputs/data/sentiment_reality_gap.csv` | Gap scores for all 29 coins |
| `outputs/data/sentiment_gap_summary.json` | Summary stats + top over/undervalued coins |

---

## 🗂️ Data Sources

| Source | What's fetched | Auth |
|--------|---------------|------|
| **Kalshi** | 136 open prediction markets (BTC, ETH) | None |
| **CoinGecko** | Prices, market caps, 30/7/1d perf for 100+ coins | None |
| **CoinGecko Community** | `sentiment_votes_up_pct` for 30 altcoins | None |
| **AlphaVantage** | BTC OHLCV, ETH/XRP exchange rates | `Alpha_Vantage_API_KEY` in `.env` |
| **FRED** | CBBTCUSD, CBETHUSD historical series | `FRED_API_KEY` in `.env` |

---

## ⚙️ Setup

```bash
# Conda environment (recommended)
conda create -n market-analysis python=3.12
conda activate market-analysis
pip install -r requirements.txt

# API keys
echo "Alpha_Vantage_API_KEY=your_key_here" >> .env
echo "FRED_API_KEY=your_key_here" >> .env
```

Free keys: [alphavantage.co](https://www.alphavantage.co/support/#api-key) · [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html)

---

## 📁 Project Structure

```
MAIN.py                        # Orchestrator — runs all 7 phases
fetch_crypto_data.py           # Phase 3: data fetching
sentiment_rally_gap.py         # Phase 7: gap analysis + 8 charts
data/
  kalshi/                      # Raw Kalshi market data
  coingecko/community_sentiment.csv
  fred/
  alphavantage/
outputs/
  charts/                      # 8 PNG visualizations
  data/                        # CSV + JSON results
docs/
  guides/                      # Full pipeline documentation
  narrative_etc/               # Hackathon video script, security notes
```

---

## 📖 Documentation

- [COMPLETE_SUMMARY.md](docs/guides/COMPLETE_SUMMARY.md) — full pipeline walkthrough ⭐
- [API_CAPABILITIES_SUMMARY.md](docs/guides/API_CAPABILITIES_SUMMARY.md) — data source details
- [OUTPUTS_GUIDE.md](docs/guides/OUTPUTS_GUIDE.md) — reading the output files
- [HACKATHON_VIDEO_SCRIPT.md](docs/narrative_etc/HACKATHON_VIDEO_SCRIPT.md) — 2-min video script

---

---

> **⚠️ Disclaimer:** This tool is for research and educational purposes only. Nothing produced by this pipeline constitutes financial advice. Cryptocurrency markets are highly volatile. Always do your own research. **Trade at your own risk.**

---

*Built on Zerve platform · polished on personal server · Python 3.12 · open source*
