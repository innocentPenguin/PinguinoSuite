"""One-time pushup baseline: writes "baseline": 805 into <data>/pushups.json (161 recorded pushup redemptions x 5). The Host adds it to the all-time count once on its next start
and marks it applied, so a restart never adds it again. DRY RUN by default; --write backs the existing file up first (pushups.json.before-seed-YYYYMMDD-HHMMSS.bak).
A file whose baseline was already APPLIED is refused (no double seeding); an unapplied one is refused unless --replace (then it is backed up first and replaced). Default --data = the Host's real data folder Data/runtime; any other folder without host files is refused.

  python Tools/seed-pushups.py --data D:/PinguinoSuite/Data/runtime            # dry run
  python Tools/seed-pushups.py --data D:/PinguinoSuite/Data/runtime --write
"""
import argparse, datetime as dt, json, os, shutil, sys
here = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA = os.path.join(os.path.dirname(here), 'Data', 'runtime')
HOST_MARKERS = ('host_secrets.json', 'automations.json', 'bots.json', 'chat_settings.json')   # files only the Host's real data folder has
def host_data(d):
    """The Host's real data dir (Data/runtime = HostApi.DataDir) is the default; a folder without any host file is refused (a typo or the parent Data/ folder would seed files the Host never reads)."""
    d = os.path.abspath(d)
    if not any(os.path.exists(os.path.join(d, m)) for m in HOST_MARKERS):
        sys.exit('refused: %s has none of %s, so it is not the Host data folder (the default is %s)' % (d, '/'.join(HOST_MARKERS), DEFAULT_DATA))
    return d
ap = argparse.ArgumentParser(); ap.add_argument('--data', default=DEFAULT_DATA); ap.add_argument('--baseline', type=int, default=805)
ap.add_argument('--note', default='161 redemptions x 5, 2026-10-30'); ap.add_argument('--write', action='store_true'); ap.add_argument('--replace', action='store_true', help='replace a baseline the Host has not applied yet'); a = ap.parse_args()
a.data = host_data(a.data); p = os.path.join(a.data, 'pushups.json'); print('target file:', p); cur = json.load(open(p, encoding='utf-8-sig')) if os.path.exists(p) else None
if cur and (cur.get('baselineApplied') is True or (cur.get('baseline') and not a.replace)): sys.exit(('refused: %s already has a baseline (%s, applied=%s)' % (p, cur.get('baseline'), cur.get('baselineApplied'))) + ('' if cur.get('baselineApplied') is True else '; --replace overwrites a baseline the Host has not applied yet'))
if cur and cur.get('baseline'): print('REPLACES the unapplied baseline %s (the Host has not added it yet; allTime stays %s)' % (cur.get('baseline'), cur.get('allTime', cur.get('count', 0))))
print('file:', p, '(exists: %s)' % bool(cur)); print('now :', json.dumps(cur)); allt = (cur or {}).get('allTime', (cur or {}).get('count', 0))
print('after the Host start: allTime = %d + %d = %d, session unchanged' % (allt, a.baseline, allt + a.baseline))
if not a.write: print('DRY RUN: nothing written. Add --write to apply.'); sys.exit(0)
if cur is not None:
    b = p + '.before-seed-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S') + '.bak'; shutil.copy2(p, b); print('backup:', b)
new = dict(cur or {'enabled': True, 'count': 0}); new.update({'baseline': a.baseline, 'baselineNote': a.note, 'baselineApplied': False})
os.makedirs(a.data, exist_ok=True); json.dump(new, open(p, 'w', encoding='utf-8'), indent=2); print('written:', p); print('a running Host reads it on its own (file newer than its memory); or POST /api/seeds/reload')
