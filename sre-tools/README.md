# CRAILS — SRE-Grade Python Toolkit

Standalone, testable Python implementations of the reliability-engineering
patterns used on the CRAILS platform (and referenced in production work at
Visa): criticality scoring, blast-radius analysis, circuit breaking, and
error-budget-driven release gating.

Each script is self-contained, dependency-light, and runnable both as a
CLI and as an importable library — so you can demo them standalone in an
interview, or wire them into the rest of CRAILS (K8s annotations, Prometheus,
ArgoCD gates).

## Contents

| Script | What it does |
|---|---|
| `criticality_engine.py` | Scores services 0.0–1.0 on traffic share, dependency fan-in, and incident history; maps the score to a tier (tier-1/2/3) with an SLA; supports manual override; can emit `kubectl`-ready annotation patches. |
| `blast_radius.py` | Walks a service dependency graph (YAML) and computes every service transitively impacted by a given failure, with hop-distance and a severity-weighted blast-radius score. |
| `circuit_breaker_sim.py` | A from-scratch CLOSED → OPEN → HALF_OPEN → CLOSED state machine, matching the mesh-level pattern Istio enforces via `DestinationRule` outlier detection. Includes a `--demo` mode simulating a flaky downstream service. |
| `error_budget_tracker.py` | Computes error-budget consumption and burn rate from an availability percentage (mock data or live Prometheus), and applies the CRAILS "Red Mode" release-gating policy (GREEN/YELLOW/RED/INCIDENT). Exit code reflects gate severity, so it can gate a CI/CD pipeline directly. |

## Setup

```bash
pip install -r requirements.txt --break-system-packages
```

## Quick start

```bash
# Criticality Engine
python criticality_engine.py --config examples/services.yaml
python criticality_engine.py --config examples/services.yaml --write-k8s-annotations

# Blast Radius
python blast_radius.py --graph examples/dependency_graph.yaml --failing postgres-primary
python blast_radius.py --graph examples/dependency_graph.yaml --failing redis-cache --format json

# Circuit Breaker (interactive demo)
python circuit_breaker_sim.py --demo

# Error Budget Tracker
python error_budget_tracker.py --mock --scenario degraded --slo 99.0
python error_budget_tracker.py --prometheus-url http://prometheus.crails.local:9090 \
    --query 'sum(rate(traefik_requests_total{code!~"5.."}[30d])) / sum(rate(traefik_requests_total[30d]))'
```

## Running tests

```bash
python -m pytest tests/ -v
```

25 unit tests, all passing, covering tier boundaries, manual overrides,
dependency-graph traversal, circuit breaker state transitions (including
half-open trial logic), and error-budget gate thresholds.

## Where this plugs into the rest of CRAILS

- **`criticality_engine.py`** output feeds Istio `DestinationRule` generation
  (tier-1 gets tighter circuit-breaking thresholds) and Prometheus alert-rule
  templating (tier-1 gets stricter burn-rate alerts) — see CRAILS HLD/LLD.
- **`blast_radius.py`** is designed to consume the same dependency data you'd
  derive from Istio's service graph or a manually maintained service catalog;
  useful for chaos-engineering pre-checks ("what will this drill actually affect?").
- **`error_budget_tracker.py`** implements the exact policy documented in
  `CRAILS_Platform_SLO_SLI.docx` Section 4.2, and is intended to be wired into
  a Jenkins/ArgoCD pipeline stage as a go/no-go gate.
- **`circuit_breaker_sim.py`** is a teaching/demo tool — the real enforcement
  in CRAILS happens at the Istio mesh level, but this shows the underlying
  mechanism in code you can walk through line by line.

## Next steps (per the CRAILS roadmap)

- [ ] Wire `criticality_engine.py` output into actual K8s annotations via `kubectl patch`
- [ ] Feed `blast_radius.py` graph data from live Istio service-graph exports
  instead of hand-maintained YAML
- [ ] Add Ansible role to deploy `error_budget_tracker.py` as a scheduled
  AWX Job Template, posting Red Mode status to a Slack/webhook
- [ ] Add Terraform-provisioned Prometheus recording rules matching the
  error-budget PromQL used here
