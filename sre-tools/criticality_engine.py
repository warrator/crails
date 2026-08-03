#!/usr/bin/env python3
"""
criticality_engine.py
======================

Auto-tags services with a criticality tier (tier-1 / tier-2 / tier-3) based
on a weighted score of measurable signals, rather than relying purely on
self-declared tags. This is the CRAILS implementation of the pattern used
in production at Visa: services get scored, tiered, and the tier is written
back as metadata that downstream systems (Istio policy generator, alert-rule
generator, CI/CD gates) can consume.

Scoring signals (weights are configurable):
    - traffic_share:     % of total platform traffic this service handles
    - dependency_fanin:  how many other services call this one (higher = more critical)
    - incident_history:  weighted count of past P1/P2 incidents caused by this service
    - manual_override:   a human-declared tier that, if set, takes precedence

Usage:
    python criticality_engine.py --config services.yaml
    python criticality_engine.py --config services.yaml --output tiers.json
    python criticality_engine.py --config services.yaml --write-k8s-annotations

Input format (services.yaml):
    services:
      - name: password-manager-backend
        traffic_share: 0.42
        dependency_fanin: 8
        incident_history: 3
        manual_override: null
      - name: internal-admin-dashboard
        traffic_share: 0.01
        dependency_fanin: 0
        incident_history: 0
        manual_override: "tier-3"
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None


# ---------------------------------------------------------------------------
# Tier definitions — edit these to match your own SLO policy
# ---------------------------------------------------------------------------

TIER_THRESHOLDS = {
    "tier-1": 0.65,   # score >= 0.65  -> tier-1 (critical)
    "tier-2": 0.30,   # score >= 0.30  -> tier-2 (important)
    # anything below tier-2 threshold falls through to tier-3
}

TIER_SLA_P99_MS = {
    "tier-1": 200,
    "tier-2": 500,
    "tier-3": 2000,
}

# Weights must sum to 1.0 across the three automated signals.
WEIGHTS = {
    "traffic_share": 0.45,
    "dependency_fanin": 0.35,
    "incident_history": 0.20,
}

# Normalisation caps — signals are clipped to these before weighting,
# so one runaway metric (e.g. 500 incidents) can't dominate the score.
MAX_FANIN = 20
MAX_INCIDENTS = 10


@dataclass
class ServiceInput:
    name: str
    traffic_share: float = 0.0        # 0.0 - 1.0
    dependency_fanin: int = 0         # count of dependent services
    incident_history: int = 0         # count of P1/P2 incidents, last 90 days
    manual_override: Optional[str] = None  # "tier-1" | "tier-2" | "tier-3" | None


@dataclass
class ServiceResult:
    name: str
    score: float
    tier: str
    sla_p99_ms: int
    tier_source: str  # "computed" | "manual_override"
    signals: dict = field(default_factory=dict)


def _normalise(value: float, cap: float) -> float:
    """Clip and scale a raw signal into a 0.0-1.0 range."""
    if cap <= 0:
        return 0.0
    return max(0.0, min(1.0, value / cap))


def score_service(svc: ServiceInput) -> float:
    """Compute a 0.0-1.0 criticality score from weighted, normalised signals."""
    traffic_component = max(0.0, min(1.0, svc.traffic_share)) * WEIGHTS["traffic_share"]
    fanin_component = _normalise(svc.dependency_fanin, MAX_FANIN) * WEIGHTS["dependency_fanin"]
    incident_component = _normalise(svc.incident_history, MAX_INCIDENTS) * WEIGHTS["incident_history"]
    return round(traffic_component + fanin_component + incident_component, 4)


def score_to_tier(score: float) -> str:
    if score >= TIER_THRESHOLDS["tier-1"]:
        return "tier-1"
    if score >= TIER_THRESHOLDS["tier-2"]:
        return "tier-2"
    return "tier-3"


def evaluate(svc: ServiceInput) -> ServiceResult:
    score = score_service(svc)
    computed_tier = score_to_tier(score)

    if svc.manual_override in TIER_SLA_P99_MS:
        tier = svc.manual_override
        source = "manual_override"
    else:
        tier = computed_tier
        source = "computed"

    return ServiceResult(
        name=svc.name,
        score=score,
        tier=tier,
        sla_p99_ms=TIER_SLA_P99_MS[tier],
        tier_source=source,
        signals={
            "traffic_share": svc.traffic_share,
            "dependency_fanin": svc.dependency_fanin,
            "incident_history": svc.incident_history,
            "computed_tier_before_override": computed_tier,
        },
    )


def load_services(config_path: Path) -> list[ServiceInput]:
    if yaml is None:
        raise RuntimeError("pyyaml is required: pip install pyyaml --break-system-packages")

    with open(config_path) as f:
        data = yaml.safe_load(f)

    services = []
    for entry in data.get("services", []):
        services.append(ServiceInput(
            name=entry["name"],
            traffic_share=float(entry.get("traffic_share", 0.0)),
            dependency_fanin=int(entry.get("dependency_fanin", 0)),
            incident_history=int(entry.get("incident_history", 0)),
            manual_override=entry.get("manual_override"),
        ))
    return services


def to_k8s_annotation_patch(result: ServiceResult) -> dict:
    """
    Produce a kubectl-annotate-ready patch for this service, matching the
    annotation scheme referenced in the CRAILS HLD/LLD:
        criticality.io/tier
        criticality.io/sla-p99
        criticality.io/score
    """
    return {
        "service": result.name,
        "annotations": {
            "criticality.io/tier": result.tier,
            "criticality.io/sla-p99": f"{result.sla_p99_ms}ms",
            "criticality.io/score": str(result.score),
            "criticality.io/tier-source": result.tier_source,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="CRAILS Criticality Engine")
    parser.add_argument("--config", required=True, type=Path, help="Path to services.yaml")
    parser.add_argument("--output", type=Path, help="Write JSON results to this file")
    parser.add_argument("--write-k8s-annotations", action="store_true",
                         help="Also emit kubectl-annotate-ready patches")
    args = parser.parse_args()

    services = load_services(args.config)
    results = [evaluate(s) for s in services]

    # Sort by tier (tier-1 first) then score descending, for readable output
    tier_order = {"tier-1": 0, "tier-2": 1, "tier-3": 2}
    results.sort(key=lambda r: (tier_order[r.tier], -r.score))

    output = {
        "results": [asdict(r) for r in results],
    }
    if args.write_k8s_annotations:
        output["k8s_annotation_patches"] = [to_k8s_annotation_patch(r) for r in results]

    text = json.dumps(output, indent=2)

    if args.output:
        args.output.write_text(text)
        print(f"Wrote {len(results)} service tiers to {args.output}")
    else:
        print(text)

    # Human-readable summary to stderr so it doesn't pollute JSON on stdout
    print("\n--- Criticality Summary ---", file=sys.stderr)
    for r in results:
        override_note = " (manual override)" if r.tier_source == "manual_override" else ""
        print(f"  {r.name:35s} score={r.score:<6} tier={r.tier}{override_note}  "
              f"p99_sla={r.sla_p99_ms}ms", file=sys.stderr)


if __name__ == "__main__":
    main()
