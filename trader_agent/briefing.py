"""Pre-session briefing — facts first (no AI needed), optional AI commentary."""

from __future__ import annotations

import pandas as pd

from .features import build_features
from .learning import setup_health
from .notifier.messages import pair_label, tz_label
from .timeutil import to_display


def briefing_facts(agent, candles_by_pair: dict[str, pd.DataFrame], now) -> str:
    """Plain-text facts: today's high-impact news, market state per pair, setup health."""
    tz = agent.settings.display_timezone
    control = agent.control()
    events = control.events() + list(agent.calendar_events)
    day = agent.sessions.trading_day_of(now)
    start, end = agent.sessions.trading_day_bounds(day)
    today = sorted((e for e in events if start <= e.time_utc < end and e.impact in agent.policy.news_impacts),
                   key=lambda e: e.time_utc)
    lines = [f"📋 Session briefing ({day})", "", "📰 Aaj ki bari news:"]
    lines += [f"- {to_display(e.time_utc, tz, '%H:%M')} {tz_label(tz)} {e.currency} {e.title}".rstrip() for e in today] or [
        "- koi nahi mili (calendar band ho to /news se khud daalein)"]
    lines += ["", "📊 Market:"]
    for pair, candles in candles_by_pair.items():
        if candles is None or candles.empty:
            continue
        row = build_features(candles, pair, agent.sessions, tz).iloc[-1]
        lines.append(f"- {pair_label(pair)}: 15m {row['m15_trend']}, 1h {row['h1_trend']}, {row['regime']}, vol {row['vol_state']}")
    lines += ["", "🧩 Setups:"]
    for setup in agent.setups:
        if setup.id in control.paused_setups:
            lines.append(f"- ⛔ {setup.id}: ruka hua — {control.paused_setups[setup.id]}")
        else:
            lines.append("- " + setup_health(agent.ssor, setup.id, agent.payout_for(setup.pairs[0], control)).line())
    if not agent.setups:
        lines.append("- koi approved setup nahi")
    return "\n".join(lines)
