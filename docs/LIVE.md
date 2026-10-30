# Live chalana (Phase 2–4)

Agent sirf **signal** deta hai. Trade aap Quotex par khud lagate hain.

## Pehli dafa (ek hi baar)

1. MT5 install karein, demo account se login karein, terminal **khula** rakhein.
2. `config/settings.yaml` mein `feed: mt5` karein.
3. `.env` mein `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
4. Check: `python scripts/check_setup.py --mt5 --telegram`
   - **Server time offset** zaroor dekhein: akhri candle ka waqt "abhi" se 1–2 minute purana hona chahiye.
     Ghalat ho to `config/settings.yaml` → `mt5.server_utc_offset_hours` set karein.
   - Broker ka symbol naam alag ho (jaise `EURUSDm`) to `mt5.symbols` mein likhein.

## Ustad ke rules aane se pehle: plumbing test

```powershell
python scripts/run_live.py --shadow-only
```

Draft setups (jaise misaal R00) **SHADOW** signals dete hain — "asli trade na lagayein"
likha aata hai. Sirf yeh dekhne ke liye ke data, timing aur Telegram theek hain.

## Asli live (approved setups ke baad)

```powershell
scripts\start_agent.bat
```

Do windows khulti hain: Telegram bot aur live loop. Draft setups ko saath mein chupke se
test karna ho (champion/challenger): `scripts\start_agent.bat --shadow-drafts`

Live ke liye zaroori: kam az kam ek `approved` setup aur `approved` risk policy.

## Windows Task Scheduler (khud shuru ho)

1. Start → **Task Scheduler** → **Create Basic Task** → naam: `AI Trader`
2. Trigger: **Daily**, waqt session se 15 minute pehle (sardiyon mein ~17:45 PKT)
3. Action: **Start a program** → `scripts\start_agent.bat` (poora path) →
   "Start in": repo folder ka path
4. Power settings: session ke dauran PC **sleep** na ho (Settings → System → Power).

Band karna: dono windows mein `Ctrl+C`.

## Din bhar kya hota hai

| Waqt | Kya |
|---|---|
| Start | "✅ Agent online" |
| Session shuru | 📋 Briefing: aaj ki news, har pair ka trend/regime, setups ki sehat (+ AI commentary agar on ho) |
| Har minute | Analysis. Setup ban raha ho to ~:45 par **⚡ TAYYAR RAHEIN** |
| Candle band | **GO** signal (buttons ke saath) ya **❌ CANCEL** |
| Expiry ke ~20 sec baad | "Quotex par kya nateeja aaya?" → 🏆 / 💔 / ➖ |
| Har 15 min | "🟢 Zinda hun" |
| Session khatam | Din ka khulasa, drift check (kharab setup khud ruk jata hai), AI ka raat ka review (agar on ho) |

## AI dimaagh on karna (Phase 3) — setups sabit hone ke baad

1. `.env`: `ANTHROPIC_API_KEY`, `BRAIN_MODEL_FAST`, `BRAIN_MODEL_BALANCED`, `BRAIN_MODEL_DEEP`
   (Anthropic ki model list se IDs).
2. `config/settings.yaml` → `brain.enabled: true`
3. AI sirf gate se paas hue signal ko **CONFIRM** ya **VETO** karta hai (8 second mein jawab
   na aaye to signal skip). VETO wale signals bhi chupke se record hote hain, taake weekly
   report mein pata chale ke AI ke VETO sahi the ya nahi. Faida na de to AI band kar dein.
4. Roz ki limit: `brain.max_calls_per_day`, `brain.max_tokens_per_day`.

## Seekhna (Phase 4)

- **Drift:** kisi setup ke pichle 50 live signals ki range break-even se neeche chali jaye to
  woh khud ruk jata hai aur Telegram par batata hai. Ustad ke saath dekh kar `/unpause R07`.
- **Tajaweez:** AI raat ko sabaq nikalta hai; 30+ trades ke saboot wali tajweez `/proposals`
  mein aati hai → Approve/Reject. Approve karne se KSoR khud nahi badalta — Claude Code draft
  version banata hai, backtest hota hai, Ustad approve karte hain.
- **Hafte ka report:** `python scripts/weekly_report.py` ya Telegram `/week`.

## Masle

| Masla | Hal |
|---|---|
| "MT5 se connect nahi ho saka" | MT5 terminal khula hai? Login sahi hai? |
| Signals ka waqt ghalat | `mt5.server_utc_offset_hours` set karein |
| Telegram par kuch nahi aata | `check_setup.py --telegram`; bot window chal rahi hai? |
| "Koi approved setup nahi" | Ustad ke setups approve karein, ya `--shadow-only` |
| AI "auth" / "model_not_found" | `.env` mein API key / model ID check karein |
