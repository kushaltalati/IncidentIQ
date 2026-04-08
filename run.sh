#!/usr/bin/env bash
# IncidentIQ — Quick Start
# Usage:
#   ./run.sh server     — Start the FastAPI server
#   ./run.sh test       — Run pytest
#   ./run.sh grader     — Run scripted agent grader (no API key needed)
#   ./run.sh llm        — Run real LLM grader (needs ANTHROPIC_API_KEY)

set -e
cd "$(dirname "$0")"

# ---------------------------------------------------------------------------
# Locate a usable Python ≥ 3.9
# ---------------------------------------------------------------------------
find_python() {
  for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
      # Verify it's Python 3
      if "$cmd" -c "import sys; assert sys.version_info >= (3, 9)" 2>/dev/null; then
        echo "$cmd"
        return
      fi
    fi
  done
  echo ""
}

PYTHON=$(find_python)
if [ -z "$PYTHON" ]; then
  echo "Error: Python 3.9+ is required but not found."
  echo "Install it via https://www.python.org/downloads/ or your package manager."
  exit 1
fi

# ---------------------------------------------------------------------------
# Auto-create virtual environment and install deps if needed
# ---------------------------------------------------------------------------
if [ ! -f .venv/bin/activate ] && [ ! -f .venv/Scripts/activate ]; then
  echo "Creating virtual environment (.venv) ..."
  "$PYTHON" -m venv .venv
fi

# Activate venv (works on macOS/Linux and Git Bash on Windows)
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
elif [ -f .venv/Scripts/activate ]; then
  source .venv/Scripts/activate
fi

# Install dependencies if not already installed
if ! python -c "import fastapi, uvicorn, anthropic" 2>/dev/null; then
  echo "Installing dependencies ..."
  pip install --quiet -r requirements.txt
fi

export PYTHONPATH=".:$PYTHONPATH"

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
case "${1:-help}" in
  server)
    echo "Starting IncidentIQ server on http://localhost:7860"
    python -m uvicorn incidentiq_env.server.app:app --host 0.0.0.0 --port 7860
    ;;
  test)
    python -m pytest test_incidentiq_environment.py -v --tb=short
    ;;
  grader)
    python incidentiq_env/run_grader.py
    ;;
  llm)
    if [ -z "$ANTHROPIC_API_KEY" ]; then
      echo "Error: Set ANTHROPIC_API_KEY first"
      echo "  export ANTHROPIC_API_KEY=sk-ant-..."
      exit 1
    fi
    python incidentiq_env/run_llm_grader.py
    ;;
  *)
    echo "IncidentIQ — Autonomous SRE Incident Response Environment"
    echo ""
    echo "Setup:  ./run.sh server  (auto-installs on first run)"
    echo ""
    echo "Usage:"
    echo "  ./run.sh server   — Start FastAPI server"
    echo "  ./run.sh test     — Run tests (82 tests)"
    echo "  ./run.sh grader   — Run scripted agent evaluation"
    echo "  ./run.sh llm      — Run Claude LLM evaluation"
    ;;
esac
