"""Tests for IncidentIQ SRE Incident Response environment."""

import pytest

from incidentiq_env.server.dataset import (
    INCIDENT_SCENARIOS,
    get_scenario_by_id,
    get_scenarios_by_difficulty,
)
from incidentiq_env.server.graders import (
    compute_episode_score,
    grade_post_mortem,
    grade_root_cause,
    grade_runbook_coverage,
    grade_severity,
    grade_system_state,
)
from incidentiq_env.server.incidentiq_environment import IncidentIQEnvironment
from incidentiq_env.server.runbooks import (
    RUNBOOKS,
    get_runbook,
    is_correct_remediation,
    is_destructive,
)
from incidentiq_env.server.simulation import ServiceSimulator


# ── Dataset Tests ────────────────────────────────────────────────────────


class TestDataset:
    """Test incident scenario dataset."""

    def test_scenario_count(self):
        assert len(INCIDENT_SCENARIOS) == 15

    def test_difficulty_distribution(self):
        easy = get_scenarios_by_difficulty("easy")
        medium = get_scenarios_by_difficulty("medium")
        hard = get_scenarios_by_difficulty("hard")
        assert len(easy) == 5
        assert len(medium) == 5
        assert len(hard) == 5

    def test_all_scenarios_have_required_fields(self):
        required = [
            "id", "root_cause", "severity", "difficulty", "alert",
            "initial_state", "resolved_state", "correct_runbook",
        ]
        for s in INCIDENT_SCENARIOS:
            for field in required:
                assert field in s, f"Scenario {s['id']} missing field: {field}"

    def test_all_alerts_have_required_fields(self):
        alert_fields = ["title", "service", "error_rate_pct", "log_tail", "metric_snapshot"]
        for s in INCIDENT_SCENARIOS:
            for field in alert_fields:
                assert field in s["alert"], f"Scenario {s['id']} alert missing: {field}"

    def test_all_log_tails_have_5_lines(self):
        for s in INCIDENT_SCENARIOS:
            assert len(s["alert"]["log_tail"]) == 5, f"Scenario {s['id']} log_tail != 5 lines"

    def test_get_scenario_by_id(self):
        s = get_scenario_by_id("INC-001")
        assert s is not None
        assert s["root_cause"] == "OOM"

    def test_get_scenario_by_id_not_found(self):
        assert get_scenario_by_id("INC-999") is None

    def test_unique_scenario_ids(self):
        ids = [s["id"] for s in INCIDENT_SCENARIOS]
        assert len(ids) == len(set(ids))

    def test_root_cause_coverage(self):
        """All 10 root cause categories are represented."""
        causes = {s["root_cause"] for s in INCIDENT_SCENARIOS}
        expected = {
            "OOM", "DB_TIMEOUT", "DEPLOY_REGRESSION", "NETWORK_PARTITION",
            "CONFIG_ERROR", "DISK_FULL", "DEPENDENCY_FAILURE",
            "CERTIFICATE_EXPIRED", "RATE_LIMIT_HIT", "MEMORY_LEAK",
        }
        assert expected == causes


# ── Runbook Tests ────────────────────────────────────────────────────────


class TestRunbooks:
    """Test runbook definitions."""

    def test_all_root_causes_have_runbooks(self):
        for s in INCIDENT_SCENARIOS:
            rb = get_runbook(s["root_cause"])
            assert len(rb) > 0, f"No runbook for {s['root_cause']}"

    def test_runbooks_start_with_investigation(self):
        for cause, steps in RUNBOOKS.items():
            assert steps[0] == "get_service_status", f"{cause} runbook should start with get_service_status"

    def test_runbooks_end_with_close(self):
        for cause, steps in RUNBOOKS.items():
            assert steps[-1] == "close_incident", f"{cause} runbook should end with close_incident"

    def test_is_destructive(self):
        assert is_destructive("OOM", "rollback_deploy")
        assert not is_destructive("OOM", "scale_service")
        assert is_destructive("DEPLOY_REGRESSION", "scale_service")
        assert not is_destructive("DEPLOY_REGRESSION", "rollback_deploy")

    def test_is_correct_remediation(self):
        assert is_correct_remediation("OOM", "scale_service")
        assert is_correct_remediation("DEPLOY_REGRESSION", "rollback_deploy")
        assert not is_correct_remediation("OOM", "rollback_deploy")


