#!/usr/bin/env python3
"""
blast_radius.py
================

Given a service dependency graph and a failing node, computes the set of
downstream services that would be impacted (directly or transitively),
along with a severity-weighted "blast radius score" — the same concept
behind the 45% blast-radius reduction referenced in the CRAILS/Visa work.

The graph is directed: an edge A -> B means "A depends on B" (A calls B).
If B fails, everything that (transitively) depends on B is impacted.

Usage:
    python blast_radius.py --graph dependency_graph.yaml --failing password-manager-backend
    python blast_radius.py --graph dependency_graph.yaml --failing redis --format json

Input format (dependency_graph.yaml):
    services:
      api-gateway:
        depends_on: [password-manager-backend, auth-service]
        tier: tier-1
      password-manager-backend:
        depends_on: [postgres-primary, redis]
        tier: tier-1
      auth-service:
        depends_on: [postgres-primary]
        tier: tier-1
      postgres-primary:
        depends_on: []
        tier: tier-1
      redis:
        depends_on: []
        tier: tier-2
      internal-admin-dashboard:
        depends_on: [postgres-primary]
        tier: tier-3
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


TIER_WEIGHT = {
    "tier-1": 1.0,
    "tier-2": 0.5,
    "tier-3": 0.2,
}


@dataclass
class Graph:
    # forward edges: service -> list of services it depends on
    depends_on: dict[str, list[str]] = field(default_factory=dict)
    tiers: dict[str, str] = field(default_factory=dict)

    def reverse_edges(self) -> dict[str, list[str]]:
        """
        Build the reverse adjacency: for each service, who depends ON it.
        This is what we need to answer "if X fails, who is impacted?"
        """
        reverse: dict[str, list[str]] = {name: [] for name in self.depends_on}
        for service, deps in self.depends_on.items():
            for dep in deps:
                reverse.setdefault(dep, [])
                reverse[dep].append(service)
        return reverse


def load_graph(path: Path) -> Graph:
    if yaml is None:
        raise RuntimeError("pyyaml is required: pip install pyyaml --break-system-packages")

    with open(path) as f:
        data = yaml.safe_load(f)

    depends_on = {}
    tiers = {}
    for name, meta in data.get("services", {}).items():
        depends_on[name] = list(meta.get("depends_on", []))
        tiers[name] = meta.get("tier", "tier-3")

    return Graph(depends_on=depends_on, tiers=tiers)


def compute_blast_radius(graph: Graph, failing_service: str) -> dict:
    """
    BFS over the reverse-dependency graph starting at the failing service.
    Returns every transitively-impacted service, the "hop distance" from
    the failure (1 = directly depends on the failed service), and an
    overall severity-weighted blast radius score.
    """
    if failing_service not in graph.depends_on:
        raise ValueError(f"Unknown service: {failing_service!r}. "
                          f"Known services: {sorted(graph.depends_on)}")

    reverse = graph.reverse_edges()

    visited: dict[str, int] = {}  # service -> hop distance from failure
    queue = [(failing_service, 0)]
    while queue:
        current, dist = queue.pop(0)
        for dependent in reverse.get(current, []):
            if dependent not in visited:
                visited[dependent] = dist + 1
                queue.append((dependent, dist + 1))

    impacted = []
    for service, hop in sorted(visited.items(), key=lambda kv: kv[1]):
        tier = graph.tiers.get(service, "tier-3")
        impacted.append({
            "service": service,
            "hops_from_failure": hop,
            "tier": tier,
        })

    total_services = len(graph.depends_on)
    impacted_count = len(impacted)
    blast_radius_pct = round((impacted_count / total_services) * 100, 1) if total_services else 0.0

    # Severity score weights closer/higher-tier impact more heavily.
    severity_score = 0.0
    for entry in impacted:
        tier_weight = TIER_WEIGHT.get(entry["tier"], 0.2)
        distance_decay = 1.0 / (entry["hops_from_failure"] + 1)
        severity_score += tier_weight * distance_decay
    severity_score = round(severity_score, 3)

    return {
        "failing_service": failing_service,
        "failing_service_tier": graph.tiers.get(failing_service, "tier-3"),
        "total_services_in_graph": total_services,
        "impacted_service_count": impacted_count,
        "blast_radius_pct": blast_radius_pct,
        "severity_score": severity_score,
        "impacted_services": impacted,
    }


def print_human_summary(result: dict):
    print(f"\nFailing service : {result['failing_service']} "
          f"({result['failing_service_tier']})", file=sys.stderr)
    print(f"Blast radius    : {result['impacted_service_count']}/"
          f"{result['total_services_in_graph']} services "
          f"({result['blast_radius_pct']}%)", file=sys.stderr)
    print(f"Severity score  : {result['severity_score']}", file=sys.stderr)
    print("\nImpacted services (closest first):", file=sys.stderr)
    for entry in result["impacted_services"]:
        print(f"  hop {entry['hops_from_failure']}: {entry['service']:35s} "
              f"({entry['tier']})", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="CRAILS Blast Radius Calculator")
    parser.add_argument("--graph", required=True, type=Path, help="Path to dependency_graph.yaml")
    parser.add_argument("--failing", required=True, help="Name of the service assumed to fail")
    parser.add_argument("--format", choices=["json", "human"], default="human")
    args = parser.parse_args()

    graph = load_graph(args.graph)
    result = compute_blast_radius(graph, args.failing)

    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        print_human_summary(result)


if __name__ == "__main__":
    main()
