"""KSoR — Knowledge System of Record (the handbook).

The Ustad's approved setups (ksor/setups/*.yaml) and the risk policy
(ksor/risk_policy.yaml). Only `approved` setups are used live; drafts can be
backtested. The agent reads KSoR and may *propose* changes (SSoR
lesson_proposals) but never edits it — a human approves and commits.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from .expr import ExprError, check_names, parse

STATUSES = ("draft", "approved", "retired")
DIRECTIONS = ("CALL", "PUT")
ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]{1,15}$")
PAIR_PATTERN = re.compile(r"^[A-Z]{6}$")


class KsorError(ValueError):
    """A KSoR file that is missing something or breaks a rule."""


@dataclass(frozen=True)
class Setup:
    id: str
    name: str
    version: int
    status: str
    direction: str
    pairs: tuple[str, ...]
    timeframe: str
    sessions: tuple[str, ...]
    conditions: tuple[str, ...]
    invalidations: tuple[str, ...]
    expiry_minutes: int
    entry: str
    approved_by: str | None
    approved_on: str | None
    source: str | None
    evidence: str | None
    notes: str | None
    path: Path | None = None

    @property
    def key(self) -> str:
        return f"{self.id}@v{self.version}"

    def referenced_features(self) -> set[str]:
        from .expr import names

        found: set[str] = set()
        for expr in self.conditions + self.invalidations:
            found |= names(expr)
        return found


def _as_tuple(value) -> tuple:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return (value,)


def setup_from_dict(raw: dict, path: Path | None = None) -> Setup:
    if not isinstance(raw, dict):
        raise KsorError(f"{path}: setup file must be a YAML mapping")
    where = path.name if path else raw.get("id", "setup")

    def need(key):
        if raw.get(key) in (None, "", []):
            raise KsorError(f"{where}: '{key}' is required")
        return raw[key]

    setup = Setup(
        id=str(need("id")).strip(),
        name=str(need("name")).strip(),
        version=need("version"),
        status=str(need("status")).strip().lower(),
        direction=str(need("direction")).strip().upper(),
        pairs=tuple(str(p).upper() for p in _as_tuple(need("pairs"))),
        timeframe=str(raw.get("timeframe", "M1")).upper(),
        sessions=tuple(str(s) for s in _as_tuple(raw.get("sessions"))),
        conditions=tuple(str(c) for c in _as_tuple(need("conditions"))),
        invalidations=tuple(str(c) for c in _as_tuple(raw.get("invalidations"))),
        expiry_minutes=raw.get("expiry_minutes", 1),
        entry=str(raw.get("entry", "next_open")),
        approved_by=raw.get("approved_by"),
        approved_on=None if raw.get("approved_on") is None else str(raw.get("approved_on")),
        source=raw.get("source"),
        evidence=raw.get("evidence"),
        notes=raw.get("notes"),
        path=path,
    )
    problems = setup_problems(setup)
    if problems:
        raise KsorError(f"{where}: " + "; ".join(problems))
    return setup


def setup_problems(setup: Setup, known_features=None, known_sessions=None) -> list[str]:
    problems = []
    if not ID_PATTERN.match(setup.id):
        problems.append(f"id {setup.id!r} should look like R07 (capital letter + letters/digits)")
    if not isinstance(setup.version, int) or isinstance(setup.version, bool) or setup.version < 1:
        problems.append("version must be a whole number >= 1")
    if setup.status not in STATUSES:
        problems.append(f"status must be one of {STATUSES}")
    if setup.direction not in DIRECTIONS:
        problems.append("direction must be CALL or PUT")
    bad_pairs = [p for p in setup.pairs if not PAIR_PATTERN.match(p)]
    if bad_pairs:
        problems.append(f"pairs look wrong: {bad_pairs} (use EURUSD style)")
    if setup.timeframe != "M1":
        problems.append("only timeframe M1 is supported for now")
    expiry = setup.expiry_minutes
    if not isinstance(expiry, int) or isinstance(expiry, bool) or not 1 <= expiry <= 15:
        problems.append("expiry_minutes must be a whole number from 1 to 15")
    if setup.entry != "next_open":
        problems.append("entry must be 'next_open' (trade at the next candle's open)")
    if setup.status == "approved" and not (setup.approved_by and setup.approved_on):
        problems.append("an approved setup needs approved_by and approved_on")
    for expr in setup.conditions + setup.invalidations:
        try:
            parse(expr)
            if known_features is not None:
                check_names(expr, known_features)
        except ExprError as exc:
            problems.append(str(exc))
    if known_sessions is not None:
        unknown = [s for s in setup.sessions if s not in known_sessions]
        if unknown:
            problems.append(f"unknown sessions {unknown}; known: {sorted(known_sessions)}")
    return problems


def load_setup(path: Path | str) -> Setup:
    path = Path(path)
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return setup_from_dict(raw, path)


def load_setups(
    directory: Path | str,
    statuses: tuple[str, ...] = ("approved",),
    known_features=None,
    known_sessions=None,
) -> list[Setup]:
    """Load setups with the given statuses. Raises KsorError listing every problem."""
    directory = Path(directory)
    setups, problems, seen = [], [], {}
    for path in sorted(directory.glob("*.yaml")):
        try:
            setup = load_setup(path)
        except (KsorError, yaml.YAMLError) as exc:
            problems.append(str(exc))
            continue
        if setup.id in seen:
            problems.append(f"{path.name}: id {setup.id} already used by {seen[setup.id]}")
            continue
        seen[setup.id] = path.name
        extra = setup_problems(setup, known_features, known_sessions)
        if extra:
            problems.append(f"{path.name}: " + "; ".join(extra))
            continue
        if setup.status in statuses:
            setups.append(setup)
    if problems:
        raise KsorError("KSoR problems:\n- " + "\n- ".join(problems))
    return setups


def governance_warnings(setups: list[Setup], changelog_text: str) -> list[str]:
    """Approved setups should have a CHANGELOG line mentioning 'R07 v2' style id/version."""
    warnings = []
    for setup in setups:
        if setup.status == "approved" and f"{setup.id} v{setup.version}" not in changelog_text:
            warnings.append(f"{setup.id} v{setup.version} is approved but not in ksor/CHANGELOG.md")
    return warnings


@dataclass(frozen=True)
class RiskPolicy:
    version: int
    status: str
    approved_by: str | None
    approved_on: str | None
    allowed_sessions: tuple[str, ...]
    max_signals_per_day: int
    max_losses_per_day: int
    cooldown_after_losses: int
    cooldown_minutes: int
    min_minutes_between_signals: int
    news_impacts: tuple[str, ...]
    news_minutes_before: int
    news_minutes_after: int
    max_feed_lag_seconds: float
    min_payout: float
    entry_window_seconds: int
    stake_percent: float
    martingale: bool
    news_whole_day: bool = False  # Ustad: no trading at all on a day with relevant news
    news_day_timezone: str = "Asia/Karachi"  # whose calendar day "the news day" is


def risk_policy_from_dict(raw: dict, known_sessions=None) -> RiskPolicy:
    if not isinstance(raw, dict):
        raise KsorError("risk policy must be a YAML mapping")
    cooldown = raw.get("cooldown") or {}
    news = raw.get("news_blackout") or {}
    try:
        policy = RiskPolicy(
            version=int(raw.get("version", 1)),
            status=str(raw.get("status", "draft")).lower(),
            approved_by=raw.get("approved_by"),
            approved_on=None if raw.get("approved_on") is None else str(raw.get("approved_on")),
            allowed_sessions=tuple(_as_tuple(raw.get("allowed_sessions"))),
            max_signals_per_day=int(raw["max_signals_per_day"]),
            max_losses_per_day=int(raw["max_losses_per_day"]),
            cooldown_after_losses=int(cooldown.get("after_consecutive_losses", 2)),
            cooldown_minutes=int(cooldown.get("minutes", 10)),
            min_minutes_between_signals=int(raw.get("min_minutes_between_signals", 2)),
            news_impacts=tuple(str(i).lower() for i in _as_tuple(news.get("impact", ["high"]))),
            news_minutes_before=int(news.get("minutes_before", 15)),
            news_minutes_after=int(news.get("minutes_after", 15)),
            max_feed_lag_seconds=float(raw.get("max_feed_lag_seconds", 5)),
            min_payout=float(raw.get("min_payout", 0.75)),
            entry_window_seconds=int(raw.get("entry_window_seconds", 10)),
            stake_percent=float(raw.get("stake_percent", 1.0)),
            martingale=bool(raw.get("martingale", False)),
            news_whole_day=bool(news.get("whole_day", False)),
            news_day_timezone=str(news.get("day_timezone", "Asia/Karachi")),
        )
    except KeyError as exc:
        raise KsorError(f"risk policy is missing {exc.args[0]!r}") from None
    problems = []
    try:
        ZoneInfo(policy.news_day_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        problems.append(f"news_blackout.day_timezone {policy.news_day_timezone!r} is not a timezone name")
    if policy.martingale:
        problems.append("martingale must stay false — it is never allowed")
    if policy.status not in STATUSES:
        problems.append(f"status must be one of {STATUSES}")
    if policy.status == "approved" and not (policy.approved_by and policy.approved_on):
        problems.append("an approved policy needs approved_by and approved_on")
    for name in ("max_signals_per_day", "max_losses_per_day", "cooldown_minutes", "entry_window_seconds"):
        if getattr(policy, name) <= 0:
            problems.append(f"{name} must be positive")
    if not 0 < policy.min_payout < 1.5:
        problems.append("min_payout looks wrong (use 0.75 for 75%)")
    if known_sessions is not None:
        unknown = [s for s in policy.allowed_sessions if s not in known_sessions]
        if unknown:
            problems.append(f"unknown allowed_sessions {unknown}")
    if problems:
        raise KsorError("risk policy: " + "; ".join(problems))
    return policy


def load_risk_policy(path: Path | str, known_sessions=None) -> RiskPolicy:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return risk_policy_from_dict(raw, known_sessions)


def ksor_commit(ksor_dir: Path | str) -> str:
    """Short git commit of the last change to KSoR (+ '-dirty' if edited since). Provenance."""
    ksor_dir = Path(ksor_dir)
    try:
        commit = subprocess.run(
            ["git", "log", "-1", "--format=%h", "--", "."],
            cwd=ksor_dir, capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "."],
            cwd=ksor_dir, capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "nogit"
    if not commit:
        return "uncommitted"
    return f"{commit}-dirty" if dirty else commit
