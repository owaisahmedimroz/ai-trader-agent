"""Phase 4 — learning loop helpers (deterministic, no AI needed).

- setup_health / check_drift: if a live setup's recent results fall clearly below
  break-even, pause it through the DSoR control file and alert the human.
- weekly_report: one page with setups, AI value, discipline, loss reviews,
  AI calibration and pending lesson proposals.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from .binary import break_even
from .control import Control
from .ssor import SSoR
from .stats import summarize, wilson_interval


@dataclass(frozen=True)
class SetupHealth:
    setup_id: str
    trades: int
    wins: int
    losses: int
    win_rate: float | None
    ci_low: float | None
    ci_high: float | None
    break_even: float
    status: str  # WARMUP | OK | WATCH | DRIFT

    def line(self) -> str:
        rate = "—" if self.win_rate is None else f"{self.win_rate:.0%}"
        band = "" if self.ci_low is None else f" (range {self.ci_low:.0%}–{self.ci_high:.0%})"
        icon = {"OK": "🟢", "WATCH": "🟡", "DRIFT": "🔴", "WARMUP": "⚪"}[self.status]
        return f"{icon} {self.setup_id}: {self.status} — {self.wins}/{self.wins + self.losses} jeet = {rate}{band}, break-even {self.break_even:.0%}"


def setup_health(ssor: SSoR, setup_id: str, payout: float, window: int = 50, min_trades: int = 30, modes=("live",)) -> SetupHealth:
    """Health of a setup from its last `window` results (all live signals, taken or not)."""
    results = [s["result"] for s in ssor.setup_outcomes(setup_id, modes=modes, limit=window)]
    wins, losses = results.count("WIN"), results.count("LOSS")
    decided = wins + losses
    be = break_even(payout)
    low, high = wilson_interval(wins, decided) if decided else (None, None)
    rate = wins / decided if decided else None
    if decided < min_trades:
        status = "WARMUP"
    elif high < be:
        status = "DRIFT"
    elif rate < be:
        status = "WATCH"
    else:
        status = "OK"
    return SetupHealth(setup_id, len(results), wins, losses, rate, low, high, be, status)


def check_drift(agent, notifier=None, now=None) -> list[SetupHealth]:
    """Pause drifting live setups (DSoR control file) and alert. Returns the newly paused ones."""
    if agent.mode != "live" or agent.control_path is None or not agent.settings.learning.get("auto_pause", True):
        return []
    learning = agent.settings.learning
    control = Control.load(agent.control_path)
    paused = []
    for setup in agent.setups:
        if setup.id in control.paused_setups:
            continue
        health = setup_health(agent.ssor, setup.id, agent.payout_for(setup.pairs[0], control),
                              int(learning["drift_window"]), int(learning["drift_min_trades"]))
        if health.status != "DRIFT":
            continue
        control.paused_setups[setup.id] = (
            f"drift {datetime.now(timezone.utc):%Y-%m-%d}: {health.wins}/{health.wins + health.losses} jeet, "
            f"range ki upar wali hadd {health.ci_high:.0%} < break-even {health.break_even:.0%}"
        )
        paused.append(health)
    if paused:
        control.save(agent.control_path)
        stamp = now or pd.Timestamp.now(tz="UTC")
        for health in paused:
            agent.ssor.record_reflection(f"auto-paused (drift): {health.line()}", "agent", stamp, tags=("drift", "dsor"))
            if notifier is not None:
                notifier.send_text(f"⛔ {health.setup_id} khud ruk gaya (drift).\n{health.line()}\n"
                                   f"Ustad ke saath review karein; dobara chalane ke liye /unpause {health.setup_id}")
    return paused


# ---- weekly report -------------------------------------------------------------------


def _rate(results: list[str]) -> str:
    s = summarize(results, 0.8)
    if s["win_rate"] is None:
        return "— (0)"
    return f"{s['win_rate']:.0%} ({s['wins'] + s['losses']}, range {s['ci_low']:.0%}–{s['ci_high']:.0%})"


def weekly_report(ssor: SSoR, start, end, payout: float, setup_ids: list[str]) -> str:
    """Markdown report for [start, end)."""
    signals = ssor.signals_between(start, end)
    by_mode: dict[str, list[dict]] = {}
    for signal in signals:
        outcome = ssor.best_outcome(signal["id"])
        signal["result"] = outcome["result"] if outcome else None
        signal["action"] = (ssor.latest_action(signal["id"]) or {}).get("action")
        by_mode.setdefault(signal["mode"], []).append(signal)
    live = by_mode.get("live", [])
    out = [f"# Hafta war report — {pd.Timestamp(start):%Y-%m-%d} → {pd.Timestamp(end):%Y-%m-%d}", ""]
    out += ["⚠️ Chand trades ka nateeja ittefaq ho sakta hai — range (95%) dekhein.", ""]

    out += ["## Setups (live signals, lagaye hon ya nahi)", "", "| Setup | Win rate | Sehat |", "|---|---|---|"]
    for setup_id in setup_ids:
        results = [s["result"] for s in live if s["setup_id"] == setup_id and s["result"]]
        out.append(f"| {setup_id} | {_rate(results)} | {setup_health(ssor, setup_id, payout).status} |")
    shadow_ids = sorted({s["setup_id"] for s in by_mode.get("shadow", [])})
    if shadow_ids:
        out += ["", "Shadow (test / AI ne roke):"]
        for setup_id in shadow_ids:
            results = [s["result"] for s in by_mode["shadow"] if s["setup_id"] == setup_id and s["result"]]
            out.append(f"- {setup_id}: {_rate(results)}")

    confirmed = [s["result"] for s in live if (s.get("brain") or {}).get("decision") == "CONFIRM" and s["result"]]
    vetoed = [s["result"] for s in by_mode.get("shadow", []) if (s.get("brain") or {}).get("decision") == "VETO" and s["result"]]
    out += ["", "## AI ki value", "", f"- AI ne CONFIRM kiye: {_rate(confirmed)}", f"- AI ne VETO kiye (bheje nahi gaye): {_rate(vetoed)}",
            "- Agar VETO wale bhi utne hi jeette hain jitne CONFIRM wale, to AI faida nahi de raha.", ""]

    taken = [s for s in live if s["action"] == "TAKEN"]
    reactions = [r["reaction_seconds"] for s in taken if (r := ssor.latest_action(s["id"])) and r["reaction_seconds"] is not None]
    summary = ssor.day_summary(start, end, mode="live")
    out += ["## Discipline", "",
            f"- Signals {summary['signals']} · lagaye {summary['taken']} · chhore {summary['skipped']} · jawab nahi {summary['no_action']}",
            f"- Der se entries: {summary['late_entries']} · reaction (median): {statistics.median(reactions):.0f}s" if reactions
            else f"- Der se entries: {summary['late_entries']}",
            f"- Lagaye hue trades: {_rate([s['result'] for s in taken if s['result']])} · P&L {summary['taken_pnl_units']:+.2f} units", ""]

    rows = ssor.conn.execute(
        "SELECT r.category, COUNT(*) AS n FROM reviews r JOIN signals s ON s.id = r.signal_id "
        "WHERE s.signal_time >= ? AND s.signal_time < ? GROUP BY r.category",
        (pd.Timestamp(start).isoformat(), pd.Timestamp(end).isoformat()),
    ).fetchall()
    out += ["## Loss reviews", ""] + ([f"- {r['category']}: {r['n']}" for r in rows] or ["- koi review nahi"]) + [""]

    buckets: dict[str, list[str]] = {}
    for s in live:
        confidence = (s.get("brain") or {}).get("confidence")
        if confidence and s["result"]:
            buckets.setdefault(confidence, []).append(s["result"])
    if buckets:
        out += ["## AI calibration (confidence vs asal jeet)", ""] + [f"- {k}: {_rate(v)}" for k, v in sorted(buckets.items())] + [""]

    proposals = ssor.pending_proposals()
    out += ["## Sabaq ki tajaweez (faisla baqi)", ""]
    out += [f"- #{p['id']} ({p['sample_size']} trades): {p['pattern']}" for p in proposals] or ["- koi nahi"]
    return "\n".join(out) + "\n"
