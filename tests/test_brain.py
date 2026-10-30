import pandas as pd
import pytest

from conftest import synthetic_candles
from helpers import FakeSDK, Recorder, make_agent
from trader_agent.brain.client import BrainClient, BrainUnavailable
from trader_agent.brain.confirm import CONFIRM_SCHEMA, Confirmer
from trader_agent.brain.review import ai_briefing, nightly_review
from trader_agent.ssor import SSoR, SignalRecord

NOW = pd.Timestamp("2026-11-10 14:00", tz="UTC")
MODELS = {"fast": "model-fast", "balanced": "model-balanced", "deep": "model-deep"}


class APITimeoutError(Exception):
    """Same class name as the SDK's timeout error."""


@pytest.fixture
def ssor():
    store = SSoR(":memory:")
    yield store
    store.close()


def client_with(ssor, sdk, **limits):
    return BrainClient(ssor, MODELS, sdk_client=sdk, **limits)


def test_ask_json_uses_schema_timeout_and_no_retries(ssor):
    sdk = FakeSDK({"decision": "CONFIRM", "reason": "theek", "confidence": "high"})
    data = client_with(ssor, sdk).ask_json(purpose="confirm", tier="fast", system="s", prompt="p",
                                            schema=CONFIRM_SCHEMA, now=NOW, timeout=7, effort="low")
    assert data["decision"] == "CONFIRM"
    request = sdk.requests[0]
    assert request["model"] == "model-fast"
    assert request["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": CONFIRM_SCHEMA}}
    assert sdk.options[0] == {"timeout": 7, "max_retries": 0}
    usage = ssor.conn.execute("SELECT purpose, model, status, input_tokens, output_tokens FROM ai_usage").fetchone()
    assert tuple(usage) == ("confirm", "model-fast", "ok", 120, 30)


@pytest.mark.parametrize(
    "sdk, status",
    [
        (FakeSDK(error=APITimeoutError()), "timeout"),
        (FakeSDK(error=ValueError("boom")), "error"),
        (FakeSDK({"decision": "CONFIRM"}, stop_reason="refusal"), "refusal"),
        (FakeSDK({"decision": "CONFIRM"}), "bad_json"),  # reason/confidence missing
    ],
)
def test_failures_become_brain_unavailable(ssor, sdk, status):
    with pytest.raises(BrainUnavailable) as info:
        client_with(ssor, sdk).ask_json(purpose="confirm", tier="fast", system="s", prompt="p",
                                        schema=CONFIRM_SCHEMA, now=NOW)
    assert info.value.status == status
    assert ssor.ai_usage_between(NOW.normalize(), NOW.normalize() + pd.Timedelta(days=1))["calls"] == 1


def test_daily_budget_and_missing_model(ssor):
    sdk = FakeSDK({"decision": "VETO", "reason": "r", "confidence": "low"})
    client = client_with(ssor, sdk, max_calls_per_day=1)
    client.ask_json(purpose="confirm", tier="fast", system="s", prompt="p", schema=CONFIRM_SCHEMA, now=NOW)
    with pytest.raises(BrainUnavailable, match="budget"):
        client.ask_json(purpose="confirm", tier="fast", system="s", prompt="p", schema=CONFIRM_SCHEMA, now=NOW)
    with pytest.raises(BrainUnavailable, match="no_model"):
        BrainClient(ssor, {}, sdk_client=sdk).ask_json(purpose="x", tier="deep", system="s", prompt="p", schema={}, now=NOW)


@pytest.mark.parametrize("policy, allowed", [("skip", False), ("rules_only", True)])
def test_unavailable_policy(ssor, policy, allowed):
    confirmer = Confirmer(client_with(ssor, FakeSDK(error=APITimeoutError())), on_unavailable=policy)
    setup = type("S", (), {"id": "R1", "version": 1, "name": "n", "direction": "CALL", "conditions": ("x",),
                           "invalidations": (), "notes": None})()
    verdict = confirmer.decide(setup=setup, features={}, episodes=[], payout=0.8, now=NOW)
    assert verdict.allowed is allowed and verdict.status == "timeout"


