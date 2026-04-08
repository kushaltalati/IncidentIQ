"""
Service simulator for IncidentIQ environment.

Pure Python state machine that simulates microservice infrastructure.
No real services — just dictionaries tracking service state.
"""

import copy
import json
from typing import Any


class ServiceSimulator:
    """Simulates a microservice environment with mutable state."""

    def __init__(self, scenario: dict[str, Any]) -> None:
        self._scenario = scenario
        self._service_states: dict[str, dict[str, Any]] = copy.deepcopy(
            scenario["initial_state"]
        )
        self._resolved = False
        self._alert = scenario["alert"]
        self._root_cause = scenario["root_cause"]
        self._additional_logs = scenario.get("additional_logs", {})
        self._additional_metrics = scenario.get("additional_metrics", {})

    @property
    def is_resolved(self) -> bool:
        return self._resolved

    def get_service_status(self, service_name: str) -> dict[str, Any]:
        """Get current status of a service."""
        if service_name not in self._service_states:
            return {"error": f"Service '{service_name}' not found"}
        state = self._service_states[service_name]
        return {
            "service": service_name,
            "status": state["status"],
            "replicas": state["replicas"],
            "memory_mb": state["memory_mb"],
            "cpu_pct": state["cpu_pct"],
            "last_deploy_version": state.get("last_deploy_version", "unknown"),
            "last_deploy_time": state.get("last_deploy_time", "unknown"),
        }

    def get_recent_logs(self, service_name: str, lines: int = 20) -> dict[str, Any]:
        """Get recent logs for a service."""
        if service_name not in self._service_states:
            return {"error": f"Service '{service_name}' not found"}

        logs = []
        # Include alert log tail for the affected service
        if service_name == self._alert["service"]:
            logs.extend(self._alert["log_tail"])

        # Add additional contextual logs
        if service_name in self._additional_logs:
            logs.extend(self._additional_logs[service_name])

        # If no logs found, return generic healthy logs
        if not logs:
            logs = [
                f"INFO  {service_name} operating normally",
                f"INFO  Health check passed for {service_name}",
            ]

        return {
            "service": service_name,
            "log_lines": logs[-lines:],
            "total_lines": len(logs),
        }

    def get_metrics(
        self, service_name: str, metric: str, window_minutes: int = 30
    ) -> dict[str, Any]:
        """Get time-series metrics for a service."""
        if service_name not in self._service_states:
            return {"error": f"Service '{service_name}' not found"}

        # Return additional metrics if available
        if (
            service_name in self._additional_metrics
            and metric in self._additional_metrics[service_name]
        ):
            values = self._additional_metrics[service_name][metric]
            return {
                "service": service_name,
                "metric": metric,
                "window_minutes": window_minutes,
                "values": values,
                "current": values[-1] if values else 0.0,
                "min": min(values) if values else 0.0,
                "max": max(values) if values else 0.0,
                "trend": "increasing" if len(values) > 1 and values[-1] > values[0] else "stable",
            }

        # Fallback: generate from current state
        state = self._service_states[service_name]
        current = state.get(metric, state.get("cpu_pct", 0.0))
        if isinstance(current, (int, float)):
            return {
                "service": service_name,
                "metric": metric,
                "window_minutes": window_minutes,
                "values": [current],
                "current": current,
                "min": current,
                "max": current,
                "trend": "stable",
            }

        return {
            "service": service_name,
            "metric": metric,
            "error": f"Metric '{metric}' not available for {service_name}",
        }

    def scale_service(self, service_name: str, replicas: int) -> dict[str, Any]:
        """Scale a service to the specified number of replicas."""
        if service_name not in self._service_states:
            return {"success": False, "error": f"Service '{service_name}' not found"}
        if replicas < 1:
            return {"success": False, "error": "Replicas must be >= 1"}

        state = self._service_states[service_name]
        old_replicas = state["replicas"]
        state["replicas"] = replicas

        # Scaling up generally helps with resource issues
        if replicas > old_replicas:
            if state["status"] == "degraded":
                state["memory_mb"] = max(512, state["memory_mb"] // 2)
                state["cpu_pct"] = max(10.0, state["cpu_pct"] * 0.6)

        self._check_resolution(service_name)
        return {
            "success": True,
            "service": service_name,
            "old_replicas": old_replicas,
            "new_replicas": replicas,
            "message": f"Scaled {service_name} from {old_replicas} to {replicas} replicas",
        }

    def restart_service(self, service_name: str) -> dict[str, Any]:
        """Restart a service."""
        if service_name not in self._service_states:
            return {"success": False, "error": f"Service '{service_name}' not found"}

        state = self._service_states[service_name]
        is_affected = service_name == self.get_affected_service()

        # Restart only fully resolves root causes where restart is the correct fix
        restart_fixes = {"DB_TIMEOUT", "NETWORK_PARTITION", "MEMORY_LEAK", "DEPENDENCY_FAILURE"}
        if is_affected and self._root_cause in restart_fixes and state["status"] in ("degraded", "down"):
            state["status"] = "healthy"
            state["memory_mb"] = max(256, state["memory_mb"] // 3)
            state["cpu_pct"] = max(5.0, state["cpu_pct"] * 0.4)
        elif is_affected and state["status"] in ("degraded", "down"):
            # Restart provides temporary relief but doesn't fix the root cause
            state["cpu_pct"] = max(10.0, state["cpu_pct"] * 0.6)
            state["memory_mb"] = max(512, state["memory_mb"] * 2 // 3)
            # Status stays degraded — the problem will recur
        elif not is_affected and state["status"] in ("degraded", "down"):
            # Non-affected services can be restarted normally
            state["status"] = "healthy"

        self._check_resolution(service_name)
        return {
            "success": True,
            "service": service_name,
            "message": f"Service {service_name} restarted successfully",
        }

    def rollback_deploy(
        self, service_name: str, version: str | None = None
    ) -> dict[str, Any]:
        """Rollback a service to a previous version."""
        if service_name not in self._service_states:
            return {"success": False, "error": f"Service '{service_name}' not found"}

        state = self._service_states[service_name]
        old_version = state.get("last_deploy_version", "unknown")

        # Rollback fixes deploy-related issues
        if self._root_cause == "DEPLOY_REGRESSION":
            state["status"] = "healthy"
            state["cpu_pct"] = max(10.0, state["cpu_pct"] * 0.5)
            state["memory_mb"] = max(512, state["memory_mb"] // 2)
        state["last_deploy_version"] = version or "rollback"

        self._check_resolution(service_name)
        return {
            "success": True,
            "service": service_name,
            "old_version": old_version,
            "new_version": version or "previous",
            "message": f"Rolled back {service_name} from {old_version}",
        }

    def update_config(
        self, service_name: str, key: str, value: str
    ) -> dict[str, Any]:
        """Update a configuration key for a service."""
        if service_name not in self._service_states:
            return {"success": False, "error": f"Service '{service_name}' not found"}

        state = self._service_states[service_name]
        # Config update fixes config-related issues
        if self._root_cause in ("CONFIG_ERROR", "CERTIFICATE_EXPIRED"):
            state["status"] = "healthy"
            state["cpu_pct"] = max(10.0, state["cpu_pct"] * 0.6)

        self._check_resolution(service_name)
        return {
            "success": True,
            "service": service_name,
            "key": key,
            "value": value,
            "message": f"Updated config {key}={value} for {service_name}",
        }

    def flush_cache(self, service_name: str) -> dict[str, Any]:
        """Flush cache for a service."""
        if service_name not in self._service_states:
            return {"success": False, "error": f"Service '{service_name}' not found"}

        state = self._service_states[service_name]
        # Flush cache helps with disk/cache related issues
        if self._root_cause in ("DISK_FULL", "RATE_LIMIT_HIT", "DEPENDENCY_FAILURE"):
            state["memory_mb"] = max(256, state["memory_mb"] // 2)

        self._check_resolution(service_name)
        return {
            "success": True,
            "service": service_name,
            "message": f"Cache flushed for {service_name}",
        }

    def _check_resolution(self, service_name: str) -> None:
        """Check if the affected service has been resolved.

        Requires status == healthy AND resource metrics in acceptable range.
        """
        affected_service = self._alert["service"]
        if service_name != affected_service:
            return

        state = self._service_states[affected_service]
        resolved_state = self._scenario.get("resolved_state", {}).get(
            affected_service, {}
        )
        if not resolved_state:
            return

        # Must be healthy
        if state["status"] != "healthy":
            return

        # Memory must be within 50% of target (not still bloated)
        target_mem = resolved_state.get("memory_mb", state["memory_mb"])
        if state["memory_mb"] > target_mem * 1.5:
            return

        self._resolved = True

    def get_affected_service(self) -> str:
        """Get the name of the primary affected service."""
        return self._alert["service"]

    def get_final_state(self) -> dict[str, Any]:
        """Get the final state for grading."""
        affected = self.get_affected_service()
        state = self._service_states.get(affected, {})
        is_healthy = state.get("status") == "healthy"
        return {
            "status": state.get("status", "unknown"),
            "error_rate_pct": 0.1 if is_healthy else self._alert["error_rate_pct"],
            "memory_mb": state.get("memory_mb", 0),
            "replicas": state.get("replicas", 0),
            "cpu_pct": state.get("cpu_pct", 0.0),
        }
