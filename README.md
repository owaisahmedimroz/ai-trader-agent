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

## Abhi kya ban chuka hai (Phase 0–1)

- ✅ Rules ki zabaan (YAML) + misaal setup `R00` (sirf misaal, Ustad ka rule nahi)
- ✅ 60+ features: RSI, EMA, ATR, ADX, Bollinger, patterns, pichle din ka high/low, sessions, 15m/1h trend…
- ✅ Risk gate: session, news, daily loss limit, cooldown, payout, /stop /pause
- ✅ SSoR database (append-only)
- ✅ Backtester + HTML report (95% range, break-even, mahine-wise, faisla KEEP/WATCH/DROP)
- ✅ Replay (purana data live jaisa chala kar dekhna), Telegram bot (buttons, commands)
- ⏳ Phase 2: MT5 se live data + live loop · Phase 3: AI dimaagh · Phase 4: seekhne ka loop

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
4. Bot dobara chalayein. Commands: `/status /today /last /why /pause /stop /resume /payout /news`

Bot sirf aap ki chat ko jawab deta hai.

## Ustad ke rules kaise add hon

Ustad ke jawab `ksor/intake/` mein → Claude unhein `ksor/setups/` mein draft YAML banata hai →
backtest → Ustad approve → `CHANGELOG.md` → commit. Tafseel: `ksor/README.md`.

## Roz/hafte ka review

`docs/REVIEW.md` — roz 10–15 minute, hafte mein Ustad ke saath.

## Claude Code ke liye

Poora plan, usool aur agle phases: `CLAUDE.md`.
