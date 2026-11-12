# Ustad ka jawab — 2026-11-11

Owner ne Telegram/WhatsApp se aaya hua jawab forward kiya. Saath mein ek file:
`2026-11-11_amir_fx_bot.py.txt` (sirf reference — `.txt` is liye ke koi isay galti se
chala na de; yeh Deriv par khud trade lagata hai).

## Asal message (jaisa aaya)

```text
RSI (oversold/overbought) plus a trend filter such as the 50 EMA
Bollinger Band reversal with candle confirmation
EMA crossover on 1-5 minute candles

. Bot architecture
Data feed: subscribe to live ticks or candles for a symbol (e.g. EUR/USD or a synthetic index).
Strategy engine: compute indicators and generate a CALL or PUT signal.
Risk manager: stake sizing, daily loss limit, max consecutive losses, and a trade cooldown.
Executor: send the proposal, buy the contract, and track the result.
Logger: save every trade (time, signal, stake, result) to CSV so you can review performance.
```

## File se nikle hue numbers

| Cheez | Value |
|---|---|
| Strategy | EMA(50) trend filter + RSI(14) pullback, band hui 1-minute candles par |
| CALL | close > EMA 50 **aur** RSI(14) < 35 |
| PUT | close < EMA 50 **aur** RSI(14) > 65 |
| Contract | 5 minute, $1 fixed stake |
| Risk | din ka max loss $5, 4 loss lagatar par din band, trades ke darmiyan 120 sec |
| Pair | EUR/USD (Deriv `frxEURUSD`) |

## Kya ab bhi baqi hai (follow-up bheja gaya)

1. Ustad khud kaunsi strategy sab se zyada use karte hain?
2. Bollinger: period/deviation (20, 2?) aur "confirmation candle" ki tareef
3. EMA crossover: kaunsi do EMA, kis timeframe par?
4. Trade 1 minute ya 5 minute?
5. Kis waqt (PKT) trade, kab nahi?
6. Bari news se kitne minute pehle/baad band?
7. Har strategy ki 3–5 jeet aur 3–5 haar ki screenshots

## KSoR mein kya bana

- `R01`–`R04` (draft): EMA 50 + RSI pullback, CALL/PUT, 1-minute aur 5-minute expiry.
  Sharten file se bilkul waisi hi; koi nayi shart apni taraf se nahi lagayi.
- Bollinger aur EMA crossover: numbers aane tak koi setup nahi.
