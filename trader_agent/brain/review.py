"""Nightly review (reflections + lesson proposals) and the AI part of the briefing."""

from __future__ import annotations

import json

import pandas as pd

from ..ssor import SSoR
from .client import BrainClient, BrainUnavailable

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "reflections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "signal_id": {"type": "integer"},
                    "lesson": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["signal_id", "lesson", "tags"],
                "additionalProperties": False,
            },
        },
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "evidence_signal_ids": {"type": "array", "items": {"type": "integer"}},
                    "rationale": {"type": "string"},
                },
                "required": ["pattern", "evidence_signal_ids", "rationale"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "reflections", "proposals"],
    "additionalProperties": False,
}

REVIEW_SYSTEM = """\
You are the nightly reviewer for a personal, signal-only trading assistant. A human trades
1-minute binary options by hand from its signals; the rules come from an experienced trader
and change only with human approval.

From the records given:
1. Write short reflections on individual signals worth learning from (wins and losses):
   what in the snapshot or context explains the result. Most single results are noise —
   say so rather than inventing causes.
2. Propose a lesson only for a pattern supported by many signals (the evidence list must
   contain at least the minimum number of signal ids given below). A proposal describes a
   possible rule change for a human to consider; it is not applied automatically.
3. Give a short summary of the day.

Write all text in simple Roman Urdu. Use only signal ids that appear in the records.
"""

BRIEFING_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "watch": {"type": "array", "items": {"type": "string"}},
        "avoid": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "watch", "avoid"],
    "additionalProperties": False,
}

BRIEFING_SYSTEM = """\
You write a short pre-session briefing for a human who trades 1-minute binary options by hand
from rule-based signals. From the facts given (scheduled news, regime and trend per pair,
recent results per rule), say what to watch and what to avoid today. Do not predict prices
and do not invent news. Write in simple Roman Urdu; at most 3 items per list.
"""


def _record_line(signal: dict, ssor: SSoR) -> str:
    outcome = ssor.best_outcome(signal["id"])
    action = ssor.latest_action(signal["id"])
    review = ssor.conn.execute(
        "SELECT category FROM reviews WHERE signal_id = ? ORDER BY id DESC LIMIT 1", (signal["id"],)
    ).fetchone()
    f = signal.get("features") or {}
    keys = ("rsi_14", "regime", "m15_trend", "h1_trend", "vol_state", "hour_pkt")
    return json.dumps({
        "id": signal["id"], "mode": signal["mode"], "setup": f"{signal['setup_id']} v{signal['setup_version']}",
        "dir": signal["direction"], "time": signal["signal_time"][:16],
        "result": outcome["result"] if outcome else None, "human": action["action"] if action else None,
        "review": review["category"] if review else None, "brain": (signal.get("brain") or {}).get("decision"),
        "ctx": {k: f.get(k) for k in keys if k in f},
    }, ensure_ascii=False)


def nightly_review(client: BrainClient, ssor: SSoR, start, end, now, min_evidence: int = 30,
                   effort: str = "high", history_days: int = 30) -> dict:
    """Ask the deep model to review the day; save reflections and (well-supported) proposals."""
    today = ssor.signals_between(start, end)
    history = ssor.signals_between(pd.Timestamp(start) - pd.Timedelta(days=history_days), start)
    if not today:
        return {"summary": "Aaj koi signal nahi — review ki zaroorat nahi.", "reflections": 0, "proposals": 0, "downgraded": 0}
    prompt = "\n".join([
        f"Minimum evidence for a proposal: {min_evidence} signal ids.",
        "## Today's signals", *[_record_line(s, ssor) for s in today],
        f"## Previous {history_days} days (for patterns)", *[_record_line(s, ssor) for s in history[-400:]],
    ])
    data = client.ask_json(purpose="review", tier="deep", system=REVIEW_SYSTEM, prompt=prompt, schema=REVIEW_SCHEMA,
                           now=now, max_tokens=16000, timeout=600, effort=effort, stream=True)
    known = {s["id"] for s in today} | {s["id"] for s in history}
    saved_reflections = 0
    for item in data["reflections"]:
        if item["signal_id"] in known:
            ssor.record_reflection(item["lesson"], "agent", now, item["signal_id"], tuple(item["tags"]))
            saved_reflections += 1
    saved, downgraded = 0, 0
    for proposal in data["proposals"]:
        evidence = sorted({i for i in proposal["evidence_signal_ids"] if i in known})
        if len(evidence) >= min_evidence:
            ssor.propose_lesson(proposal["pattern"], evidence, {"rationale": proposal["rationale"]}, "agent", now)
            saved += 1
        else:  # not enough evidence yet: keep the idea as a reflection, not a proposal
            ssor.record_reflection(f"(data kam: {len(evidence)}) {proposal['pattern']} — {proposal['rationale']}",
                                   "agent", now, tags=("idea",))
            downgraded += 1
    ssor.record_reflection(data["summary"], "agent", now, tags=("daily_summary",))
    return {"summary": data["summary"], "reflections": saved_reflections, "proposals": saved, "downgraded": downgraded}


def ai_briefing(client: BrainClient, facts: str, now, effort: str = "medium") -> str | None:
    """AI commentary on the deterministic briefing facts. None when the AI is unavailable."""
    try:
        data = client.ask_json(purpose="briefing", tier="balanced", system=BRIEFING_SYSTEM, prompt=facts,
                               schema=BRIEFING_SCHEMA, now=now, max_tokens=4000, timeout=60, effort=effort)
    except BrainUnavailable:
        return None
    lines = [f"🤖 {data['summary']}"]
    lines += [f"👀 {item}" for item in data["watch"][:3]]
    lines += [f"🚫 {item}" for item in data["avoid"][:3]]
    return "\n".join(lines)
