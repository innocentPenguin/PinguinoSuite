"""Exact return-to-player of the !slots table by full enumeration (5 symbols, 3 reels, each equally likely).
Usage: python Tools/slots-ev.py            prints the table for the proposed payouts and writes Docs/SLOTS_TABLE.md
       python Tools/slots-ev.py 2 3 4 6 11 [pair]   try other triple payouts (cherry fish star soccer penguin) and a pair payout"""
import itertools, os, sys
sys.stdout.reconfigure(encoding='utf-8')
SYM = ['🍒', '🐟', '⭐', '⚽', '🐧']; NAME = ['cherry', 'fish', 'star', 'soccer ball', 'penguin (jackpot)']
trip = [2, 3, 4, 6, 11]; pair = 1.5
a = [float(x) for x in sys.argv[1:]]
if len(a) >= 5: trip = a[:5]
if len(a) >= 6: pair = a[5]
N = len(SYM) ** 3; rtp = 0.0; rows = []
n_trip = {i: 0 for i in range(5)}; n_pair = 0
for r in itertools.product(range(5), repeat=3):
    if r[0] == r[1] == r[2]: n_trip[r[0]] += 1; rtp += trip[r[0]]
    elif len(set(r)) == 2: n_pair += 1; rtp += pair
rtp /= N
def ev(idx): return trip[idx] * n_trip[idx] / N
out = ['# Slots payout table', '',
       'Three reels, five symbols, every symbol equally likely (1 in 5 per reel). Pay = bet x multiplier (the bet is not returned on top).', '',
       '| Result | Chance | Pays | Share of the 100% |', '|---|---|---|---|']
for i in range(5):
    out.append('| 3 x %s %s | %.2f%% (1 in %d) | %gx | %.1f%% |' % (SYM[i], NAME[i], 100 * n_trip[i] / N, N // n_trip[i], trip[i], 100 * ev(i)))
out.append('| any 2 the same | %.2f%% | %gx | %.1f%% |' % (100 * n_pair / N, pair, 100 * pair * n_pair / N))
out.append('| nothing | %.2f%% | 0 | 0%% |' % (100 * (N - n_pair - sum(n_trip.values())) / N))
out += ['', '**Return to player: %.2f%%. House edge: %.2f%%.** (An average of %.2f points back for every 1 point bet, over many spins.)' % (100 * rtp, 100 - 100 * rtp, rtp), '',
        'Before: all triples 5x, penguin 10x, pair 1.5x = 96.0%% back. Now the low symbols pay less and the penguin more, and the total is %.1f%%.' % (100 * rtp), '',
        'Setting: `slotsSymbolPayouts` in the gamble config (symbol -> multiplier). `{}` falls back to `slotsTriplePayout` / `slotsJackpotPayout`. `slotsPairPayout` is unchanged at 1.5.',
        'Check any other numbers with `python Tools/slots-ev.py <cherry> <fish> <star> <soccer> <penguin> [pair]`.']
txt = '\n'.join(out) + '\n'; print(txt)
if len(a) == 0:
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Docs', 'SLOTS_TABLE.md'); open(p, 'w', encoding='utf-8').write(txt); print('written', p)
