# Backtest round 2: EMA 9/21 crossover (+ Bollinger ka andaza) — 2026-11-12

**Data:** HistData M1 — EUR/USD Jan 2024 → Oct 2026, GBP/USD 2025.
**Tareeqa:** signal candle band hone par, entry agli candle ke open par, **1 minute** expiry
(Ustad: "trade 1 min just"), koi session filter nahi (Ustad: "kisi bhi time").
Payout 80% → break-even **55.6%**. Prices data provider ki, Quotex ki nahi.
News wale din ka rule backtest mein shamil **nahi** (purana news calendar data nahi hai).

## R05 / R06 — EMA 9/21 crossover (Ustad ka rule)

| Pair | Setup | Sample | Trades | Jeet | 95% range | Har $1 par |
|---|---|---|---|---|---|---|
| EUR/USD | R05 CALL (9 ne 21 ko upar cross kiya) | 2024 | 8,685 | 48.2% | 47.1–49.3% | — |
| EUR/USD | R05 CALL | 2025–Oct 2026 | 16,250 | 48.3% | 47.5–49.1% | −0.12 |
| EUR/USD | R06 PUT (neeche cross) | 2024 | 8,673 | 49.0% | 47.9–50.1% | — |
| EUR/USD | R06 PUT | 2025–Oct 2026 | 16,241 | 49.5% | 48.7–50.3% | −0.10 |
| GBP/USD | R05 CALL | 2025 H2 | 4,429 | 49.3% | 47.8–50.9% | −0.10 |
| GBP/USD | R06 PUT | 2025 H2 | 4,408 | 47.8% | 46.3–49.3% | −0.13 |

Har session (Tokyo, London, New York, overlap) mein 46–48.5% — koi waqt behtar nahi.
**Faisla: DROP.** 1-minute par crossover ke baad price aksar thora wapas aati hai, is liye 50% se bhi kam.

## Research: Bollinger (20, 2) reversal — Ustad ka rule NAHI (unhone numbers nahi diye)

Andaza: band ko chhua + candle wapas band ke andar band hui (CALL hari, PUT laal).

| Pair | Setup | Sample | Trades | Jeet | 95% range |
|---|---|---|---|---|---|
| EUR/USD | CALL | 2025–Oct 2026 | 20,064 | 49.3% | 48.5–50.0% |
| EUR/USD | PUT | 2025–Oct 2026 | 20,269 | 49.6% | 48.9–50.3% |
| GBP/USD | CALL | 2025 H2 | 5,689 | 49.5% | 48.2–50.8% |
| GBP/USD | PUT | 2025 H2 | 5,448 | 50.4% | 49.1–51.8% |

## Ab tak ka khulasa (round 1 + 2)

| Strategy | Nateeja |
|---|---|
| EMA 50 + RSI (file wali) | Trade hi nahi deti |
| 15-min trend + RSI (variant) | 51–53% — break-even se neeche |
| EMA 9/21 crossover | 48–50% — DROP |
| Bollinger (20,2) andaza | 49–50.5% — edge nahi |

Teeno "textbook" strategies 1-minute par **sikka uchhalne jaisi** hain; 80% payout ke baad har trade
par 10–12% ka nuqsan. Yeh Ustad ki ghalti nahi — yeh strategies internet par mashhoor hain, isi liye
in ka edge (agar kabhi tha) khatam ho chuka hai.

## Ustad se kya poochein

1. Woh khud (live account par) in mein se kis par jeet-te hain — kya un ke paas apne trades ka record hai?
2. Woh setup lene se **pehle** kya dekhte hain jo yahan nahi likha (levels, candle size, news, din)?
3. Bollinger par "khud decide karta hun" — kin cheezon ko dekh kar? 2–3 misaalein screenshots ke saath.
