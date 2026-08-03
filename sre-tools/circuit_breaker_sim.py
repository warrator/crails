#!/usr/bin/env python3
"""
circuit_breaker_sim.py
========================

A from-scratch circuit breaker implementation (the same pattern Istio
enforces at the mesh level via DestinationRule outlier detection), built
here as a standalone Python state machine so you can demonstrate you
understand the mechanism itself, not just the YAML that configures it.

States:
    CLOSED     -> requests flow normally; failures are counted in a rolling window
    OPEN       -> requests are rejected immediately (fail fast); no calls reach
                  the downstream service until the reset timeout elapses
    HALF_OPEN  -> a limited number of trial requests are allowed through to
                  test if the downstream service has recovered

Transitions:
    CLOSED -> OPEN        : failure rate exceeds threshold within the rolling window
    OPEN -> HALF_OPEN      : reset_timeout_seconds has elapsed since opening
    HALF_OPEN -> CLOSED    : trial requests succeed at/above the success threshold
    HALF_OPEN -> OPEN      : any trial request fails (fail closed again, conservatively)

Usage as a library:
    from circuit_breaker_sim import CircuitBreaker

    cb = CircuitBreaker(failure_threshold=0.5, window_size=20,
                         reset_timeout_seconds=30, half_open_trial_requests=5)

    if cb.allow_request():
        try:
            result = call_downstream()
            cb.record_success()
        except Exception:
            cb.record_failure()
    else:
        # fail fast / return cached / fallback response
        ...

Run directly for a simulated demo against a flaky downstream service:
    python circuit_breaker_sim.py --demo
"""

from __future__ import annotations

import argparse
import random
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum


class State(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreaker:
    failure_threshold: float = 0.5          # fraction of failures in window to trip OPEN
    window_size: int = 20                    # rolling window of recent call outcomes
    reset_timeout_seconds: float = 30.0      # how long to stay OPEN before trialing again
    half_open_trial_requests: int = 5        # trial calls allowed in HALF_OPEN
    half_open_success_threshold: float = 0.8 # fraction of trials that must succeed to close

    _state: State = field(default=State.CLOSED, init=False)
    _results: deque = field(default_factory=deque, init=False)
    _opened_at: float = field(default=0.0, init=False)
    _half_open_results: list = field(default_factory=list, init=False)

    # -- public API -----------------------------------------------------

    @property
    def state(self) -> State:
        self._maybe_transition_from_open()
        return self._state

    def allow_request(self) -> bool:
        """Call this before making the downstream request."""
        current = self.state
        if current == State.OPEN:
            return False
        return True  # CLOSED or HALF_OPEN both allow (HALF_OPEN allows trial calls)

    def record_success(self):
        if self._state == State.HALF_OPEN:
            self._half_open_results.append(True)
            self._evaluate_half_open()
        else:
            self._push_result(True)
            self._evaluate_closed()

    def record_failure(self):
        if self._state == State.HALF_OPEN:
            self._half_open_results.append(False)
            # Fail-fast: any failure during trial reopens the breaker immediately
            self._trip_open()
        else:
            self._push_result(False)
            self._evaluate_closed()

    # -- internals --------------------------------------------------------

    def _push_result(self, success: bool):
        self._results.append(success)
        if len(self._results) > self.window_size:
            self._results.popleft()

    def _current_failure_rate(self) -> float:
        if not self._results:
            return 0.0
        failures = sum(1 for r in self._results if not r)
        return failures / len(self._results)

    def _evaluate_closed(self):
        if self._state != State.CLOSED:
            return
        # Wait for a full rolling window before evaluating, so a handful of
        # early failures can't trip the breaker before enough samples have
        # accumulated to judge the true failure rate.
        if len(self._results) >= self.window_size:
            if self._current_failure_rate() >= self.failure_threshold:
                self._trip_open()

    def _trip_open(self):
        self._state = State.OPEN
        self._opened_at = time.monotonic()
        self._results.clear()
        self._half_open_results.clear()

    def _maybe_transition_from_open(self):
        if self._state == State.OPEN:
            if time.monotonic() - self._opened_at >= self.reset_timeout_seconds:
                self._state = State.HALF_OPEN
                self._half_open_results.clear()

    def _evaluate_half_open(self):
        if len(self._half_open_results) >= self.half_open_trial_requests:
            success_rate = sum(1 for r in self._half_open_results if r) / len(self._half_open_results)
            if success_rate >= self.half_open_success_threshold:
                self._state = State.CLOSED
                self._results.clear()
            else:
                self._trip_open()


# ---------------------------------------------------------------------------
# Demo: simulate a flaky downstream service and watch the breaker react
# ---------------------------------------------------------------------------

def _simulate_downstream_call(failure_probability: float) -> bool:
    """Returns True on success, False on failure."""
    return random.random() > failure_probability


def run_demo():
    cb = CircuitBreaker(
        failure_threshold=0.5,
        window_size=10,
        reset_timeout_seconds=2.0,   # shortened for a fast demo
        half_open_trial_requests=3,
        half_open_success_threshold=0.67,
    )

    print(f"{'tick':>4}  {'state':<10}  {'failure_prob':<13}  outcome")

    # Phase 1: healthy downstream (0% failures)
    # Phase 2: downstream degrades (80% failures) -> breaker should trip OPEN
    # Phase 3: downstream recovers (5% failures) -> breaker should close again
    phases = (
        [0.0] * 8 +
        [0.8] * 12 +
        [0.05] * 15
    )

    for tick, failure_prob in enumerate(phases, start=1):
        allowed = cb.allow_request()
        if not allowed:
            print(f"{tick:>4}  {cb.state.value:<10}  {failure_prob:<13}  REJECTED (fail-fast)")
            time.sleep(0.2)
            continue

        success = _simulate_downstream_call(failure_prob)
        if success:
            cb.record_success()
            outcome = "ok"
        else:
            cb.record_failure()
            outcome = "FAILED"

        print(f"{tick:>4}  {cb.state.value:<10}  {failure_prob:<13}  {outcome}")
        time.sleep(0.2)

    print(f"\nFinal state: {cb.state.value}")


def main():
    parser = argparse.ArgumentParser(description="CRAILS Circuit Breaker Simulator")
    parser.add_argument("--demo", action="store_true", help="Run the built-in flaky-service demo")
    args = parser.parse_args()

    if args.demo:
        run_demo()
    else:
        print("Nothing to do. Run with --demo, or import CircuitBreaker as a library.")


if __name__ == "__main__":
    main()