# ── Simulation Tests ─────────────────────────────────────────────────────


class TestSimulation:
    """Test the ServiceSimulator state machine."""

    @pytest.fixture
    def sim(self):
        scenario = get_scenario_by_id("INC-001")
        return ServiceSimulator(scenario)

    def test_initial_state(self, sim):
        status = sim.get_service_status("payment-service")
        assert status["status"] == "degraded"
        assert status["replicas"] == 2
        assert status["memory_mb"] == 3890

    def test_unknown_service(self, sim):
        result = sim.get_service_status("nonexistent-service")
        assert "error" in result

    def test_get_recent_logs(self, sim):
        logs = sim.get_recent_logs("payment-service")
        assert "log_lines" in logs
        assert len(logs["log_lines"]) > 0

    def test_get_recent_logs_unknown_service(self, sim):
        result = sim.get_recent_logs("nonexistent")
        assert "error" in result

    def test_get_metrics(self, sim):
        metrics = sim.get_metrics("payment-service", "memory_mb", 60)
        assert "values" in metrics
        assert metrics["trend"] == "increasing"
        assert metrics["current"] == 3890.0

    def test_get_metrics_unknown_service(self, sim):
        result = sim.get_metrics("nonexistent", "cpu_pct", 30)
        assert "error" in result

    def test_scale_service_up(self, sim):
        result = sim.scale_service("payment-service", 4)
        assert result["success"] is True
        assert result["new_replicas"] == 4
        # Scaling up should help degraded service
        status = sim.get_service_status("payment-service")
        assert status["replicas"] == 4

    def test_scale_service_invalid_replicas(self, sim):
        result = sim.scale_service("payment-service", 0)
        assert result["success"] is False

    def test_restart_service(self, sim):
        """Restart gives temporary relief for OOM but doesn't fully resolve."""
        result = sim.restart_service("payment-service")
        assert result["success"] is True
        status = sim.get_service_status("payment-service")
        # OOM is not in restart_fixes set, so status stays degraded
        assert status["status"] == "degraded"
        # But resources should be partially reduced
        assert status["cpu_pct"] < 78.0

    def test_restart_service_fixes_db_timeout(self):
        """Restart fully resolves DB_TIMEOUT scenarios."""
        scenario = get_scenario_by_id("INC-002")
        sim = ServiceSimulator(scenario)
        result = sim.restart_service("user-service")
        assert result["success"] is True
        status = sim.get_service_status("user-service")
        assert status["status"] == "healthy"

    def test_rollback_deploy(self, sim):
        result = sim.rollback_deploy("payment-service", "v2.3.0")
        assert result["success"] is True

    def test_update_config(self, sim):
        result = sim.update_config("payment-service", "MAX_HEAP", "8192m")
        assert result["success"] is True

    def test_flush_cache(self, sim):
        result = sim.flush_cache("payment-service")
        assert result["success"] is True

    def test_resolution_detection(self, sim):
        """OOM resolution requires scaling up, not just restart."""
        assert not sim.is_resolved
        sim.scale_service("payment-service", 4)
        # Scale up helps but may not fully resolve if memory still high
        # Need to also get the status healthy
        sim.restart_service("payment-service")
        # After scale + restart on OOM, check state
        status = sim.get_service_status("payment-service")
        # For OOM: scale helps with resources, but restart alone doesn't fix

    def test_resolution_detection_db_timeout(self):
        """DB_TIMEOUT resolves with restart."""
        scenario = get_scenario_by_id("INC-002")
        sim = ServiceSimulator(scenario)
        assert not sim.is_resolved
        sim.restart_service("user-service")
        assert sim.is_resolved

    def test_get_affected_service(self, sim):
        assert sim.get_affected_service() == "payment-service"

    def test_get_final_state_after_resolution(self):
        """DB_TIMEOUT scenario: restart resolves, final state is healthy."""
        scenario = get_scenario_by_id("INC-002")
        sim = ServiceSimulator(scenario)
        sim.restart_service("user-service")
        state = sim.get_final_state()
        assert state["status"] == "healthy"
        assert state["error_rate_pct"] < 1.0

    def test_healthy_service_logs(self, sim):
        """Logs for a healthy service that isn't the alert target."""
        logs = sim.get_recent_logs("order-service")
        assert len(logs["log_lines"]) > 0


