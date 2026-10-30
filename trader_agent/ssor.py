"""SSoR — State System of Record: the case file.

Every signal, what the human did, how it ended, reviews, reflections, lesson
proposals and every gate decision. Append-only: SQLite triggers reject UPDATE
and DELETE, so the history can be trusted and replayed. "Current status" is
always derived from the latest rows.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .timeutil import as_utc

APPEND_ONLY_TABLES = (
    "signals",
    "human_actions",
    "outcomes",
    "reviews",
    "reflections",
    "lesson_proposals",
    "proposal_decisions",
    "decision_log",
    "ai_usage",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('live', 'shadow', 'replay', 'backtest')),
    pair TEXT NOT NULL,
    setup_id TEXT NOT NULL,
    setup_version INTEGER NOT NULL,
    ksor_commit TEXT,
    direction TEXT NOT NULL CHECK (direction IN ('CALL', 'PUT')),
    bar_time TEXT NOT NULL,
    signal_time TEXT NOT NULL,
    entry_deadline TEXT NOT NULL,
    expiry_minutes INTEGER NOT NULL,
    payout REAL,
    features_json TEXT NOT NULL,
    gate_json TEXT,
    brain_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_signals_time ON signals (signal_time);

CREATE TABLE IF NOT EXISTS human_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL REFERENCES signals (id),
    action TEXT NOT NULL CHECK (action IN ('TAKEN', 'SKIPPED')),
    at TEXT NOT NULL,
    reaction_seconds REAL,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_actions_signal ON human_actions (signal_id);

CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL REFERENCES signals (id),
    source TEXT NOT NULL CHECK (source IN ('feed', 'broker')),
    result TEXT NOT NULL CHECK (result IN ('WIN', 'LOSS', 'DRAW')),
    entry_price REAL,
    exit_price REAL,
    payout REAL,
    pnl_units REAL,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outcomes_signal ON outcomes (signal_id);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL REFERENCES signals (id),
    category TEXT NOT NULL CHECK (category IN ('normal', 'agent_error', 'execution_error', 'news_spike')),
    note TEXT,
    at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reflections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER REFERENCES signals (id),
    author TEXT NOT NULL CHECK (author IN ('agent', 'human')),
    text TEXT NOT NULL,
    tags TEXT,
    at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lesson_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    pattern TEXT NOT NULL,
    evidence_signal_ids TEXT NOT NULL,
    sample_size INTEGER NOT NULL,
    stats_json TEXT,
    proposed_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS proposal_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER NOT NULL REFERENCES lesson_proposals (id),
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    decided_by TEXT NOT NULL,
    note TEXT,
    at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    pair TEXT NOT NULL,
    setup_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('signal', 'blocked')),
    reasons_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_time ON decision_log (at);

CREATE TABLE IF NOT EXISTS ai_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    purpose TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_time ON ai_usage (at);
"""

TRIGGERS = "\n".join(
    f"""
CREATE TRIGGER IF NOT EXISTS {table}_no_update BEFORE UPDATE ON {table}
BEGIN SELECT RAISE(ABORT, 'SSoR is append-only'); END;
CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table}
BEGIN SELECT RAISE(ABORT, 'SSoR is append-only'); END;
"""
    for table in APPEND_ONLY_TABLES
)


def iso(ts) -> str:
    return as_utc(ts).isoformat()


def _json(value) -> str:
    return json.dumps(value, default=str, ensure_ascii=False, sort_keys=True)


def pnl_units(result: str, payout: float | None) -> float:
    if result == "WIN":
        return float(payout or 0.0)
    if result == "LOSS":
        return -1.0
    return 0.0


@dataclass
class SignalRecord:
    mode: str
    pair: str
    setup_id: str
    setup_version: int
    direction: str
    bar_time: pd.Timestamp
    signal_time: pd.Timestamp
    entry_deadline: pd.Timestamp
    expiry_minutes: int
    payout: float | None
    features: dict = field(default_factory=dict)
    gate: dict | None = None
    brain: dict | None = None
    ksor_commit: str | None = None


