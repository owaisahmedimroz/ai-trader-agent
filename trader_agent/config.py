"""Settings (config/settings.yaml) and environment values (.env / environment).

Secrets never live in the repository: they are read from environment variables,
optionally loaded from a local, git-ignored `.env` file. AI model IDs also come
from `.env`, so the repository never pins a model.
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

SECRET_KEYS = (
    "ANTHROPIC_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "MT5_LOGIN",
    "MT5_PASSWORD",
    "MT5_SERVER",
)
MODEL_KEYS = ("BRAIN_MODEL_FAST", "BRAIN_MODEL_BALANCED", "BRAIN_MODEL_DEEP")
ENV_KEYS = SECRET_KEYS + MODEL_KEYS

DEFAULTS = {
    "live": {
        "lookback_bars": 5000,
        "heartbeat_minutes": 15,
        "heads_up": True,
        "heads_up_second": 45,
        "settle_seconds": 2.0,
        "result_prompt_delay_seconds": 20,
    },
    "calendar": {"enabled": False, "url": "", "refresh_hours": 6},
    "brain": {
        "enabled": False,
        "on_unavailable": "skip",
        "confirm_timeout_seconds": 8,
        "max_calls_per_day": 300,
        "max_tokens_per_day": 2_000_000,
        "effort": {"confirm": "low", "briefing": "medium", "review": "high"},
    },
    "learning": {"drift_window": 50, "drift_min_trades": 30, "auto_pause": True, "proposal_min_evidence": 30},
}


def _merge(base: dict, override: dict | None) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        out[key] = _merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


@dataclass(frozen=True)
class Settings:
    pairs: tuple[str, ...]
    display_timezone: str
    payout_default: float
    feed: str
    db_path: Path
    ksor_dir: Path
    reports_dir: Path
    history_dir: Path
    lookback_bars: int
    heartbeat_minutes: int
    mt5_symbols: dict[str, str] = field(default_factory=dict)
    mt5_server_utc_offset_hours: float | None = None
    live: dict = field(default_factory=lambda: copy.deepcopy(DEFAULTS["live"]))
    calendar: dict = field(default_factory=lambda: copy.deepcopy(DEFAULTS["calendar"]))
    brain: dict = field(default_factory=lambda: copy.deepcopy(DEFAULTS["brain"]))
    learning: dict = field(default_factory=lambda: copy.deepcopy(DEFAULTS["learning"]))

    @property
    def sessions_path(self) -> Path:
        return self.ksor_dir / "sessions.yaml"

    @property
    def risk_policy_path(self) -> Path:
        return self.ksor_dir / "risk_policy.yaml"

    @property
    def setups_dir(self) -> Path:
        return self.ksor_dir / "setups"

    @property
    def data_dir(self) -> Path:
        return self.db_path.parent

    @property
    def control_path(self) -> Path:
        return self.data_dir / "control.json"


def _resolve(path_value: str, root: Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else root / path


def load_settings(path: Path | None = None, root: Path = REPO_ROOT) -> Settings:
    path = path or root / "config" / "settings.yaml"
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    paths = raw.get("paths") or {}
    live = _merge(DEFAULTS["live"], raw.get("live"))
    mt5 = raw.get("mt5") or {}
    offset = mt5.get("server_utc_offset_hours")
    payout = float(raw.get("payout_default", 0.80))
    if not 0 < payout < 1.5:
        raise ValueError(f"payout_default looks wrong: {payout} (use 0.80 for 80%)")
    brain = _merge(DEFAULTS["brain"], raw.get("brain"))
    if brain["on_unavailable"] not in ("skip", "rules_only"):
        raise ValueError("brain.on_unavailable must be 'skip' or 'rules_only'")
    return Settings(
        pairs=tuple(p.upper() for p in raw.get("pairs", ["EURUSD"])),
        display_timezone=raw.get("display_timezone", "Asia/Karachi"),
        payout_default=payout,
        feed=raw.get("feed", "replay"),
        db_path=_resolve(paths.get("db", "data/ssor.sqlite3"), root),
        ksor_dir=_resolve(paths.get("ksor", "ksor"), root),
        reports_dir=_resolve(paths.get("reports", "reports"), root),
        history_dir=_resolve(paths.get("history", "data/history"), root),
        lookback_bars=int(live["lookback_bars"]),
        heartbeat_minutes=int(live["heartbeat_minutes"]),
        mt5_symbols={k.upper(): v for k, v in (mt5.get("symbols") or {}).items()},
        mt5_server_utc_offset_hours=None if offset in (None, "") else float(offset),
        live=live,
        calendar=_merge(DEFAULTS["calendar"], raw.get("calendar")),
        brain=brain,
        learning=_merge(DEFAULTS["learning"], raw.get("learning")),
    )


def load_secrets(env_file: Path | None = None) -> dict[str, str]:
    """Environment values that are set (secrets + model IDs). Never print or log secret values."""
    env_file = env_file or REPO_ROOT / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
        except ImportError:  # python-dotenv not installed: rely on the real environment
            pass
        else:
            load_dotenv(env_file, override=False)
    return {key: os.environ[key] for key in ENV_KEYS if os.environ.get(key)}


def brain_models(env: dict[str, str]) -> dict[str, str]:
    """Model ID per tier, from BRAIN_MODEL_FAST / _BALANCED / _DEEP."""
    tiers = {"fast": "BRAIN_MODEL_FAST", "balanced": "BRAIN_MODEL_BALANCED", "deep": "BRAIN_MODEL_DEEP"}
    return {tier: env[key] for tier, key in tiers.items() if env.get(key)}
