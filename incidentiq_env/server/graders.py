"""
Grading functions for IncidentIQ environment.

Four graders evaluate different aspects of incident response:
1. Root Cause Accuracy (0.0 -> 1.0)
2. Runbook Coverage (0.0 -> 1.0)
3. System State Hash (0.0 -> 1.0)
4. Post-Mortem Quality (0.0 -> 1.0)
"""

from typing import Any

# Clamp score to strictly (0, 1) — validators reject exact 0.0 and 1.0.
_EPSILON = 0.001

def _clamp(score: float) -> float:
    return max(_EPSILON, min(1.0 - _EPSILON, score))

# Related root cause categories for partial credit.
RELATED_CATEGORIES: dict[str, list[str]] = {
    "OOM": ["MEMORY_LEAK"],
    "MEMORY_LEAK": ["OOM"],
    "DB_TIMEOUT": ["DEPENDENCY_FAILURE"],
    "DEPENDENCY_FAILURE": ["NETWORK_PARTITION", "DB_TIMEOUT"],
    "NETWORK_PARTITION": ["DEPENDENCY_FAILURE"],
}

# Required sections and keywords for post-mortem quality grading.
POSTMORTEM_SECTIONS: dict[str, list[str]] = {
    "what_happened": [
        "incident", "alert", "affected", "down", "degraded",
        "outage", "issue", "problem", "error",
    ],
    "root_cause": [
        "caused by", "root cause", "because", "due to",
        "reason", "source", "origin", "triggered by",
    ],
    "fix_applied": [
        "fixed", "resolved", "restarted", "scaled", "rolled back",
        "remediated", "mitigated", "restored", "updated", "flushed",
    ],
    "prevention": [
        "prevent", "future", "monitor", "alert", "threshold",
        "improve", "action item", "follow-up", "recommendation",
    ],
}

# Task-mode-specific scoring weights.
# alert_triage:            diagnosis is everything (no runbook/state/postmortem)
# runbook_execution:       runbook + state dominate (root cause is given)
# full_incident_response:  balanced across all dimensions
TASK_WEIGHTS: dict[str, dict[str, float]] = {
    "alert_triage": {
        "root_cause": 0.60,
        "severity": 0.25,
        "runbook": 0.00,
        "state": 0.00,
        "postmortem": 0.00,
        "efficiency": 0.15,
    },
    "runbook_execution": {
        "root_cause": 0.10,
        "severity": 0.05,
        "runbook": 0.40,
        "state": 0.30,
        "postmortem": 0.00,
        "efficiency": 0.15,
    },
    "full_incident_response": {
        "root_cause": 0.25,
        "severity": 0.05,
        "runbook": 0.25,
        "state": 0.20,
        "postmortem": 0.15,
        "efficiency": 0.10,
    },
}


def grade_root_cause(predicted: str | None, ground_truth: str) -> float:
    """
    Grade root cause classification accuracy.

    Returns:
        1.0 for exact match, 0.5 for related category, 0.0 for wrong.
    """
    if not predicted:
        return _clamp(0.0)
    predicted = predicted.upper().strip()
    ground_truth = ground_truth.upper().strip()

    if predicted == ground_truth:
        return _clamp(1.0)

    if predicted in RELATED_CATEGORIES.get(ground_truth, []):
        return _clamp(0.5)

    return _clamp(0.0)


def grade_severity(predicted: str | None, ground_truth: str) -> float:
    """
    Grade severity classification accuracy.

    Returns:
        ~1.0 for exact match, 0.5 for off-by-one, ~0.0 for wrong.
    """
    if not predicted:
        return _clamp(0.0)

    severity_order = {"P1": 1, "P2": 2, "P3": 3}
    pred_val = severity_order.get(predicted.upper().strip(), 0)
    truth_val = severity_order.get(ground_truth.upper().strip(), 0)

    if pred_val == 0 or truth_val == 0:
        return _clamp(0.0)
    if pred_val == truth_val:
        return _clamp(1.0)
    if abs(pred_val - truth_val) == 1:
        return _clamp(0.5)
    return _clamp(0.0)


