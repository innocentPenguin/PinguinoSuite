"""One-time pushup baseline: writes "baseline": 805 into <data>/pushups.json (161 recorded pushup redemptions x 5). The Host adds it to the all-time count once on its next start
and marks it applied, so a restart never adds it again. DRY RUN by default; --write backs the existing file up first (pushups.json.before-seed-YYYYMMDD-HHMMSS.bak).
A file that already carries a baseline is refused (no double seeding).

  python Tools/seed-pushups.py --data D:/PinguinoSuite/Data            # dry run
  python Tools/seed-pushups.py --data D:/PinguinoSuite/Data --write
"""
import argparse, datetime as dt, json, os, shutil, sys
ap = argparse.ArgumentParser(); ap.add_argument('--data', required=True); ap.add_argument('--baseline', type=int, default=805)
ap.add_argument('--note', default='161 redemptions x 5, 2026-10-30'); ap.add_argument('--write', action='store_true'); a = ap.parse_args()
p = os.path.join(a.data, 'pushups.json'); cur = json.load(open(p, encoding='utf-8-sig')) if os.path.exists(p) else None
if cur and (cur.get('baseline') or cur.get('baselineApplied')): sys.exit('refused: %s already has a baseline (%s, applied=%s)' % (p, cur.get('baseline'), cur.get('baselineApplied')))
print('file:', p, '(exists: %s)' % bool(cur)); print('now :', json.dumps(cur)); allt = (cur or {}).get('allTime', (cur or {}).get('count', 0))
print('after the Host start: allTime = %d + %d = %d, session unchanged' % (allt, a.baseline, allt + a.baseline))
if not a.write: print('DRY RUN: nothing written. Add --write to apply.'); sys.exit(0)
if cur is not None:
    b = p + '.before-seed-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S') + '.bak'; shutil.copy2(p, b); print('backup:', b)
new = dict(cur or {'enabled': True, 'count': 0}); new.update({'baseline': a.baseline, 'baselineNote': a.note, 'baselineApplied': False})
os.makedirs(a.data, exist_ok=True); json.dump(new, open(p, 'w', encoding='utf-8'), indent=2); print('written:', p)
