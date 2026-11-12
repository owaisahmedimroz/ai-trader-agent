# Backtest: Ustad ki EMA 50 + RSI pullback strategy — 2026-11-12

**Data:** HistData M1 — EUR/USD Jan 2024 → Oct 2026 (10.5 lakh candles), GBP/USD 2025.
**Tareeqa:** signal candle band hone par, entry agli candle ke open par, exit expiry candle ke close par.
2024 = in-sample, Jan 2025 → Oct 2026 = out-of-sample (faisla isi par). Payout 80% → break-even **55.6%**.
Prices data provider ki hain, Quotex ki nahi — nateeja andaza hai.

## 1. Strategy bilkul waisi jaisi file mein hai (R01–R04)

| Setup | Candles | Signals (2024 → Oct 2026) |
|---|---|---|
| R01 CALL 1 min | M1 | 1 |
| R02 PUT 1 min | M1 | 2 |
| R03 CALL 5 min | M1 | 1 |
| R04 PUT 5 min | M1 | 2 |
| Wahi logic, 5-minute candles par | M5 | CALL 2, PUT 0 |

File ke apne formulas se alag se check kiya: 2024–2025 mein CALL **0**, PUT **2**.

**Wajah:** jab 1-minute (ya 5-minute) chart par RSI(14) 35 se neeche jata hai, price us waqt
taqreeban hamesha pehle hi EMA 50 se neeche ja chuki hoti hai (RSI < 35 ke waqt price aur EMA 50
ka farq: median −4.7 pips, sab se zyada 0.0). Yani "EMA 50 se upar + RSI 35 se neeche" ek
hi timeframe par saath hota hi nahi. **Is shakal mein yeh strategy trade deti hi nahi.**

## 2. Research variant (Ustad ka rule NAHI): 15-min trend + 1-min RSI

Trend filter: M15 close vs M15 EMA 50; RSI(14) M1 < 35 (CALL) / > 65 (PUT).

| Pair | Setup | Sample | Trades | Jeet | 95% range | Har $1 par |
|---|---|---|---|---|---|---|
| EUR/USD | CALL 1 min | 2024 | 8,704 | 50.9% | 49.8–52.0% | −0.076 |
| EUR/USD | CALL 1 min | 2025–26 | 15,082 | 51.0% | 50.2–51.8% | −0.077 |
| EUR/USD | CALL 5 min | 2025–26 | 7,539 | 51.9% | 50.8–53.1% | −0.063 |
| EUR/USD | PUT 1 min | 2025–26 | 15,796 | 51.1% | 50.3–51.9% | −0.075 |
| EUR/USD | PUT 5 min | 2025–26 | 7,847 | 51.8% | 50.7–52.9% | −0.066 |
| GBP/USD | CALL 5 min | 2025 | 4,315 | 53.5% | 52.0–55.0% | −0.036 |
| GBP/USD | PUT 1 min | 2025 | 8,158 | 51.5% | 50.4–52.6% | −0.069 |

Sab ki range break-even (55.6%) se **neeche** — dono saal, dono pairs. Hazaron trades ke baad
bhi jeet ~51–53% hai: sikka uchhalne se thora behtar, magar payout ke baad nuqsan.

## Nateeja

- **R01–R04 (file wali shakal):** trade hi nahi deti → **retire** karne ka mashwara (faisla owner/Ustad).
- **Variant:** kaafi data, lekin break-even se neeche → **DROP**.
- Yeh aam "textbook" strategy 1-minute binary par edge nahi deti. Ustad ka apna, zyada khaas
  tareeqa (kab NAHI lena, kaunsa waqt, kaunsi levels) chahiye.

## Ustad se poochne wali baatein

1. EMA 50 aur RSI kis timeframe par? Dono ek hi chart par, ya trend bare chart (15m/1h) se?
2. RSI ki limits 35/65 hi, ya kuch aur? Kya woh RSI ke wapas palatne (cross back) ka intezar karte hain?
3. Kaunse waqt aur kaunse pairs par yeh sab se achha chalta hai unke tajurbe mein?
4. Bollinger aur EMA crossover ke numbers.

## Dobara chalana

```text
python scripts/run_backtest.py --data data/history/csv/DAT_ASCII_EURUSD_M1_2024.csv data/history/csv/DAT_ASCII_EURUSD_M1_2025.csv data/history/csv/DAT_ASCII_EURUSD_M1_2026*.csv --pair EURUSD --include-drafts --setup R01 --setup R02 --setup R03 --setup R04 --oos-from 2025-01-01
```
