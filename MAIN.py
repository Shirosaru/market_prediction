#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════════════════════════════
  COMPLETE CRYPTO MARKET PREDICTION PIPELINE — INTEGRATED EXECUTION
════════════════════════════════════════════════════════════════════════════════

This is the MAIN orchestration script that runs all phases in sequence:
  1. Fetch documentation from APIs
  2. Analyze API capabilities
  3. Fetch live cryptocurrency data
  4. Merge and unify data sources
  5. Altcoin season analysis
  6. BTC/ETH momentum signals & forecast
  7. Sentiment vs reality gap analysis

All scripts execute in the correct order with output tracking.
════════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
import subprocess
import time
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# SETUP & CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
WORKSPACE = Path("/home2/makret_prediction")
os.chdir(WORKSPACE)

# Ensure output directories exist
(WORKSPACE / "data").mkdir(exist_ok=True)
(WORKSPACE / "data/alphavantage").mkdir(exist_ok=True, parents=True)
(WORKSPACE / "data/kalshi").mkdir(exist_ok=True, parents=True)
(WORKSPACE / "data/polymarket").mkdir(exist_ok=True, parents=True)
(WORKSPACE / "data/fred").mkdir(exist_ok=True, parents=True)
(WORKSPACE / "docs").mkdir(exist_ok=True)
(WORKSPACE / "outputs").mkdir(exist_ok=True)

# Color codes
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

def log_header(text):
    """Print formatted header."""
    print(f"\n{BLUE}{'='*85}{RESET}")
    print(f"{BOLD}{BLUE}{text.center(85)}{RESET}")
    print(f"{BLUE}{'='*85}{RESET}\n")

def log_phase(num, name):
    """Print phase header."""
    print(f"\n{GREEN}{'─'*85}{RESET}")
    print(f"{BOLD}{GREEN}PHASE {num}: {name}{RESET}")
    print(f"{GREEN}{'─'*85}{RESET}\n")

def execute_script(script_name, description):
    """Execute a Python script and return success status."""
    script_path = WORKSPACE / script_name
    
    if not script_path.exists():
        print(f"{RED}✗ SKIPPED: {script_name} (file not found){RESET}\n")
        return False
    
    print(f"{YELLOW}Executing: {script_name}{RESET}")
    print(f"{YELLOW}Description: {description}{RESET}\n")
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout per script
        )
        
        if result.returncode == 0:
            print(f"{GREEN}✓ SUCCESS{RESET}: {script_name}\n")
            # Print first and last parts of output
            if result.stdout:
                lines = result.stdout.split('\n')
                if len(lines) > 50:
                    print("OUTPUT (first 25 lines):")
                    print('\n'.join(lines[:25]))
                    print(f"\n{YELLOW}... ({len(lines)-50} lines omitted) ...{RESET}\n")
                    print("OUTPUT (last 25 lines):")
                    print('\n'.join(lines[-25:]))
                else:
                    print("OUTPUT:")
                    print(result.stdout)
            return True
        else:
            print(f"{RED}✗ FAILED{RESET}: {script_name}")
            print(f"Return code: {result.returncode}\n")
            if result.stderr:
                print("STDERR:")
                print(result.stderr[:1000])
            return False
    
    except subprocess.TimeoutExpired:
        print(f"{RED}✗ TIMEOUT{RESET}: {script_name} (execution exceeded 10 minutes)\n")
        return False
    except Exception as e:
        print(f"{RED}✗ EXCEPTION{RESET}: {script_name}")
        print(f"Error: {e}\n")
        return False

# ─────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE EXECUTION
# ─────────────────────────────────────────────────────────────────────────────

