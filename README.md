# Cryptocurrency Market Prediction Pipeline

A complete 7-phase analysis system for cryptocurrency market prediction combining real-time data from 5+ APIs with technical and sentiment analysis.

## 🚀 Quick Start

```bash
# Run complete pipeline
python MAIN.py

# Run specific phases
python MAIN.py 1    # Phase 1: Collect documentation
python MAIN.py 3    # Phase 3: Fetch live data
python MAIN.py 5    # Phase 5: Altcoin season analysis
```

## 📖 Documentation

**All documentation consolidated in [`docs/guides/`](docs/guides/)**

Start here → **[COMPLETE_SUMMARY.md](docs/guides/COMPLETE_SUMMARY.md)** ⭐

Additional guides:
- **[QUICKSTART.txt](docs/guides/QUICKSTART.txt)** — 5-minute quick reference
- **[COMPLETE_PIPELINE_GUIDE.txt](docs/guides/COMPLETE_PIPELINE_GUIDE.txt)** — Detailed walkthrough
- **[API_CAPABILITIES_SUMMARY.md](docs/guides/API_CAPABILITIES_SUMMARY.md)** — Data sources
- **[OUTPUTS_GUIDE.md](docs/guides/OUTPUTS_GUIDE.md)** — Output file formats
- **[NAVIGATION.md](docs/guides/NAVIGATION.md)** — Find anything quickly

## 📊 Results

- **Charts**: [`outputs/charts/`](outputs/charts/) — 3 PNG visualizations
- **Data**: [`outputs/data/`](outputs/data/) — CSV/JSON market data (2.3 MB)
- **Report**: [`outputs/reports/ANALYSIS_REPORT.md`](outputs/reports/ANALYSIS_REPORT.md) — Full analysis

## 🔄 Pipeline Phases

1. **Docs Collector** — Fetch 100+ API documentation pages
2. **API Analysis** — Analyze docs for capabilities  
3. **Fetch Data** — Download live crypto data (400+ markets)
4. **Merge Data** — Unify data from all sources
5. **Altseason Analysis** — Compute season index + charts
6. **Momentum Signals** — Technical analysis + forecast
7. **Sentiment Gap** — Crowd vs reality comparison

## ⚙️ Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate
