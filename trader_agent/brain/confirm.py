"""Live confirm/veto of a candidate that already passed the risk gate."""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..binary import break_even
from ..ksor import Setup
from .client import BrainClient, BrainUnavailable

CONFIRM_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["CONFIRM", "VETO"]},
        "reason": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["decision", "reason", "confidence"],
    "additionalProperties": False,
}

CONFIRM_SYSTEM = """\
You review one signal candidate for a human who trades 1-minute binary options by hand.
The candidate already matches an approved rule written by an experienced trader, and it
already passed the deterministic risk checks. Your only choices are CONFIRM or VETO.
You cannot create trades, change rules, change limits or suggest a different direction.

Decide from the evidence given:
- does the feature snapshot match the rule's intent, not just its letter?
- does the market context (regime, volatility, higher-timeframe trend) support it?
- how did similar past episodes of this rule end?
A random 1-minute move is close to a coin flip, so only CONFIRM when the evidence is
clearly favourable; when evidence is thin or conflicting, VETO.

Write `reason` in simple Roman Urdu, at most two short sentences, naming the deciding factor.
"""


@dataclass(frozen=True)
class Verdict:
    allowed: bool  # may the signal be sent to the human?
    decision: str  # CONFIRM | VETO | UNAVAILABLE
    reason: str
    confidence: str | None
    status: str  # ok | timeout | budget | refusal | error | no_model | ...

    def as_json(self) -> dict:
        return {"decision": self.decision, "reason": self.reason, "confidence": self.confidence, "status": self.status}


def _episode_line(episode: dict) -> str:
    f = episode.get("features") or {}
    keys = ("rsi_14", "regime", "m15_trend", "vol_state", "hour_pkt")
    shown = ", ".join(f"{k}={f.get(k)}" for k in keys if k in f)
    return f"- {episode['signal_time'][:16]} {episode['result']} ({shown})"


def render_prompt(setup: Setup, features: dict, episodes: list[dict], payout: float) -> str:
    wins = sum(e["result"] == "WIN" for e in episodes)
    losses = sum(e["result"] == "LOSS" for e in episodes)
    decided = wins + losses
    record = f"{wins}/{decided} wins" if decided else "no history yet"
    rule = {"id": setup.id, "version": setup.version, "name": setup.name, "direction": setup.direction,
            "conditions": list(setup.conditions), "invalidations": list(setup.invalidations), "notes": setup.notes}
    lines = [
        "## Rule (approved)",
        json.dumps(rule, ensure_ascii=False, indent=1),
        "## Candidate snapshot (candle just closed)",
        json.dumps(features, ensure_ascii=False, sort_keys=True),
        f"## Similar past episodes of this rule ({record}; break-even win rate {break_even(payout):.1%})",
        *([_episode_line(e) for e in episodes[:20]] or ["- none"]),
        "Return your decision.",
    ]
    return "\n".join(lines)


class Confirmer:
    def __init__(self, client: BrainClient, on_unavailable: str = "skip", timeout: float = 8.0, effort: str = "low"):
        self.client = client
        self.on_unavailable = on_unavailable
        self.timeout = timeout
        self.effort = effort

    def decide(self, *, setup: Setup, features: dict, episodes: list[dict], payout: float, now) -> Verdict:
        try:
            data = self.client.ask_json(
                purpose="confirm", tier="fast", system=CONFIRM_SYSTEM,
                prompt=render_prompt(setup, features, episodes, payout), schema=CONFIRM_SCHEMA,
                now=now, max_tokens=2048, timeout=self.timeout, effort=self.effort,
            )
        except BrainUnavailable as exc:
            allowed = self.on_unavailable == "rules_only"
            return Verdict(allowed, "UNAVAILABLE", f"AI ka jawab nahi aaya ({exc.status})", None, exc.status)
        decision = data["decision"]
        return Verdict(decision == "CONFIRM", decision, str(data["reason"])[:300], data.get("confidence"), "ok")
