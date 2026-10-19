r"""Copies the few Streamer.bot globals the Suite needs (dayCounter, the First 5 stats) out of globals.db (a LiteDB file) into the Host's data.
Read-only on Streamer.bot: it reads a COPY of globals.db.  Preview by default; --apply writes Data runtime\host_globals.json + automation_vars.json
(stop the Host first, it rewrites those files).
Usage: python Tools/import-streamerbot-globals.py [--apply] [--db PATH] [--data PATH]"""
import json, os, re, shutil, struct, sys, tempfile
a = sys.argv[1:]
def opt(n, d): return a[a.index(n) + 1] if n in a else d
db = opt('--db', os.path.join(os.path.expanduser('~'), 'Documents', 'PinguinoB0t', 'data', 'globals.db'))
data = opt('--data', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Data', 'runtime'))
tmp = os.path.join(tempfile.gettempdir(), 'sb_globals_copy.db'); shutil.copy(db, tmp); b = open(tmp, 'rb').read()
WANT = ['dayCounter', 'firstPlaceStats', 'secondPlaceStats', 'thirdPlaceStats', 'fourthPlaceStats', 'fifthPlaceStats']
def find(name):
    best = None
    for m in re.finditer(b'\x02_id\x00' + re.escape(struct.pack('<i', len(name) + 1) + name.encode()) + b'\x00', b):
        i = m.end(); v = None
        if b[i:i + 7] == b'\x02value\x00':
            n = struct.unpack('<i', b[i + 7:i + 11])[0]; v = b[i + 11:i + 11 + n - 1].decode('utf-8', 'replace'); j = i + 11 + n
        elif b[i:i + 7] == b'\x10value\x00':
            v = str(struct.unpack('<i', b[i + 7:i + 11])[0]); j = i + 11
        else: continue
        lw = struct.unpack('<q', b[j + 10:j + 18])[0] if b[j:j + 10] == b'\tlastWrite\x00' else 0
        if name.endswith('Stats'):   # old copies in the file can be cut off by neighbouring pages: only a complete JSON counts
            try: json.loads(v)
            except Exception: continue
        if best is None or lw >= best[0]: best = (lw, v)
    return best[1] if best else None
found = {n: find(n) for n in WANT}
for n, v in found.items():
    if v is None: print('%-18s not readable from the copy (Streamer.bot keeps it in pieces): open Streamer.bot > Globals, copy the value and save it into host_globals.json under this name' % n if n.endswith('Stats') else '%-18s not found' % n); continue
    if n.endswith('Stats'):
        try: d = json.loads(v); print('%-18s %d players, %d wins' % (n, len(d), sum(d.values())))
        except Exception: print('%-18s unreadable' % n); found[n] = None
    else: print('%-18s %s' % (n, v))
if '--apply' in a:
    gp = os.path.join(data, 'host_globals.json'); g = json.load(open(gp)) if os.path.exists(gp) else {}
    for n, v in found.items():
        if v is not None and n.endswith('Stats'): g[n] = v
    if found['dayCounter'] is not None: g['dayCounter'] = found['dayCounter']
    json.dump(g, open(gp, 'w'), indent=2)
    if found['dayCounter'] is not None:
        vp = os.path.join(data, 'automation_vars.json'); vs = json.load(open(vp)) if os.path.exists(vp) else {}
        vs['dayCounter'] = found['dayCounter']; json.dump(vs, open(vp, 'w'), indent=2)
    print('written to', os.path.abspath(data))
else: print('(preview only: add --apply with the Host stopped)')
