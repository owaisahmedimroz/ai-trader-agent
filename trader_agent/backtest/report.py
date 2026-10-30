"""Backtest report: honest numbers, ranges and a plain-language verdict.

Verdict rules (per setup, on the out-of-sample part when one is given):
- KEEP  — at least 300 decided trades, the whole 95% range above break-even,
          and at least 60% of months (min 3) at or above break-even
- DROP  — at least 100 decided trades and even the top of the range is below break-even
- WATCH — anything else (not enough data, or the range still crosses break-even)
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ..stats import summarize, wilson_interval
from .engine import BacktestResult

MIN_TRADES_KEEP = 300
MIN_TRADES_DROP = 100
BREAKDOWNS = (
    ("session", "Session"),
    ("hour_pkt", "Ghanta (PKT)"),
    ("weekday", "Din (0 = Peer)"),
    ("regime", "Regime"),
    ("vol_state", "Volatility"),
    ("m15_trend", "M15 trend"),
    ("month", "Mahina"),
)


def pct(value) -> str:
    return "—" if value is None or pd.isna(value) else f"{value * 100:.1f}%"


def breakdown(trades: pd.DataFrame, by: str, payout: float) -> pd.DataFrame:
    rows = []
    for key, group in trades.groupby(by, sort=True):
        wins = int((group["result"] == "WIN").sum())
        losses = int((group["result"] == "LOSS").sum())
        decided = wins + losses
        low, high = wilson_interval(wins, decided)
        rows.append(
            {
                by: key,
                "trades": len(group),
                "win_rate": wins / decided if decided else None,
                "ci_low": low if decided else None,
                "ci_high": high if decided else None,
                "ev_per_trade": (wins * payout - losses) / len(group),
            }
        )
    return pd.DataFrame(rows)


def monthly_consistency(trades: pd.DataFrame, break_even: float) -> tuple[float | None, int]:
    if trades.empty:
        return None, 0
    by_month = trades[trades["result"] != "DRAW"].groupby("month")["result"].apply(lambda r: (r == "WIN").mean())
    if by_month.empty:
        return None, 0
    return float((by_month >= break_even).mean()), int(len(by_month))


def verdict(summary: dict, month_share: float | None, months: int) -> tuple[str, str]:
    if not summary["trades"] or summary["win_rate"] is None:
        return "NO DATA", "Koi trade nahi bani."
    decided = summary["wins"] + summary["losses"]
    be = summary["break_even"]
    if decided >= MIN_TRADES_DROP and summary["ci_high"] < be:
        return "DROP", f"Jeet ki upar wali hadd ({pct(summary['ci_high'])}) bhi break-even ({pct(be)}) se neeche hai."
    missing = []
    if decided < MIN_TRADES_KEEP:
        missing.append(f"sirf {decided} trades (kam az kam {MIN_TRADES_KEEP} chahiye)")
    if summary["ci_low"] <= be:
        missing.append(f"range ({pct(summary['ci_low'])}–{pct(summary['ci_high'])}) break-even {pct(be)} ko chhoo rahi hai")
    if months < 3 or (month_share or 0) < 0.6:
        missing.append(f"mahinon mein consistency kam ({pct(month_share)} of {months} months)")
    if not missing:
        return "KEEP", "Kaafi trades, poori range break-even se upar, aur mahinon mein mustaqil."
    return "WATCH", "Abhi sabit nahi: " + "; ".join(missing) + "."


def build_report(result: BacktestResult, meta: dict | None = None) -> dict:
    meta = dict(meta or {})
    payout = result.config.payout
    trades = result.trades
    sections = []
    for setup in result.setups:
        subset = trades[trades["setup_id"] == setup.id] if not trades.empty else trades
        results = subset["result"].tolist() if not subset.empty else []
        overall = summarize(results, payout)
        samples = {}
        judged = subset
        if result.config.oos_from is not None and not subset.empty:
            for name in ("in", "out"):
                part = subset[subset["sample"] == name]
                samples[name] = summarize(part["result"].tolist(), payout)
            if samples["out"]["trades"]:
                judged = subset[subset["sample"] == "out"]
        judged_summary = summarize(judged["result"].tolist() if not judged.empty else [], payout)
        share, months = monthly_consistency(judged, judged_summary["break_even"]) if not judged.empty else (None, 0)
        label, reason = verdict(judged_summary, share, months)
        tables = {}
        if not subset.empty:
            for column, title in BREAKDOWNS:
                tables[title] = breakdown(subset, column, payout)
        sections.append(
            {
                "setup": setup,
                "overall": overall,
                "samples": samples,
                "verdict": label,
                "reason": reason,
                "judged_on": "out-of-sample" if judged is not subset else "all data",
                "tables": tables,
            }
        )
    meta.setdefault("generated_at", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    return {"pair": result.pair, "config": result.config, "diagnostics": result.diagnostics, "meta": meta, "sections": sections}


def _warnings(report: dict) -> list[str]:
    notes = [
        "Prices data provider ki hain, Quotex ki nahi — yeh andaza hai. Asal imtihan demo par forward test hai.",
        "Entry = agli candle ka open, exit = expiry candle ka close. Insaan ki chand second ki der shamil nahi.",
        "Ek din ya chand trades ka nateeja ittefaq ho sakta hai — range (95%) dekhein, sirf win rate nahi.",
    ]
    if any(s["setup"].status != "approved" for s in report["sections"]):
        notes.insert(0, "DRAFT setups shamil hain — Ustad ki approval baqi hai.")
    if report["meta"].get("synthetic"):
        notes.insert(0, "SYNTHETIC (random) DATA — sirf pipeline test. In nateejon ka trading se koi talluq nahi.")
    return notes


def _summary_rows(summary: dict) -> list[tuple[str, str]]:
    return [
        ("Trades", str(summary["trades"])),
        ("Jeet / Haar / Draw", f"{summary['wins']} / {summary['losses']} / {summary['draws']}"),
        ("Win rate", pct(summary["win_rate"])),
        ("95% range", f"{pct(summary['ci_low'])} – {pct(summary['ci_high'])}"),
        ("Break-even", pct(summary["break_even"])),
        ("Har trade ka avg munafa (1 unit par)", "—" if summary["ev_per_trade"] is None else f"{summary['ev_per_trade']:+.3f}"),
        ("p-value (break-even se behtar?)", "—" if summary["p_value_vs_break_even"] is None else f"{summary['p_value_vs_break_even']:.3f}"),
        ("Lagatar sab se zyada loss", str(summary["max_losing_streak"])),
    ]


def _md_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_(khali)_\n"
    shown = frame.copy()
    for column in ("win_rate", "ci_low", "ci_high"):
        if column in shown:
            shown[column] = shown[column].map(pct)
    if "ev_per_trade" in shown:
        shown["ev_per_trade"] = shown["ev_per_trade"].map(lambda v: f"{v:+.3f}")
    header = "| " + " | ".join(map(str, shown.columns)) + " |"
    rule = "|" + "---|" * len(shown.columns)
    lines = ["| " + " | ".join(map(str, row)) + " |" for row in shown.itertuples(index=False)]
    return "\n".join([header, rule, *lines]) + "\n"


def render_markdown(report: dict) -> str:
    config, meta = report["config"], report["meta"]
    out = [f"# Backtest — {report['pair']}", ""]
    out.append(f"- Banaya: {meta['generated_at']}")
    if meta.get("data"):
        out.append(f"- Data: `{meta['data']}`")
    diag = report["diagnostics"]
    if diag.get("first_bar"):
        out.append(f"- Muddat: {diag['first_bar']} → {diag['last_bar']} ({diag['bars']} candles)")
    out.append(f"- Payout: {pct(config.payout)} · Risk gate: {'on' if config.use_gate else 'off'}")
    if config.oos_from is not None:
        out.append(f"- Out-of-sample (faisla isi par): {config.oos_from:%Y-%m-%d} ke baad")
    out += ["", "## ⚠️ Zaroori baatein", ""] + [f"- {note}" for note in _warnings(report)] + [""]
    for section in report["sections"]:
        setup = section["setup"]
        out += [f"## {setup.id} v{setup.version} — {setup.name} ({setup.direction}, {setup.status})", ""]
        out += [f"**Faisla: {section['verdict']}** ({section['judged_on']}) — {section['reason']}", ""]
        out += ["| | |", "|---|---|"] + [f"| {k} | {v} |" for k, v in _summary_rows(section["overall"])] + [""]
        for name, summary in section["samples"].items():
            label = "In-sample" if name == "in" else "Out-of-sample"
            out.append(f"- {label}: {summary['trades']} trades, win {pct(summary['win_rate'])} "
                       f"(range {pct(summary['ci_low'])}–{pct(summary['ci_high'])})")
        if section["samples"]:
            out.append("")
        for title, frame in section["tables"].items():
            out += [f"### {title}", "", _md_table(frame)]
    skipped = diag.get("skipped") or {}
    out += ["## Diagnostics", "", f"- Raw signals: {diag.get('raw_signals')}", f"- Skipped: {skipped}",
            f"- Gate ne roke: {diag.get('blocked', 0)}", ""]
    return "\n".join(out)


def render_html(report: dict) -> str:
    """Self-contained HTML version of the Markdown report."""
    body = []
    in_table = False
    for line in render_markdown(report).splitlines():
        if line.startswith("|"):
            cells = [html.escape(c.strip()) for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-"):
                continue
            if not in_table:
                body.append("<table>")
                in_table = True
            body.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            body.append("</table>")
            in_table = False
        text = html.escape(line).replace("**", "")
        if line.startswith("### "):
            body.append(f"<h3>{text[4:]}</h3>")
        elif line.startswith("## "):
            body.append(f"<h2>{text[3:]}</h2>")
        elif line.startswith("# "):
            body.append(f"<h1>{text[2:]}</h1>")
        elif line.startswith("- "):
            body.append(f"<p class='li'>• {text[2:]}</p>")
        elif text:
            body.append(f"<p>{text}</p>")
    if in_table:
        body.append("</table>")
    style = (
        "body{font-family:system-ui,sans-serif;max-width:960px;margin:24px auto;padding:0 16px;"
        "background:#fff;color:#1a1a1a}table{border-collapse:collapse;margin:8px 0 16px}"
        "td{border:1px solid #ccc;padding:4px 10px;font-size:14px}tr:first-child td{font-weight:600;background:#f3f3f3}"
        "h2{margin-top:32px;border-bottom:1px solid #ddd}.li{margin:2px 0}"
        "@media (prefers-color-scheme: dark){body{background:#151515;color:#e8e8e8}td{border-color:#444}"
        "tr:first-child td{background:#262626}h2{border-color:#333}}"
    )
    title = html.escape(f"Backtest — {report['pair']}")
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title><style>{style}</style></head><body>{''.join(body)}</body></html>"


def write_report(report: dict, out_dir: Path | str, stem: str) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path, html_path = out_dir / f"{stem}.md", out_dir / f"{stem}.html"
    md_path.write_text(render_markdown(report), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
    return md_path, html_path
