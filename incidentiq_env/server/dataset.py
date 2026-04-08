"""
Incident scenario dataset for IncidentIQ environment.

15 pre-seeded incidents covering 10 root cause categories from production systems.
Each scenario includes alert data, initial system state, resolved state, and ground truth.
"""

from typing import Any

# ── Root Cause Categories ──
ROOT_CAUSES = [
    "OOM",
    "DB_TIMEOUT",
    "DEPLOY_REGRESSION",
    "NETWORK_PARTITION",
    "CONFIG_ERROR",
    "DISK_FULL",
    "DEPENDENCY_FAILURE",
    "CERTIFICATE_EXPIRED",
    "RATE_LIMIT_HIT",
    "MEMORY_LEAK",
]

SEVERITIES = ["P1", "P2", "P3"]


def _scenario(
    id: str,
    root_cause: str,
    severity: str,
    alert: dict,
    initial_state: dict[str, dict],
    resolved_state: dict[str, dict],
    correct_runbook: list[str],
    red_herrings: list[str],
    additional_logs: dict[str, list[str]] | None = None,
    additional_metrics: dict[str, dict[str, list[float]]] | None = None,
    difficulty: str = "easy",
) -> dict[str, Any]:
    return {
        "id": id,
        "root_cause": root_cause,
        "severity": severity,
        "difficulty": difficulty,
        "alert": alert,
        "initial_state": initial_state,
        "resolved_state": resolved_state,
        "correct_runbook": correct_runbook,
        "red_herrings": red_herrings,
        "additional_logs": additional_logs or {},
        "additional_metrics": additional_metrics or {},
    }


