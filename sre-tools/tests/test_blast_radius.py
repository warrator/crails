import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blast_radius import Graph, compute_blast_radius


@pytest.fixture
def sample_graph():
    # api-gateway -> svc-a -> db
    #             -> svc-b -> db
    return Graph(
        depends_on={
            "api-gateway": ["svc-a", "svc-b"],
            "svc-a": ["db"],
            "svc-b": ["db"],
            "db": [],
            "unrelated-batch-job": ["other-db"],
            "other-db": [],
        },
        tiers={
            "api-gateway": "tier-1",
            "svc-a": "tier-1",
            "svc-b": "tier-2",
            "db": "tier-1",
            "unrelated-batch-job": "tier-3",
            "other-db": "tier-3",
        },
    )


def test_db_failure_impacts_everything_upstream(sample_graph):
    result = compute_blast_radius(sample_graph, "db")
    impacted_names = {e["service"] for e in result["impacted_services"]}
    assert impacted_names == {"svc-a", "svc-b", "api-gateway"}
    assert "unrelated-batch-job" not in impacted_names
    assert "other-db" not in impacted_names


def test_leaf_service_failure_has_zero_blast_radius(sample_graph):
    # api-gateway has nothing depending on it
    result = compute_blast_radius(sample_graph, "api-gateway")
    assert result["impacted_service_count"] == 0
    assert result["blast_radius_pct"] == 0.0


def test_hop_distance_increases_with_depth(sample_graph):
    result = compute_blast_radius(sample_graph, "db")
    hops = {e["service"]: e["hops_from_failure"] for e in result["impacted_services"]}
    assert hops["svc-a"] == 1
    assert hops["svc-b"] == 1
    assert hops["api-gateway"] == 2


def test_unknown_service_raises():
    graph = Graph(depends_on={"a": []}, tiers={"a": "tier-3"})
    with pytest.raises(ValueError):
        compute_blast_radius(graph, "nonexistent")


def test_blast_radius_pct_is_calculated_correctly(sample_graph):
    result = compute_blast_radius(sample_graph, "db")
    # 3 impacted out of 6 total services = 50.0%
    assert result["blast_radius_pct"] == 50.0


def test_severity_score_is_positive_when_impacted(sample_graph):
    result = compute_blast_radius(sample_graph, "db")
    assert result["severity_score"] > 0
