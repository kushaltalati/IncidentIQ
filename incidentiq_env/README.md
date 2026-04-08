# IncidentIQ — Autonomous SRE Incident Response Environment

## Overview
IncidentIQ is an OpenEnv-compliant RL environment that simulates production incident
response. An LLM agent acts as an on-call SRE: it receives PagerDuty-style alerts,
investigates using observability tools, diagnoses root cause, executes remediation,
and verifies resolution — just like a real engineer.

## Motivation
- 78% of engineers waste 30% of their time on operational toil ($9.4M/year per team)
- AWS launched a commercial DevOps Agent (Dec 2025) — this is a billion-dollar space
- No existing OpenEnv environment covers SRE incident response
- TheAgentCompany (NeurIPS 2025) found Admin/Ops tasks have near-0% LLM success rates

## Tasks

| Task | Difficulty | Steps | Description |
|------|-----------|-------|-------------|
| `alert_triage` | Easy | 5 | Classify root cause from alert + logs |
| `runbook_execution` | Medium | 10 | Execute remediation runbook in correct order |
| `full_incident_response` | Hard | 15 | Full pipeline: investigate, diagnose, fix, verify, post-mortem |

## Root Cause Categories

| Category | Description |
|----------|-------------|
| `OOM` | Out of memory — OOMKilled in logs |
| `DB_TIMEOUT` | Database query timeouts |
| `DEPLOY_REGRESSION` | Error spike after deployment |
| `NETWORK_PARTITION` | Connection refused across services |
| `CONFIG_ERROR` | Missing environment variables |
| `DISK_FULL` | No space left on device |
| `DEPENDENCY_FAILURE` | Upstream 503 errors |
| `CERTIFICATE_EXPIRED` | TLS handshake failures |
| `RATE_LIMIT_HIT` | 429 responses from downstream |
| `MEMORY_LEAK` | Steadily increasing memory over time |

## MCP Tools (Action Space)

### Investigation
- `get_instructions()` — Get task instructions and alert details
- `get_service_status(service_name)` — Check service health
- `get_recent_logs(service_name, lines)` — Read service logs
- `get_metrics(service_name, metric, window_minutes)` — Get time-series metrics

### Diagnosis
- `classify_root_cause(root_cause, severity)` — Classify the incident
- `recommend_action(action_recommendation)` — Suggest remediation

### Remediation
- `scale_service(service_name, replicas)` — Scale service replicas
- `restart_service(service_name)` — Restart a service
- `rollback_deploy(service_name, version)` — Rollback deployment
- `update_config(service_name, config_key, config_value)` — Update config
- `flush_cache(service_name)` — Clear service cache

### Resolution
- `notify_stakeholders(message, severity)` — Notify team
- `write_post_mortem(summary)` — Write incident post-mortem
- `close_incident()` — Close and get final scores

## Scoring

### Dense Rewards (per step)
- Investigation: +0.10 per new tool call
- Classification: +0.50 exact match, +0.20 related, -0.30 wrong
- Remediation: +0.30 correct, -0.50 destructive, -1.00 worsening
- Verification: +0.30 for checking health after fix
- Communication: +0.10 for stakeholder notification
- Post-mortem: +0.10 scaled by quality score

### Episode Score (weighted)
| Component | Weight |
|-----------|--------|
| Root cause accuracy | 30% |
| Runbook coverage | 30% |
| System state | 25% |
| Post-mortem quality | 10% |
| Efficiency bonus | 5% |

> **Note:** Post-Mortem (PM) scoring is only applied to Hard difficulty tasks, as they require multi-step runbook execution and a written post-incident analysis. Easy and Medium tasks omit PM by design.

## Setup

### Local Run
```bash
cd envs/incidentiq_env
PYTHONPATH=src:envs uv run server
```

### Run Inference
```bash
export HF_TOKEN=your_token
export MODEL_NAME=gpt-4.1-mini
PYTHONPATH=src:envs uv run python inference.py
```

### Docker
```bash
docker build -t incidentiq-env -f server/Dockerfile .
docker run -p 7860:7860 incidentiq-env
```

### Client Usage
```python
from incidentiq_env import IncidentIQEnv

with IncidentIQEnv(base_url="http://localhost:7860").sync() as env:
    env.reset(task_mode="full_incident_response")
    
    instr = env.call_tool("get_instructions")
    status = env.call_tool("get_service_status", service_name="payment-service")
    result = env.call_tool("classify_root_cause", root_cause="OOM", severity="P1")
    env.call_tool("close_incident")
```

## Project Structure
```
incidentiq_env/
├── __init__.py              # Package exports
├── client.py                # IncidentIQEnv(MCPToolClient)
├── inference.py             # Baseline LLM inference script
├── openenv.yaml             # Environment manifest
├── pyproject.toml           # Package config
├── README.md                # This file
└── server/
    ├── __init__.py
    ├── app.py               # FastAPI app via create_app()
    ├── incidentiq_environment.py  # Main MCPEnvironment
    ├── simulation.py         # ServiceSimulator state machine
    ├── dataset.py            # 15 incident scenarios
    ├── runbooks.py           # Correct step sequences
    ├── graders.py            # 4 grading functions
    └── Dockerfile            # Container build
```
