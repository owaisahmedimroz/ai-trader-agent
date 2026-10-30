# Review — roz, hafte, mahine

**Bunyadi usool:** roz **apna rawaiya aur bugs** dekhein · hafte mein **rules** ka
faisla · mahine mein **poore system** ka faisla.

Kyun? 20 trades wale din ka win rate ±22% tak ittefaqi ho sakta hai, aur 58%
jeetne wala acha system bhi 1,000 trades mein taqreeban 7 loss lagatar dikhata
hai. Ek din ka nateeja kuch sabit nahi karta.

## Roz (raat ko 10–15 minute)

Telegram `/today` aur `/last` dekhein.

1. **Score** — signals, lagaye, jeet/haar. Sirf dekhein, faisla nahi.
2. **Discipline** (yeh roz judge karein):
   - Kitni entries waqt par (deadline se pehle)? Bot "der se" batata hai.
   - Kaunse signals chhore, aur kyun?
   - Koi trade signal ke baghair to nahi li?
3. **Har loss ki qisam** — bot loss ke baad 4 button deta hai:

| Button | Matlab | Kya karna |
|---|---|---|
| 🎲 Normal loss | Setup sahi tha, market ne saath nahi diya | Kuch nahi — khel ka hissa |
| 🐞 Agent ki ghalti | Setup bana hi nahi tha / bug | Claude ko batayein |
| ✋ Meri ghalti | Der, ghalat direction, ghalat amount | Discipline note |
| 📰 News/spike | Achanak move | News/filter check |

4. **Jeet bhi check karein** — ghalat setup par jeet bhi ghalti hai (qismat).
5. **Kal ka plan** — kaunsi bari news hai? `/news 18:30 USD high CPI` se pehle se daal dein.

## Hafta (Itwar, 30–45 minute, 15–20 minute Ustad ke saath)

- Har setup ka win rate **range ke saath** (backtest report jaisa)
- AI ke sabaq ki tajaweez (Phase 4) — approve / reject
- Koi setup break-even se neeche ja raha ho → pause
- Naye rules → `ksor/` mein draft → backtest → approve → `CHANGELOG.md`

## Mahina

Demo se real paisa sirf tab, jab:
- 500+ signals ho chuke hon
- Win rate ki **neechli hadd** bhi break-even se upar ho
- 90% se zyada entries waqt par hui hon

Aur tab bhi chhote stake se. Martingale (loss ke baad stake barhana) kabhi nahi.
