# Ustad ka follow-up jawab — 2026-11-12

Owner ne forward kiya (hamare 7 follow-up sawalon ke number ke mutabiq).

## Asal jawab (jaisa aaya)

```text
2: Bollinger aur period ustad k mutabiq ye khud decide krta hu.
3: EMA (9/21)
4: Trade 1 min just.
5: Pakistani time me kisi bhi time trade ho ske.
6: jis din news hogi us din trade krni hi nhi he.
```

## Sawal → jawab → KSoR mein kya hua

| # | Sawal | Jawab | KSoR |
|---|---|---|---|
| 1 | Sab se zyada kaunsi strategy? | — | Baqi |
| 2 | Bollinger period/deviation, confirmation candle | "Khud decide karta hun" (fixed nahi) | Setup nahi — sirf research (BB 20,2 ka andaza, Ustad ka rule nahi) |
| 3 | EMA crossover ki EMAs | **9 / 21** | `R05` (CALL) / `R06` (PUT) draft |
| 4 | 1 ya 5 minute | **Sirf 1 minute** | `expiry_minutes: 1` |
| 5 | Waqt (PKT) | **Koi bhi waqt** | Setups mein session filter nahi; risk policy `allowed_sessions: []` |
| 6 | News | **News wale din trade hi nahi** | Risk policy: `news_blackout.whole_day: true` (PKT ka din) |
| 7 | Screenshots | — | Baqi |

## Abhi bhi mubham

- EMA crossover kis chart par: 1-minute? (Jawab 4 se 1-minute trade pakki; crossover bhi 1-min chart par maana)
- "News" se kaunsi news: sirf high impact, ya har news? (Abhi: high impact, pair ki dono currencies)
- Bollinger: Ustad ka faisla kis cheez par hota hai — agar bata sakein to code ho sakta hai
