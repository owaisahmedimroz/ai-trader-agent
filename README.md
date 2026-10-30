# ai-trader-agent

AI Driven & AI Native Development — ek **personal AI Trader Agent** jo market
dekh kar Telegram par signal deta hai. **Trade aap khud lagate hain.**

> ⚠️ Yeh agent trade nahi lagata, Quotex se connect nahi hota, aur koi
> munafa guarantee nahi karta. Binary options mein paisa doobne ka khatra
> bohot zyada hai. Real paisa sirf tab, jab demo par nateeje sabit ho jayein.

## Yeh kaise kaam karta hai

```
Ustad ke rules (KSoR) → Live price (MT5) → Jaanch (session, news, trend, setup)
   → Risk ki ijazat (DSoR) → Signal (Telegram) → Aap Quotex par trade lagate hain
   → Har signal aur nateeja yaad (SSoR) → Raat ko sabaq → Ustad approve → rules update
```

| Hissa | Kya hai | Kahan |
|---|---|---|
| **KSoR** — Handbook | Ustad ke approved rules, risk ki hadein, sessions | `ksor/` |
| **SSoR** — Case file | Har signal, aap ka action, nateeja, review (badla nahi ja sakta) | `data/ssor.sqlite3` |
| **DSoR** — Ijazat | Loss limit, cooldown, news blackout, /stop — AI bhi nahi tor sakta | `trader_agent/gate.py` |

## Kya ban chuka hai

**Phase 0–1 — bunyaad**
- ✅ Rules ki zabaan (YAML) + misaal setup `R00` (sirf misaal, Ustad ka rule nahi)
- ✅ 60+ features: RSI, EMA, ATR, ADX, Bollinger, patterns, pichle din ka high/low, sessions, 15m/1h trend…
- ✅ Risk gate: session, news, daily loss limit, cooldown, payout, /stop /pause
- ✅ SSoR database (append-only), backtester + HTML report (KEEP/WATCH/DROP), replay

**Phase 2 — live loop** (code tayyar; aapke PC par MT5 ke saath verify hona baqi)
- ✅ Har minute analysis, ~:45 par ⚡ TAYYAR, candle band par GO ya ❌ CANCEL
- ✅ Expiry ke baad Quotex result ke buttons, har 15 min "zinda hun", session briefing aur khulasa
- ✅ `start_agent.bat` + Task Scheduler, shadow test mode, economic calendar (band, verify ke baad on)

**Phase 3 — AI dimaagh** (code tayyar, default band)
- ✅ Claude sirf CONFIRM/VETO karta hai, 8 sec timeout, roz ki limit, har call ka record
- ✅ VETO wale signals bhi record — weekly report batata hai AI faida de raha hai ya nahi
- ✅ Briefing commentary, raat ka review, sabaq ki tajaweez (30+ trades ka saboot)

**Phase 4 — seekhna** (code tayyar)
- ✅ Kharab chalne wala setup khud ruk jata hai (drift), `/setups /unpause /proposals /week`
- ✅ Hafte ka report: setups, AI ki value, discipline, loss reviews

**Phase 5 — baad mein** (jab asli data jama ho): dashboard, ML, VPS, tick-data backtest.

Live chalane ka poora tareeqa: **`docs/LIVE.md`**.

## Windows par setup (ek dafa)

PowerShell kholein, repo folder mein jayein:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env
python scripts/check_setup.py
```

`.env` file Notepad mein khol kar keys bharein. Yeh file kabhi share na karein.

Tests chalane ke liye: `python -m pytest -q`

## Backtest (Ustad ke rules purane data par)

1. Purana data download karein — tareeqa `docs/DATA.md` mein.
2. Chalayein:

```powershell
python scripts/run_backtest.py --data data/history/DAT_ASCII_EURUSD_M1_2025.csv --pair EURUSD --include-drafts --oos-from 2025-10-01
```

3. `reports/` folder mein HTML report khulegi. **Faisla** dekhein:
   - **KEEP** — kaafi trades, poori range break-even se upar, har mahine theek
   - **WATCH** — abhi sabit nahi (data kam, ya range break-even ko chhoo rahi hai)
   - **DROP** — break-even se neeche

Data na ho to pehle tool check karne ke liye nakli (random) data:
`python scripts/make_sample_data.py` phir backtest mein `--format generic --synthetic`.
Random data par nateeja ~50% hi aata hai — yahi sahi hai.

## Replay (live jaisa dry-run)

```powershell
python scripts/replay.py --data data/history/DAT_ASCII_EURUSD_M1_2025.csv --pair EURUSD --from 2025-03-03 --to 2025-03-04 --include-drafts
```

## Telegram bot

1. Telegram par **@BotFather** → `/newbot` → token `.env` mein `TELEGRAM_BOT_TOKEN=` ke aage.
2. Bot chalayein: `python -m trader_agent.notifier.telegram_bot`
3. Apne bot ko `/start` bhejein — woh aap ki **chat ID** batayega → `.env` mein `TELEGRAM_CHAT_ID=`.
4. Bot dobara chalayein. Commands: `/status /today /last /why /pause /stop /resume /payout /news /setups /unpause /proposals /week`

Bot sirf aap ki chat ko jawab deta hai.

## Ustad ke rules kaise add hon

Ustad ke jawab `ksor/intake/` mein → Claude unhein `ksor/setups/` mein draft YAML banata hai →
backtest → Ustad approve → `CHANGELOG.md` → commit. Tafseel: `ksor/README.md`.

## Roz/hafte ka review

`docs/REVIEW.md` — roz 10–15 minute, hafte mein Ustad ke saath.

## Claude Code ke liye

Poora plan, usool aur agle phases: `CLAUDE.md`.
