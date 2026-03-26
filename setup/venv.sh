#!/bin/bash
set -e
cd "$(dirname "$0")/.."
python3 -m venv src/venv
src/venv/bin/pip install --upgrade pip
src/venv/bin/pip install requests beautifulsoup4 python-dotenv openai pytest pyyaml
echo "Venv ready. Activate with: source src/venv/bin/activate"