def _grade_step_order(executed: list[str], correct: list[str]) -> float:
    """Grade how well the executed steps follow the correct order.

    Uses a greedy matching approach that handles repeated steps correctly
    by consuming matched positions from the correct runbook.
    """
    if not executed or not correct:
        return _clamp(0.0)

    # Build list of indices by greedily matching executed steps to correct steps
    remaining = list(range(len(correct)))
    matched_indices = []
    for step in executed:
        for i, ri in enumerate(remaining):
            if correct[ri] == step:
                matched_indices.append(ri)
                remaining.pop(i)
                break

    if len(matched_indices) <= 1:
        return _clamp(1.0) if matched_indices else _clamp(0.0)

    # Check if matched indices are monotonically increasing (correct order)
    in_order = sum(
        1 for i in range(1, len(matched_indices))
        if matched_indices[i] > matched_indices[i - 1]
    )

    return _clamp(in_order / (len(matched_indices) - 1))


def grade_runbook_coverage(
    executed_steps: list[str], correct_steps: list[str]
) -> float:
    """
    Grade runbook step coverage and order.

    Handles repeated steps correctly — e.g. get_service_status appearing
    twice in the runbook (before and after remediation) counts as 2 required steps.

    Returns:
        Weighted score: 80% coverage + 20% order correctness.
    """
    if not correct_steps:
        return _clamp(0.0)

    # Count-based coverage: handles repeated steps properly
    # E.g., if runbook has get_service_status x2, agent must call it x2
    from collections import Counter
    correct_counts = Counter(correct_steps)
    executed_counts = Counter(executed_steps)

    matched = 0
    total_required = len(correct_steps)
    for step, required in correct_counts.items():
        matched += min(executed_counts.get(step, 0), required)

    coverage = matched / total_required if total_required > 0 else 0.0

    order_score = _grade_step_order(executed_steps, correct_steps)

    return _clamp(min(1.0, coverage * 0.8 + order_score * 0.2))


def grade_system_state(
    final_state: dict[str, Any], target_state: dict[str, Any]
) -> float:
    """
    Grade whether the system was restored to a healthy state.

    Compares key metrics against the resolved ground truth.
    Checks status, error rate, memory, and replicas.
    """
    checks = [
        ("status", lambda a, b: 1.0 if a == b else 0.0),
        ("error_rate_pct", lambda a, b: 1.0 if a < 1.0 else 0.3 if a < 5.0 else 0.0),
        ("memory_mb", lambda a, b: 1.0 if a <= b * 1.1 else 0.5 if a <= b * 1.5 else 0.0),
        ("replicas", lambda a, b: 1.0 if a >= b else 0.5 if a >= b - 1 else 0.0),
    ]

    score = 0.0
    count = 0
    for key, fn in checks:
        if key in final_state and key in target_state:
            score += fn(final_state[key], target_state[key])
            count += 1

    if count == 0:
        return _clamp(0.0)
    return _clamp(score / count)


def grade_post_mortem(text: str | None) -> float:
    """
    Grade post-mortem quality based on required section coverage.

    Returns:
        0.25 per section found (max ~1.0).
    """
    if not text:
        return _clamp(0.0)

    score = 0.0
    text_lower = text.lower()

    for section, keywords in POSTMORTEM_SECTIONS.items():
        if any(kw.lower() in text_lower for kw in keywords):
            score += 0.25

    return _clamp(score)


def compute_episode_score(
    root_cause_score: float,
    runbook_score: float,
    state_score: float,
    postmortem_score: float,
    efficiency_bonus: float,
    task_mode: str = "full_incident_response",
    severity_score: float = 0.0,
) -> float:
    """
    Compute final episode score using task-mode-aware weighted components.

    Different task modes emphasize different aspects:
    - alert_triage: 60% root cause, 25% severity, 15% efficiency
    - runbook_execution: 40% runbook, 30% state, 15% efficiency
    - full_incident_response: balanced across all dimensions
    """
    w = TASK_WEIGHTS.get(task_mode, TASK_WEIGHTS["full_incident_response"])

    raw = (
        w["root_cause"] * root_cause_score
        + w.get("severity", 0.0) * severity_score
        + w["runbook"] * runbook_score
        + w["state"] * state_score
        + w["postmortem"] * postmortem_score
        + w["efficiency"] * max(0.0, efficiency_bonus)
    )
    return _clamp(raw)