def replay_window(agent, candles, start, minutes):
    first = candles.index.get_loc(pd.Timestamp(start, tz="UTC"))
    for pos in range(first, first + minutes):
        agent.on_closed_candle("EURUSD", candles.iloc[max(0, pos - 1999): pos + 1])


def test_veto_keeps_the_signal_as_shadow_and_does_not_notify(repo_root, tmp_path):
    candles = synthetic_candles(days=3, seed=2)
    agent = make_agent(repo_root, tmp_path, notifier=Recorder())
    agent.brain = Confirmer(client_with(agent.ssor, FakeSDK({"decision": "VETO", "reason": "trend kamzor", "confidence": "medium"})))
    replay_window(agent, candles, "2026-03-04 13:30", 30)
    assert agent.notifier.signals == []
    shadow = agent.ssor.signals_between(pd.Timestamp("2026-03-04", tz="UTC"), pd.Timestamp("2026-03-05", tz="UTC"), mode="shadow")
    assert shadow and shadow[0]["brain"]["decision"] == "VETO"
    reasons = " ".join(" ".join(d["reasons"]) for d in agent.ssor.recent_decisions(100))
    assert "AI VETO: trend kamzor" in reasons


def test_confirm_sends_with_ai_reason(repo_root, tmp_path):
    from trader_agent.notifier.messages import format_signal

    candles = synthetic_candles(days=3, seed=2)
    agent = make_agent(repo_root, tmp_path, notifier=Recorder())
    sdk = FakeSDK({"decision": "CONFIRM", "reason": "support par bounce", "confidence": "high"})
    agent.brain = Confirmer(client_with(agent.ssor, sdk))
    replay_window(agent, candles, "2026-03-04 13:30", 30)
    assert agent.notifier.signals
    assert "🤖 AI: support par bounce (high)" in format_signal(agent.notifier.signals[0])
    assert "Rule (approved)" in sdk.requests[0]["messages"][0]["content"]


def test_nightly_review_saves_reflections_and_only_supported_proposals(ssor):
    ids = []
    for minute in range(3):
        at = NOW + pd.Timedelta(minutes=minute * 5)
        ids.append(ssor.record_signal(SignalRecord("live", "EURUSD", "R1", 1, "CALL", at, at, at, 1, 0.8, {"rsi_14": 30})))
        ssor.record_outcome(ids[-1], "feed", "LOSS", at + pd.Timedelta(minutes=1))
    payload = {
        "summary": "aaj 3 loss",
        "reflections": [{"signal_id": ids[0], "lesson": "trend ke khilaf", "tags": ["trend"]},
                        {"signal_id": 999, "lesson": "ghalat id", "tags": []}],
        "proposals": [{"pattern": "R1 high vol mein band", "evidence_signal_ids": ids, "rationale": "3 loss"},
                      {"pattern": "kam saboot", "evidence_signal_ids": ids[:1], "rationale": "1"}],
    }
    sdk = FakeSDK(payload)
    result = nightly_review(client_with(ssor, sdk), ssor, NOW - pd.Timedelta(hours=1), NOW + pd.Timedelta(hours=1),
                            NOW + pd.Timedelta(hours=2), min_evidence=3)
    assert result == {"summary": "aaj 3 loss", "reflections": 1, "proposals": 1, "downgraded": 1}
    assert [p["pattern"] for p in ssor.pending_proposals()] == ["R1 high vol mein band"]
    assert sdk.requests[0]["model"] == "model-deep"  # streamed via the deep tier


def test_briefing_text_and_unavailable(ssor):
    ok = client_with(ssor, FakeSDK({"summary": "aaj CPI hai", "watch": ["EURUSD range"], "avoid": ["18:30 ke aas paas"]}))
    text = ai_briefing(ok, "facts", NOW)
    assert "aaj CPI hai" in text and "👀 EURUSD range" in text and "🚫 18:30" in text
    assert ai_briefing(client_with(ssor, FakeSDK(error=APITimeoutError())), "facts", NOW) is None