def main():
    log_header("CRYPTO MARKET PREDICTION PIPELINE")
    
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Workspace: {WORKSPACE}\n")
    
    pipeline_steps = [
        ("docs_collector.py", 1, "Documentation Collector",
         "Fetch and collect documentation from Polymarket, Kalshi, Metaculus, FRED, AlphaVantage, SEC"),
        
        ("crypto_api_analysis.py", 2, "API Analysis",
         "Analyze collected docs for API capabilities, endpoints, auth methods, crypto coverage"),
        
        ("fetch_crypto_data.py", 3, "Fetch Live Crypto Data",
         "Fetch from AlphaVantage, Kalshi, Polymarket, FRED, CoinGecko APIs"),
        
        ("load_and_merge_unified_data.py", 4, "Load & Merge Data",
         "Merge Kalshi, Polymarket, and CoinGecko data into unified dataframes"),
        
        ("altcoin_season_analysis.py", 5, "Altcoin Season Analysis",
         "Compute altcoin season index, BTC dominance history, correlation analysis"),
        
        ("btc_momentum,signals.py", 6, "BTC/ETH Momentum Signals",
         "Technical indicators (RSI, MACD, MA), 30-day forecast, Kalshi/Polymarket probs"),
        
        ("sentiment_rally_gap.py", 7, "Sentiment vs Reality Gap",
         "Compare crowd sentiment against technical signals, identify divergences"),
    ]
    
    results = {}
    start_time = time.time()
    
    for script, phase_num, phase_name, description in pipeline_steps:
        log_phase(phase_num, phase_name)
        success = execute_script(script, description)
        results[script] = success
        time.sleep(1)  # Brief pause between scripts
    
    # ─────────────────────────────────────────────────────────────────────────
    # FINAL SUMMARY
    # ─────────────────────────────────────────────────────────────────────────
    elapsed = time.time() - start_time
    
    log_header("PIPELINE EXECUTION SUMMARY")
    
    success_count = sum(1 for success in results.values() if success)
    total_count = len(results)
    
    print(f"Completion Status: {success_count}/{total_count} phases successful")
    print(f"Total Duration: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)\n")
    
    print("Phase Results:")
    for idx, (script, phase_num, phase_name, _) in enumerate(pipeline_steps, 1):
        status = "✓ SUCCESS" if results[script] else "✗ FAILED"
        color = GREEN if results[script] else RED
        print(f"  {color}{status}{RESET} — Phase {phase_num}: {phase_name}")
    
    print(f"\n{BLUE}{'─'*85}{RESET}")
    print("\nOutput Files Generated:")
    print("  📁 data/               → CSV/JSON data from all sources")
    print("  📁 data/alphavantage/  → Currency exchange rates")
    print("  📁 data/kalshi/        → Prediction market data")
    print("  📁 data/polymarket/    → Polymarket event & market data")
    print("  📁 data/fred/          → Federal Reserve economic data")
    print("  📁 docs/               → API documentation collected from sources")
    print("  📁 outputs/            → Analysis results & summaries")
    print("  📊 *.png               → Matplotlib visualization charts")
    print(f"\n{BLUE}{'='*85}{RESET}\n")
    
    print(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    if success_count == total_count:
        print(f"{GREEN}{BOLD}✓ ALL PHASES COMPLETED SUCCESSFULLY!{RESET}\n")
        return 0
    else:
        print(f"{YELLOW}{BOLD}⚠ Some phases failed. Please review errors above.{RESET}\n")
        return 1

# ─────────────────────────────────────────────────────────────────────────────
# MANUAL PHASE RUNNERS (optional — run individual phases)
# ─────────────────────────────────────────────────────────────────────────────

def run_phase(phase_num):
    """Run a single phase by number."""
    phases = {
        1: ("docs_collector.py", "Documentation Collector"),
        2: ("crypto_api_analysis.py", "API Analysis"),
        3: ("fetch_crypto_data.py", "Fetch Live Crypto Data"),
        4: ("load_and_merge_unified_data.py", "Load & Merge Data"),
        5: ("altcoin_season_analysis.py", "Altcoin Season Analysis"),
        6: ("btc_momentum,signals.py", "BTC/ETH Momentum Signals"),
        7: ("sentiment_rally_gap.py", "Sentiment vs Reality Gap"),
    }
    
    if phase_num not in phases:
        print(f"{RED}Invalid phase number: {phase_num}{RESET}")
        return False
    
    script, name = phases[phase_num]
    log_phase(phase_num, name)
    return execute_script(script, f"Run {name}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        # Run single phase: python MAIN.py 1
        phase = int(sys.argv[1])
        sys.exit(0 if run_phase(phase) else 1)
    else:
        # Run full pipeline
        sys.exit(main())
