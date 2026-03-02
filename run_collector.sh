#!/bin/bash
# Quick start script for documentation collection

echo "========================================"
echo "Documentation Collector Setup & Run"
echo "========================================"
echo ""

# Check if conda is available
if ! command -v conda &> /dev/null; then
    echo "Error: Conda is not installed or not in PATH"
    exit 1
fi

echo "✓ Conda found"
echo ""

# Check if environment exists
if conda env list | grep -q "docs-collect"; then
    echo "✓ Conda environment 'docs-collect' already exists"
else
    echo "Creating conda environment 'docs-collect'..."
    conda create -n docs-collect python=3.11 requests beautifulsoup4 -y
    echo "✓ Environment created"
fi

echo ""
echo "Activating environment..."
eval "$(conda shell.bash hook)"
conda activate docs-collect

echo "✓ Environment activated"
echo ""
echo "Running documentation collector..."
echo "========================================"
echo ""

cd /home2/makret_prediction
python3 docs_collector.py

echo ""
echo "========================================"
echo "Collection complete!"
echo "Documentation saved to: /home2/makret_prediction/docs/"
echo ""
echo "View the index with:"
echo "  cat docs/INDEX.json"
echo "  cat docs/README.md"
echo ""
echo "To deactivate environment: conda deactivate"
