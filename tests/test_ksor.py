import copy

import pytest

from trader_agent.features import feature_names
from trader_agent.ksor import (
    KsorError,
    governance_warnings,
    load_risk_policy,
    load_setups,
    risk_policy_from_dict,
    setup_from_dict,
    setup_problems,
)

GOOD = {
    "id": "R07",
    "name": "Test setup",
    "version": 1,
    "status": "draft",
    "direction": "CALL",
    "pairs": ["EURUSD"],
    "sessions": ["london_newyork"],
    "conditions": ["rsi_14 < 30", "bullish_engulfing"],
    "invalidations": ["vol_state == 'high'"],
    "expiry_minutes": 1,
}


def variant(**changes):
    raw = copy.deepcopy(GOOD)
    raw.update(changes)
    return raw


def test_repo_ksor_files_are_valid(repo_root, sessions):
    names = feature_names(sessions)
    setups = load_setups(repo_root / "ksor" / "setups", ("draft", "approved", "retired"), names, sessions.names())
    assert setups, "at least the example setup should load"
    load_risk_policy(repo_root / "ksor" / "risk_policy.yaml", sessions.names())


def test_live_loads_only_approved(repo_root, sessions):
    approved = load_setups(repo_root / "ksor" / "setups", known_features=feature_names(sessions))
    assert all(s.status == "approved" for s in approved)


def test_good_setup(sessions):
    setup = setup_from_dict(GOOD)
    assert setup.key == "R07@v1"
    assert setup_problems(setup, feature_names(sessions), sessions.names()) == []
    assert setup.referenced_features() == {"rsi_14", "bullish_engulfing", "vol_state"}


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"direction": "UP"}, "CALL or PUT"),
        ({"id": "r7"}, "id"),
        ({"version": 0}, "version"),
        ({"status": "live"}, "status"),
        ({"pairs": ["EUR/USD"]}, "pairs"),
        ({"expiry_minutes": 30}, "expiry"),
        ({"conditions": ["rsi_14 <"]}, "cannot read"),
        ({"conditions": ["rsi_14 ** 2 > 1"]}, "only"),
        ({"status": "approved"}, "approved_by"),
    ],
)
def test_bad_setups_are_rejected(changes, message):
    with pytest.raises(KsorError, match=message):
        setup_from_dict(variant(**changes))


def test_unknown_feature_and_session_are_caught(sessions):
    setup = setup_from_dict(variant(conditions=["rsi < 30"], sessions=["dubai"]))
    problems = " ".join(setup_problems(setup, feature_names(sessions), sessions.names()))
    assert "rsi" in problems and "dubai" in problems


def test_approved_setup_needs_changelog_entry():
    setup = setup_from_dict(variant(status="approved", approved_by="Ustad", approved_on="2026-11-02"))
    assert governance_warnings([setup], "nothing here")
    assert not governance_warnings([setup], "- R07 v1 — approved by Ustad on 2026-11-02")


POLICY = {
    "version": 1,
    "status": "draft",
    "allowed_sessions": ["london_newyork"],
    "max_signals_per_day": 15,
    "max_losses_per_day": 3,
    "cooldown": {"after_consecutive_losses": 2, "minutes": 10},
    "news_blackout": {"impact": ["high"], "minutes_before": 15, "minutes_after": 15},
}


def test_martingale_is_never_allowed():
    with pytest.raises(KsorError, match="martingale"):
        risk_policy_from_dict({**POLICY, "martingale": True})


def test_policy_needs_limits():
    raw = dict(POLICY)
    raw.pop("max_losses_per_day")
    with pytest.raises(KsorError, match="max_losses_per_day"):
        risk_policy_from_dict(raw)
