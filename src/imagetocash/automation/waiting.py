"""Explicit waits. No fixed sleeps anywhere else in the code base: everything polls a condition."""

from __future__ import annotations

import time
from collections.abc import Callable

DEFAULT_POLL_SECONDS = 0.1


class WaitTimeout(TimeoutError):
    pass


def wait_until[T](
    probe: Callable[[], T | None],
    *,
    timeout: float,
    what: str,
    done: Callable[[T], bool] = bool,
    interval: float = DEFAULT_POLL_SECONDS,
) -> T:
    """Poll `probe` until `done(result)` is true. Exceptions from the probe count as "not yet"."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while True:
        try:
            result = probe()
            if result is not None and done(result):
                return result
        except Exception as error:  # UI elements appear/disappear while we poll
            last_error = error
        if time.monotonic() >= deadline:
            detail = f" (last error: {last_error})" if last_error else ""
            raise WaitTimeout(f"timed out after {timeout:.1f}s waiting for {what}{detail}")
        time.sleep(interval)


def wait_until_stable[T](
    probe: Callable[[], T],
    *,
    timeout: float,
    what: str,
    stable_polls: int = 2,
    interval: float = 0.25,
) -> T:
    """Spec 2.2 "wait for the list to stabilize": the same value on `stable_polls` reads in a row."""
    deadline = time.monotonic() + timeout
    previous: T | None = None
    same_count = 0
    while True:
        current = probe()
        same_count = same_count + 1 if current == previous else 1
        if same_count >= stable_polls:
            return current
        previous = current
        if time.monotonic() >= deadline:
            raise WaitTimeout(f"{what} did not stabilize within {timeout:.1f}s")
        time.sleep(interval)
