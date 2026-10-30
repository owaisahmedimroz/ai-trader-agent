"""Settings (config/settings.yaml) and secrets (.env / environment).

Secrets never live in the repository: they are read from environment variables,
optionally loaded from a local, git-ignored `.env` file.
"""

from __future__ import annotations

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

    @property
    def sessions_path(self) -> Path:
        return self.ksor_dir / "sessions.yaml"

    @property
    def risk_policy_path(self) -> Path:
        return self.ksor_dir / "risk_policy.yaml"

    @property
    def setups_dir(self) -> Path:
        return self.ksor_dir / "setups"


def _resolve(path_value: str, root: Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else root / path


def load_settings(path: Path | None = None, root: Path = REPO_ROOT) -> Settings:
    path = path or root / "config" / "settings.yaml"
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    paths = raw.get("paths") or {}
    live = raw.get("live") or {}
    mt5 = raw.get("mt5") or {}
    offset = mt5.get("server_utc_offset_hours")
    payout = float(raw.get("payout_default", 0.80))
    if not 0 < payout < 1.5:
        raise ValueError(f"payout_default looks wrong: {payout} (use 0.80 for 80%)")
    return Settings(
        pairs=tuple(p.upper() for p in raw.get("pairs", ["EURUSD"])),
        display_timezone=raw.get("display_timezone", "Asia/Karachi"),
        payout_default=payout,
        feed=raw.get("feed", "replay"),
        db_path=_resolve(paths.get("db", "data/ssor.sqlite3"), root),
        ksor_dir=_resolve(paths.get("ksor", "ksor"), root),
        reports_dir=_resolve(paths.get("reports", "reports"), root),
        history_dir=_resolve(paths.get("history", "data/history"), root),
        lookback_bars=int(live.get("lookback_bars", 5000)),
        heartbeat_minutes=int(live.get("heartbeat_minutes", 15)),
        mt5_symbols={k.upper(): v for k, v in (mt5.get("symbols") or {}).items()},
        mt5_server_utc_offset_hours=None if offset in (None, "") else float(offset),
    )


def load_secrets(env_file: Path | None = None) -> dict[str, str]:
    """Return the secrets that are set. Values must never be printed or logged."""
    env_file = env_file or REPO_ROOT / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
        except ImportError:  # python-dotenv not installed: rely on the real environment
            pass
        else:
            load_dotenv(env_file, override=False)
    return {key: os.environ[key] for key in SECRET_KEYS if os.environ.get(key)}
