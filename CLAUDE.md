# AI Trader Agent — project guide for Claude Code

## What this is

A **personal, signal-only** trading assistant for one trader (the owner), who
trades 1-minute binary options on Quotex **by hand**. The agent watches the
market, applies an experienced trader's ("Ustad") approved rules, and sends a
signal to Telegram. **The human decides and places every trade.**

Hard boundaries — never cross them, even if asked casually:
- No auto-trading. No connection to Quotex (no API exists; unofficial access breaks its terms).
- MT5 (demo account) is a **price feed only**; never place orders through it.
- No martingale or stake escalation, ever (the risk policy loader rejects it).
- No secrets in the repo. Keys live in a local `.env` (git-ignored); never print them.
- Never present synthetic data or backtests as live performance. Reports show ranges and caveats.

The owner communicates in Roman Urdu. User-facing text (Telegram messages,
reports, README) is Roman Urdu; code, identifiers and this file are English.

## Architecture: three systems of record

```
                ┌──────── KSoR (handbook) ─ ksor/ ────────┐
                │ approved setups · risk policy · sessions │
                └───────────────┬──────────────────────────┘
                                │ approved only (live)
 price feed → features → rules engine → DSoR risk gate → [AI brain, Phase 3] → Telegram → human trades
   (MT5)     (features.py) (rules_engine.py)  (gate.py)        confirm/veto only                │
                                │                                                               ▼
                ┌──────── SSoR (case file) ─ SQLite, append-only ─────────┐       buttons: taken/skipped,
                │ signals · human actions · outcomes · reviews ·           │◄────── broker result, loss review
                │ reflections · lesson proposals · every gate decision      │
                └───────────────────────────────────────────────────────────┘
```

- **KSoR** (`ksor/`, `trader_agent/ksor.py`) — how we operate. Versioned YAML,
  approved by a human (status `draft` → `approved` → `retired`, CHANGELOG entry).
- **SSoR** (`trader_agent/ssor.py`) — what happened and why. SQLite with triggers
  that reject UPDATE/DELETE. Current status is derived from the latest rows.
- **DSoR** (`trader_agent/gate.py`, `control.py`) — what is true now and whether
  we may act. Limits come from the approved risk policy; running state is
  rebuilt from SSoR + the control file (`/stop`, `/pause`, `/payout`, `/news`).

Invariants (keep them true in every change):
1. **One authority per fact.** Rules → KSoR. History → SSoR. Current state/permission → DSoR.
2. **Provenance.** Every signal stores setup id + version, KSoR git commit, a feature
   snapshot and the gate decision.
3. **DSoR authorizes independently.** Nothing — including the AI — bypasses a blocked
   gate decision. The AI may read KSoR/SSoR and *propose* lessons; it never edits
   `ksor/`, risk limits or the control file.
4. **One code path.** Backtest, replay and live all use `build_features` +
   `setup_mask`/`candidates_at` + `RiskGate`. Never fork logic per mode.
5. **No look-ahead.** Row t of the feature frame uses only candles <= t; higher
   timeframes join only completed candles. `tests/test_features.py` enforces this.
6. **UTC inside, PKT outside.** All stored times are UTC ISO strings; display uses
   `display_timezone` (Asia/Karachi). Sessions are defined in local market time and
   converted with zoneinfo (DST-safe).
7. **Decision time = candle close.** A signal on candle t is decided at t+1 min;
   session/market checks use that moment. Backtest entry = open of t+1, exit =
   close of t+expiry.

## Code map

| Path | Role |
|---|---|
| `trader_agent/config.py` | `config/settings.yaml` + secrets from `.env` |
| `trader_agent/timeutil.py` | `SessionBook`: sessions, overlaps, market hours, trading day (17:00 NY rollover) |
| `trader_agent/indicators.py` | EMA/RMA (SMA-seeded like TradingView), RSI, ATR, Bollinger (ddof=0), DMI/ADX, Stochastic |
| `trader_agent/levels.py` | previous-day/today levels, session range, round numbers, confirmed swings |
| `trader_agent/regime.py` | M15/H1 resample + completed-candle join, trend/regime/volatility labels |
| `trader_agent/features.py` | `build_features` — every name a rule may use (`BASE_FEATURES`) |
| `trader_agent/expr.py` | safe vectorised condition language (ast, no eval) |
| `trader_agent/ksor.py` | setup + risk policy schemas, validation, governance warnings, `ksor_commit` |
| `trader_agent/rules_engine.py` | `setup_mask` (whole frame) and `candidates_at` (latest candle) |
| `trader_agent/news.py` | news events, manual parsing, blackout checks |
| `trader_agent/gate.py` | `DayState`, `RiskGate.check` → `GateDecision(allowed, reasons)` |
| `trader_agent/control.py` | `data/control.json` (stop/pause/payout/news) shared by bot and loop |
| `trader_agent/ssor.py` | append-only SQLite store + summaries |
| `trader_agent/pipeline.py` | `Agent.on_closed_candle` (per-candle body), `Agent.preview` (heads-up), AI confirm hook |
| `trader_agent/live.py` | `LiveRunner`: candle-close timing, heads-up/GO/CANCEL, result prompts, heartbeat, session start/end |
| `trader_agent/briefing.py` | deterministic pre-session facts (news, regime per pair, setup health) |
| `trader_agent/calendar_feed.py` | Forex Factory weekly JSON → `NewsEvent`s (unofficial feed, off by default) |
| `trader_agent/brain/` | `client.py` (SDK wrapper: timeout, no retries, JSON schema, `ai_usage`, budget), `confirm.py`, `review.py` |
| `trader_agent/learning.py` | setup health, drift auto-pause (DSoR control), weekly report |
| `trader_agent/backtest/` | `run_backtest` (optional gate simulation, OOS split) and HTML/Markdown report |
| `trader_agent/notifier/` | message text, button actions, console, Telegram sender (HTTP) and bot (inbound) |
| `trader_agent/feeds/` | `Feed` interface; `mt5_feed.py` (Windows, **unverified**) |
| `scripts/` | `check_setup.py`, `run_backtest.py`, `replay.py`, `run_live.py`, `weekly_report.py`, `start_agent.bat`, `make_sample_data.py` |

