#!/bin/bash
set -e
cd "$(dirname "$0")/.."
python3 -m venv scripts/venv
scripts/venv/bin/pip install --upgrade pip
scripts/venv/bin/pip install requests beautifulsoup4 python-dotenv openai pytest pyyaml
echo "Venv ready. Activate with: source scripts/venv/bin/activate"
