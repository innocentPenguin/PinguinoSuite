"""nightly-review.py must hide opted-out chatters even though chat_memory.json is keyed by Twitch id (login in v['Login'] / v['Aliases']).
Builds a throwaway suite tree in a temp dir (copy of the script, fake chat_memory.json + one day of live log), runs it, checks the report. Usage: python Tools/test-nightly-optout.py"""
import json, os, shutil, subprocess, sys, tempfile
here = os.path.dirname(os.path.abspath(__file__)); tmp = tempfile.mkdtemp(prefix='pgno_')
bad = []
try:
    os.makedirs(os.path.join(tmp, 'Tools')); shutil.copy(os.path.join(here, 'nightly-review.py'), os.path.join(tmp, 'Tools'))
    os.makedirs(os.path.join(tmp, 'Data', 'runtime')); os.makedirs(os.path.join(tmp, 'Data', 'chat_logs', 'live'))
    json.dump({'111': {'Login': 'hideme', 'Aliases': ['hideme_alt'], 'Privacy': 'anon'}, '222': {'Login': 'showme', 'Privacy': ''}},
              open(os.path.join(tmp, 'Data', 'runtime', 'chat_memory.json'), 'w'))
    with open(os.path.join(tmp, 'Data', 'chat_logs', 'live', '2026-01-01.jsonl'), 'w') as f:
        for i in range(6):
            for u in ('hideme', 'hideme_alt', 'showme'):
                f.write(json.dumps({'t': 1767225600000 + i * 1000, 'u': u, 'm': 'hello %d' % i}) + '\n')
    out = os.path.join(tmp, 'o.md')
    r = subprocess.run([sys.executable, os.path.join(tmp, 'Tools', 'nightly-review.py'), '2026-01-01', '--out', out], capture_output=True, text=True)
    if r.returncode: bad.append('script failed: ' + (r.stderr or r.stdout)[-300:])
    else:
        txt = open(out, encoding='utf-8').read().lower()
        if 'hideme' in txt: bad.append('opted-out login (or alias) appears in the report')
        if 'showme' not in txt: bad.append('normal chatter missing from the report')
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print('FAIL\n - ' + '\n - '.join(bad) if bad else 'PASS nightly-review opt-out'); sys.exit(1 if bad else 0)
