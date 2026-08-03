import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from criticality_engine import ServiceInput, score_service, score_to_tier, evaluate


def test_high_traffic_high_fanin_scores_tier1():
    svc = ServiceInput(name="critical-api", traffic_share=0.8, dependency_fanin=15, incident_history=5)
    result = evaluate(svc)
    assert result.tier == "tier-1"
    assert result.sla_p99_ms == 200


def test_low_signal_service_scores_tier3():
    svc = ServiceInput(name="admin-tool", traffic_share=0.01, dependency_fanin=0, incident_history=0)
    result = evaluate(svc)
    assert result.tier == "tier-3"
    assert result.sla_p99_ms == 2000


def test_manual_override_takes_precedence():
    # Signals alone would produce tier-1, but manual override forces tier-3
    svc = ServiceInput(name="forced-low", traffic_share=0.9, dependency_fanin=20,
                        incident_history=10, manual_override="tier-3")
    result = evaluate(svc)
    assert result.tier == "tier-3"
    assert result.tier_source == "manual_override"
    assert result.signals["computed_tier_before_override"] == "tier-1"


def test_score_is_clipped_between_0_and_1():
    svc = ServiceInput(name="overload", traffic_share=5.0, dependency_fanin=1000, incident_history=1000)
    score = score_service(svc)
    assert 0.0 <= score <= 1.0


def test_score_to_tier_boundaries():
    assert score_to_tier(0.65) == "tier-1"
    assert score_to_tier(0.64999) == "tier-2"
    assert score_to_tier(0.30) == "tier-2"
    assert score_to_tier(0.29999) == "tier-3"
    assert score_to_tier(0.0) == "tier-3"


def test_tier_source_is_computed_when_no_override():
    svc = ServiceInput(name="normal-service", traffic_share=0.5, dependency_fanin=5, incident_history=1)
    result = evaluate(svc)
    assert result.tier_source == "computed"
