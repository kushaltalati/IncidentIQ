"""
IncidentIQ Grader Runner — evaluates agent performance across all scenarios.

Runs 4 agent strategies:
  1. Perfect Agent:    knows ground truth, follows correct runbook
  2. Heuristic Agent:  reads logs/metrics, reasons about root cause (simulates LLM)
  3. Naive Agent:      always restarts without investigation
  4. Random Agent:     picks actions at random

Reports per-scenario and aggregate scores.
"""

import os
import random
import re
import sys
import time

from incidentiq_env.server.dataset import INCIDENT_SCENARIOS
from incidentiq_env.server.incidentiq_environment import IncidentIQEnvironment
from incidentiq_env.server.runbooks import REMEDIATION_ACTIONS, get_runbook

DIFFICULTY_TO_TASK = {
    "easy": "alert_triage",
    "medium": "runbook_execution",
    "hard": "full_incident_response",
}


def run_perfect_agent(env, scenario):
    """Agent with full knowledge — follows the exact correct runbook."""
    task = DIFFICULTY_TO_TASK[scenario["difficulty"]]
    env.reset(task_mode=task, scenario_id=scenario["id"])

    svc = scenario["alert"]["service"]
    rc = scenario["root_cause"]
    sev = scenario["severity"]

    # For alert_triage, just classify — that ends the episode
    if task == "alert_triage":
        env._handle_tool_call("classify_root_cause", root_cause=rc, severity=sev)
        return _get_last_result(env)

    runbook = scenario.get("correct_runbook", get_runbook(rc))

    for step in runbook:
        if env._done:
            break
        if step == "get_service_status":
            env._handle_tool_call("get_service_status", service_name=svc)
        elif step == "get_recent_logs":
            env._handle_tool_call("get_recent_logs", service_name=svc)
        elif step == "get_metrics":
            env._handle_tool_call("get_metrics", service_name=svc, metric="memory_mb", window_minutes=60)
        elif step == "scale_service":
            env._handle_tool_call("scale_service", service_name=svc, replicas=4)
        elif step == "restart_service":
            env._handle_tool_call("restart_service", service_name=svc)
        elif step == "rollback_deploy":
            env._handle_tool_call("rollback_deploy", service_name=svc, version="previous")
        elif step == "update_config":
            env._handle_tool_call("update_config", service_name=svc, config_key="fix", config_value="applied")
        elif step == "flush_cache":
            env._handle_tool_call("flush_cache", service_name=svc)
        elif step == "notify_stakeholders":
            env._handle_tool_call("notify_stakeholders", message=f"Resolved {rc} on {svc}", severity=sev)
        elif step == "write_post_mortem":
            env._handle_tool_call(
                "write_post_mortem",
                summary=f"Incident affected {svc}. Root cause was caused by {rc}. "
                f"Fixed by following runbook. To prevent future issues, improve monitoring.",
            )
        elif step == "close_incident":
            pass  # Handled below

    # Classify before closing
    if not env._classified_root_cause:
        env._handle_tool_call("classify_root_cause", root_cause=rc, severity=sev)

    # Write post-mortem for hard scenarios if not done
    if task == "full_incident_response" and not env._post_mortem:
        env._handle_tool_call(
            "write_post_mortem",
            summary=f"Incident affected {svc}. Root cause was caused by {rc}. "
            f"Fixed by following runbook. To prevent future issues, improve monitoring.",
        )

    if not env._done:
        result = env._handle_tool_call("close_incident")
        return result
    return _get_last_result(env)


