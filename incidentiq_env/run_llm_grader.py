"""
IncidentIQ — Real LLM Agent Evaluation.

Runs Claude against all 15 scenarios across 3 task modes,
measuring how well a real LLM performs as an on-call SRE.
"""

import json
import os
import re
import sys
import time


from anthropic import Anthropic

from incidentiq_env.server.dataset import INCIDENT_SCENARIOS
from incidentiq_env.server.incidentiq_environment import IncidentIQEnvironment

DIFFICULTY_TO_TASK = {
    "easy": "alert_triage",
    "medium": "runbook_execution",
    "hard": "full_incident_response",
}

MODEL = os.environ.get("MODEL_NAME", "claude-sonnet-4-20250514")

client = Anthropic()

SYSTEM_PROMPT = """You are an expert SRE. You receive a production incident alert and must diagnose and fix it.

Respond with ONLY a JSON object each turn. No other text.

WORKFLOW — follow IN ORDER, one tool per turn:

1. {"tool": "get_instructions", "args": {}}
   Read the alert carefully. The log_tail and metric_snapshot contain KEY diagnostic clues.

2. {"tool": "get_recent_logs", "args": {"service_name": "<affected_service>"}}
   CRITICAL: The logs contain the root cause signal. Look for keywords like:
   - OOMKilled, OutOfMemoryError, heap → OOM
   - QueryTimeout, connection pool exhausted → DB_TIMEOUT
   - NullPointer after deploy, error spike post-deploy → DEPLOY_REGRESSION
   - Connection refused, link down → NETWORK_PARTITION
   - KeyError, missing env var, config → CONFIG_ERROR
   - no space left on device → DISK_FULL
   - HTTP 503 from upstream → DEPENDENCY_FAILURE
   - certificate expired, TLS handshake → CERTIFICATE_EXPIRED
   - HTTP 429, rate limit → RATE_LIMIT_HIT
   - memory growing steadily, leak detected → MEMORY_LEAK

3. {"tool": "classify_root_cause", "args": {"root_cause": "<CATEGORY>", "severity": "<P1|P2|P3>"}}
   Pick ONE: OOM, DB_TIMEOUT, DEPLOY_REGRESSION, NETWORK_PARTITION, CONFIG_ERROR, DISK_FULL, DEPENDENCY_FAILURE, CERTIFICATE_EXPIRED, RATE_LIMIT_HIT, MEMORY_LEAK

4. Apply the correct fix:
   - OOM/MEMORY_LEAK → {"tool": "scale_service", "args": {"service_name": "<name>", "replicas": 4}}
   - DB_TIMEOUT/NETWORK_PARTITION/DEPENDENCY_FAILURE → {"tool": "restart_service", "args": {"service_name": "<name>"}}
   - DEPLOY_REGRESSION → {"tool": "rollback_deploy", "args": {"service_name": "<name>", "version": "previous"}}
   - CONFIG_ERROR/CERTIFICATE_EXPIRED → {"tool": "update_config", "args": {"service_name": "<name>", "config_key": "fix", "config_value": "applied"}}
   - DISK_FULL/RATE_LIMIT_HIT → {"tool": "flush_cache", "args": {"service_name": "<name>"}}

5. {"tool": "get_service_status", "args": {"service_name": "<name>"}}
6. {"tool": "notify_stakeholders", "args": {"message": "<what happened and fix>", "severity": "<P1|P2|P3>"}}
7. (hard tasks) {"tool": "write_post_mortem", "args": {"summary": "Incident affected <service>. Root cause was caused by <X>. Fixed by <action>. To prevent future issues, improve monitoring."}}
8. {"tool": "close_incident", "args": {}}

RULES:
- NEVER call the same tool twice in a row.
- The log_tail in get_instructions ALREADY has diagnostic clues. Use them.
- After reading logs, IMMEDIATELY classify. Do not investigate further."""


def parse_response(raw: str) -> dict:
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        raw = m.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[^{}]*\}", raw)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {"tool": "get_instructions", "args": {}}


