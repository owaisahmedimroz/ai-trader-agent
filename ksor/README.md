# KSoR — Knowledge System of Record (Handbook)

Yeh folder agent ka **"handbook"** hai: Ustad ka approved ilm. Agent sirf yahan
likhe rules par chalta hai. Agent khud yahan kuch nahi badalta — woh sirf
*tajweez* (lesson proposal) deta hai; aap/Ustad approve karke commit karte hain.

| File | Kya hai |
|---|---|
| `setups/*.yaml` | Har setup (CALL/PUT ki sharten) — ek file, ek setup |
| `risk_policy.yaml` | Risk ki hadein (loss limit, cooldown, news blackout…) |
| `sessions.yaml` | Forex sessions (local time mein) |
| `CHANGELOG.md` | Har approval/tabdeeli ka record |
| `intake/` | Ustad ke asal jawab (text, voice notes ki likhai, screenshots) |

## Risk policy: news ka rule

`news_blackout.whole_day: true` → jis din (Pakistan ka calendar din, `day_timezone`)
pair ki kisi currency ki bari news ho, us **poore din** koi signal nahi (Ustad ka rule).
`whole_day: false` → sirf news se `minutes_before` pehle aur `minutes_after` baad tak band.

## Setup ka status (lifecycle)

`draft` → (backtest + Ustad ka review) → `approved` → (kaam karna chhor de) → `retired`

- **Live mein sirf `approved`** setups chalte hain.
- `draft` sirf backtest/replay mein (`--include-drafts`).
- Approved setup badalna ho to **version barhayein** (v1 → v2), `CHANGELOG.md` mein
  likhein, aur commit karein. Purana version git history mein mehfooz rehta hai.

## Setup file ke fields

| Field | Zaroori | Matlab |
|---|---|---|
| `id` | ✅ | `R07` jaisa — capital letter + numbers |
| `name` | ✅ | Aam naam |
| `version` | ✅ | 1, 2, 3… |
| `status` | ✅ | `draft` / `approved` / `retired` |
| `direction` | ✅ | `CALL` ya `PUT` |
| `pairs` | ✅ | `[EURUSD, GBPUSD]` |
| `sessions` | | `[london_newyork]` — khali = har session |
| `conditions` | ✅ | Sab sach hon to signal (AND) |
| `invalidations` | | Koi bhi sach ho to signal nahi (OR) |
| `expiry_minutes` | | Default 1 |
| `entry` | | `next_open` (agli candle khulte hi) |
| `approved_by`, `approved_on` | approved ke liye ✅ | Kis ne, kab |
| `source`, `evidence`, `notes` | | Kahan se aaya, kya saboot hai |

## Condition ki zabaan

```text
rsi_14 < 30
low <= pdl + 0.5 * atr_14
20 < adx_14 < 40
m15_trend == 'up'
regime in ['range', 'mixed']
bullish_engulfing or pin_bar_bull
not doji
abs(close - ema_50) < 0.3 * atr_14
```

Allowed: `+ - * /`, `< <= > >= == !=`, `and or not`, `in [...]`, `abs() min() max()`.
Kuch aur (imports, attributes, `**`) mana hai — code isay reject kar deta hai.

## Features (rules mein yeh naam use hote hain)

| Naam | Matlab |
|---|---|
| `open high low close` | Candle ki prices |
| `prev_open prev_high prev_low prev_close` | Pichli candle |
| `body candle_range upper_wick lower_wick` | Candle ka size |
| `bullish bearish doji` | Candle ki qisam |
| `bullish_engulfing bearish_engulfing pin_bar_bull pin_bar_bear` | Patterns |
| `ema_9 ema_21 ema_50 ema_200` | EMA (TradingView jaisi) |
| `prev_ema_9 prev_ema_21` | Pichli candle ki EMA — crossover ke liye (`ema_9 > ema_21 and prev_ema_9 <= prev_ema_21`) |
| `rsi_14 atr_14 adx_14 plus_di minus_di` | Indicators |
| `bb_mid bb_up bb_low bb_width` | Bollinger (20, 2) |
| `stoch_k stoch_d` | Stochastic (14, 3, 3) |
| `pdh pdl` | Pichle trading din ka high/low |
| `day_high day_low` | Aaj ka ab tak high/low |
| `asia_high asia_low` | Tokyo session ki range (aaj) |
| `dist_round_00_pips dist_round_50_pips` | Round number (1.0800 / 1.0850) se faasla, pips mein |
| `last_swing_high last_swing_low` | Akhri confirmed swing |
| `m15_trend h1_trend` | `'up'` / `'down'` / `'flat'` |
| `m15_close m15_ema_50 m15_adx` | 15-minute ki values |
| `regime` | `'trend'` / `'range'` / `'mixed'` |
| `atr_pct_rank vol_state` | Volatility (0..1) / `'low'` `'normal'` `'high'` |
| `in_london in_new_york in_tokyo in_sydney in_london_newyork` | Session flags |
| `hour_pkt minute weekday` | Waqt (PKT) |

Poori list aur tafseel: `trader_agent/features.py` (`BASE_FEATURES`).

## Ustad ke jawab se setup tak

1. Ustad ke jawab `intake/` mein rakhein.
2. Claude unhein `setups/Rxx_*.yaml` (status `draft`) mein badalta hai.
3. Backtest chalayein → report Ustad ko dikhayein.
4. Ustad approve karein → `status: approved`, `approved_by`, `approved_on`, aur `CHANGELOG.md` mein entry.
5. Commit karein. Ab yeh setup live mein chal sakta hai.
