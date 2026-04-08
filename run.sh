#!/bin/bash
# IncidentIQ — Quick Start
# Usage:
#   ./run.sh server     — Start the FastAPI server
#   ./run.sh test       — Run pytest
#   ./run.sh grader     — Run scripted agent grader (no API key needed)
#   ./run.sh llm        — Run real LLM grader (needs ANTHROPIC_API_KEY)

set -e
cd "$(dirname "$0")"
export PYTHONPATH=".:$PYTHONPATH"

# Activate the project venv if it exists
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
fi

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
    echo "Setup:  pip install -r requirements.txt"
    echo ""
    echo "Usage:"
    echo "  ./run.sh server   — Start FastAPI server"
    echo "  ./run.sh test     — Run tests (82 tests)"
    echo "  ./run.sh grader   — Run scripted agent evaluation"
    echo "  ./run.sh llm      — Run Claude LLM evaluation"
    ;;
esac
