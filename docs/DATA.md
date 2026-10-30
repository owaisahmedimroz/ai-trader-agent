# Purana data (backtest ke liye)

Backtest ko 1-minute (M1) candles chahiye — kam az kam **1–2 saal**, taake har
qisam ki market (trend, range, tez, sust) shamil ho.

## Option 1: HistData.com (free, sab se aasan)

1. Browser mein `histdata.com` → **Download Free Forex Data**
2. **ASCII** → **1-Minute Bar Quotes** chunein
3. Pair chunein (jaise EUR/USD) → saal chunein → zip download karein
4. Zip ke andar wali `.csv` file `data/history/` folder mein rakhein
   (folder na ho to bana lein)
5. Backtest: `--format histdata` (default)

Timezone: HistData apni files ka waqt **EST bina daylight saving (UTC-5)**
batata hai, aur code isay UTC mein badal deta hai. Agar kabhi shak ho, ek din
ka data TradingView ke chart se mila kar dekhein; farq ho to `--tz-offset` badlein.

HistData ki terms ke mutabiq data personal istemal ke liye hai — aage share na karein.

## Option 2: Dukascopy (free, tick data bhi)

Dukascopy ka data in tools se download hota hai: **QuantDataManager** (free
version), **Tickstory**, ya Python tool **duka**. 1-minute candles CSV mein
export karein (columns: `time,open,high,low,close`, time UTC mein) aur
`--format generic` lagayein.

Tick data (har price change) baad mein insaan ki chand second ki der ko
durust tareeqe se test karne ke kaam aayega.

## Option 3: MT5 (Phase 2)

MT5 terminal se bhi purana data aata hai (`copy_rates_range`). Kitna purana —
yeh broker par depend karta hai. Phase 2 mein script banega.

## Yaad rakhein

- Yeh sab **data provider ki prices** hain, Quotex ki nahi. Real-market pairs
  par farq chhota hota hai; **OTC pairs ka data kahin nahi milta** (Quotex
  khud banata hai) — is liye OTC se bachein.
- `data/` folder GitHub par upload nahi hota (`.gitignore`).
- Nakli data (`make_sample_data.py`) sirf tool check karne ke liye hai.
