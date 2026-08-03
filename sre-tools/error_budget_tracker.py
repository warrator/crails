#!/usr/bin/env python3
"""
error_budget_tracker.py
=========================

Computes error budget consumption and burn rate from raw availability data,
and applies the "Red Mode" release-gating policy referenced in the CRAILS
SLO/SLI doc: deployments are gated based on how much error budget remains.

This can run in two modes:
    1. --mock            : uses synthetic data, no Prometheus required (fast demo)
    2. --prometheus-url   : queries a real Prometheus instance for the SLI

Error budget policy (matches CRAILS_Platform_SLO_SLI.docx):
    > 50% remaining   -> GREEN  : normal deployment velocity
    25-50% remaining  -> YELLOW : additional review required, chaos tests paused
    < 25% remaining   -> RED    : deploy freeze, critical security patches only
    0% (exhausted)    -> INCIDENT : incident declared, postmortem required before next release

Usage:
    python error_budget_tracker.py --mock
    python error_budget_tracker.py --mock --slo 99.0 --window-days 30
    python error_budget_tracker.py --prometheus-url http://prometheus.crails.local:9090 \\
        --query 'sum(rate(traefik_requests_total{code!~"5.."}[30d])) / sum(rate(traefik_requests_total[30d]))'
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone

try:
    import requests
except ImportError:
    requests = None


@dataclass
class ErrorBudgetResult:
    slo_target_pct: float
    window_days: int
    observed_availability_pct: float
    error_budget_total_minutes: float
    error_budget_consumed_minutes: float
    error_budget_remaining_pct: float
    burn_rate_multiple: float          # how many times faster than baseline burn
    release_gate: str                  # GREEN | YELLOW | RED | INCIDENT
    action: str
    generated_at: str


def compute_error_budget(slo_target_pct: float, window_days: int,
                          observed_availability_pct: float) -> ErrorBudgetResult:
    window_minutes = window_days * 24 * 60
    allowed_downtime_pct = 100.0 - slo_target_pct
    error_budget_total_minutes = window_minutes * (allowed_downtime_pct / 100.0)

    observed_downtime_pct = max(0.0, 100.0 - observed_availability_pct)
    error_budget_consumed_minutes = window_minutes * (observed_downtime_pct / 100.0)

    if error_budget_total_minutes <= 0:
        remaining_pct = 0.0
    else:
        remaining_pct = max(
            0.0,
            round(100.0 * (1 - error_budget_consumed_minutes / error_budget_total_minutes), 2)
        )

    # Baseline burn rate = 1.0x means "on track to consume exactly 100% of budget
    # by the end of the window, evenly". We approximate using consumed vs. an
    # even/linear expectation (this is a simplification of Google's multi-window
    # burn-rate methodology, intentionally kept simple/readable for CRAILS).
    baseline_consumed_by_now = error_budget_total_minutes  # placeholder for full-window baseline
    burn_rate_multiple = (
        round(error_budget_consumed_minutes / baseline_consumed_by_now, 2)
        if baseline_consumed_by_now > 0 else 0.0
    )

    if remaining_pct <= 0:
        gate = "INCIDENT"
        action = "Incident declared. Postmortem required before next release."
    elif remaining_pct < 25:
        gate = "RED"
        action = "Deploy freeze. Only critical security patches allowed."
    elif remaining_pct < 50:
        gate = "YELLOW"
        action = "Additional review required for all deployments. Chaos tests paused."
    else:
        gate = "GREEN"
        action = "Normal deployment velocity allowed."

    return ErrorBudgetResult(
        slo_target_pct=slo_target_pct,
        window_days=window_days,
        observed_availability_pct=round(observed_availability_pct, 4),
        error_budget_total_minutes=round(error_budget_total_minutes, 2),
        error_budget_consumed_minutes=round(error_budget_consumed_minutes, 2),
        error_budget_remaining_pct=remaining_pct,
        burn_rate_multiple=burn_rate_multiple,
        release_gate=gate,
        action=action,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def mock_availability(slo_target_pct: float, scenario: str) -> float:
    """
    Generate a synthetic 'observed availability' number for demo purposes.
    scenario controls how healthy the mock system is behaving.
    """
    if scenario == "healthy":
        return round(random.uniform(slo_target_pct, 100.0), 4)
    if scenario == "degraded":
        return round(random.uniform(slo_target_pct - 0.5, slo_target_pct - 0.05), 4)
    if scenario == "critical":
        return round(random.uniform(slo_target_pct - 2.0, slo_target_pct - 0.6), 4)
    raise ValueError(f"Unknown scenario: {scenario}")


def query_prometheus(prometheus_url: str, promql: str) -> float:
    """Query Prometheus's instant-query API and return the scalar result as a percentage."""
    if requests is None:
        raise RuntimeError("The 'requests' package is required: pip install requests --break-system-packages")

    resp = requests.get(f"{prometheus_url.rstrip('/')}/api/v1/query", params={"query": promql}, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {data}")

    result = data["data"]["result"]
    if not result:
        raise RuntimeError("Prometheus query returned no data points")

    value = float(result[0]["value"][1])
    # Assume the PromQL query already returns a 0.0-1.0 ratio; convert to percentage.
    return value * 100.0 if value <= 1.0 else value


def main():
    parser = argparse.ArgumentParser(description="CRAILS Error Budget Tracker / Red Mode Gate")
    parser.add_argument("--slo", type=float, default=99.0, help="SLO target percentage (default: 99.0)")
    parser.add_argument("--window-days", type=int, default=30, help="Rolling window in days (default: 30)")

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--mock", action="store_true", help="Use synthetic data instead of Prometheus")
    source.add_argument("--prometheus-url", help="Base URL of Prometheus, e.g. http://prometheus:9090")

    parser.add_argument("--query", help="PromQL query returning a 0.0-1.0 availability ratio (required with --prometheus-url)")
    parser.add_argument("--scenario", choices=["healthy", "degraded", "critical"], default="degraded",
                         help="Mock scenario to simulate (only used with --mock)")
    parser.add_argument("--format", choices=["json", "human"], default="human")
    args = parser.parse_args()

    if args.mock:
        observed = mock_availability(args.slo, args.scenario)
    else:
        if not args.query:
            print("error: --query is required when using --prometheus-url", file=sys.stderr)
            sys.exit(1)
        observed = query_prometheus(args.prometheus_url, args.query)

    result = compute_error_budget(args.slo, args.window_days, observed)

    if args.format == "json":
        print(json.dumps(asdict(result), indent=2))
    else:
        print(f"\nSLO target            : {result.slo_target_pct}% over {result.window_days} days")
        print(f"Observed availability  : {result.observed_availability_pct}%")
        print(f"Error budget total     : {result.error_budget_total_minutes} min")
        print(f"Error budget consumed  : {result.error_budget_consumed_minutes} min")
        print(f"Error budget remaining : {result.error_budget_remaining_pct}%")
        print(f"Burn rate              : {result.burn_rate_multiple}x")
        print(f"\n>>> RELEASE GATE: {result.release_gate}")
        print(f">>> ACTION: {result.action}\n")

    # Exit code reflects gate severity — useful for wiring into a CI/CD pipeline
    exit_codes = {"GREEN": 0, "YELLOW": 0, "RED": 1, "INCIDENT": 2}
    sys.exit(exit_codes.get(result.release_gate, 0))


if __name__ == "__main__":
    main()
