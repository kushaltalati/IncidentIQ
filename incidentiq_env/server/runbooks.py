"""
Runbook definitions for IncidentIQ environment.

Maps each root cause category to its correct remediation step sequence.
Also defines which remediation actions are destructive (wrong action for wrong cause).
"""

from typing import Any

# Correct runbook steps per root cause category.
# Each entry is an ordered list of action_types the agent should execute.
RUNBOOKS: dict[str, list[str]] = {
    "OOM": [
        "get_service_status",
        "get_metrics",
        "scale_service",
        "get_service_status",
        "notify_stakeholders",
        "close_incident",
    ],
    "DB_TIMEOUT": [
        "get_service_status",
        "get_recent_logs",
        "get_metrics",
        "restart_service",
        "get_service_status",
        "notify_stakeholders",
        "close_incident",
    ],
    "DEPLOY_REGRESSION": [
        "get_service_status",
        "get_recent_logs",
        "rollback_deploy",
        "get_service_status",
        "notify_stakeholders",
        "close_incident",
    ],
    "NETWORK_PARTITION": [
        "get_service_status",
        "get_recent_logs",
        "get_metrics",
        "restart_service",
        "get_service_status",
        "notify_stakeholders",
        "close_incident",
    ],
    "CONFIG_ERROR": [
        "get_service_status",
        "get_recent_logs",
        "update_config",
        "restart_service",
        "get_service_status",
        "notify_stakeholders",
        "close_incident",
    ],
    "DISK_FULL": [
        "get_service_status",
        "get_recent_logs",
        "flush_cache",
        "restart_service",
        "get_service_status",
        "notify_stakeholders",
        "close_incident",
    ],
    "DEPENDENCY_FAILURE": [
        "get_service_status",
        "get_recent_logs",
        "get_metrics",
        "flush_cache",
        "restart_service",
        "get_service_status",
        "notify_stakeholders",
        "close_incident",
    ],
    "CERTIFICATE_EXPIRED": [
        "get_service_status",
        "get_recent_logs",
        "update_config",
        "restart_service",
        "get_service_status",
        "notify_stakeholders",
        "close_incident",
    ],
    "RATE_LIMIT_HIT": [
        "get_service_status",
        "get_recent_logs",
        "get_metrics",
        "scale_service",
        "flush_cache",
        "get_service_status",
        "notify_stakeholders",
        "close_incident",
    ],
    "MEMORY_LEAK": [
        "get_service_status",
        "get_metrics",
        "get_recent_logs",
        "restart_service",
        "scale_service",
        "get_service_status",
        "notify_stakeholders",
        "close_incident",
    ],
}

# Remediation actions that are WRONG for a given root cause.
# Maps root_cause -> set of action_types that would be harmful or incorrect.
DESTRUCTIVE_ACTIONS: dict[str, set[str]] = {
    "OOM": {"rollback_deploy"},  # Rolling back won't fix memory issues
    "DB_TIMEOUT": {"rollback_deploy", "scale_service"},  # Scaling doesn't fix DB
    "DEPLOY_REGRESSION": {"scale_service", "flush_cache"},  # Scaling bad code = more bad
    "NETWORK_PARTITION": {"rollback_deploy", "flush_cache"},
    "CONFIG_ERROR": {"rollback_deploy", "scale_service"},
    "DISK_FULL": {"scale_service", "rollback_deploy"},
    "DEPENDENCY_FAILURE": {"rollback_deploy", "scale_service"},
    "CERTIFICATE_EXPIRED": {"rollback_deploy", "scale_service", "flush_cache"},
    "RATE_LIMIT_HIT": {"rollback_deploy", "restart_service"},
    "MEMORY_LEAK": {"rollback_deploy", "flush_cache"},
}

# Actions that worsen the incident (even worse than just "wrong").
# e.g., scaling DOWN during OOM = catastrophic.
WORSENING_ACTIONS: dict[str, dict[str, Any]] = {
    "OOM": {
        "scale_service": {"condition": "replicas_decreased"},
    },
    "MEMORY_LEAK": {
        "scale_service": {"condition": "replicas_decreased"},
    },
}

# Valid remediation action types (as opposed to investigation/diagnosis).
REMEDIATION_ACTIONS = {
    "scale_service",
    "restart_service",
    "rollback_deploy",
    "update_config",
    "flush_cache",
}

# Investigation action types.
INVESTIGATION_ACTIONS = {
    "get_service_status",
    "get_recent_logs",
    "get_metrics",
}

# Diagnosis action types.
DIAGNOSIS_ACTIONS = {
    "classify_root_cause",
    "recommend_action",
}

# Communication action types.
COMMUNICATION_ACTIONS = {
    "notify_stakeholders",
}

# Resolution action types.
RESOLUTION_ACTIONS = {
    "write_post_mortem",
    "close_incident",
}


def get_runbook(root_cause: str) -> list[str]:
    """Get the correct runbook for a root cause."""
    return RUNBOOKS.get(root_cause, [])


def is_destructive(root_cause: str, action_type: str) -> bool:
    """Check if an action is destructive for the given root cause."""
    return action_type in DESTRUCTIVE_ACTIONS.get(root_cause, set())


def is_correct_remediation(root_cause: str, action_type: str) -> bool:
    """Check if an action is in the correct runbook for the root cause."""
    return action_type in RUNBOOKS.get(root_cause, [])