INCIDENT_SCENARIOS: list[dict[str, Any]] = [
    # ──────────────────────────────────────────────────────────────────────
    # EASY scenarios (1-5): clear signals, obvious root cause
    # ──────────────────────────────────────────────────────────────────────
    _scenario(
        id="INC-001",
        root_cause="OOM",
        severity="P1",
        difficulty="easy",
        alert={
            "title": "ALERT: payment-service memory > 95%",
            "service": "payment-service",
            "error_rate_pct": 23.4,
            "log_tail": [
                "2025-04-08T02:14:33 ERROR OutOfMemoryError: Java heap space",
                "2025-04-08T02:14:34 WARN  GC overhead limit exceeded",
                "2025-04-08T02:14:35 ERROR Failed to process payment request",
                "2025-04-08T02:14:36 ERROR Container killed: OOMKilled",
                "2025-04-08T02:14:37 INFO  Pod restarting...",
            ],
            "metric_snapshot": {
                "memory_mb": 3890,
                "cpu_pct": 78.0,
                "latency_p99": 2340.0,
                "request_rate": 450.0,
            },
        },
        initial_state={
            "payment-service": {
                "status": "degraded",
                "replicas": 2,
                "memory_mb": 3890,
                "cpu_pct": 78.0,
                "last_deploy_version": "v2.3.1",
                "last_deploy_time": "2025-04-07T22:00:00Z",
            },
            "order-service": {
                "status": "healthy",
                "replicas": 3,
                "memory_mb": 512,
                "cpu_pct": 25.0,
                "last_deploy_version": "v1.8.0",
                "last_deploy_time": "2025-04-06T14:00:00Z",
            },
            "api-gateway": {
                "status": "healthy",
                "replicas": 2,
                "memory_mb": 256,
                "cpu_pct": 15.0,
                "last_deploy_version": "v3.1.0",
                "last_deploy_time": "2025-04-05T10:00:00Z",
            },
        },
        resolved_state={
            "payment-service": {
                "status": "healthy",
                "replicas": 4,
                "memory_mb": 1200,
                "cpu_pct": 35.0,
                "error_rate_pct": 0.1,
            },
        },
        correct_runbook=[
            "get_service_status",
            "get_metrics",
            "scale_service",
            "get_service_status",
            "notify_stakeholders",
            "close_incident",
        ],
        red_herrings=[
            "Recent deploy 4h ago - unrelated version bump",
            "CPU at 78% - secondary effect of GC thrashing",
        ],
        additional_logs={
            "payment-service": [
                "2025-04-08T02:10:00 INFO  Processing batch of 500 payments",
                "2025-04-08T02:11:12 WARN  Heap usage at 85%",
                "2025-04-08T02:12:30 WARN  Heap usage at 90%",
                "2025-04-08T02:13:45 ERROR GC pause exceeded 5s",
                "2025-04-08T02:14:00 ERROR OutOfMemoryError: Java heap space",
            ],
        },
        additional_metrics={
            "payment-service": {
                "memory_mb": [2100.0, 2400.0, 2800.0, 3200.0, 3500.0, 3890.0],
                "cpu_pct": [35.0, 42.0, 55.0, 65.0, 72.0, 78.0],
                "latency_p99": [120.0, 250.0, 500.0, 1200.0, 1800.0, 2340.0],
                "error_rate": [0.1, 0.5, 2.0, 8.0, 15.0, 23.4],
            },
        },
    ),
    _scenario(
        id="INC-002",
        root_cause="DB_TIMEOUT",
        severity="P2",
        difficulty="easy",
        alert={
            "title": "ALERT: user-service high latency (p99 > 5s)",
            "service": "user-service",
            "error_rate_pct": 12.1,
            "log_tail": [
                "2025-04-08T03:22:10 ERROR QueryTimeoutError: query exceeded 30s timeout",
                "2025-04-08T03:22:11 WARN  Connection pool exhausted (50/50 in use)",
                "2025-04-08T03:22:12 ERROR Failed to fetch user profile: timeout",
                "2025-04-08T03:22:13 ERROR Slow query: SELECT * FROM users WHERE last_login > ...",
                "2025-04-08T03:22:14 WARN  DB replica lag: 45s",
            ],
            "metric_snapshot": {
                "memory_mb": 1024,
                "cpu_pct": 45.0,
                "latency_p99": 5200.0,
                "request_rate": 320.0,
            },
        },
        initial_state={
            "user-service": {
                "status": "degraded",
                "replicas": 3,
                "memory_mb": 1024,
                "cpu_pct": 45.0,
                "last_deploy_version": "v4.1.2",
                "last_deploy_time": "2025-04-07T18:00:00Z",
            },
            "postgres-primary": {
                "status": "degraded",
                "replicas": 1,
                "memory_mb": 8192,
                "cpu_pct": 92.0,
                "last_deploy_version": "v14.2",
                "last_deploy_time": "2025-03-15T10:00:00Z",
            },
            "api-gateway": {
                "status": "healthy",
                "replicas": 2,
                "memory_mb": 256,
                "cpu_pct": 18.0,
                "last_deploy_version": "v3.1.0",
                "last_deploy_time": "2025-04-05T10:00:00Z",
            },
        },
        resolved_state={
            "user-service": {
                "status": "healthy",
                "replicas": 3,
                "memory_mb": 1024,
                "cpu_pct": 30.0,
                "error_rate_pct": 0.2,
            },
        },
        correct_runbook=[
            "get_service_status",
            "get_recent_logs",
            "get_metrics",
            "restart_service",
            "get_service_status",
            "notify_stakeholders",
            "close_incident",
        ],
        red_herrings=[
            "Memory at 1024MB - normal for this service",
            "Deploy 9h ago - too old to be related",
        ],
        additional_logs={
            "user-service": [
                "2025-04-08T03:18:00 WARN  Slow query detected: 12.3s",
                "2025-04-08T03:19:15 WARN  Connection pool usage: 40/50",
                "2025-04-08T03:20:30 ERROR Query timeout after 30s",
                "2025-04-08T03:21:00 ERROR Connection pool exhausted",
                "2025-04-08T03:22:10 ERROR QueryTimeoutError: query exceeded 30s timeout",
            ],
        },
        additional_metrics={
            "user-service": {
                "memory_mb": [1020.0, 1022.0, 1024.0, 1024.0, 1024.0, 1024.0],
                "cpu_pct": [30.0, 32.0, 35.0, 38.0, 42.0, 45.0],
                "latency_p99": [150.0, 800.0, 2000.0, 3500.0, 4800.0, 5200.0],
                "error_rate": [0.1, 1.0, 3.0, 6.0, 9.0, 12.1],
            },
        },
    ),
    _scenario(
        id="INC-003",
        root_cause="DEPLOY_REGRESSION",
        severity="P1",
        difficulty="easy",
        alert={
            "title": "ALERT: checkout-service error rate > 20%",
            "service": "checkout-service",
            "error_rate_pct": 34.5,
            "log_tail": [
                "2025-04-08T04:01:05 ERROR NullPointerException in CheckoutHandler.process()",
                "2025-04-08T04:01:06 ERROR Failed to complete checkout: null cart reference",
                "2025-04-08T04:01:07 ERROR NullPointerException in CheckoutHandler.process()",
                "2025-04-08T04:01:08 INFO  Deploy v2.5.0 completed 3 minutes ago",
                "2025-04-08T04:01:09 ERROR 500 Internal Server Error on /api/checkout",
            ],
            "metric_snapshot": {
                "memory_mb": 768,
                "cpu_pct": 30.0,
                "latency_p99": 890.0,
                "request_rate": 180.0,
            },
        },
        initial_state={
            "checkout-service": {
                "status": "degraded",
                "replicas": 3,
                "memory_mb": 768,
                "cpu_pct": 30.0,
                "last_deploy_version": "v2.5.0",
                "last_deploy_time": "2025-04-08T03:58:00Z",
            },
            "cart-service": {
                "status": "healthy",
                "replicas": 2,
                "memory_mb": 512,
                "cpu_pct": 20.0,
                "last_deploy_version": "v1.3.0",
                "last_deploy_time": "2025-04-01T12:00:00Z",
            },
            "payment-service": {
                "status": "healthy",
                "replicas": 2,
                "memory_mb": 1024,
                "cpu_pct": 22.0,
                "last_deploy_version": "v2.3.1",
                "last_deploy_time": "2025-04-07T22:00:00Z",
            },
        },
        resolved_state={
            "checkout-service": {
                "status": "healthy",
                "replicas": 3,
                "memory_mb": 768,
                "cpu_pct": 25.0,
                "error_rate_pct": 0.3,
            },
        },
        correct_runbook=[
            "get_service_status",
            "get_recent_logs",
            "rollback_deploy",
            "get_service_status",
            "notify_stakeholders",
            "close_incident",
        ],
        red_herrings=[
            "Cart service is healthy - not the cause",
            "Memory and CPU are normal",
        ],
        additional_logs={
            "checkout-service": [
                "2025-04-08T03:58:00 INFO  Deploying v2.5.0...",
                "2025-04-08T03:58:30 INFO  Deploy v2.5.0 completed successfully",
                "2025-04-08T03:59:00 ERROR NullPointerException in CheckoutHandler.process()",
                "2025-04-08T04:00:00 ERROR Error rate climbing: 15%",
                "2025-04-08T04:01:00 ERROR Error rate climbing: 34%",
            ],
        },
        additional_metrics={
            "checkout-service": {
                "memory_mb": [760.0, 762.0, 765.0, 768.0, 768.0, 768.0],
                "cpu_pct": [22.0, 23.0, 25.0, 28.0, 30.0, 30.0],
                "latency_p99": [100.0, 100.0, 350.0, 600.0, 800.0, 890.0],
                "error_rate": [0.2, 0.2, 5.0, 15.0, 25.0, 34.5],
            },
        },
    ),
    _scenario(
        id="INC-004",
        root_cause="DISK_FULL",
        severity="P2",
        difficulty="easy",
        alert={
            "title": "ALERT: logging-service disk usage > 95%",
            "service": "logging-service",
            "error_rate_pct": 8.5,
            "log_tail": [
                "2025-04-08T05:10:00 ERROR write /var/log/app.log: no space left on device",
                "2025-04-08T05:10:01 ERROR Failed to write audit log entry",
                "2025-04-08T05:10:02 WARN  Disk usage at 97% on /var/log",
                "2025-04-08T05:10:03 ERROR write /var/log/app.log: no space left on device",
                "2025-04-08T05:10:04 ERROR Log rotation failed: insufficient space",
            ],
            "metric_snapshot": {
                "memory_mb": 512,
                "cpu_pct": 15.0,
                "latency_p99": 450.0,
                "request_rate": 200.0,
            },
        },
        initial_state={
            "logging-service": {
                "status": "degraded",
                "replicas": 2,
                "memory_mb": 512,
                "cpu_pct": 15.0,
                "last_deploy_version": "v1.2.0",
                "last_deploy_time": "2025-04-01T08:00:00Z",
            },
            "api-gateway": {
                "status": "healthy",
                "replicas": 2,
                "memory_mb": 256,
                "cpu_pct": 12.0,
                "last_deploy_version": "v3.1.0",
                "last_deploy_time": "2025-04-05T10:00:00Z",
            },
        },
        resolved_state={
            "logging-service": {
                "status": "healthy",
                "replicas": 2,
                "memory_mb": 512,
                "cpu_pct": 10.0,
                "error_rate_pct": 0.0,
            },
        },
        correct_runbook=[
            "get_service_status",
            "get_recent_logs",
            "flush_cache",
            "restart_service",
            "get_service_status",
            "notify_stakeholders",
            "close_incident",
        ],
        red_herrings=[
            "CPU and memory are fine",
            "No recent deploys",
        ],
        additional_logs={
            "logging-service": [
                "2025-04-08T04:00:00 WARN  Disk usage at 85%",
                "2025-04-08T04:30:00 WARN  Disk usage at 90%",
                "2025-04-08T05:00:00 WARN  Disk usage at 95%",
                "2025-04-08T05:05:00 ERROR Log rotation failed",
                "2025-04-08T05:10:00 ERROR no space left on device",
            ],
        },
        additional_metrics={
            "logging-service": {
                "memory_mb": [510.0, 511.0, 512.0, 512.0, 512.0, 512.0],
                "cpu_pct": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0],
                "latency_p99": [50.0, 80.0, 150.0, 250.0, 350.0, 450.0],
                "error_rate": [0.0, 0.5, 2.0, 4.0, 6.0, 8.5],
            },
        },
    ),
    _scenario(
        id="INC-005",
        root_cause="CONFIG_ERROR",
        severity="P2",
        difficulty="easy",
        alert={
            "title": "ALERT: auth-service 500 errors spiking",
            "service": "auth-service",
            "error_rate_pct": 45.0,
            "log_tail": [
                "2025-04-08T06:00:10 ERROR KeyError: 'JWT_SECRET' not found in environment",
                "2025-04-08T06:00:11 ERROR Failed to validate token: missing config",
                "2025-04-08T06:00:12 ERROR 500 Internal Server Error on /api/auth/verify",
                "2025-04-08T06:00:13 ERROR KeyError: 'JWT_SECRET' not found in environment",
                "2025-04-08T06:00:14 WARN  Config reload triggered but key still missing",
            ],
            "metric_snapshot": {
                "memory_mb": 384,
                "cpu_pct": 12.0,
                "latency_p99": 200.0,
                "request_rate": 500.0,
            },
        },
        initial_state={
            "auth-service": {
                "status": "degraded",
                "replicas": 3,
                "memory_mb": 384,
                "cpu_pct": 12.0,
                "last_deploy_version": "v3.0.1",
                "last_deploy_time": "2025-04-08T05:55:00Z",
            },
            "user-service": {
                "status": "healthy",
                "replicas": 3,
                "memory_mb": 1024,
                "cpu_pct": 30.0,
                "last_deploy_version": "v4.1.2",
                "last_deploy_time": "2025-04-07T18:00:00Z",
            },
        },
        resolved_state={
            "auth-service": {
                "status": "healthy",
                "replicas": 3,
                "memory_mb": 384,
                "cpu_pct": 10.0,
                "error_rate_pct": 0.1,
            },
        },
        correct_runbook=[
            "get_service_status",
            "get_recent_logs",
            "update_config",
            "restart_service",
            "get_service_status",
            "notify_stakeholders",
            "close_incident",
        ],
        red_herrings=[
            "Deploy 5 min ago - related but root cause is config, not code",
            "Memory and CPU normal",
        ],
        additional_logs={
            "auth-service": [
                "2025-04-08T05:55:00 INFO  Deploying v3.0.1...",
                "2025-04-08T05:55:30 INFO  Deploy completed",
                "2025-04-08T05:56:00 ERROR KeyError: 'JWT_SECRET'",
                "2025-04-08T05:58:00 ERROR All auth requests failing",
                "2025-04-08T06:00:00 ERROR Error rate at 45%",
            ],
        },
        additional_metrics={
            "auth-service": {
                "memory_mb": [380.0, 382.0, 384.0, 384.0, 384.0, 384.0],
                "cpu_pct": [8.0, 9.0, 10.0, 11.0, 12.0, 12.0],
                "latency_p99": [50.0, 50.0, 100.0, 150.0, 180.0, 200.0],
                "error_rate": [0.1, 0.1, 10.0, 25.0, 38.0, 45.0],
            },
        },
    ),
    # ──────────────────────────────────────────────────────────────────────
    # MEDIUM scenarios (6-10): require investigation, multiple signals
    # ──────────────────────────────────────────────────────────────────────
    _scenario(
        id="INC-006",
        root_cause="NETWORK_PARTITION",
        severity="P1",
        difficulty="medium",
        alert={
            "title": "ALERT: order-service upstream connection failures",
            "service": "order-service",
            "error_rate_pct": 18.7,
            "log_tail": [
                "2025-04-08T07:30:00 ERROR Connection refused: inventory-service:8080",
                "2025-04-08T07:30:01 ERROR Timeout connecting to payment-service:8080",
                "2025-04-08T07:30:02 WARN  Circuit breaker OPEN for inventory-service",
                "2025-04-08T07:30:03 ERROR Connection refused: inventory-service:8080",
                "2025-04-08T07:30:04 ERROR Failed to place order: upstream unavailable",
            ],
            "metric_snapshot": {
                "memory_mb": 768,
                "cpu_pct": 25.0,
                "latency_p99": 30000.0,
                "request_rate": 120.0,
            },
        },
        initial_state={
            "order-service": {
                "status": "degraded",
                "replicas": 3,
                "memory_mb": 768,
                "cpu_pct": 25.0,
                "last_deploy_version": "v2.1.0",
                "last_deploy_time": "2025-04-06T16:00:00Z",
            },
            "inventory-service": {
                "status": "down",
                "replicas": 2,
                "memory_mb": 512,
                "cpu_pct": 0.0,
                "last_deploy_version": "v1.5.0",
                "last_deploy_time": "2025-04-05T14:00:00Z",
            },
            "payment-service": {
                "status": "degraded",
                "replicas": 2,
                "memory_mb": 1024,
                "cpu_pct": 40.0,
                "last_deploy_version": "v2.3.1",
                "last_deploy_time": "2025-04-07T22:00:00Z",
            },
        },
        resolved_state={
            "order-service": {
                "status": "healthy",
                "replicas": 3,
                "memory_mb": 768,
                "cpu_pct": 20.0,
                "error_rate_pct": 0.2,
            },
            "inventory-service": {
                "status": "healthy",
                "replicas": 2,
                "memory_mb": 512,
                "cpu_pct": 15.0,
                "error_rate_pct": 0.1,
            },
        },
        correct_runbook=[
            "get_service_status",
            "get_service_status",
            "get_recent_logs",
            "get_metrics",
            "restart_service",
            "get_service_status",
            "notify_stakeholders",
            "close_incident",
        ],
        red_herrings=[
            "Payment service also degraded - secondary effect",
            "No recent deploys on affected services",
        ],
        additional_logs={
            "order-service": [
                "2025-04-08T07:25:00 WARN  Increased latency to inventory-service",
                "2025-04-08T07:26:00 ERROR Connection timeout to inventory-service",
                "2025-04-08T07:28:00 WARN  Circuit breaker HALF-OPEN",
                "2025-04-08T07:29:00 ERROR Circuit breaker OPEN",
                "2025-04-08T07:30:00 ERROR Connection refused: inventory-service:8080",
            ],
            "inventory-service": [
                "2025-04-08T07:24:55 ERROR Network interface eth0: link down",
                "2025-04-08T07:24:56 ERROR Unable to reach DNS server",
                "2025-04-08T07:24:57 ERROR Health check failed",
                "2025-04-08T07:25:00 ERROR Pod marked NotReady",
                "2025-04-08T07:25:01 INFO  Attempting reconnection...",
            ],
        },
        additional_metrics={
            "order-service": {
                "memory_mb": [760.0, 762.0, 765.0, 768.0, 768.0, 768.0],
                "cpu_pct": [18.0, 19.0, 20.0, 22.0, 24.0, 25.0],
                "latency_p99": [200.0, 500.0, 5000.0, 15000.0, 25000.0, 30000.0],
                "error_rate": [0.2, 2.0, 5.0, 10.0, 15.0, 18.7],
            },
        },
    ),
    _scenario(
        id="INC-007",
        root_cause="DEPENDENCY_FAILURE",
        severity="P2",
        difficulty="medium",
        alert={
            "title": "ALERT: notification-service failing to send emails",
            "service": "notification-service",
            "error_rate_pct": 28.3,
            "log_tail": [
                "2025-04-08T08:15:00 ERROR HTTP 503 from smtp-relay.external.com",
                "2025-04-08T08:15:01 ERROR Failed to send email: upstream service unavailable",
                "2025-04-08T08:15:02 WARN  Retry attempt 3/3 for email delivery",
                "2025-04-08T08:15:03 ERROR HTTP 503 from smtp-relay.external.com",
                "2025-04-08T08:15:04 ERROR Email queue backing up: 1523 pending",
            ],
            "metric_snapshot": {
                "memory_mb": 640,
                "cpu_pct": 35.0,
                "latency_p99": 15000.0,
                "request_rate": 80.0,
            },
        },
        initial_state={
            "notification-service": {
                "status": "degraded",
                "replicas": 2,
                "memory_mb": 640,
                "cpu_pct": 35.0,
                "last_deploy_version": "v2.0.3",
                "last_deploy_time": "2025-04-06T09:00:00Z",
            },
            "smtp-relay": {
                "status": "down",
                "replicas": 1,
                "memory_mb": 256,
                "cpu_pct": 0.0,
                "last_deploy_version": "external",
                "last_deploy_time": "N/A",
            },
            "user-service": {
                "status": "healthy",
                "replicas": 3,
                "memory_mb": 1024,
                "cpu_pct": 28.0,
                "last_deploy_version": "v4.1.2",
                "last_deploy_time": "2025-04-07T18:00:00Z",
            },
        },
        resolved_state={
            "notification-service": {
                "status": "healthy",
                "replicas": 2,
                "memory_mb": 640,
                "cpu_pct": 20.0,
                "error_rate_pct": 0.5,
            },
        },
        correct_runbook=[
            "get_service_status",
            "get_recent_logs",
            "get_metrics",
            "flush_cache",
            "restart_service",
            "get_service_status",
            "notify_stakeholders",
            "close_incident",
        ],
        red_herrings=[
            "CPU at 35% - elevated due to retry loops, not root cause",
            "Memory growing slowly - queue buildup, not leak",
        ],
        additional_logs={
            "notification-service": [
                "2025-04-08T08:00:00 WARN  SMTP relay response time: 5s (threshold: 2s)",
                "2025-04-08T08:05:00 ERROR First 503 from smtp-relay",
                "2025-04-08T08:10:00 WARN  Email queue depth: 500",
                "2025-04-08T08:12:00 ERROR All retries exhausted for batch",
                "2025-04-08T08:15:00 ERROR Queue depth: 1523",
            ],
        },
        additional_metrics={
            "notification-service": {
                "memory_mb": [580.0, 590.0, 600.0, 610.0, 625.0, 640.0],
                "cpu_pct": [15.0, 18.0, 22.0, 28.0, 32.0, 35.0],
                "latency_p99": [200.0, 2000.0, 5000.0, 10000.0, 13000.0, 15000.0],
                "error_rate": [0.5, 3.0, 8.0, 15.0, 22.0, 28.3],
            },
        },
    ),
    _scenario(
        id="INC-008",
        root_cause="CERTIFICATE_EXPIRED",
        severity="P1",
        difficulty="medium",
        alert={
            "title": "ALERT: api-gateway TLS handshake failures",
            "service": "api-gateway",
            "error_rate_pct": 100.0,
            "log_tail": [
                "2025-04-08T00:00:05 ERROR SSL: certificate has expired",
                "2025-04-08T00:00:06 ERROR TLS handshake failed: certificate verify failed",
                "2025-04-08T00:00:07 ERROR Unable to establish secure connection",
                "2025-04-08T00:00:08 ERROR All HTTPS requests failing",
                "2025-04-08T00:00:09 ERROR Certificate expired at 2025-04-07T23:59:59Z",
            ],
            "metric_snapshot": {
                "memory_mb": 256,
                "cpu_pct": 5.0,
                "latency_p99": 0.0,
                "request_rate": 0.0,
            },
        },
        initial_state={
            "api-gateway": {
                "status": "down",
                "replicas": 2,
                "memory_mb": 256,
                "cpu_pct": 5.0,
                "last_deploy_version": "v3.1.0",
                "last_deploy_time": "2025-04-05T10:00:00Z",
            },
            "user-service": {
                "status": "healthy",
                "replicas": 3,
                "memory_mb": 1024,
                "cpu_pct": 5.0,
                "last_deploy_version": "v4.1.2",
                "last_deploy_time": "2025-04-07T18:00:00Z",
            },
            "payment-service": {
                "status": "healthy",
                "replicas": 2,
                "memory_mb": 1024,
                "cpu_pct": 5.0,
                "last_deploy_version": "v2.3.1",
                "last_deploy_time": "2025-04-07T22:00:00Z",
            },
        },
        resolved_state={
            "api-gateway": {
                "status": "healthy",
                "replicas": 2,
                "memory_mb": 256,
                "cpu_pct": 15.0,
                "error_rate_pct": 0.0,
            },
        },
        correct_runbook=[
            "get_service_status",
            "get_recent_logs",
            "update_config",
            "restart_service",
            "get_service_status",
            "notify_stakeholders",
            "close_incident",
        ],
        red_herrings=[
            "All backend services healthy - they're fine, only gateway is broken",
            "Low CPU/memory - service isn't doing work because all requests fail at TLS",
        ],
        additional_logs={
            "api-gateway": [
                "2025-04-07T23:59:50 INFO  Certificate expiry warning: 10 seconds",
                "2025-04-07T23:59:59 ERROR Certificate expired",
                "2025-04-08T00:00:00 ERROR TLS handshake failures starting",
                "2025-04-08T00:00:01 ERROR All inbound HTTPS traffic dropped",
                "2025-04-08T00:00:05 ERROR 100% error rate on all endpoints",
            ],
        },
        additional_metrics={
            "api-gateway": {
                "memory_mb": [256.0, 256.0, 256.0, 256.0, 256.0, 256.0],
                "cpu_pct": [18.0, 18.0, 5.0, 5.0, 5.0, 5.0],
                "latency_p99": [80.0, 80.0, 0.0, 0.0, 0.0, 0.0],
                "error_rate": [0.1, 0.1, 100.0, 100.0, 100.0, 100.0],
            },
        },
    ),
    _scenario(
        id="INC-009",
        root_cause="RATE_LIMIT_HIT",
        severity="P2",
        difficulty="medium",
        alert={
            "title": "ALERT: search-service receiving 429 from Elasticsearch",
            "service": "search-service",
            "error_rate_pct": 15.2,
            "log_tail": [
                "2025-04-08T09:45:00 ERROR HTTP 429 Too Many Requests from elasticsearch:9200",
                "2025-04-08T09:45:01 WARN  Search request rejected: rate limit exceeded",
                "2025-04-08T09:45:02 ERROR Bulk indexing failed: 429 response",
                "2025-04-08T09:45:03 WARN  Circuit breaker tripped for ES cluster",
                "2025-04-08T09:45:04 ERROR Search results degraded: using stale cache",
            ],
            "metric_snapshot": {
                "memory_mb": 896,
                "cpu_pct": 55.0,
                "latency_p99": 3500.0,
                "request_rate": 800.0,
            },
        },
        initial_state={
            "search-service": {
                "status": "degraded",
                "replicas": 4,
                "memory_mb": 896,
                "cpu_pct": 55.0,
                "last_deploy_version": "v3.2.1",
                "last_deploy_time": "2025-04-07T20:00:00Z",
            },
            "elasticsearch": {
                "status": "degraded",
                "replicas": 3,
                "memory_mb": 16384,
                "cpu_pct": 88.0,
                "last_deploy_version": "v8.12.0",
                "last_deploy_time": "2025-03-20T08:00:00Z",
            },
        },
        resolved_state={
            "search-service": {
                "status": "healthy",
                "replicas": 4,
                "memory_mb": 896,
                "cpu_pct": 30.0,
                "error_rate_pct": 0.3,
            },
        },
        correct_runbook=[
            "get_service_status",
            "get_recent_logs",
            "get_metrics",
            "scale_service",
            "flush_cache",
            "get_service_status",
            "notify_stakeholders",
            "close_incident",
        ],
        red_herrings=[
            "ES cluster CPU at 88% - consequence of rate limiting, not cause",
            "Deploy yesterday - too old to be cause",
        ],
        additional_logs={
            "search-service": [
                "2025-04-08T09:30:00 INFO  Request rate increasing: 600 req/s",
                "2025-04-08T09:35:00 WARN  Request rate: 700 req/s (threshold: 750)",
                "2025-04-08T09:40:00 ERROR First 429 from ES cluster",
                "2025-04-08T09:42:00 WARN  Circuit breaker half-open",
                "2025-04-08T09:45:00 ERROR Rate limit fully exceeded",
            ],
        },
        additional_metrics={
            "search-service": {
                "memory_mb": [850.0, 860.0, 870.0, 880.0, 890.0, 896.0],
                "cpu_pct": [30.0, 35.0, 40.0, 45.0, 50.0, 55.0],
                "latency_p99": [200.0, 500.0, 1000.0, 2000.0, 3000.0, 3500.0],
                "error_rate": [0.2, 1.0, 4.0, 8.0, 12.0, 15.2],
            },
        },
    ),
    _scenario(
        id="INC-010",
        root_cause="MEMORY_LEAK",
        severity="P2",
        difficulty="medium",
        alert={
            "title": "ALERT: analytics-service gradual memory increase",
            "service": "analytics-service",
            "error_rate_pct": 5.2,
            "log_tail": [
                "2025-04-08T10:30:00 WARN  Heap usage at 82% (was 45% 6h ago)",
                "2025-04-08T10:30:01 WARN  GC frequency increased: every 30s",
                "2025-04-08T10:30:02 INFO  Request processing slowing down",
                "2025-04-08T10:30:03 WARN  Connection objects not being released",
                "2025-04-08T10:30:04 WARN  Object count growing: HttpClient instances = 4523",
            ],
            "metric_snapshot": {
                "memory_mb": 3400,
                "cpu_pct": 65.0,
                "latency_p99": 1800.0,
                "request_rate": 150.0,
            },
        },
        initial_state={
            "analytics-service": {
                "status": "degraded",
                "replicas": 2,
                "memory_mb": 3400,
                "cpu_pct": 65.0,
                "last_deploy_version": "v1.9.0",
                "last_deploy_time": "2025-04-06T11:00:00Z",
            },
            "data-pipeline": {
                "status": "healthy",
                "replicas": 3,
                "memory_mb": 2048,
                "cpu_pct": 40.0,
                "last_deploy_version": "v2.5.0",
                "last_deploy_time": "2025-04-04T09:00:00Z",
            },
        },
        resolved_state={
            "analytics-service": {
                "status": "healthy",
                "replicas": 3,
                "memory_mb": 1200,
                "cpu_pct": 30.0,
                "error_rate_pct": 0.2,
            },
        },
        correct_runbook=[
            "get_service_status",
            "get_metrics",
            "get_recent_logs",
            "restart_service",
            "scale_service",
            "get_service_status",
            "notify_stakeholders",
            "close_incident",
        ],
        red_herrings=[
            "CPU elevated - secondary to GC activity",
            "Deploy 2 days ago - leak was introduced then but gradual",
        ],
        additional_logs={
            "analytics-service": [
                "2025-04-08T04:00:00 INFO  Memory: 1800MB (normal)",
                "2025-04-08T06:00:00 WARN  Memory: 2200MB (growing)",
                "2025-04-08T08:00:00 WARN  Memory: 2800MB (growing)",
                "2025-04-08T09:00:00 WARN  Memory: 3100MB (critical)",
                "2025-04-08T10:30:00 WARN  Memory: 3400MB (danger)",
            ],
        },
        additional_metrics={
            "analytics-service": {
                "memory_mb": [1800.0, 2200.0, 2600.0, 2900.0, 3200.0, 3400.0],
                "cpu_pct": [30.0, 35.0, 42.0, 50.0, 58.0, 65.0],
                "latency_p99": [200.0, 350.0, 600.0, 1000.0, 1400.0, 1800.0],
                "error_rate": [0.1, 0.5, 1.5, 3.0, 4.0, 5.2],
            },
        },
    ),
    # ──────────────────────────────────────────────────────────────────────
    # HARD scenarios (11-15): red herrings, multi-signal, require reasoning
    # ──────────────────────────────────────────────────────────────────────
    _scenario(
        id="INC-011",
        root_cause="DB_TIMEOUT",
        severity="P1",
        difficulty="hard",
        alert={
            "title": "ALERT: order-service high CPU and slow responses",
            "service": "order-service",
            "error_rate_pct": 22.0,
            "log_tail": [
                "2025-04-08T11:00:00 WARN  CPU at 92% - request threads piling up",
                "2025-04-08T11:00:01 ERROR Request timeout after 30s on /api/orders",
                "2025-04-08T11:00:02 WARN  Thread pool exhausted: 200/200 threads busy",
                "2025-04-08T11:00:03 ERROR Waiting for DB connection: pool full",
                "2025-04-08T11:00:04 ERROR QueryTimeoutError on orders table",
            ],
            "metric_snapshot": {
                "memory_mb": 2048,
                "cpu_pct": 92.0,
                "latency_p99": 32000.0,
                "request_rate": 50.0,
            },
        },
        initial_state={
            "order-service": {
                "status": "degraded",
                "replicas": 3,
                "memory_mb": 2048,
                "cpu_pct": 92.0,
                "last_deploy_version": "v2.1.0",
                "last_deploy_time": "2025-04-06T16:00:00Z",
            },
            "postgres-primary": {
                "status": "degraded",
                "replicas": 1,
                "memory_mb": 8192,
                "cpu_pct": 95.0,
                "last_deploy_version": "v14.2",
                "last_deploy_time": "2025-03-15T10:00:00Z",
            },
            "redis-cache": {
                "status": "healthy",
                "replicas": 3,
                "memory_mb": 4096,
                "cpu_pct": 15.0,
                "last_deploy_version": "v7.2",
                "last_deploy_time": "2025-03-20T08:00:00Z",
            },
        },
        resolved_state={
            "order-service": {
                "status": "healthy",
                "replicas": 3,
                "memory_mb": 2048,
                "cpu_pct": 35.0,
                "error_rate_pct": 0.3,
            },
        },
        correct_runbook=[
            "get_service_status",
            "get_recent_logs",
            "get_metrics",
            "restart_service",
            "get_service_status",
            "notify_stakeholders",
            "write_post_mortem",
            "close_incident",
        ],
        red_herrings=[
            "CPU at 92% - looks like CPU issue but caused by DB timeout thread pile-up",
            "Deploy 2 days ago - unrelated",
            "Redis cache healthy - not the bottleneck",
        ],
        additional_logs={
            "order-service": [
                "2025-04-08T10:45:00 WARN  DB query time increasing: avg 5s",
                "2025-04-08T10:50:00 ERROR DB connection pool: 180/200 in use",
                "2025-04-08T10:55:00 ERROR Threads waiting for DB: 150",
                "2025-04-08T10:58:00 WARN  CPU climbing due to thread contention",
                "2025-04-08T11:00:00 ERROR CPU 92% - all threads blocked on DB",
            ],
            "postgres-primary": [
                "2025-04-08T10:40:00 WARN  Long-running query detected: 45s",
                "2025-04-08T10:45:00 ERROR Lock contention on orders table",
                "2025-04-08T10:50:00 WARN  Autovacuum running on large table",
                "2025-04-08T10:55:00 ERROR max_connections nearly exhausted",
                "2025-04-08T11:00:00 ERROR Query timeout threshold exceeded",
            ],
        },
        additional_metrics={
            "order-service": {
                "memory_mb": [2000.0, 2010.0, 2020.0, 2030.0, 2040.0, 2048.0],
                "cpu_pct": [35.0, 45.0, 60.0, 75.0, 85.0, 92.0],
                "latency_p99": [200.0, 2000.0, 8000.0, 15000.0, 25000.0, 32000.0],
                "error_rate": [0.3, 2.0, 6.0, 12.0, 18.0, 22.0],
            },
        },
    ),
    _scenario(
        id="INC-012",
        root_cause="CONFIG_ERROR",
        severity="P1",
        difficulty="hard",
        alert={
            "title": "ALERT: payment-service 500 errors after scheduled maintenance",
            "service": "payment-service",
            "error_rate_pct": 67.0,
            "log_tail": [
                "2025-04-08T12:05:00 ERROR Connection to stripe-api failed: invalid API key",
                "2025-04-08T12:05:01 ERROR Payment processing failed: authentication error",
                "2025-04-08T12:05:02 INFO  Recent deploy: v2.3.2 (30 min ago)",
                "2025-04-08T12:05:03 ERROR Stripe API: 401 Unauthorized",
                "2025-04-08T12:05:04 ERROR Revenue loss: estimated $4,200/min",
            ],
            "metric_snapshot": {
                "memory_mb": 1024,
                "cpu_pct": 18.0,
                "latency_p99": 500.0,
                "request_rate": 300.0,
            },
        },
        initial_state={
            "payment-service": {
                "status": "degraded",
                "replicas": 3,
                "memory_mb": 1024,
                "cpu_pct": 18.0,
                "last_deploy_version": "v2.3.2",
                "last_deploy_time": "2025-04-08T11:35:00Z",
            },
            "checkout-service": {
                "status": "degraded",
                "replicas": 3,
                "memory_mb": 768,
                "cpu_pct": 30.0,
                "last_deploy_version": "v2.4.9",
                "last_deploy_time": "2025-04-07T15:00:00Z",
            },
            "order-service": {
                "status": "healthy",
                "replicas": 3,
                "memory_mb": 2048,
                "cpu_pct": 25.0,
                "last_deploy_version": "v2.1.0",
                "last_deploy_time": "2025-04-06T16:00:00Z",
            },
        },
        resolved_state={
            "payment-service": {
                "status": "healthy",
                "replicas": 3,
                "memory_mb": 1024,
                "cpu_pct": 20.0,
                "error_rate_pct": 0.1,
            },
        },
        correct_runbook=[
            "get_service_status",
            "get_recent_logs",
            "get_metrics",
            "update_config",
            "restart_service",
            "get_service_status",
            "notify_stakeholders",
            "write_post_mortem",
            "close_incident",
        ],
        red_herrings=[
            "Deploy 30 min ago - deploy itself was fine, but config was rotated during maintenance",
            "Checkout service degraded - cascading failure from payment, not root cause",
            "Low CPU/memory - misleading, issue is authentication not resource",
        ],
        additional_logs={
            "payment-service": [
                "2025-04-08T11:35:00 INFO  Deploy v2.3.2 completed",
                "2025-04-08T11:40:00 INFO  Scheduled key rotation started",
                "2025-04-08T11:45:00 INFO  New Stripe API key deployed to vault",
                "2025-04-08T11:50:00 ERROR Config not reloaded - using stale key",
                "2025-04-08T12:05:00 ERROR Stripe API: 401 Unauthorized",
            ],
        },
        additional_metrics={
            "payment-service": {
                "memory_mb": [1020.0, 1022.0, 1024.0, 1024.0, 1024.0, 1024.0],
                "cpu_pct": [20.0, 20.0, 18.0, 18.0, 18.0, 18.0],
                "latency_p99": [120.0, 120.0, 300.0, 400.0, 480.0, 500.0],
                "error_rate": [0.1, 0.1, 15.0, 35.0, 55.0, 67.0],
            },
        },
    ),
    _scenario(
        id="INC-013",
        root_cause="MEMORY_LEAK",
        severity="P1",
        difficulty="hard",
        alert={
            "title": "ALERT: api-gateway high memory and intermittent 502s",
            "service": "api-gateway",
            "error_rate_pct": 8.5,
            "log_tail": [
                "2025-04-08T13:00:00 WARN  Memory at 89% - gradual increase over 12h",
                "2025-04-08T13:00:01 ERROR 502 Bad Gateway: upstream timeout",
                "2025-04-08T13:00:02 INFO  Recent config change pushed 2h ago",
                "2025-04-08T13:00:03 WARN  GC pause: 800ms (threshold: 200ms)",
                "2025-04-08T13:00:04 ERROR Connection pool leak detected: 2847 unreleased",
            ],
            "metric_snapshot": {
                "memory_mb": 3600,
                "cpu_pct": 70.0,
                "latency_p99": 4500.0,
                "request_rate": 1200.0,
            },
        },
        initial_state={
            "api-gateway": {
                "status": "degraded",
                "replicas": 2,
                "memory_mb": 3600,
                "cpu_pct": 70.0,
                "last_deploy_version": "v3.2.0",
                "last_deploy_time": "2025-04-07T16:00:00Z",
            },
            "user-service": {
                "status": "healthy",
                "replicas": 3,
                "memory_mb": 1024,
                "cpu_pct": 30.0,
                "last_deploy_version": "v4.1.2",
                "last_deploy_time": "2025-04-07T18:00:00Z",
            },
            "payment-service": {
                "status": "healthy",
                "replicas": 2,
                "memory_mb": 1024,
                "cpu_pct": 22.0,
                "last_deploy_version": "v2.3.1",
                "last_deploy_time": "2025-04-07T22:00:00Z",
            },
        },
        resolved_state={
            "api-gateway": {
                "status": "healthy",
                "replicas": 3,
                "memory_mb": 800,
                "cpu_pct": 25.0,
                "error_rate_pct": 0.1,
            },
        },
        correct_runbook=[
            "get_service_status",
            "get_metrics",
            "get_recent_logs",
            "restart_service",
            "scale_service",
            "get_service_status",
            "notify_stakeholders",
            "write_post_mortem",
            "close_incident",
        ],
        red_herrings=[
            "Config change 2h ago - looks like config error but is actually unrelated",
            "502 errors look like network issue but caused by memory pressure",
            "CPU at 70% - secondary GC overhead, not root cause",
        ],
        additional_logs={
            "api-gateway": [
                "2025-04-08T01:00:00 INFO  Memory: 1200MB (post-restart baseline)",
                "2025-04-08T05:00:00 WARN  Memory: 2000MB (growing steadily)",
                "2025-04-08T09:00:00 WARN  Memory: 2800MB (leak suspected)",
                "2025-04-08T11:00:00 INFO  Config change: updated rate limits",
                "2025-04-08T13:00:00 ERROR Memory: 3600MB (critical)",
            ],
        },
        additional_metrics={
            "api-gateway": {
                "memory_mb": [1200.0, 1600.0, 2000.0, 2500.0, 3100.0, 3600.0],
                "cpu_pct": [20.0, 28.0, 38.0, 50.0, 60.0, 70.0],
                "latency_p99": [80.0, 150.0, 400.0, 1200.0, 2800.0, 4500.0],
                "error_rate": [0.0, 0.2, 1.0, 3.0, 5.5, 8.5],
            },
        },
    ),
    _scenario(
        id="INC-014",
        root_cause="DEPLOY_REGRESSION",
        severity="P1",
        difficulty="hard",
        alert={
            "title": "ALERT: inventory-service data inconsistency detected",
            "service": "inventory-service",
            "error_rate_pct": 12.0,
            "log_tail": [
                "2025-04-08T14:15:00 ERROR Stock count mismatch: DB says 0, cache says 50",
                "2025-04-08T14:15:01 ERROR Order placed for out-of-stock item SKU-7842",
                "2025-04-08T14:15:02 WARN  Cache invalidation not triggering on write",
                "2025-04-08T14:15:03 ERROR Data integrity violation in inventory_updates",
                "2025-04-08T14:15:04 INFO  Memory at 85% - cache growing unbounded",
            ],
            "metric_snapshot": {
                "memory_mb": 3400,
                "cpu_pct": 55.0,
                "latency_p99": 1200.0,
                "request_rate": 400.0,
            },
        },
        initial_state={
            "inventory-service": {
                "status": "degraded",
                "replicas": 3,
                "memory_mb": 3400,
                "cpu_pct": 55.0,
                "last_deploy_version": "v1.6.0",
                "last_deploy_time": "2025-04-08T13:45:00Z",
            },
            "order-service": {
                "status": "healthy",
                "replicas": 3,
                "memory_mb": 2048,
                "cpu_pct": 30.0,
                "last_deploy_version": "v2.1.0",
                "last_deploy_time": "2025-04-06T16:00:00Z",
            },
            "redis-cache": {
                "status": "healthy",
                "replicas": 3,
                "memory_mb": 4096,
                "cpu_pct": 20.0,
                "last_deploy_version": "v7.2",
                "last_deploy_time": "2025-03-20T08:00:00Z",
            },
        },
        resolved_state={
            "inventory-service": {
                "status": "healthy",
                "replicas": 3,
                "memory_mb": 1500,
                "cpu_pct": 25.0,
                "error_rate_pct": 0.1,
            },
        },
        correct_runbook=[
            "get_service_status",
            "get_recent_logs",
            "get_metrics",
            "rollback_deploy",
            "flush_cache",
            "get_service_status",
            "notify_stakeholders",
            "write_post_mortem",
            "close_incident",
        ],
        red_herrings=[
            "Memory at 85% looks like memory leak - actually unbounded cache from broken invalidation",
            "Redis cache healthy - the bug is in the service's cache invalidation code, not Redis",
            "CPU moderate - not a resource issue",
        ],
        additional_logs={
            "inventory-service": [
                "2025-04-08T13:45:00 INFO  Deploy v1.6.0 completed",
                "2025-04-08T13:50:00 INFO  Processing inventory updates normally",
                "2025-04-08T14:00:00 WARN  Cache miss rate dropped to 0% (suspicious)",
                "2025-04-08T14:10:00 ERROR Stock count mismatch detected",
                "2025-04-08T14:15:00 ERROR Multiple data integrity violations",
            ],
        },
        additional_metrics={
            "inventory-service": {
                "memory_mb": [1500.0, 1800.0, 2200.0, 2700.0, 3100.0, 3400.0],
                "cpu_pct": [25.0, 30.0, 35.0, 42.0, 48.0, 55.0],
                "latency_p99": [100.0, 200.0, 400.0, 700.0, 1000.0, 1200.0],
                "error_rate": [0.1, 0.5, 2.0, 5.0, 8.0, 12.0],
            },
        },
    ),
    _scenario(
        id="INC-015",
        root_cause="OOM",
        severity="P1",
        difficulty="hard",
        alert={
            "title": "ALERT: report-service pods restarting in crash loop",
            "service": "report-service",
            "error_rate_pct": 55.0,
            "log_tail": [
                "2025-04-08T15:30:00 ERROR CrashLoopBackOff: container restarted 5 times",
                "2025-04-08T15:30:01 ERROR Last exit code: 137 (OOMKilled)",
                "2025-04-08T15:30:02 INFO  Large report generation request queued",
                "2025-04-08T15:30:03 ERROR Memory limit 4096MB exceeded",
                "2025-04-08T15:30:04 WARN  Batch job running: monthly financial report",
            ],
            "metric_snapshot": {
                "memory_mb": 4096,
                "cpu_pct": 45.0,
                "latency_p99": 60000.0,
                "request_rate": 10.0,
            },
        },
        initial_state={
            "report-service": {
                "status": "down",
                "replicas": 2,
                "memory_mb": 4096,
                "cpu_pct": 45.0,
                "last_deploy_version": "v1.2.0",
                "last_deploy_time": "2025-04-03T09:00:00Z",
            },
            "data-warehouse": {
                "status": "healthy",
                "replicas": 1,
                "memory_mb": 32768,
                "cpu_pct": 60.0,
                "last_deploy_version": "v3.0.0",
                "last_deploy_time": "2025-03-25T12:00:00Z",
            },
            "api-gateway": {
                "status": "healthy",
                "replicas": 2,
                "memory_mb": 256,
                "cpu_pct": 12.0,
                "last_deploy_version": "v3.1.0",
                "last_deploy_time": "2025-04-05T10:00:00Z",
            },
        },
        resolved_state={
            "report-service": {
                "status": "healthy",
                "replicas": 4,
                "memory_mb": 2048,
                "cpu_pct": 30.0,
                "error_rate_pct": 0.0,
            },
        },
        correct_runbook=[
            "get_service_status",
            "get_recent_logs",
            "get_metrics",
            "scale_service",
            "restart_service",
            "get_service_status",
            "notify_stakeholders",
            "write_post_mortem",
            "close_incident",
        ],
        red_herrings=[
            "No recent deploy - OOM triggered by batch job, not code change",
            "Data warehouse CPU at 60% - normal for report generation",
            "Batch job is expected - the issue is memory limits, not the job itself",
        ],
        additional_logs={
            "report-service": [
                "2025-04-08T15:00:00 INFO  Monthly report batch job started",
                "2025-04-08T15:10:00 INFO  Processing 2.3M rows for financial report",
                "2025-04-08T15:20:00 WARN  Memory at 75%: 3072MB used",
                "2025-04-08T15:25:00 ERROR Memory at 95%: 3891MB used",
                "2025-04-08T15:28:00 ERROR OOMKilled: container exceeded 4096MB limit",
            ],
        },
        additional_metrics={
            "report-service": {
                "memory_mb": [1024.0, 1800.0, 2500.0, 3200.0, 3800.0, 4096.0],
                "cpu_pct": [10.0, 20.0, 30.0, 38.0, 42.0, 45.0],
                "latency_p99": [500.0, 5000.0, 15000.0, 30000.0, 45000.0, 60000.0],
                "error_rate": [0.0, 0.0, 5.0, 20.0, 40.0, 55.0],
            },
        },
    ),
]


def get_scenarios_by_difficulty(difficulty: str) -> list[dict[str, Any]]:
    """Get scenarios filtered by difficulty level."""
    return [s for s in INCIDENT_SCENARIOS if s["difficulty"] == difficulty]


def get_scenario_by_id(scenario_id: str) -> dict[str, Any] | None:
    """Get a specific scenario by ID."""
    for s in INCIDENT_SCENARIOS:
        if s["id"] == scenario_id:
            return s
    return None
