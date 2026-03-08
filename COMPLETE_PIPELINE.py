"""
═══════════════════════════════════════════════════════════════════════════════
  CRYPTO MARKET PREDICTION PIPELINE — COMPLETE ORCHESTRATION
═══════════════════════════════════════════════════════════════════════════════

Execution order:
  1. docs_collector.py      → Collect API documentation
  2. crypto_api_analysis.py → Analyze collected docs
  3. fetch_crypto_data.py   → Fetch live crypto data
  4. load_and_merge_unified_data.py → Unify all data sources
  5. altcoin_season_analysis.py → Alt season analysis + charts
  6. btc_momentum_signals.py → BTC/ETH momentum + forecast
  7. sentiment_rally_gap.py → Sentiment vs reality gap analysis

This script runs the full pipeline with output checkpoints & summary.
═══════════════════════════════════════════════════════════════════════════════
"""

import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime

# Color codes for terminal output
BOLD = "\033[1m"
RESET = "\033[0m"
GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RED = "\033[91m"

scripts_pipeline = [
    ("docs_collector.py", "📚 PHASE 1: Collect API Documentation"),
    ("crypto_api_analysis.py", "🔍 PHASE 2: Analyze Documentation"),
    ("fetch_crypto_data.py", "📊 PHASE 3: Fetch Live Crypto Data"),
    ("load_and_merge_unified_data.py", "🔗 PHASE 4: Merge Unified Data"),
    ("altcoin_season_analysis.py", "📈 PHASE 5: Altcoin Season Analysis"),
    ("btc_momentum_signals.py", "🚀 PHASE 6: BTC/ETH Momentum Analysis"),
    ("sentiment_rally_gap.py", "⚖️ PHASE 7: Sentiment vs Reality Gap"),
]

def run_pipeline():
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BOLD}{BLUE}CRYPTO MARKET PREDICTION PIPELINE - COMPLETE{RESET}")
    print(f"{BLUE}{'='*80}{RESET}\n")
    
    workspace = Path("/home2/makret_prediction")
    os.chdir(workspace)
    
    print(f"{YELLOW}Workspace: {workspace}{RESET}\n")
    
    results = {}
    start_time = datetime.now()
    
    for idx, (script, phase_name) in enumerate(scripts_pipeline, 1):
        script_path = workspace / script
        
        if not script_path.exists():
            print(f"{RED}✗ SKIPPED{RESET}: {script} (file not found)")
            results[script] = {"status": "skipped", "error": "File not found"}
            continue
        
        print(f"\n{BLUE}{'─'*80}{RESET}")
        print(f"{GREEN}{phase_name}{RESET}")
        print(f"{BLUE}{'─'*80}{RESET}")
        print(f"Running: {script}\n")
        
        try:
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                print(f"{GREEN}✓ SUCCESS{RESET}: {script}")
                results[script] = {"status": "success"}
                if result.stdout:
                    print(result.stdout[:2000])  # First 2000 chars
            else:
                print(f"{RED}✗ ERROR{RESET}: {script}")
                results[script] = {"status": "error", "returncode": result.returncode}
                if result.stderr:
                    print(f"STDERR:\n{result.stderr[:1000]}")
        
        except subprocess.TimeoutExpired:
            print(f"{YELLOW}⏱ TIMEOUT: {script} (>5 min){RESET}")
            results[script] = {"status": "timeout"}
        
        except Exception as e:
            print(f"{RED}✗ EXCEPTION{RESET}: {script}")
            print(f"  {e}")
            results[script] = {"status": "exception", "error": str(e)}
    
    # Final summary
    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()
    
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BOLD}{GREEN}PIPELINE SUMMARY{RESET}")
    print(f"{BLUE}{'='*80}{RESET}\n")
    
    success_count = sum(1 for r in results.values() if r.get("status") == "success")
    total_count = len(results)
    
    print(f"Completed: {success_count}/{total_count} phases")
    print(f"Duration: {elapsed:.1f} seconds\n")
    
    for script, result in results.items():
        status = result.get("status", "unknown")
        if status == "success":
            print(f"  {GREEN}✓{RESET} {script}")
        elif status == "skipped":
            print(f"  {YELLOW}⊘{RESET} {script} (skipped)")
        else:
            print(f"  {RED}✗{RESET} {script} ({status})")
    
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"Output files saved to:")
    print(f"  - data/        (CSV/JSON data)")
    print(f"  - docs/        (API documentation)")
    print(f"  - *.png        (Matplotlib charts)")
    print(f"{BLUE}{'='*80}{RESET}\n")

if __name__ == "__main__":
    run_pipeline()
