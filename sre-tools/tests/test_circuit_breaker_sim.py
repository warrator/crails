import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from circuit_breaker_sim import CircuitBreaker, State


def make_breaker(**overrides):
    defaults = dict(
        failure_threshold=0.5,
        window_size=5,
        reset_timeout_seconds=0.2,   # short timeout so tests run fast
        half_open_trial_requests=3,
        half_open_success_threshold=0.67,
    )
    defaults.update(overrides)
    return CircuitBreaker(**defaults)


def test_starts_closed():
    cb = make_breaker()
    assert cb.state == State.CLOSED
    assert cb.allow_request() is True


def test_trips_open_after_failure_threshold_exceeded():
    cb = make_breaker()  # default window_size=5
    # Push failures to fill the full window with 100% failures
    for _ in range(5):
        cb.record_failure()
    assert cb.state == State.OPEN
    assert cb.allow_request() is False


def test_stays_closed_when_failures_below_threshold():
    cb = make_breaker(window_size=10)
    for _ in range(3):
        cb.record_failure()
    for _ in range(7):
        cb.record_success()
    # Full window of 10 reached: 3 failures / 10 = 30%, below the 50% threshold
    assert cb.state == State.CLOSED


def test_transitions_to_half_open_after_timeout():
    cb = make_breaker(reset_timeout_seconds=0.1)
    for _ in range(5):
        cb.record_failure()
    assert cb.state == State.OPEN

    time.sleep(0.15)
    assert cb.state == State.HALF_OPEN


def test_half_open_closes_on_successful_trials():
    cb = make_breaker(reset_timeout_seconds=0.05, half_open_trial_requests=3,
                       half_open_success_threshold=0.67)
    for _ in range(5):
        cb.record_failure()
    time.sleep(0.1)
    assert cb.state == State.HALF_OPEN

    cb.record_success()
    cb.record_success()
    cb.record_success()
    assert cb.state == State.CLOSED


def test_half_open_reopens_on_any_trial_failure():
    cb = make_breaker(reset_timeout_seconds=0.05, half_open_trial_requests=3)
    for _ in range(5):
        cb.record_failure()
    time.sleep(0.1)
    assert cb.state == State.HALF_OPEN

    cb.record_success()
    cb.record_failure()  # single failure during trial reopens immediately
    assert cb.state == State.OPEN


def test_allow_request_false_while_open():
    cb = make_breaker(reset_timeout_seconds=10)  # long timeout, stays open
    for _ in range(5):
        cb.record_failure()
    assert cb.allow_request() is False
