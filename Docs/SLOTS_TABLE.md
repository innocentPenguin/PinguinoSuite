# Slots payout table

Three reels, five symbols, every symbol equally likely (1 in 5 per reel). Pay = bet x multiplier (the bet is not returned on top).

| Result | Chance | Pays | Share of the 100% |
|---|---|---|---|
| 3 x 🍒 cherry | 0.80% (1 in 125) | 2x | 1.6% |
| 3 x 🐟 fish | 0.80% (1 in 125) | 3x | 2.4% |
| 3 x ⭐ star | 0.80% (1 in 125) | 4x | 3.2% |
| 3 x ⚽ soccer ball | 0.80% (1 in 125) | 6x | 4.8% |
| 3 x 🐧 penguin (jackpot) | 0.80% (1 in 125) | 11x | 8.8% |
| any 2 the same | 48.00% | 1.5x | 72.0% |
| nothing | 48.00% | 0 | 0% |

**Return to player: 92.80%. House edge: 7.20%.** (An average of 0.93 points back for every 1 point bet, over many spins.)

Before: all triples 5x, penguin 10x, pair 1.5x = 96.0% back. Now the low symbols pay less and the penguin more, and the total is 92.8%.

Setting: `slotsSymbolPayouts` in the gamble config (symbol -> multiplier). `{}` falls back to `slotsTriplePayout` / `slotsJackpotPayout`. `slotsPairPayout` is unchanged at 1.5.
Check any other numbers with `python Tools/slots-ev.py <cherry> <fish> <star> <soccer> <penguin> [pair]`.
