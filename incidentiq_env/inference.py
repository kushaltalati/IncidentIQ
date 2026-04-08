"""
Baseline inference script for IncidentIQ Environment.

Uses an LLM to act as an on-call SRE agent, interacting with the
environment via MCP tool calls to triage, diagnose, and remediate incidents.

Emits structured stdout logs in [START], [STEP], [END] format.
"""

import json
import os
import re
import sys
import time

from openai import OpenAI

API_BASE_URL = os.environ.get("API_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "gpt-4.1-mini")
HF_TOKEN = os.environ.get("HF_TOKEN")
ENV_URL = os.environ.get("ENV_URL", "http://localhost:8000")

if HF_TOKEN is None:
    raise ValueError("HF_TOKEN environment variable is required")

llm = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)

SYSTEM_PROMPT = """You are an expert SRE (Site Reliability Engineer) responding to a production incident.

You interact with the environment by calling tools. Based on the current state, decide which tool to call next.

WORKFLOW:
1. Call get_instructions to understand the task and see the alert
2. INVESTIGATE: Use get_service_status, get_recent_logs, get_metrics to gather information
3. DIAGNOSE: Use classify_root_cause to identify the problem
4. REMEDIATE: Use the appropriate fix (scale_service, restart_service, rollback_deploy, update_config, flush_cache)
5. VERIFY: Call get_service_status after remediation to confirm the fix
6. COMMUNICATE: Use notify_stakeholders to inform the team
7. RESOLVE: For hard tasks, use write_post_mortem then close_incident

Available root causes: OOM, DB_TIMEOUT, DEPLOY_REGRESSION, NETWORK_PARTITION, CONFIG_ERROR, DISK_FULL, DEPENDENCY_FAILURE, CERTIFICATE_EXPIRED, RATE_LIMIT_HIT, MEMORY_LEAK

Respond with ONLY a JSON object specifying the tool call:
{"tool": "<tool_name>", "args": {<arguments>}}

Examples:
{"tool": "get_instructions", "args": {}}
{"tool": "get_service_status", "args": {"service_name": "payment-service"}}
{"tool": "classify_root_cause", "args": {"root_cause": "OOM", "severity": "P1"}}
{"tool": "scale_service", "args": {"service_name": "payment-service", "replicas": 4}}
{"tool": "close_incident", "args": {}}

Rules:
- Investigate BEFORE remediating
- Verify service health AFTER remediating
- Always close_incident at the end
- ONLY respond with valid JSON, no other text"""


TASKS = ["alert_triage", "runbook_execution", "full_incident_response"]


def parse_llm_response(raw: str) -> dict:
    """Parse LLM response into tool call dict."""
    raw = raw.strip()
    # Try to extract JSON from markdown code blocks
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        raw = match.group(1)
    # Try direct JSON parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to find JSON object in the response
        match = re.search(r"\{[^{}]*\}", raw)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {"tool": "get_instructions", "args": {}}


def call_llm(history: list[dict]) -> str:
    """Call the LLM and return raw response text."""
    response = llm.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
        max_tokens=500,
        temperature=0.0,
    )
    return response.choices[0].message.content.strip()


def run_task(task_mode: str) -> None:
    """Run a single task through the environment."""
    from incidentiq_env import IncidentIQEnv

    history: list[dict] = []
    all_rewards: list[float] = []
    step = 0
    success = False
    last_error = "null"

    try:
        with IncidentIQEnv(base_url=ENV_URL).sync() as env:
            env.reset(task_mode=task_mode)
            print(f"[START] task={task_mode} env=incidentiq model={MODEL_NAME}")

            done = False
            while not done:
                # Get LLM decision
                raw = call_llm(history)
                history.append({"role": "assistant", "content": raw})

                # Parse the tool call
                parsed = parse_llm_response(raw)
                tool_name = parsed.get("tool", "get_instructions")
                tool_args = parsed.get("args", {})

                # Execute tool call
                try:
                    result = env.call_tool(tool_name, **tool_args)
                except Exception as e:
                    result = {"error": str(e)[:80]}

                # Extract reward and done status
                if isinstance(result, dict):
                    reward = result.get("reward", 0.0)
                    done = result.get("done", False)
                    last_error = result.get("error", "null") or "null"
                else:
                    reward = 0.0
                    done = False
                    last_error = "null"

                step += 1
                all_rewards.append(reward if isinstance(reward, (int, float)) else 0.0)

                # Log step
                print(
                    f"[STEP] step={step} action={tool_name} "
                    f"reward={reward:.2f} done={'true' if done else 'false'} "
                    f"error={last_error}"
                )

                # Add result to conversation history
                result_str = json.dumps(result, default=str) if isinstance(result, dict) else str(result)
                history.append({"role": "user", "content": f"Tool result:\n{result_str}"})

            # Check success
            cumulative = sum(all_rewards)
            success = cumulative > 0.5

    except Exception as e:
        last_error = str(e)[:80]
        print(
            f"[STEP] step={step + 1} action=null "
            f"reward=0.00 done=true error={last_error}"
        )

    finally:
        rewards_str = ",".join(f"{r:.2f}" for r in all_rewards) if all_rewards else "0.00"
        print(f"[END] success={'true' if success else 'false'} steps={step} rewards={rewards_str}")


if __name__ == "__main__":
    for task in TASKS:
        run_task(task)