def run_heuristic_agent(env, scenario):
    """
    Agent that reads logs and metrics to infer root cause.
    Simulates what a good LLM would do — pattern matching on log keywords.
    """
    task = DIFFICULTY_TO_TASK[scenario["difficulty"]]
    env.reset(task_mode=task, scenario_id=scenario["id"])

    svc = scenario["alert"]["service"]
    sev = scenario["severity"]

    # Step 1: Get instructions and status
    env._handle_tool_call("get_service_status", service_name=svc)

    # Step 2: Read logs
    logs_result = env._handle_tool_call("get_recent_logs", service_name=svc)
    log_text = " ".join(logs_result.get("log_lines", []))

    # Step 3: Get metrics
    env._handle_tool_call("get_metrics", service_name=svc, metric="memory_mb", window_minutes=60)

    # Step 4: Heuristic root cause inference from logs
    inferred_rc = _infer_root_cause(log_text, scenario["alert"]["metric_snapshot"])

    # Step 5: Classify
    env._handle_tool_call("classify_root_cause", root_cause=inferred_rc, severity=sev)

    if task == "alert_triage":
        # Already done for triage
        return _get_last_result(env)

    # Step 6: Remediate based on inferred cause
    if inferred_rc in ("OOM", "MEMORY_LEAK", "RATE_LIMIT_HIT"):
        env._handle_tool_call("scale_service", service_name=svc, replicas=4)
    elif inferred_rc == "DEPLOY_REGRESSION":
        env._handle_tool_call("rollback_deploy", service_name=svc, version="previous")
    elif inferred_rc in ("CONFIG_ERROR", "CERTIFICATE_EXPIRED"):
        env._handle_tool_call("update_config", service_name=svc, config_key="fix", config_value="applied")
    elif inferred_rc == "DISK_FULL":
        env._handle_tool_call("flush_cache", service_name=svc)
    else:
        env._handle_tool_call("restart_service", service_name=svc)

    # Step 7: Verify
    env._handle_tool_call("get_service_status", service_name=svc)

    # Step 8: Notify
    env._handle_tool_call("notify_stakeholders", message=f"Resolved {inferred_rc} on {svc}", severity=sev)

    # Step 9: Post-mortem (hard only)
    if task == "full_incident_response":
        env._handle_tool_call(
            "write_post_mortem",
            summary=f"Incident affected {svc}. Root cause was caused by {inferred_rc}. "
            f"Fixed by remediation. To prevent future issues, add monitoring alerts.",
        )

    # Step 10: Close
    result = env._handle_tool_call("close_incident")
    return result


def _infer_root_cause(log_text: str, metrics: dict) -> str:
    """Heuristic root cause detection from logs and metrics."""
    log_lower = log_text.lower()

    # Pattern matching (what an LLM would do)
    if "oomkilled" in log_lower or "outofmemoryerror" in log_lower or "heap space" in log_lower:
        if "gradual" in log_lower or "steadily" in log_lower or "growing" in log_lower:
            return "MEMORY_LEAK"
        return "OOM"
    if "certificate" in log_lower and ("expired" in log_lower or "tls" in log_lower):
        return "CERTIFICATE_EXPIRED"
    if "no space left" in log_lower or "disk usage" in log_lower:
        return "DISK_FULL"
    if "keyerror" in log_lower or "missing" in log_lower and ("env" in log_lower or "config" in log_lower):
        return "CONFIG_ERROR"
    if "401" in log_lower and ("api key" in log_lower or "unauthorized" in log_lower):
        return "CONFIG_ERROR"
    if "deploy" in log_lower and ("nullpointer" in log_lower or "regression" in log_lower):
        return "DEPLOY_REGRESSION"
    if "connection refused" in log_lower or "network" in log_lower and "link down" in log_lower:
        return "NETWORK_PARTITION"
    if "503" in log_lower and "upstream" in log_lower:
        return "DEPENDENCY_FAILURE"
    if "429" in log_lower or "rate limit" in log_lower:
        return "RATE_LIMIT_HIT"
    if "querytimeout" in log_lower or "connection pool" in log_lower and "exhausted" in log_lower:
        return "DB_TIMEOUT"
    if "leak" in log_lower or ("memory" in log_lower and "growing" in log_lower):
        return "MEMORY_LEAK"
    if "crash" in log_lower and "oom" in log_lower:
        return "OOM"
    if "mismatch" in log_lower or "data integrity" in log_lower:
        return "DEPLOY_REGRESSION"

    # Fallback: check metrics
    if metrics.get("memory_mb", 0) > 3000:
        return "OOM"
    if metrics.get("latency_p99", 0) > 10000:
        return "DB_TIMEOUT"

    return "CONFIG_ERROR"  # Default guess