def run_llm_on_scenario(scenario):
    """Run Claude on a single scenario."""
    task = DIFFICULTY_TO_TASK[scenario["difficulty"]]
    env = IncidentIQEnvironment()
    env.reset(task_mode=task, scenario_id=scenario["id"])

    history = []
    steps = []
    max_turns = {"alert_triage": 5, "runbook_execution": 10, "full_incident_response": 14}[task]

    for turn in range(max_turns):
        if env._done:
            break

        # Call LLM
        resp = client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=history or [{"role": "user", "content": "Start the incident response. Call get_instructions first."}],
        )
        raw = resp.content[0].text
        parsed = parse_response(raw)
        tool_name = parsed.get("tool", "get_instructions")
        tool_args = parsed.get("args", {})

        # Execute
        try:
            result = env._handle_tool_call(tool_name, **tool_args)
        except Exception as e:
            result = {"error": str(e)[:100]}

        reward = result.get("reward", 0.0)
        done = result.get("done", False)

        steps.append({
            "step": turn + 1,
            "action": tool_name,
            "reward": reward,
            "done": done,
        })

        # Update history with phase-aware nudge
        if not history:
            history.append({"role": "user", "content": "Start. Call get_instructions first. Respond with ONLY JSON."})
        history.append({"role": "assistant", "content": raw})

        result_str = json.dumps(result, default=str)
        steps_remaining = result.get("steps_remaining", max_turns - turn - 1)

        # Phase-aware nudge — timing depends on task mode step budget
        nudge = ""
        classify_threshold = 2 if task == "alert_triage" else 3
        if not env._classified_root_cause and turn >= classify_threshold:
            nudge = "\n\nIMPORTANT: You have investigated enough. NOW call classify_root_cause. Look at the log lines you've seen — they contain the answer."
        elif env._classified_root_cause and not env._remediation_applied:
            nudge = "\n\nIMPORTANT: You classified the root cause. NOW call a remediation tool (restart_service, scale_service, rollback_deploy, update_config, or flush_cache)."
        elif env._remediation_applied and not env._verified_after_remediation:
            nudge = "\n\nIMPORTANT: Remediation applied. NOW call get_service_status to verify the fix."
        elif env._verified_after_remediation and not env._notified:
            nudge = "\n\nIMPORTANT: Fix verified. NOW call notify_stakeholders."
        elif env._notified and task == "full_incident_response" and not env._post_mortem:
            nudge = "\n\nIMPORTANT: NOW call write_post_mortem with a summary."
        elif env._notified and (task != "full_incident_response" or env._post_mortem):
            nudge = "\n\nIMPORTANT: NOW call close_incident to finish."

        history.append({"role": "user", "content": f"Tool result ({steps_remaining} steps remaining):\n{result_str}{nudge}"})

    # Close if not done
    if not env._done:
        result = env._handle_tool_call("close_incident")
        steps.append({"step": len(steps) + 1, "action": "close_incident", "reward": result.get("reward", 0), "done": True})

    # Compute final scores
    from incidentiq_env.server.graders import (
        compute_episode_score, grade_post_mortem, grade_root_cause,
        grade_runbook_coverage, grade_severity, grade_system_state,
    )
    from incidentiq_env.server.runbooks import get_runbook

    rc_score = grade_root_cause(env._classified_root_cause, scenario["root_cause"])
    sev_score = grade_severity(env._classified_severity, scenario["severity"])
    executed = [h["action_type"] for h in env._tool_history]
    correct = scenario.get("correct_runbook", get_runbook(scenario["root_cause"]))
    rb_score = grade_runbook_coverage(executed, correct)
    final_state = env._simulator.get_final_state()
    affected = env._simulator.get_affected_service()
    target = scenario.get("resolved_state", {}).get(affected, {})
    st_score = grade_system_state(final_state, target)
    pm_score = grade_post_mortem(env._post_mortem)

    budget_pct = env._step_number / env._max_steps
    eff = 0.20 if budget_pct <= 0.5 else 0.10 if budget_pct <= 0.75 else 0.0
    ep_score = compute_episode_score(rc_score, rb_score, st_score, pm_score, eff,
                                      task_mode=task, severity_score=sev_score)

    return {
        "scenario_id": scenario["id"],
        "difficulty": scenario["difficulty"],
        "actual_rc": scenario["root_cause"],
        "predicted_rc": env._classified_root_cause,
        "rc_correct": (env._classified_root_cause or "").upper() == scenario["root_cause"].upper(),
        "scores": {
            "root_cause": round(rc_score, 2),
            "severity": round(sev_score, 2),
            "runbook": round(rb_score, 2),
            "system_state": round(st_score, 2),
            "postmortem": round(pm_score, 2),
            "efficiency": round(eff, 2),
        },
        "episode_score": round(ep_score, 4),
        "steps": steps,
        "cumulative_reward": round(env._cumulative_reward, 2),
        "resolved": env._simulator.is_resolved,
    }


if __name__ == "__main__":
    print(f"\n{'='*75}")
    print(f"  IncidentIQ — Real LLM Evaluation ({MODEL})")
    print(f"  15 scenarios across easy/medium/hard")
    print(f"{'='*75}\n")

    all_results = []
    scores_by_diff = {"easy": [], "medium": [], "hard": []}
    rc_correct = 0
    start = time.time()

    for i, scenario in enumerate(INCIDENT_SCENARIOS):
        task = DIFFICULTY_TO_TASK[scenario["difficulty"]]
        print(f"  [{i+1:2d}/15] {scenario['id']} ({scenario['difficulty']}/{task}) "
              f"RC={scenario['root_cause']:<22}", end="", flush=True)

        t0 = time.time()
        result = run_llm_on_scenario(scenario)
        dt = time.time() - t0

        all_results.append(result)
        scores_by_diff[scenario["difficulty"]].append(result["episode_score"])
        if result["rc_correct"]:
            rc_correct += 1

        rc_mark = "✓" if result["rc_correct"] else "✗"
        pred = result["predicted_rc"] or "None"
        print(f"  {rc_mark} {pred:<22} score={result['episode_score']:.4f}  "
              f"({len(result['steps'])} steps, {dt:.1f}s)")

        # Print step details
        for s in result["steps"]:
            print(f"       step {s['step']:2d}: {s['action']:<25} reward={s['reward']:+.2f}")

    elapsed = time.time() - start

    print(f"\n{'='*75}")
    print(f"  RESULTS — {MODEL}")
    print(f"{'='*75}")
    print(f"\n  {'Difficulty':<15} {'Avg Score':>10} {'Scenarios':>10}")
    print(f"  {'-'*35}")
    for diff in ["easy", "medium", "hard"]:
        s = scores_by_diff[diff]
        avg = sum(s) / len(s) if s else 0
        print(f"  {diff.upper():<15} {avg:>10.4f} {len(s):>10}")

    all_scores = [r["episode_score"] for r in all_results]
    overall = sum(all_scores) / len(all_scores)
    print(f"\n  {'OVERALL':<15} {overall:>10.4f} {len(all_scores):>10}")
    print(f"\n  Root Cause Accuracy: {rc_correct}/15 ({100*rc_correct//15}%)")
    print(f"  System Resolved:     {sum(1 for r in all_results if r['resolved'])}/15")
    print(f"  Time:                {elapsed:.1f}s total ({elapsed/15:.1f}s avg per scenario)")
    print()