## Commands

The owner runs Windows 10/11 with Python 3.11. Use a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest -q
python scripts/check_setup.py            # add --mt5 --telegram once .env is filled
python scripts/run_backtest.py --data data/history/<file>.csv --pair EURUSD --include-drafts --oos-from 2025-10-01
python scripts/replay.py --data data/history/<file>.csv --pair EURUSD --from 2025-03-03 --to 2025-03-04 --include-drafts
python -m trader_agent.notifier.telegram_bot
python scripts/run_live.py --shadow-only          # live plumbing test with draft setups
scripts\start_agent.bat                           # bot + live loop (see docs/LIVE.md)
python scripts/weekly_report.py
```

Tests must pass on pandas 2.x (pinned) and stay warning-free on pandas 3.x.

## Phases

**Phase 0–1 (done):** structure, KSoR format + example draft setup, safe rule
language, features, risk gate, append-only SSoR, backtester + report, replay
pipeline, Telegram sender/bot skeleton, setup checker, tests.

**Phase 2 — live loop (code done, needs verification on the owner's PC):**
`scripts/run_live.py` / `start_agent.bat` → `LiveRunner`: sleeps to each candle close
(+`settle_seconds`), waits for the feed to publish the closed candle, runs every agent,
GO/CANCEL after a ~:45 heads-up (`Agent.preview` on the forming candle — records
nothing), broker-result prompts after expiry, heartbeat, session-start briefing,
session-end summary + drift check + nightly review; errors are alerted with backoff,
never fatal. Modes: live (approved only), `--shadow-drafts` (drafts silently as
shadow next to live = champion/challenger), `--shadow-only` (plumbing test, visible
SHADOW signals). Still to verify on Windows: `MT5Feed` connection, symbol names,
**server-time offset**, closed-candle timing, Task Scheduler start. The economic
calendar (`calendar_feed.py`) is off until its unofficial format and terms are checked.

**Phase 3 — AI brain (code done, off by default):** enable only after setups prove
themselves (`brain.enabled`, `ANTHROPIC_API_KEY`, `BRAIN_MODEL_FAST/_BALANCED/_DEEP` in
`.env` — never commit model IDs). Fast tier confirms/vetoes a gate-approved candidate
with a hard timeout and no retries; timeout/refusal/budget ⇒ `on_unavailable`
(`skip` default). Vetoed or skipped candidates are recorded as `shadow` with
`brain_json` so the weekly report can compare CONFIRM vs VETO outcomes — keep the AI
only if CONFIRM clearly beats VETO. Balanced tier: briefing commentary. Deep tier:
nightly reflections; proposals need ≥ `proposal_min_evidence` signal ids (else saved
as an "idea" reflection). Every call is in SSoR `ai_usage`; daily call/token caps.

**Phase 4 — learning loop (code done):** `setup_health` (last 50 live results,
Wilson range vs break-even) → DRIFT pauses the setup in `control.paused_setups`
(deterministic DSoR code, alert, `/unpause`). Telegram `/setups /proposals /week`;
proposal approve/reject is recorded in SSoR — turning an approved proposal into a new
draft KSoR version is a human/Claude Code task (backtest + Ustad approval).

**Phase 5 — later, once real data exists:** Streamlit dashboard (the weekly report
covers the basics now), ML meta-labeling on SSoR history, Windows VPS for MT5,
tick-data backtests with the human's entry delay.

## Working with KSoR

Ustad's raw answers go to `ksor/intake/`. Convert them into `ksor/setups/Rxx_*.yaml`
with `status: draft`, using only names from `BASE_FEATURES`; ask the owner when a
rule is vague (e.g. "strong market") instead of guessing. Backtest, then show the
plain-language rule + report to the owner/Ustad. Only a human sets `approved`,
`approved_by`, `approved_on` and writes the CHANGELOG line.

## Data notes

- HistData M1 files are documented as EST without DST, but the 2024–2026 files are New York local
  time WITH DST (NFP spike at 08:30 file time in winter and summer; weekly open Sunday 17:00).
  The loader defaults to `America/New_York`; `--tz-offset` forces a fixed offset for other sources.
- First real backtest (2026-11-12, `ksor/intake/2026-11-12_backtest_ema50_rsi.md`): Ustad's EMA50+RSI
  rule almost never fires on M1/M5 (the two conditions exclude each other on one timeframe); a
  15-min-trend variant wins ~51–53%, below the 55.6% break-even at 80% payout.
- Data provider prices are not Quotex prices; Quotex OTC prices cannot be obtained at all. Avoid OTC.
- `data/` and `reports/` are git-ignored (large, machine-specific).
