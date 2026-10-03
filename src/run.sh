#!/usr/bin/env sh
# Start the School Fee Tracker on Linux / macOS. First run creates .venv and installs packages.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3.10 -m venv .venv || python3 -m venv .venv
. .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
exec streamlit run app.py