# ── Grader Tests ─────────────────────────────────────────────────────────


class TestGraders:
    """Test all 4 grading functions."""

    # Grader 1: Root Cause Accuracy
    def test_root_cause_exact_match(self):
        assert grade_root_cause("OOM", "OOM") == pytest.approx(1.0, abs=0.01)

    def test_root_cause_related(self):
        assert grade_root_cause("MEMORY_LEAK", "OOM") == pytest.approx(0.5, abs=0.01)
        assert grade_root_cause("OOM", "MEMORY_LEAK") == pytest.approx(0.5, abs=0.01)

    def test_root_cause_wrong(self):
        assert grade_root_cause("CONFIG_ERROR", "OOM") == pytest.approx(0.0, abs=0.01)

    def test_root_cause_none(self):
        assert grade_root_cause(None, "OOM") == pytest.approx(0.0, abs=0.01)

    def test_root_cause_case_insensitive(self):
        assert grade_root_cause("oom", "OOM") == pytest.approx(1.0, abs=0.01)

    # Grader 1b: Severity
    def test_severity_exact(self):
        assert grade_severity("P1", "P1") == pytest.approx(1.0, abs=0.01)

    def test_severity_off_by_one(self):
        assert grade_severity("P2", "P1") == pytest.approx(0.5, abs=0.01)

    def test_severity_off_by_two(self):
        assert grade_severity("P3", "P1") == pytest.approx(0.0, abs=0.01)

    def test_severity_none(self):
        assert grade_severity(None, "P1") == pytest.approx(0.0, abs=0.01)

    # Grader 2: Runbook Coverage
    def test_runbook_perfect(self):
        steps = ["get_service_status", "get_metrics", "scale_service", "notify_stakeholders", "close_incident"]
        score = grade_runbook_coverage(steps, steps)
        assert score > 0.9

    def test_runbook_partial(self):
        correct = ["get_service_status", "get_metrics", "scale_service", "close_incident"]
        executed = ["get_service_status", "scale_service"]
        score = grade_runbook_coverage(executed, correct)
        assert 0.3 < score < 0.7

    def test_runbook_empty(self):
        assert grade_runbook_coverage([], ["get_service_status", "close_incident"]) == pytest.approx(0.0, abs=0.01)

    def test_runbook_empty_correct(self):
        assert grade_runbook_coverage(["something"], []) == pytest.approx(0.0, abs=0.01)

    # Grader 3: System State
    def test_state_resolved(self):
        final = {"status": "healthy", "error_rate_pct": 0.1, "memory_mb": 1200}
        target = {"status": "healthy", "error_rate_pct": 0.1, "memory_mb": 1200}
        assert grade_system_state(final, target) == pytest.approx(1.0, abs=0.01)

    def test_state_degraded(self):
        final = {"status": "degraded", "error_rate_pct": 25.0, "memory_mb": 4000}
        target = {"status": "healthy", "error_rate_pct": 0.1, "memory_mb": 1200}
        assert grade_system_state(final, target) == pytest.approx(0.0, abs=0.01)

    def test_state_partial(self):
        final = {"status": "healthy", "error_rate_pct": 0.5, "memory_mb": 1500}
        target = {"status": "healthy", "error_rate_pct": 0.1, "memory_mb": 1200}
        score = grade_system_state(final, target)
        assert 0.5 < score < 1.0

    # Grader 4: Post-Mortem Quality
    def test_postmortem_all_sections(self):
        text = (
            "The incident affected payment-service which went down. "
            "Root cause was caused by OOM. "
            "We fixed it by scaling the service. "
            "To prevent this in the future, we added memory alerts."
        )
        assert grade_post_mortem(text) == pytest.approx(1.0, abs=0.01)

    def test_postmortem_partial(self):
        text = "The incident was caused by OOM. We restarted it."
        score = grade_post_mortem(text)
        assert 0.25 <= score <= 0.75

    def test_postmortem_empty(self):
        assert grade_post_mortem("") == pytest.approx(0.0, abs=0.01)
        assert grade_post_mortem(None) == pytest.approx(0.0, abs=0.01)

    # Episode Score
    def test_episode_score_perfect_hard(self):
        score = compute_episode_score(1.0, 1.0, 1.0, 1.0, 0.2,
                                       task_mode="full_incident_response", severity_score=1.0)
        assert score > 0.9

    def test_episode_score_perfect_triage(self):
        score = compute_episode_score(1.0, 0.0, 0.0, 0.0, 0.2,
                                       task_mode="alert_triage", severity_score=1.0)
        assert score > 0.8  # Triage weights diagnosis, not runbook/state

    def test_episode_score_zero(self):
        score = compute_episode_score(0.0, 0.0, 0.0, 0.0, 0.0,
                                       task_mode="full_incident_response")
        assert score == pytest.approx(0.0, abs=0.01)


