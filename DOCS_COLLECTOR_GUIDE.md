# Documentation Collector Guide

## Overview
The `docs_collector.py` script automatically fetches and organizes documentation from 6 key financial/prediction market data sources for indexing purposes.

## What It Does

### Sources Collected
1. **Polymarket** - Prediction market documentation
   - URL: https://docs.polymarket.com/
   - Collects API docs, guides, and reference materials

2. **Kalshi** - Event derivatives trading platform
   - URL: https://docs.kalshi.com/welcome
   - Fetches API documentation and trading guides

3. **Metaculus** - Prediction aggregation platform
   - URL: https://www.metaculus.com/api/
   - Collects API documentation and schema information

4. **FRED** - Federal Reserve Economic Data
   - URL: https://fred.stlouisfed.org/
   - Gathers API documentation and economic data guides

5. **Alpha Vantage** - Stock market data provider
   - URL: https://www.alphavantage.co/
   - Collects API documentation and usage examples

6. **SEC** - Securities and Exchange Commission filings
   - URL: https://www.sec.gov/search-filings
   - Fetches search documentation and filing guides

### How It Works
- **Fetches HTML pages** from each source
- **Extracts links** and follows documentation pages (limited to 20 per source for efficiency)
- **Organizes files** into separate folders by source
- **Rate limiting** (0.5s delays between requests) to be respectful to servers
- **Error handling** with detailed logging
- **Creates index** in JSON format with metadata
- **Generates README** summary of collected documentation

## Setup

### Prerequisites
- Conda installed
- Internet connection for downloading documentation

### Create the Environment

```bash
cd /home2/makret_prediction
conda create -n docs-collect python=3.11 requests beautifulsoup4 -y
```

The environment is already created with:
- **Python 3.11** - Latest stable Python for better performance
- **requests** - HTTP library for fetching pages
- **beautifulsoup4** - HTML parsing for extracting links

## How to Run

### 1. Activate the Environment
```bash
conda activate docs-collect
```

### 2. Run the Documentation Collector
```bash
cd /home2/makret_prediction
python3 docs_collector.py
```

### 3. Expected Output
```
2026-03-02 12:34:56,789 - INFO - ============================================================
2026-03-02 12:34:56,789 - INFO - Collecting Polymarket docs...
2026-03-02 12:34:56,789 - INFO - ============================================================
2026-03-02 12:34:57,123 - INFO - Fetching: https://docs.polymarket.com/
2026-03-02 12:34:58,456 - INFO - Saved: docs/polymarket/index.html
2026-03-02 12:34:58,789 - INFO - Fetching: https://docs.polymarket.com/start-here
...
[continues for all 6 sources]
...
2026-03-02 12:45:23,456 - INFO - Documentation collection completed in 625.67 seconds
```

## Output Structure

After running, your `docs/` folder will contain:

```
docs/
├── polymarket/
│   ├── index.html
│   ├── start_here.html
│   └── [more pages...]
├── kalshi/
│   ├── index.html
│   ├── api_introduction.html
│   └── [more pages...]
├── metaculus/
│   ├── api.html
│   ├── schema.html
│   └── [more pages...]
├── fred/
│   ├── index.html
│   ├── docs_api.html
│   └── [more pages...]
├── alphavantage/
│   ├── index.html
│   ├── documentation.html
│   └── [more pages...]
├── sec/
│   ├── search-filings.html
│   ├── cgi-bin_browse-edgar.html
│   └── [more pages...]
├── INDEX.json          # Metadata of all collected files
└── README.md           # Summary of collection
```

## Understanding the Output

### INDEX.json
Contains structured metadata:
```json
{
  "timestamp": "2026-03-02T12:45:23.456789",
  "sources": [
    {
      "name": "polymarket",
      "file_count": 18,
      "files": [
        "polymarket/index.html",
        "polymarket/api_guide.html",
        ...
      ]
    },
    ...
  ]
}
```

### README.md
Human-readable summary with:
- Collection timestamp
- File counts per source
- List of collected files

## Use Cases

### Indexing
- Extract text from HTML files for full-text search indexing
- Build search database for internal documentation lookup

### Analysis
- Understand API capabilities across different platforms
- Compare features and requirements between services
- Track documentation structure and organization

### Integration
- Reference locally cached documentation when building integrations
- Avoid repeated external HTTP requests during development
- Provide offline access to API documentation

## Customization

### Modify Limits
In `docs_collector.py`, change this line to collect more/fewer pages:
```python
for link in list(links)[:20]:  # Change 20 to desired number
```

### Add More Sources
Add a new method in the `DocCollector` class:
```python
def collect_newsource(self):
    """Collect documentation from new source"""
    logger.info("Collecting New Source docs...")
    base_url = "https://example.com/docs"
    folder = self.base_dir / "newsource"
    folder.mkdir(exist_ok=True)
    
    try:
        html = self.fetch_page(base_url)
        if html:
            self.save_content(html, folder / "index.html")
    except Exception as e:
        logger.error(f"Error: {e}")
```

Then add it to `collect_all()`:
```python
self.collect_newsource()
time.sleep(1)
```

## Deactivating the Environment

When done:
```bash
conda deactivate
```

## Troubleshooting

### Network Issues
- Check your internet connection
- Some corporate firewalls may block requests
- Try running with different User-Agent headers

### Permission Errors
- Ensure write permissions in `/home2/makret_prediction/`
- Check disk space availability

### Missing Dependencies
- Make sure conda environment is activated
- Re-create environment if needed: `conda remove -n docs-collect --all && conda create -n docs-collect python=3.11 requests beautifulsoup4 -y`

## Notes

- Script respects websites with 0.5s delays between requests
- Collection typically takes 10-15 minutes depending on documentation size
- All content is stored locally in HTML format for easy parsing
- No authentication required for public documentation APIs
