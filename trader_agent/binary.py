"""Binary-option arithmetic: break-even, expected value, trade outcome."""

from __future__ import annotations


def break_even(payout: float) -> float:
    """Win rate needed to not lose money. 80% payout -> 55.6%."""
    if payout <= 0:
        raise ValueError("payout must be positive (0.80 for 80%)")
    return 1.0 / (1.0 + payout)


def expected_value(win_rate: float, payout: float) -> float:
    """Average profit per 1 unit staked (draws ignored)."""
    return win_rate * payout - (1.0 - win_rate)


def resolve(direction: str, entry_price: float, exit_price: float) -> str:
    if exit_price == entry_price:
        return "DRAW"
    went_up = exit_price > entry_price
    if direction == "CALL":
        return "WIN" if went_up else "LOSS"
    if direction == "PUT":
        return "LOSS" if went_up else "WIN"
    raise ValueError(f"direction must be CALL or PUT, got {direction!r}")