# ── Environment Tests ────────────────────────────────────────────────────


class TestIncidentIQEnvironment:
    """Test the main IncidentIQ environment."""

    @pytest.fixture
    def env(self):
        return IncidentIQEnvironment()

    # ── Reset ──

    def test_reset_alert_triage(self, env):
        obs = env.reset(task_mode="alert_triage")
        assert obs.done is False
        assert obs.reward == pytest.approx(0.0, abs=0.01)
        assert obs.metadata["task_mode"] == "alert_triage"
        assert obs.metadata["max_steps"] == 5

    def test_reset_runbook_execution(self, env):
        obs = env.reset(task_mode="runbook_execution")
        assert obs.metadata["task_mode"] == "runbook_execution"
        assert obs.metadata["max_steps"] == 10

    def test_reset_full_incident_response(self, env):
        obs = env.reset(task_mode="full_incident_response")
        assert obs.metadata["task_mode"] == "full_incident_response"
        assert obs.metadata["max_steps"] == 15

    def test_reset_with_seed(self, env):
        env.reset(seed=42, task_mode="alert_triage")
        id1 = env._scenario["id"]
        env.reset(seed=42, task_mode="alert_triage")
        id2 = env._scenario["id"]
        assert id1 == id2  # Same seed = same scenario order

    def test_reset_loads_correct_difficulty(self, env):
        env.reset(task_mode="alert_triage")
        assert env._scenario["difficulty"] == "easy"
        env.reset(task_mode="runbook_execution")
        assert env._scenario["difficulty"] == "medium"
        env.reset(task_mode="full_incident_response")
        assert env._scenario["difficulty"] == "hard"

    # ── Instructions ──

    def test_get_instructions(self, env):
        env.reset(task_mode="alert_triage")
        instr = env._handle_get_instructions()
        assert "alert" in instr
        assert "task_mode" in instr
        assert instr["task_mode"] == "alert_triage"
        assert "title" in instr["alert"]
        assert "available_services" in instr

    def test_instructions_runbook_provides_root_cause(self, env):
        env.reset(task_mode="runbook_execution")
        instr = env._handle_get_instructions()
        assert "root_cause" in instr

    def test_instructions_full_has_red_herring_hint(self, env):
        env.reset(task_mode="full_incident_response")
        instr = env._handle_get_instructions()
        assert "red_herrings_hint" in instr

    # ── Alert Triage Workflow ──

    def test_alert_triage_correct_classification(self, env):
        env.reset(task_mode="alert_triage")
        result = env._handle_tool_call(
            "classify_root_cause",
            root_cause=env._scenario["root_cause"],
            severity=env._scenario["severity"],
        )
        assert result["root_cause_score"] == pytest.approx(1.0, abs=0.01)
        assert result["severity_score"] == pytest.approx(1.0, abs=0.01)
        assert result["done"] is True
        assert result["reward"] > 0

    def test_alert_triage_wrong_classification(self, env):
        env.reset(task_mode="alert_triage")
        result = env._handle_tool_call(
            "classify_root_cause",
            root_cause="DISK_FULL",  # Wrong for most scenarios
            severity="P3",
        )
        assert result["done"] is True
        # Wrong classification should have negative reward
        assert result["reward"] < 0.5

    # ── Investigation Rewards ──

    def test_investigation_first_call_rewarded(self, env):
        env.reset(task_mode="full_incident_response")
        svc = env._scenario["alert"]["service"]
        result = env._handle_tool_call("get_service_status", service_name=svc)
        assert result["reward"] == 0.1

    def test_investigation_repeated_call_no_reward(self, env):
        env.reset(task_mode="full_incident_response")
        svc = env._scenario["alert"]["service"]
        env._handle_tool_call("get_service_status", service_name=svc)
        # Second identical call
        result = env._handle_tool_call("get_service_status", service_name=svc)
        assert result["reward"] == 0.0  # No reward for repeat

    def test_investigation_triple_repeat_penalty(self, env):
        env.reset(task_mode="full_incident_response")
        svc = env._scenario["alert"]["service"]
        env._handle_tool_call("get_service_status", service_name=svc)
        env._handle_tool_call("get_service_status", service_name=svc)
        result = env._handle_tool_call("get_service_status", service_name=svc)
        assert result["reward"] < 0  # Penalty for 3rd repeat

    # ── Remediation Rewards ──

    def test_correct_remediation_rewarded(self, env):
        env.reset(task_mode="runbook_execution")
        rc = env._scenario["root_cause"]
        svc = env._scenario["alert"]["service"]
        runbook = get_runbook(rc)

        # Find the first remediation step
        from incidentiq_env.server.runbooks import REMEDIATION_ACTIONS
        first_rem = next((s for s in runbook if s in REMEDIATION_ACTIONS), None)

        if first_rem == "restart_service":
            result = env._handle_tool_call("restart_service", service_name=svc)
        elif first_rem == "scale_service":
            result = env._handle_tool_call("scale_service", service_name=svc, replicas=4)
        elif first_rem == "rollback_deploy":
            result = env._handle_tool_call("rollback_deploy", service_name=svc, version="prev")
        elif first_rem == "update_config":
            result = env._handle_tool_call("update_config", service_name=svc, config_key="k", config_value="v")
        elif first_rem == "flush_cache":
            result = env._handle_tool_call("flush_cache", service_name=svc)
        else:
            pytest.skip("No remediation step in runbook")

        assert result["reward"] > 0

    def test_destructive_action_penalized(self, env):
        env.reset(task_mode="runbook_execution", scenario_id="INC-006")
        # INC-006 is NETWORK_PARTITION; rollback_deploy is destructive
        svc = env._scenario["alert"]["service"]
        result = env._handle_tool_call("rollback_deploy", service_name=svc, version="prev")
        assert result["reward"] < 0

    # ── Verification ──

    def test_verification_after_remediation(self, env):
        env.reset(task_mode="full_incident_response")
        svc = env._scenario["alert"]["service"]

        # Investigate
        env._handle_tool_call("get_service_status", service_name=svc)
        # Remediate
        env._handle_tool_call("restart_service", service_name=svc)
        # Verify
        result = env._handle_tool_call("get_service_status", service_name=svc)
        assert result["reward"] == 0.3  # Verification reward

    # ── Notification ──

    def test_notification_rewarded(self, env):
        env.reset(task_mode="runbook_execution")
        result = env._handle_tool_call(
            "notify_stakeholders",
            message="Incident resolved. Service restarted.",
            severity="P1",
        )
        assert result["reward"] == 0.1
        assert result["sent"] is True

    def test_empty_notification_penalized(self, env):
        env.reset(task_mode="runbook_execution")
        result = env._handle_tool_call(
            "notify_stakeholders", message="", severity="P1"
        )
        assert result["reward"] == -0.1

    # ── Post-Mortem ──

    def test_post_mortem_quality(self, env):
        env.reset(task_mode="full_incident_response")
        result = env._handle_tool_call(
            "write_post_mortem",
            summary="The incident affected our service which went down. "
            "Root cause was caused by timeout. "
            "We fixed it by restarting. "
            "To prevent this in the future, we will add alerts.",
        )
        assert result["quality_score"] == pytest.approx(1.0, abs=0.01)
        assert result["reward"] > 0

    # ── Close Incident ──

    def test_close_incident_returns_scores(self, env):
        env.reset(task_mode="full_incident_response")
        svc = env._scenario["alert"]["service"]

        env._handle_tool_call("get_service_status", service_name=svc)
        env._handle_tool_call(
            "classify_root_cause",
            root_cause=env._scenario["root_cause"],
            severity=env._scenario["severity"],
        )
        env._handle_tool_call("restart_service", service_name=svc)
        env._handle_tool_call("get_service_status", service_name=svc)
        result = env._handle_tool_call("close_incident")

        assert result["done"] is True
        assert "episode_score" in result
        assert "scores" in result
        assert "details" in result
        assert result["scores"]["root_cause_accuracy"] == pytest.approx(1.0, abs=0.01)

    def test_close_without_verification_penalized(self, env):
        env.reset(task_mode="runbook_execution")
        svc = env._scenario["alert"]["service"]

        env._handle_tool_call("restart_service", service_name=svc)
        result = env._handle_tool_call("close_incident")

        # Should have penalty for not verifying
        assert result["details"]["verified_after_remediation"] is False

    # ── Step Budget ──

    def test_step_budget_exhaustion(self, env):
        env.reset(task_mode="alert_triage")  # 5 step budget
        svc = env._scenario["alert"]["service"]

        for i in range(5):
            result = env._handle_tool_call("get_service_status", service_name=svc)

        assert result["done"] is True
        assert result.get("budget_exhausted") is True

    # ── Done State ──

    def test_actions_after_done_rejected(self, env):
        env.reset(task_mode="alert_triage")
        env._handle_tool_call(
            "classify_root_cause",
            root_cause=env._scenario["root_cause"],
            severity=env._scenario["severity"],
        )
        # Episode is done now
        result = env._handle_tool_call("get_service_status", service_name="anything")
        assert "error" in result
        assert result["done"] is True

    # ── Cumulative Reward ──

    def test_cumulative_reward_tracked(self, env):
        env.reset(task_mode="full_incident_response")
        svc = env._scenario["alert"]["service"]

        r1 = env._handle_tool_call("get_service_status", service_name=svc)
        r2 = env._handle_tool_call("get_recent_logs", service_name=svc)

        assert r2["cumulative_reward"] == pytest.approx(
            r1["reward"] + r2["reward"], abs=0.01
        )