def run_naive_agent(env, scenario):
    """Naive agent — just restarts the service without any investigation."""
    task = DIFFICULTY_TO_TASK[scenario["difficulty"]]
    env.reset(task_mode=task, scenario_id=scenario["id"])

    svc = scenario["alert"]["service"]

    # Skip investigation, just restart
    env._handle_tool_call("restart_service", service_name=svc)

    # Classify with a guess
    env._handle_tool_call("classify_root_cause", root_cause="OOM", severity="P1")

    if task != "alert_triage":
        env._handle_tool_call("close_incident")
        return _get_last_result(env)
    return _get_last_result(env)


def run_random_agent(env, scenario):
    """Random agent — picks actions randomly."""
    task = DIFFICULTY_TO_TASK[scenario["difficulty"]]
    env.reset(task_mode=task, scenario_id=scenario["id"])

    svc = scenario["alert"]["service"]
    services = list(scenario["initial_state"].keys())
    root_causes = ["OOM", "DB_TIMEOUT", "DEPLOY_REGRESSION", "NETWORK_PARTITION",
                   "CONFIG_ERROR", "DISK_FULL", "DEPENDENCY_FAILURE",
                   "CERTIFICATE_EXPIRED", "RATE_LIMIT_HIT", "MEMORY_LEAK"]
    rng = random.Random(42)

    max_steps = {"alert_triage": 4, "runbook_execution": 9, "full_incident_response": 14}[task]

    for _ in range(max_steps):
        if env._done:
            break
        action = rng.choice([
            "get_service_status", "get_recent_logs", "get_metrics",
            "restart_service", "scale_service", "classify_root_cause",
        ])
        target_svc = rng.choice(services)
        if action == "get_service_status":
            env._handle_tool_call("get_service_status", service_name=target_svc)
        elif action == "get_recent_logs":
            env._handle_tool_call("get_recent_logs", service_name=target_svc)
        elif action == "get_metrics":
            env._handle_tool_call("get_metrics", service_name=target_svc, metric="cpu_pct", window_minutes=30)
        elif action == "restart_service":
            env._handle_tool_call("restart_service", service_name=target_svc)
        elif action == "scale_service":
            env._handle_tool_call("scale_service", service_name=target_svc, replicas=rng.randint(1, 5))
        elif action == "classify_root_cause":
            env._handle_tool_call("classify_root_cause", root_cause=rng.choice(root_causes), severity=rng.choice(["P1", "P2", "P3"]))

    if not env._done:
        env._handle_tool_call("close_incident")
    return _get_last_result(env)


def _get_last_result(env):
    """Compute scores from environment state when close_incident wasn't called."""
    from incidentiq_env.server.graders import (
        compute_episode_score,
        grade_post_mortem,
        grade_root_cause,
        grade_runbook_coverage,
        grade_severity,
        grade_system_state,
    )

    rc_score = grade_root_cause(env._classified_root_cause, env._scenario["root_cause"])
    sev_score = grade_severity(env._classified_severity, env._scenario["severity"])
    executed = [h["action_type"] for h in env._tool_history]
    correct = env._scenario.get("correct_runbook", get_runbook(env._scenario["root_cause"]))
    rb_score = grade_runbook_coverage(executed, correct)

    final_state = env._simulator.get_final_state() if env._simulator else {}
    affected = env._simulator.get_affected_service() if env._simulator else ""
    target = env._scenario.get("resolved_state", {}).get(affected, {})
    st_score = grade_system_state(final_state, target)
    pm_score = grade_post_mortem(env._post_mortem)

    budget_pct = env._step_number / env._max_steps if env._max_steps > 0 else 1.0
    if budget_pct <= 0.50:
        eff = 0.20
    elif budget_pct <= 0.75:
        eff = 0.10
    else:
        eff = max(-0.10, -0.10 * (budget_pct - 0.80) / 0.20) if budget_pct > 0.80 else 0.0

    ep_score = compute_episode_score(
        rc_score, rb_score, st_score, pm_score, eff,
        task_mode=env._task_mode, severity_score=sev_score,
    )

    return {
        "episode_score": ep_score,
        "cumulative_reward": env._cumulative_reward,
        "scores": {
            "root_cause_accuracy": round(rc_score, 2),
            "runbook_coverage": round(rb_score, 2),
            "system_state": round(st_score, 2),
            "post_mortem_quality": round(pm_score, 2),
            "efficiency_bonus": round(eff, 2),
        },
        "details": {
            "predicted_root_cause": env._classified_root_cause,
            "actual_root_cause": env._scenario["root_cause"],
            "steps_used": env._step_number,
        },
    }


