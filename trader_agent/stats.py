"""Honest statistics for win rates: confidence intervals, significance, streaks."""

from __future__ import annotations

import math
from collections.abc import Iterable

from .binary import break_even


def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% range for the true win rate (Wilson score interval)."""
    if n <= 0:
        return (0.0, 1.0)
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def binomial_sf(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p), computed exactly in log space."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    if p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    log_p, log_q = math.log(p), math.log1p(-p)
    terms = [
        math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * log_p + (n - i) * log_q
        for i in range(k, n + 1)
    ]
    top = max(terms)
    return min(1.0, math.exp(top) * sum(math.exp(t - top) for t in terms))


def max_streak(results: Iterable[str], target: str = "LOSS") -> int:
    best = current = 0
    for result in results:
        if result == target:
            current += 1
            best = max(best, current)
        elif result != "DRAW":
            current = 0
    return best


def summarize(results: list[str], payout: float) -> dict:
    """Win rate over decided trades (draws refunded), with range, EV and significance."""
    wins = sum(r == "WIN" for r in results)
    losses = sum(r == "LOSS" for r in results)
    draws = sum(r == "DRAW" for r in results)
    decided = wins + losses
    be = break_even(payout)
    low, high = wilson_interval(wins, decided)
    return {
        "trades": len(results),
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "win_rate": wins / decided if decided else None,
        "ci_low": low if decided else None,
        "ci_high": high if decided else None,
        "break_even": be,
        "ev_per_trade": (wins * payout - losses) / len(results) if results else None,
        "p_value_vs_break_even": binomial_sf(wins, decided, be) if decided else None,
        "max_losing_streak": max_streak(results, "LOSS"),
    }