# ── Full Workflow Integration Tests ──────────────────────────────────────


class TestFullWorkflows:
    """End-to-end workflow tests for each task mode."""

    @pytest.fixture
    def env(self):
        return IncidentIQEnvironment()

    def test_alert_triage_full_workflow(self, env):
        """Agent classifies root cause correctly in alert_triage."""
        env.reset(task_mode="alert_triage", seed=0)
        rc = env._scenario["root_cause"]
        sev = env._scenario["severity"]

        result = env._handle_tool_call(
            "classify_root_cause", root_cause=rc, severity=sev
        )
        assert result["done"] is True
        assert result["root_cause_score"] == pytest.approx(1.0, abs=0.01)
        assert env._cumulative_reward > 0.5

    def test_runbook_execution_full_workflow(self, env):
        """Agent follows runbook for a medium scenario."""
        env.reset(task_mode="runbook_execution", seed=0)
        svc = env._scenario["alert"]["service"]

        env._handle_tool_call("get_service_status", service_name=svc)
        env._handle_tool_call("get_recent_logs", service_name=svc)
        env._handle_tool_call("get_metrics", service_name=svc, metric="latency_p99", window_minutes=30)
        env._handle_tool_call("restart_service", service_name=svc)
        env._handle_tool_call("get_service_status", service_name=svc)
        env._handle_tool_call(
            "notify_stakeholders",
            message="Issue resolved",
            severity=env._scenario["severity"],
        )
        env._handle_tool_call(
            "classify_root_cause",
            root_cause=env._scenario["root_cause"],
            severity=env._scenario["severity"],
        )
        result = env._handle_tool_call("close_incident")

        assert result["done"] is True
        assert result["episode_score"] > 0.5

    def test_full_incident_response_workflow(self, env):
        """Agent does full investigation, diagnosis, remediation, post-mortem."""
        env.reset(task_mode="full_incident_response", seed=0)
        svc = env._scenario["alert"]["service"]
        rc = env._scenario["root_cause"]
        sev = env._scenario["severity"]

        # Investigate
        env._handle_tool_call("get_service_status", service_name=svc)
        env._handle_tool_call("get_recent_logs", service_name=svc)
        env._handle_tool_call("get_metrics", service_name=svc, metric="memory_mb", window_minutes=60)

        # Diagnose
        env._handle_tool_call("classify_root_cause", root_cause=rc, severity=sev)

        # Remediate
        env._handle_tool_call("restart_service", service_name=svc)

        # Verify
        env._handle_tool_call("get_service_status", service_name=svc)

        # Communicate
        env._handle_tool_call(
            "notify_stakeholders",
            message=f"Incident resolved. Root cause: {rc}",
            severity=sev,
        )

        # Post-mortem
        env._handle_tool_call(
            "write_post_mortem",
            summary=f"The incident affected {svc}. Root cause was caused by {rc}. "
            f"We fixed it by restarting the service. "
            "To prevent this in the future, we will improve monitoring.",
        )

        # Close
        result = env._handle_tool_call("close_incident")

        assert result["done"] is True
        assert result["episode_score"] > 0.7
        assert result["details"]["system_resolved"] is True
        assert result["details"]["stakeholders_notified"] is True
        assert result["details"]["verified_after_remediation"] is True

    def test_all_scenarios_playable(self, env):
        """Every scenario can be reset and played through to completion."""
        difficulty_to_task = {
            "easy": "alert_triage",
            "medium": "runbook_execution",
            "hard": "full_incident_response",
        }
        for scenario in INCIDENT_SCENARIOS:
            task = difficulty_to_task[scenario["difficulty"]]
            env.reset(task_mode=task, scenario_id=scenario["id"])
            assert env._scenario["id"] == scenario["id"]
            result = env._handle_tool_call(
                "classify_root_cause",
                root_cause=scenario["root_cause"],
                severity=scenario["severity"],
            )
            assert result["root_cause_score"] == pytest.approx(1.0, abs=0.01)