def print_header(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def print_scenario_result(scenario_id, difficulty, root_cause, result, predicted_rc=None):
    score = result.get("episode_score", 0.0)
    cum_reward = result.get("cumulative_reward", env._cumulative_reward if 'env' in dir() else 0.0)
    scores = result.get("scores", {})
    details = result.get("details", {})

    rc_match = "✓" if details.get("predicted_root_cause") == details.get("actual_root_cause") else "✗"
    pred = details.get("predicted_root_cause", predicted_rc or "?")

    rc_score = scores.get("root_cause_accuracy", "?")
    rb_score = scores.get("runbook_coverage", "?")
    st_score = scores.get("system_state", "?")
    pm_score = scores.get("post_mortem_quality", "?")

    print(
        f"  {scenario_id:<8} {difficulty:<7} {root_cause:<22} "
        f"{rc_match} {pred:<22} "
        f"RC={rc_score:<5} RB={rb_score:<5} ST={st_score:<5} PM={pm_score:<5} "
        f"Score={score:.4f}"
    )


def run_agent_on_all_scenarios(agent_fn, agent_name):
    print_header(f"{agent_name} Agent")
    print(
        f"  {'ID':<8} {'Diff':<7} {'Actual RC':<22} "
        f"{'?'} {'Predicted RC':<22} "
        f"{'RC':<6} {'RB':<6} {'ST':<6} {'PM':<6} "
        f"Score"
    )
    print(f"  {'-'*110}")

    scores_by_difficulty = {"easy": [], "medium": [], "hard": []}
    all_scores = []
    rc_correct = 0

    for scenario in INCIDENT_SCENARIOS:
        env = IncidentIQEnvironment()
        result = agent_fn(env, scenario)

        score = result.get("episode_score", 0.0)
        details = result.get("details", {})
        pred = details.get("predicted_root_cause", env._classified_root_cause)
        actual = scenario["root_cause"]

        if pred and pred.upper() == actual.upper():
            rc_correct += 1

        scores_by_difficulty[scenario["difficulty"]].append(score)
        all_scores.append(score)

        print_scenario_result(
            scenario["id"],
            scenario["difficulty"],
            scenario["root_cause"],
            result,
            predicted_rc=pred,
        )

    print(f"  {'-'*110}")

    for diff in ["easy", "medium", "hard"]:
        s = scores_by_difficulty[diff]
        avg = sum(s) / len(s) if s else 0
        print(f"  {diff.upper():<15} avg_score={avg:.4f}  ({len(s)} scenarios)")

    overall = sum(all_scores) / len(all_scores) if all_scores else 0
    print(f"\n  OVERALL         avg_score={overall:.4f}  "
          f"root_cause_accuracy={rc_correct}/{len(INCIDENT_SCENARIOS)} "
          f"({100*rc_correct/len(INCIDENT_SCENARIOS):.0f}%)")

    return overall, rc_correct


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  IncidentIQ Environment — Agent Performance Evaluation")
    print("  15 scenarios × 4 agents = 60 episodes")
    print("=" * 70)

    start = time.time()
    results = {}

    for agent_fn, name in [
        (run_perfect_agent, "Perfect (Oracle)"),
        (run_heuristic_agent, "Heuristic (Simulated LLM)"),
        (run_naive_agent, "Naive (Restart-Only)"),
        (run_random_agent, "Random"),
    ]:
        score, rc = run_agent_on_all_scenarios(agent_fn, name)
        results[name] = {"score": score, "rc_correct": rc}

    elapsed = time.time() - start

    print_header("SUMMARY — Agent Comparison")
    print(f"  {'Agent':<30} {'Avg Score':>10} {'RC Accuracy':>15}")
    print(f"  {'-'*55}")
    for name, r in results.items():
        print(
            f"  {name:<30} {r['score']:>10.4f} "
            f"{r['rc_correct']:>6}/15 ({100*r['rc_correct']/15:.0f}%)"
        )

    print(f"\n  Total time: {elapsed:.1f}s for {4*15} episodes")
    print()
