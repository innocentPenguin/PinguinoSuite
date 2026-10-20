"""Mechanical file index. Read-only except its own output.
Writes Data/index/files.json (path, kind, purpose, owner session, last changed) and
Data/index/index-gaps.md (items that Docs/INDEX.md does not mention). Never edits other files.
Usage: python Tools/build-index.py"""
import os, re, json, time, sys

SUITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(SUITE, 'Data', 'index')
INDEX_DOC = os.path.join(SUITE, 'Docs', 'INDEX.md')

SKIP_DIRS = {'bin', 'obj', 'build', '__pycache__', 'node_modules', '.git', 'Archive', 'backups', 'wt05b',
             's05data', 'dist', 'target', 'logs', 'venv', '.venv', 'site-packages', 'archive', 'chat_logs', 'secrets', 'index', 'SessionsArchive'}
SRC_EXT = {'.cs', '.py', '.ps1', '.bat', '.cmd', '.js', '.html', '.css', '.csproj', '.txt'}
DOC_EXT = {'.md'}
DATA_EXT = {'.json', '.txt', '.csv'}
# first path segment -> (kind, owner). Owner = session number from the coordinator notes; '?' when unknown.
OWNERS = [('Suite/modules/multi', '04'), ('Suite/modules/link', '03'), ('Suite/modules/voice', '06'), ('Suite/modules/listen', '06'), ('PinguinoHost', '02'), ('HelperPinguino', '02'), ('PinguinoChat', '02'), ('PinguinoB0t', '02'),
          ('Shared', '02'), ('PinguinoSite', '05'), ('PinguinoSite-cmd', '05'), ('PinguinoSite-v', '05'),
          ('PinguinoApp', '00'), ('App', '00'), ('Suite', '00'), ('Deploy', '00'), ('Pipeline', '00'),
          ('Docs/PinguinoLink', '03'), ('Docs/PinguinoMulti', '04'), ('Docs', '00'), ('Tools', '999'),
          ('Tests', '999'), ('Data', '02')]
TOOL_OWNER_HINT = [('test-host', '02'), ('gen-index', '02'), ('build-index', '999'), ('build-channel-lore', '02'),
                   ('build-namehistory', '02'), ('build-helper-pack', '02'), ('test-helper-pack', '02'),
                   ('mock-', '02'), ('obs_probe', '02')]


def owner_of(rel):
    r = rel.replace('\\', '/')
    for pre, o in OWNERS:
        if r == pre or r.startswith(pre + '/'):
            if pre == 'Tools':
                b = os.path.basename(r)
                for h, oo in TOOL_OWNER_HINT:
                    if b.startswith(h):
                        return oo
            return o
    return '?'


def purpose_of(path, ext):
    try:
        with open(path, encoding='utf-8-sig', errors='replace') as f:
            head = [next(f, '') for _ in range(25)]
    except Exception:
        return ''
    text = ''.join(head)
    if ext == '.py':
        m = re.search(r'^\s*(?:"""|\'\'\')(.+?)(?:"""|\'\'\'|\n)', text, re.S)
        if m:
            ls = m.group(1).strip().splitlines()
            if ls:
                return ls[0][:140]
    if ext == '.md':
        for l in head:
            if l.startswith('#'):
                return l.lstrip('# ').strip()[:140]
    if ext in ('.cs', '.js', '.ps1', '.bat'):
        for l in head:
            s = l.strip()
            if s.startswith('//') or s.startswith('#') or s.lower().startswith('rem ') or s.startswith('<#'):
                s = s.lstrip('/#<> ').strip()
                if len(s) > 6 and not s.startswith('<<'):
                    return s[:140]
    if ext == '.json':
        return ''
    return ''


def kind_of(rel, ext):
    r = rel.replace('\\', '/')
    if r.startswith('Docs/') and ext in DOC_EXT:
        return 'doc'
    if r.startswith('Tools/'):
        return 'tool'
    if r.startswith('Tests/'):
        return 'test'
    if r.startswith('Data/'):
        return 'data'
    if ext in SRC_EXT:
        return 'module'
    return 'other'


def walk():
    for root, dirs, files in os.walk(SUITE):
        rel_root = os.path.relpath(root, SUITE)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        top = rel_root.replace('\\', '/').split('/')[0]
        for fn in files:
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, SUITE).replace('\\', '/')
            ext = os.path.splitext(fn)[1].lower()
            if top == 'Data':
                # data: top-level files and one level of directory contents only (keeps the index small)
                depth = rel.count('/')
                if depth > 2 or ext not in DATA_EXT:
                    continue
            elif ext not in SRC_EXT | DOC_EXT:
                continue
            if fn.endswith('.csproj') or rel.startswith('Deploy/'):
                pass
            yield p, rel, ext


def main():
    rows = []
    for p, rel, ext in walk():
        try:
            st = os.stat(p)
        except OSError:
            continue
        rows.append({'path': rel, 'kind': kind_of(rel, ext), 'purpose': purpose_of(p, ext),
                     'owner': owner_of(rel), 'changed': time.strftime('%Y-%m-%d %H:%M', time.localtime(st.st_mtime)),
                     'bytes': st.st_size})
    rows.sort(key=lambda r: r['path'])
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, 'files.json'), 'w', encoding='utf-8') as f:
        json.dump({'built': time.strftime('%Y-%m-%d %H:%M'), 'count': len(rows), 'files': rows}, f, indent=1)

    # gap check: every module / data / tool / doc must be named in Docs/INDEX.md (basename or stem match)
    idx = ''
    if os.path.exists(INDEX_DOC):
        idx = open(INDEX_DOC, encoding='utf-8-sig', errors='replace').read().lower()
    gaps = {}
    seen_dirs = set()
    for r in rows:
        if r['kind'] not in ('module', 'data', 'tool', 'doc'):
            continue
        base = os.path.basename(r['path']).lower()
        stem = os.path.splitext(base)[0]
        if base in idx or r['path'].lower() in idx or (len(stem) > 5 and stem in idx):
            continue
        # data files inside a directory: covered when the directory is named
        if r['kind'] == 'data' and r['path'].count('/') >= 2:
            d = r['path'].split('/')[1].lower()
            nidx = idx.replace('\\', '/')
            if ('data/' + d) in nidx or (d + '/') in nidx:
                continue
            key = 'Data/' + d + '/ (directory)'
            if key in seen_dirs:
                continue
            seen_dirs.add(key)
            r = dict(r, path=key)
        gaps.setdefault((r['owner'], r['kind']), []).append(r)
    lines = ['# Index gaps (generated by Tools/build-index.py, report only)', '',
             'Built %s. Items below are not named in Docs/INDEX.md. Nothing was edited.' % time.strftime('%Y-%m-%d %H:%M'), '']
    total = 0
    for (own, kind), items in sorted(gaps.items()):
        lines += ['## owner %s - %s (%d)' % (own, kind, len(items)), '']
        lines += ['- `%s`' % i['path'] for i in items[:200]]
        if len(items) > 200:
            lines.append('- ... %d more' % (len(items) - 200))
        lines.append('')
        total += len(items)
    with open(os.path.join(OUT_DIR, 'index-gaps.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    by = {}
    for r in rows:
        by[r['kind']] = by.get(r['kind'], 0) + 1
    print('indexed', len(rows), by)
    print('gaps vs Docs/INDEX.md:', total, {'%s/%s' % k: len(v) for k, v in sorted(gaps.items())})


if __name__ == '__main__':
    main()
