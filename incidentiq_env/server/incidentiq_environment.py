"""
IncidentIQ Environment — Autonomous SRE Incident Response.

An RL environment where an LLM agent acts as an on-call SRE:
receives production alerts, investigates using observability tools,
diagnoses root cause, executes remediation, and verifies resolution.
"""

import copy
import json
import random
from typing import Any, Optional
from uuid import uuid4

from fastmcp import FastMCP
from openenv.core.env_server.mcp_environment import MCPEnvironment
from openenv.core.env_server.types import Action, Observation, State

from .dataset import INCIDENT_SCENARIOS, get_scenarios_by_difficulty
from .graders import (
    compute_episode_score,
    grade_post_mortem,
    grade_root_cause,
    grade_runbook_coverage,
    grade_severity,
    grade_system_state,
)
from .runbooks import (
    DESTRUCTIVE_ACTIONS,
    INVESTIGATION_ACTIONS,
    REMEDIATION_ACTIONS,
    get_runbook,
    is_correct_remediation,
    is_destructive,
)
from .simulation import ServiceSimulator

# Step budgets per task mode.
STEP_BUDGETS = {
    "alert_triage": 5,
    "runbook_execution": 10,
    "full_incident_response": 15,
}


class IncidentIQEnvironment(MCPEnvironment):
    """
    MCP-based environment for SRE incident response training.

    Exposes investigation, diagnosis, remediation, and resolution tools.
    Tracks agent actions, computes dense rewards, and grades episodes.
    """

    def __init__(self) -> None:
        mcp = FastMCP("incidentiq_env")
        self._register_tools(mcp)
        super().__init__(mcp)

        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._task_mode: str = "alert_triage"
        self._scenario: dict[str, Any] = {}
        self._simulator: Optional[ServiceSimulator] = None
        self._step_number: int = 0
        self._max_steps: int = 5
        self._done: bool = False
        self._cumulative_reward: float = 0.0
        self._tool_history: list[dict[str, Any]] = []
        self._classified_root_cause: Optional[str] = None
        self._classified_severity: Optional[str] = None
        self._action_recommendation: Optional[str] = None
        self._post_mortem: Optional[str] = None
        self._notified: bool = False
        self._verified_after_remediation: bool = False
        self._remediation_applied: bool = False
        self._scenarios: list[dict[str, Any]] = []
        self._scenario_idx: int = 0

    def _register_tools(self, mcp: FastMCP) -> None:
        """Register all MCP tools for the environment."""

        @mcp.tool
        def get_instructions() -> dict:
            """
            Get instructions for the current incident task.

            Returns the task mode, step budget, scenario info, and available actions.
            """
            return self._handle_get_instructions()

        @mcp.tool
        def get_service_status(service_name: str) -> dict:
            """
            Get the current status of a microservice.

            Args:
                service_name: Name of the service to check (e.g. 'payment-service')
            """
            return self._handle_tool_call("get_service_status", service_name=service_name)

        @mcp.tool
        def get_recent_logs(service_name: str, lines: int = 20) -> dict:
            """
            Get recent log lines from a service.

            Args:
                service_name: Name of the service
                lines: Number of log lines to retrieve (default: 20)
            """
            return self._handle_tool_call("get_recent_logs", service_name=service_name, lines=lines)

        @mcp.tool
        def get_metrics(service_name: str, metric: str, window_minutes: int = 30) -> dict:
            """
            Get time-series metrics for a service.

            Args:
                service_name: Name of the service
                metric: Metric name (memory_mb, cpu_pct, latency_p99, error_rate)
                window_minutes: Time window in minutes (default: 30)
            """
            return self._handle_tool_call(
                "get_metrics",
                service_name=service_name,
                metric=metric,
                window_minutes=window_minutes,
            )

        @mcp.tool
        def classify_root_cause(root_cause: str, severity: str) -> dict:
            """
            Classify the root cause and severity of the incident.

            Args:
                root_cause: One of: OOM, DB_TIMEOUT, DEPLOY_REGRESSION, NETWORK_PARTITION,
                           CONFIG_ERROR, DISK_FULL, DEPENDENCY_FAILURE, CERTIFICATE_EXPIRED,
                           RATE_LIMIT_HIT, MEMORY_LEAK
                severity: One of: P1, P2, P3
            """
            return self._handle_tool_call(
                "classify_root_cause", root_cause=root_cause, severity=severity
            )

        @mcp.tool
        def recommend_action(action_recommendation: str) -> dict:
            """
            Recommend a remediation action based on diagnosis.

            Args:
                action_recommendation: Description of recommended action
            """
            return self._handle_tool_call(
                "recommend_action", action_recommendation=action_recommendation
            )

        @mcp.tool
        def scale_service(service_name: str, replicas: int) -> dict:
            """
            Scale a service to the specified number of replicas.

            Args:
                service_name: Name of the service to scale
                replicas: Target number of replicas
            """
            return self._handle_tool_call(
                "scale_service", service_name=service_name, replicas=replicas
            )

        @mcp.tool
        def restart_service(service_name: str) -> dict:
            """
            Restart a service to clear transient issues.

            Args:
                service_name: Name of the service to restart
            """
            return self._handle_tool_call("restart_service", service_name=service_name)

        @mcp.tool
        def rollback_deploy(service_name: str, version: str = "previous") -> dict:
            """
            Rollback a service to a previous deployment version.

            Args:
                service_name: Name of the service
                version: Version to rollback to (default: 'previous')
            """
            return self._handle_tool_call(
                "rollback_deploy", service_name=service_name, version=version
            )

        @mcp.tool
        def update_config(service_name: str, config_key: str, config_value: str) -> dict:
            """
            Update a configuration key for a service.

            Args:
                service_name: Name of the service
                config_key: Configuration key to update
                config_value: New value for the configuration key
            """
            return self._handle_tool_call(
                "update_config",
                service_name=service_name,
                config_key=config_key,
                config_value=config_value,
            )

        @mcp.tool
        def flush_cache(service_name: str) -> dict:
            """
            Flush the cache for a service.

            Args:
                service_name: Name of the service
            """
            return self._handle_tool_call("flush_cache", service_name=service_name)

        @mcp.tool
        def notify_stakeholders(message: str, severity: str) -> dict:
            """
            Notify stakeholders about the incident status.

            Args:
                message: Brief status update message
                severity: Incident severity (P1, P2, P3)
            """
            return self._handle_tool_call(
                "notify_stakeholders", message=message, severity=severity
            )

        @mcp.tool
        def write_post_mortem(summary: str) -> dict:
            """
            Write a post-mortem summary for the incident.

            Should include: what happened, root cause, fix applied, prevention measures.

            Args:
                summary: Post-mortem text covering what/why/fix/prevention
            """
            return self._handle_tool_call("write_post_mortem", summary=summary)

        @mcp.tool
        def close_incident() -> dict:
            """
            Close the incident and finalize the episode.

            Should be called after remediation is verified and stakeholders notified.
            """
            return self._handle_tool_call("close_incident")

    # ── Reset ────────────────────────────────────────────────────────────

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        task_mode: str = "alert_triage",
        scenario_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Observation:
        """Reset the environment for a new incident episode."""
        self._task_mode = task_mode
        self._max_steps = STEP_BUDGETS.get(task_mode, 15)
        self._step_number = 0
        self._done = False
        self._cumulative_reward = 0.0
        self._tool_history = []
        self._classified_root_cause = None
        self._classified_severity = None
        self._action_recommendation = None
        self._post_mortem = None
        self._notified = False
        self._verified_after_remediation = False
        self._remediation_applied = False

        # Load scenarios
        if task_mode == "alert_triage":
            self._scenarios = get_scenarios_by_difficulty("easy")
        elif task_mode == "runbook_execution":
            self._scenarios = get_scenarios_by_difficulty("medium")
        else:
            self._scenarios = get_scenarios_by_difficulty("hard")

        if not self._scenarios:
            self._scenarios = list(INCIDENT_SCENARIOS)

        # Shuffle with seed if provided
        if seed is not None:
            rng = random.Random(seed)
            rng.shuffle(self._scenarios)

        # Select scenario
        if scenario_id:
            for i, s in enumerate(self._scenarios):
                if s["id"] == scenario_id:
                    self._scenario_idx = i
                    break
            else:
                self._scenario_idx = 0
        else:
            self._scenario_idx = 0

        self._scenario = copy.deepcopy(self._scenarios[self._scenario_idx])
        self._simulator = ServiceSimulator(self._scenario)

        self._state = State(
            episode_id=episode_id or str(uuid4()),
            step_count=0,
        )

        return Observation(
            done=False,
            reward=0.001,
            metadata={
                "status": "ready",
                "task_mode": self._task_mode,
                "scenario_id": self._scenario["id"],
                "total_scenarios": len(self._scenarios),
                "max_steps": self._max_steps,
                "message": f"Incident episode started. Task: {task_mode}. "
                f"Use get_instructions to see the alert details.",
            },
        )

    # ── Step ─────────────────────────────────────────────────────────────

    def _step_impl(self, action: Action, timeout_s: Optional[float] = None, **kwargs: Any) -> Observation:
        return Observation(
            done=False,
            reward=0.001,
            metadata={
                "error": f"Unknown action type: {type(action).__name__}. "
                "Use MCP tools (get_service_status, classify_root_cause, etc.)."
            },
        )

    def step(self, action: Action, timeout_s: Optional[float] = None, **kwargs: Any) -> Observation:
        self._state.step_count += 1
        return super().step(action, timeout_s=timeout_s, **kwargs)

    async def step_async(self, action: Action, timeout_s: Optional[float] = None, **kwargs: Any) -> Observation:
        self._state.step_count += 1
        return await super().step_async(action, timeout_s=timeout_s, **kwargs)

    @property
    def state(self) -> State:
        return self._state

    # ── Tool Handlers ────────────────────────────────────────────────────

    def _handle_get_instructions(self) -> dict[str, Any]:
        """Return task instructions and alert context."""
        alert = self._scenario["alert"]
        services = list(self._scenario["initial_state"].keys())

        result: dict[str, Any] = {
            "task_mode": self._task_mode,
            "scenario_id": self._scenario["id"],
            "max_steps": self._max_steps,
            "step_number": self._step_number,
            "steps_remaining": self._max_steps - self._step_number,
            "alert": {
                "title": alert["title"],
                "service": alert["service"],
                "error_rate_pct": alert["error_rate_pct"],
                "log_tail": alert["log_tail"],
                "metric_snapshot": alert["metric_snapshot"],
            },
            "available_services": services,
            "total_scenarios": len(self._scenarios),
            "current_scenario": self._scenario_idx + 1,
            "next_scenario_available": self._scenario_idx + 1 < len(self._scenarios),
        }

        if self._task_mode == "alert_triage":
            result["instructions"] = (
                "Classify the root cause and severity of this incident. "
                "Use classify_root_cause with the correct root_cause category and severity level."
            )
        elif self._task_mode == "runbook_execution":
            result["root_cause"] = self._scenario["root_cause"]
            result["instructions"] = (
                f"Root cause is {self._scenario['root_cause']}. "
                "Execute the correct remediation runbook steps in order. "
                "Investigate, remediate, verify, notify, and close."
            )
        else:
            result["instructions"] = (
                "Full incident response. Investigate the alert, diagnose the root cause, "
                "execute remediation, verify the fix, write a post-mortem, and close the incident."
            )
            result["red_herrings_hint"] = (
                "Warning: some signals may be misleading. Investigate thoroughly before acting."
            )

        return result

    def _handle_tool_call(self, action_type: str, **params: Any) -> dict[str, Any]:
        """Process a tool call, compute reward, update state."""
        if self._done:
            return {
                "error": "Episode is already complete. Reset to start a new episode.",
                "done": True,
            }

        self._step_number += 1
        reward = 0.0
        result: dict[str, Any] = {}
        error: Optional[str] = None

        # Record the call
        call_record = {"action_type": action_type, "params": params, "step": self._step_number}
        self._tool_history.append(call_record)

        # Check for repeated identical calls
        repeat_count = sum(
            1 for h in self._tool_history[:-1]
            if h["action_type"] == action_type and h["params"] == params
        )

        if repeat_count >= 2:
            reward -= 0.20  # Loop penalty
        elif repeat_count == 1:
            reward += 0.0  # No reward for repeat

        # ── Dispatch to handler ──
        if action_type == "get_instructions":
            result = self._handle_get_instructions()
            # get_instructions is free — don't count as a real step
            self._step_number -= 1
            self._tool_history.pop()
            return {
                **result,
                "step_number": self._step_number,
                "steps_remaining": max(0, self._max_steps - self._step_number),
                "reward": 0.001,
                "cumulative_reward": round(self._cumulative_reward, 4),
                "done": False,
            }

        elif action_type in INVESTIGATION_ACTIONS and self._simulator:
            result, reward_delta = self._handle_investigation(action_type, params, repeat_count)
            reward += reward_delta

        elif action_type == "classify_root_cause":
            result, reward_delta = self._handle_classify(params)
            reward += reward_delta

        elif action_type == "recommend_action":
            self._action_recommendation = params.get("action_recommendation", "")
            correct_first_step = get_runbook(self._scenario["root_cause"])
            if correct_first_step:
                first_remediation = next(
                    (s for s in correct_first_step if s not in INVESTIGATION_ACTIONS),
                    None,
                )
                if first_remediation and first_remediation in self._action_recommendation.lower():
                    reward += 0.20
            result = {
                "recorded": True,
                "recommendation": self._action_recommendation,
            }

        elif action_type in REMEDIATION_ACTIONS and self._simulator:
            result, reward_delta = self._handle_remediation(action_type, params)
            reward += reward_delta

        elif action_type == "notify_stakeholders":
            result, reward_delta = self._handle_notify(params)
            reward += reward_delta

        elif action_type == "write_post_mortem":
            self._post_mortem = params.get("summary", "")
            pm_score = grade_post_mortem(self._post_mortem)
            reward += 0.10 * pm_score
            result = {
                "recorded": True,
                "quality_score": round(pm_score, 4),
            }

        elif action_type == "close_incident":
            result, reward_delta = self._handle_close()
            reward += reward_delta

        else:
            error = f"Unknown action: {action_type}"
            result = {"error": error}

        # Update cumulative reward
        self._cumulative_reward += reward

        # Check step budget
        if self._step_number >= self._max_steps and not self._done:
            self._done = True
            result["budget_exhausted"] = True

        # Build response
        response = {
            **result,
            "step_number": self._step_number,
            "steps_remaining": max(0, self._max_steps - self._step_number),
            "reward": round(reward, 4),
            "cumulative_reward": round(self._cumulative_reward, 4),
            "done": self._done,
        }

        if error:
            response["error"] = error

        return response

    def _handle_investigation(
        self, action_type: str, params: dict[str, Any], repeat_count: int
    ) -> tuple[dict[str, Any], float]:
        """Handle investigation tool calls."""
        reward = 0.0

        if action_type == "get_service_status":
            result = self._simulator.get_service_status(params["service_name"])
            # Reward for first check of affected service
            if repeat_count == 0 and params["service_name"] == self._simulator.get_affected_service():
                reward += 0.10
            # Reward for verification after remediation (once)
            if self._remediation_applied and not self._verified_after_remediation:
                self._verified_after_remediation = True
                reward += 0.30

        elif action_type == "get_recent_logs":
            result = self._simulator.get_recent_logs(
                params["service_name"], params.get("lines", 20)
            )
            if repeat_count == 0:
                reward += 0.10

        elif action_type == "get_metrics":
            result = self._simulator.get_metrics(
                params["service_name"],
                params.get("metric", "memory_mb"),
                params.get("window_minutes", 30),
            )
            if repeat_count == 0:
                reward += 0.10

        else:
            result = {"error": f"Unknown investigation tool: {action_type}"}

        return result, reward

    def _handle_classify(self, params: dict[str, Any]) -> tuple[dict[str, Any], float]:
        """Handle root cause classification."""
        predicted_rc = params.get("root_cause", "")
        predicted_sev = params.get("severity", "")
        ground_truth_rc = self._scenario["root_cause"]
        ground_truth_sev = self._scenario["severity"]

        self._classified_root_cause = predicted_rc
        self._classified_severity = predicted_sev

        rc_score = grade_root_cause(predicted_rc, ground_truth_rc)
        sev_score = grade_severity(predicted_sev, ground_truth_sev)

        reward = 0.0
        if rc_score > 0.9:
            reward += 0.50
        elif rc_score > 0.3:
            reward += 0.20
        else:
            reward -= 0.30

        if sev_score >= 0.5:
            reward += 0.20 * sev_score

        result = {
            "classified": True,
            "root_cause": predicted_rc,
            "severity": predicted_sev,
            "root_cause_score": round(rc_score, 4),
            "severity_score": round(sev_score, 4),
        }

        # For alert_triage, classification can end the episode
        if self._task_mode == "alert_triage":
            self._done = True
            result["episode_complete"] = True

        return result, reward

    def _handle_remediation(
        self, action_type: str, params: dict[str, Any]
    ) -> tuple[dict[str, Any], float]:
        """Handle remediation tool calls."""
        reward = 0.0
        root_cause = self._scenario["root_cause"]

        # Check if action is destructive for this root cause
        if is_destructive(root_cause, action_type):
            reward -= 0.50
        elif is_correct_remediation(root_cause, action_type):
            reward += 0.30

            # Bonus for correct order
            correct_runbook = get_runbook(root_cause)
            executed_remediation = [
                h["action_type"]
                for h in self._tool_history
                if h["action_type"] in REMEDIATION_ACTIONS
            ]
            if executed_remediation and correct_runbook:
                # Check if this step is in the right position
                rem_steps_in_runbook = [s for s in correct_runbook if s in REMEDIATION_ACTIONS]
                current_idx = len(executed_remediation) - 1
                if current_idx < len(rem_steps_in_runbook):
                    if action_type == rem_steps_in_runbook[current_idx]:
                        reward += 0.10
        else:
            reward -= 0.20

        # Check for worsening actions
        if action_type == "scale_service" and root_cause in ("OOM", "MEMORY_LEAK"):
            service_name = params.get("service_name", "")
            if service_name == self._simulator.get_affected_service():
                current = self._simulator.get_service_status(service_name)
                if params.get("replicas", 0) < current.get("replicas", 0):
                    reward -= 1.00  # Worsening penalty

        # Execute the action on the simulator
        if action_type == "scale_service":
            result = self._simulator.scale_service(
                params["service_name"], params["replicas"]
            )
        elif action_type == "restart_service":
            result = self._simulator.restart_service(params["service_name"])
        elif action_type == "rollback_deploy":
            result = self._simulator.rollback_deploy(
                params["service_name"], params.get("version")
            )
        elif action_type == "update_config":
            result = self._simulator.update_config(
                params["service_name"],
                params.get("config_key", ""),
                params.get("config_value", ""),
            )
        elif action_type == "flush_cache":
            result = self._simulator.flush_cache(params["service_name"])
        else:
            result = {"error": f"Unknown remediation tool: {action_type}"}

        self._remediation_applied = True
        return result, reward

    def _handle_notify(self, params: dict[str, Any]) -> tuple[dict[str, Any], float]:
        """Handle stakeholder notification."""
        message = params.get("message", "")
        severity = params.get("severity", "")
        reward = 0.0

        if message and len(message) > 5:
            reward += 0.10
            self._notified = True
        else:
            reward -= 0.10

        return {
            "sent": True,
            "message": message,
            "severity": severity,
            "recipients": ["oncall-team", "engineering-lead", "stakeholders"],
        }, reward

    def _handle_close(self) -> tuple[dict[str, Any], float]:
        """Handle incident closure and compute final scores."""
        reward = 0.0

        # Penalty for closing without verification
        if not self._verified_after_remediation and self._task_mode != "alert_triage":
            reward -= 0.10

        # Compute final scores
        rc_score = grade_root_cause(
            self._classified_root_cause, self._scenario["root_cause"]
        )
        sev_score = grade_severity(
            self._classified_severity, self._scenario["severity"]
        )

        executed_steps = [h["action_type"] for h in self._tool_history]
        correct_runbook = self._scenario.get("correct_runbook", get_runbook(self._scenario["root_cause"]))
        runbook_score = grade_runbook_coverage(executed_steps, correct_runbook)

        final_state = self._simulator.get_final_state() if self._simulator else {}
        affected = self._simulator.get_affected_service() if self._simulator else ""
        target_state = self._scenario.get("resolved_state", {}).get(affected, {})
        state_score = grade_system_state(final_state, target_state)

        pm_score = grade_post_mortem(self._post_mortem)

        # Efficiency bonus (clamped to strict (0, 1))
        budget_pct = self._step_number / self._max_steps if self._max_steps > 0 else 1.0
        if budget_pct <= 0.50:
            efficiency_bonus = 0.20
        elif budget_pct <= 0.75:
            efficiency_bonus = 0.10
        elif budget_pct > 0.80:
            efficiency_bonus = max(0.001, -0.10 * (budget_pct - 0.80) / 0.20)
        else:
            efficiency_bonus = 0.05

        episode_score = compute_episode_score(
            rc_score, runbook_score, state_score, pm_score, efficiency_bonus,
            task_mode=self._task_mode, severity_score=sev_score,
        )

        # System restored bonus
        if self._simulator and self._simulator.is_resolved:
            reward += 0.20
        else:
            reward -= 0.20

        self._done = True

        return {
            "incident_closed": True,
            "episode_score": round(episode_score, 4),
            "scores": {
                "root_cause_accuracy": round(rc_score, 4),
                "severity_accuracy": round(sev_score, 4),
                "runbook_coverage": round(runbook_score, 4),
                "system_state": round(state_score, 4),
                "post_mortem_quality": round(pm_score, 4),
                "efficiency_bonus": round(efficiency_bonus, 2),
            },
            "details": {
                "predicted_root_cause": self._classified_root_cause,
                "actual_root_cause": self._scenario["root_cause"],
                "predicted_severity": self._classified_severity,
                "actual_severity": self._scenario["severity"],
                "steps_used": self._step_number,
                "max_steps": self._max_steps,
                "system_resolved": self._simulator.is_resolved if self._simulator else False,
                "stakeholders_notified": self._notified,
                "verified_after_remediation": self._verified_after_remediation,
            },
            "next_scenario_available": self._scenario_idx + 1 < len(self._scenarios),
        }, reward