class SSoR:
    def __init__(self, path: Path | str):
        path_str = str(path)
        if path_str != ":memory:":
            Path(path_str).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path_str)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA + TRIGGERS)
        self.conn.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '1')")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "SSoR":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- writes (insert only) -------------------------------------------------

    def _insert(self, table: str, values: dict) -> int:
        columns = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        cursor = self.conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks})", list(values.values()))
        self.conn.commit()
        return int(cursor.lastrowid)

    def record_signal(self, rec: SignalRecord, created_at=None) -> int:
        return self._insert(
            "signals",
            {
                "created_at": iso(created_at or pd.Timestamp.now(tz="UTC")),
                "mode": rec.mode,
                "pair": rec.pair.upper(),
                "setup_id": rec.setup_id,
                "setup_version": int(rec.setup_version),
                "ksor_commit": rec.ksor_commit,
                "direction": rec.direction,
                "bar_time": iso(rec.bar_time),
                "signal_time": iso(rec.signal_time),
                "entry_deadline": iso(rec.entry_deadline),
                "expiry_minutes": int(rec.expiry_minutes),
                "payout": rec.payout,
                "features_json": _json(rec.features),
                "gate_json": None if rec.gate is None else _json(rec.gate),
                "brain_json": None if rec.brain is None else _json(rec.brain),
            },
        )

    def record_action(self, signal_id: int, action: str, at, note: str | None = None) -> int:
        signal = self.get_signal(signal_id)
        if signal is None:
            raise KeyError(f"no signal #{signal_id}")
        reaction = (as_utc(at) - pd.Timestamp(signal["signal_time"])).total_seconds()
        return self._insert(
            "human_actions",
            {"signal_id": signal_id, "action": action, "at": iso(at), "reaction_seconds": reaction, "note": note},
        )

    def record_outcome(self, signal_id: int, source: str, result: str, at, entry_price=None, exit_price=None, payout=None) -> int:
        if payout is None:
            signal = self.get_signal(signal_id)
            payout = signal["payout"] if signal else None
        return self._insert(
            "outcomes",
            {
                "signal_id": signal_id,
                "source": source,
                "result": result,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "payout": payout,
                "pnl_units": pnl_units(result, payout),
                "at": iso(at),
            },
        )

    def record_review(self, signal_id: int, category: str, at, note: str | None = None) -> int:
        return self._insert("reviews", {"signal_id": signal_id, "category": category, "note": note, "at": iso(at)})

    def record_reflection(self, text: str, author: str, at, signal_id: int | None = None, tags=()) -> int:
        return self._insert(
            "reflections",
            {"signal_id": signal_id, "author": author, "text": text, "tags": ",".join(tags), "at": iso(at)},
        )

    def propose_lesson(self, pattern: str, evidence_signal_ids, stats: dict, proposed_by: str, at) -> int:
        ids = [int(i) for i in evidence_signal_ids]
        return self._insert(
            "lesson_proposals",
            {
                "created_at": iso(at),
                "pattern": pattern,
                "evidence_signal_ids": _json(ids),
                "sample_size": len(ids),
                "stats_json": _json(stats),
                "proposed_by": proposed_by,
            },
        )

    def decide_proposal(self, proposal_id: int, decision: str, decided_by: str, at, note: str | None = None) -> int:
        return self._insert(
            "proposal_decisions",
            {"proposal_id": proposal_id, "decision": decision, "decided_by": decided_by, "note": note, "at": iso(at)},
        )

    def record_ai_usage(self, at, purpose: str, model: str, status: str, input_tokens: int = 0,
                        output_tokens: int = 0, latency_ms: int | None = None) -> int:
        return self._insert(
            "ai_usage",
            {"at": iso(at), "purpose": purpose, "model": model, "status": status,
             "input_tokens": int(input_tokens), "output_tokens": int(output_tokens), "latency_ms": latency_ms},
        )

    def log_decision(self, at, pair: str, setup_id: str, decision: str, reasons) -> int:
        return self._insert(
            "decision_log",
            {"at": iso(at), "pair": pair.upper(), "setup_id": setup_id, "decision": decision, "reasons_json": _json(list(reasons))},
        )

    # ---- reads ----------------------------------------------------------------

    @staticmethod
    def _signal_dict(row: sqlite3.Row) -> dict:
        data = dict(row)
        data["features"] = json.loads(data.pop("features_json"))
        gate, brain = data.pop("gate_json"), data.pop("brain_json")
        data["gate"] = json.loads(gate) if gate else None
        data["brain"] = json.loads(brain) if brain else None
        return data

    def get_signal(self, signal_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
        return self._signal_dict(row) if row else None

    def signals_between(self, start, end, mode: str | None = None) -> list[dict]:
        query = "SELECT * FROM signals WHERE signal_time >= ? AND signal_time < ?"
        params: list = [iso(start), iso(end)]
        if mode:
            query += " AND mode = ?"
            params.append(mode)
        rows = self.conn.execute(query + " ORDER BY signal_time, id", params).fetchall()
        return [self._signal_dict(r) for r in rows]

    def last_signals(self, limit: int = 5) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [self._signal_dict(r) for r in rows]

    def latest_action(self, signal_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM human_actions WHERE signal_id = ? ORDER BY id DESC LIMIT 1", (signal_id,)
        ).fetchone()
        return dict(row) if row else None

    def best_outcome(self, signal_id: int) -> dict | None:
        """The human-confirmed (broker) result wins over the feed's estimate."""
        row = self.conn.execute(
            "SELECT * FROM outcomes WHERE signal_id = ? ORDER BY source = 'broker' DESC, id DESC LIMIT 1",
            (signal_id,),
        ).fetchone()
        return dict(row) if row else None

    def unresolved_signals(self, mode: str | None = None) -> list[dict]:
        query = (
            "SELECT * FROM signals s WHERE NOT EXISTS "
            "(SELECT 1 FROM outcomes o WHERE o.signal_id = s.id AND o.source = 'feed')"
        )
        params: list = []
        if mode:
            query += " AND s.mode = ?"
            params.append(mode)
        rows = self.conn.execute(query + " ORDER BY s.signal_time", params).fetchall()
        return [self._signal_dict(r) for r in rows]

    def has_feed_outcome(self, signal_id: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM outcomes WHERE signal_id = ? AND source = 'feed' LIMIT 1", (signal_id,)
        ).fetchone()
        return row is not None

    def setup_outcomes(self, setup_id: str, modes=("live",), limit: int = 50, before=None) -> list[dict]:
        """Most recent signals of a setup that have a result (newest first), with the human's action."""
        marks = ", ".join("?" for _ in modes)
        query = f"SELECT * FROM signals WHERE setup_id = ? AND mode IN ({marks})"
        params: list = [setup_id, *modes]
        if before is not None:
            query += " AND signal_time < ?"
            params.append(iso(before))
        rows = self.conn.execute(query + " ORDER BY signal_time DESC, id DESC", params).fetchall()
        out = []
        for row in rows:
            signal = self._signal_dict(row)
            outcome = self.best_outcome(signal["id"])
            if outcome is None:
                continue
            action = self.latest_action(signal["id"])
            signal["result"] = outcome["result"]
            signal["result_source"] = outcome["source"]
            signal["action"] = action["action"] if action else None
            out.append(signal)
            if len(out) >= limit:
                break
        return out

    def taken_without_broker_result(self, start, end) -> list[dict]:
        """Live signals the human took but whose Quotex result has not been entered yet."""
        rows = self.conn.execute(
            "SELECT s.* FROM signals s WHERE s.mode = 'live' AND s.signal_time >= ? AND s.signal_time < ? "
            "AND EXISTS (SELECT 1 FROM human_actions a WHERE a.signal_id = s.id AND a.action = 'TAKEN' "
            "AND a.id = (SELECT MAX(id) FROM human_actions WHERE signal_id = s.id)) "
            "AND NOT EXISTS (SELECT 1 FROM outcomes o WHERE o.signal_id = s.id AND o.source = 'broker') "
            "ORDER BY s.signal_time",
            (iso(start), iso(end)),
        ).fetchall()
        return [self._signal_dict(r) for r in rows]

    def ai_usage_between(self, start, end) -> dict:
        row = self.conn.execute(
            "SELECT COUNT(*) AS calls, COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens "
            "FROM ai_usage WHERE at >= ? AND at < ?",
            (iso(start), iso(end)),
        ).fetchone()
        return {"calls": int(row["calls"]), "tokens": int(row["tokens"])}

    def pending_proposals(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM lesson_proposals p WHERE NOT EXISTS "
            "(SELECT 1 FROM proposal_decisions d WHERE d.proposal_id = p.id) ORDER BY p.id"
        ).fetchall()
        return [dict(r) for r in rows]

    def recent_decisions(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM decision_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for row in rows:
            data = dict(row)
            data["reasons"] = json.loads(data.pop("reasons_json"))
            out.append(data)
        return out

    def day_summary(self, start, end, mode: str | None = None) -> dict:
        """Counts for a time window: signals, what the human did, and results."""
        signals = self.signals_between(start, end, mode)
        summary = {
            "signals": len(signals),
            "taken": 0,
            "skipped": 0,
            "no_action": 0,
            "late_entries": 0,
            "taken_wins": 0,
            "taken_losses": 0,
            "taken_draws": 0,
            "taken_pnl_units": 0.0,
            "all_wins": 0,
            "all_losses": 0,
            "all_draws": 0,
        }
        plural = {"WIN": "wins", "LOSS": "losses", "DRAW": "draws"}
        for signal in signals:
            action = self.latest_action(signal["id"])
            outcome = self.best_outcome(signal["id"])
            if outcome:
                summary[f"all_{plural[outcome['result']]}"] += 1
            if action is None:
                summary["no_action"] += 1
                continue
            if action["action"] == "SKIPPED":
                summary["skipped"] += 1
                continue
            summary["taken"] += 1
            if action["at"] > signal["entry_deadline"]:
                summary["late_entries"] += 1
            if outcome:
                summary[f"taken_{plural[outcome['result']]}"] += 1
                summary["taken_pnl_units"] += outcome["pnl_units"] or 0.0
        decided = summary["taken_wins"] + summary["taken_losses"]
        summary["taken_win_rate"] = summary["taken_wins"] / decided if decided else None
        decided_all = summary["all_wins"] + summary["all_losses"]
        summary["all_win_rate"] = summary["all_wins"] / decided_all if decided_all else None
        return summary
