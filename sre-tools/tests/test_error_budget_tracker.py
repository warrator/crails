import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from error_budget_tracker import compute_error_budget


def test_full_availability_gives_green_gate():
    result = compute_error_budget(slo_target_pct=99.0, window_days=30, observed_availability_pct=100.0)
    assert result.release_gate == "GREEN"
    assert result.error_budget_remaining_pct == 100.0


def test_exact_slo_availability_gives_zero_remaining_budget():
    # Observed availability exactly at the SLO target means the allowed
    # downtime budget has been used in full over the window (by definition:
    # avg availability == target implies avg downtime == allowed downtime).
    result = compute_error_budget(slo_target_pct=99.0, window_days=30, observed_availability_pct=99.0)
    assert result.error_budget_remaining_pct == 0.0
    assert result.release_gate == "INCIDENT"


def test_budget_fully_exhausted_triggers_incident():
    # Availability well below SLO -> consumed minutes exceed total budget -> 0% remaining
    result = compute_error_budget(slo_target_pct=99.0, window_days=30, observed_availability_pct=90.0)
    assert result.error_budget_remaining_pct == 0.0
    assert result.release_gate == "INCIDENT"


def test_moderate_breach_triggers_yellow_or_red():
    # 1% allowed downtime budget; consume roughly 60% of it
    # allowed_downtime_pct = 1.0; we want observed_downtime_pct = 0.6
    result = compute_error_budget(slo_target_pct=99.0, window_days=30, observed_availability_pct=99.4)
    assert result.release_gate in ("YELLOW", "RED")
    assert 0 < result.error_budget_remaining_pct < 50


def test_zero_downtime_allowed_slo_of_100_handles_gracefully():
    result = compute_error_budget(slo_target_pct=100.0, window_days=30, observed_availability_pct=100.0)
    # No budget exists at all; treat as 0% remaining rather than raising
    assert result.error_budget_remaining_pct == 0.0


def test_action_text_matches_gate():
    result = compute_error_budget(slo_target_pct=99.0, window_days=30, observed_availability_pct=90.0)
    assert "Incident declared" in result.action
