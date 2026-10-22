# Generates PinguinoLite icons (pure python, no PIL). Run from D:\PinguinoSuite\PinguinoLite:  python ..\Tools\lite-make-icon.py
# Family look = the Suite icon (App\src-tauri\icons\icon.png: orange ring + baby penguin photo).
# Lite variant = same ring, the ORIGINAL photo in black and white, plus a dark badge with a big orange lightning bolt.
import zlib, struct, math, os, sys
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'App', 'src-tauri', 'icons', 'icon.png')

def read_png(path):
    d = open(path, 'rb').read(); pos = 8; idat = b''
    while pos < len(d):
        n, t = struct.unpack('>I4s', d[pos:pos+8]); body = d[pos+8:pos+8+n]; pos += 12 + n
        if t == b'IHDR': w, h, bd, ct = struct.unpack('>IIBB', body[:10])
        elif t == b'IDAT': idat += body
    assert bd == 8 and ct in (2, 6), (bd, ct)
    bpp = 4 if ct == 6 else 3; raw = zlib.decompress(idat); stride = w * bpp; rows = []; prev = bytearray(stride); p = 0
    for _ in range(h):
        f = raw[p]; line = bytearray(raw[p+1:p+1+stride]); p += 1 + stride
        for i in range(stride):
            a = line[i-bpp] if i >= bpp else 0; b = prev[i]; c = prev[i-bpp] if i >= bpp else 0
            if f == 1: line[i] = (line[i] + a) & 255
            elif f == 2: line[i] = (line[i] + b) & 255
            elif f == 3: line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line); prev = line
    return w, h, bpp, rows

W, H, BPP, SRC_ROWS = read_png(SRC)
ORANGE = (255, 153, 0); DARK = (22, 17, 12)
def src(x, y):
    x = min(W-1, max(0, int(x))); y = min(H-1, max(0, int(y))); r = SRC_ROWS[y]; i = x * BPP
    return (r[i], r[i+1], r[i+2], r[i+3] if BPP == 4 else 255)

def cov(d):  # 1px anti-aliased edge: d<0 inside
    return min(1.0, max(0.0, 0.5 - d))
# lightning bolt, coordinates in badge space (centre 0,0), y down
BOLT = [(round(a*.78),round(b*.78)) for a,b in [(16, -74), (-44, 8), (-7, 8), (-21, 76), (44, -12), (7, -12)]]
def in_poly(px, py, poly):
    c = False; j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]; xj, yj = poly[j]
        if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi: c = not c
        j = i
    return c

BX, BY, BR = 368, 374, 94  # badge centre / radius in 512 space (large sizes)
SMALL = False  # sizes <= 64: dedicated art, badge ~45% of the icon, pure grayscale with extra contrast
def master(x, y):
    """pixel (x,y) of the 512 master -> (r,g,b,a) with a in 0..255"""
    cx = cy = 256.0; d = math.hypot(x + .5 - cx, y + .5 - cy)
    s = src(x, y)
    if s[3] == 0 and d > 255: return (0, 0, 0, 0)
    r, g, b, a = s
    # black and white: pure grayscale for everything inside the ring (no sepia); only the orange ring itself keeps its colour
    if d < 212:
        l = 0.3 * r + 0.59 * g + 0.11 * b
        if SMALL: l = min(255, max(0, (l - 120) * 1.35 + 128))
        r = g = b = l
    out = [r, g, b, a / 255.0]
    # badge
    bx, by, br = (366, 366, 120) if SMALL else (BX, BY, BR); k = br / 94.0
    db = math.hypot(x + .5 - bx, y + .5 - by)
    if db < br + 6:
        # dark halo cuts the badge out of the photo (matches the Suite's dark surfaces)
        for (rad, col) in ((br + 5, DARK), (br - 5 * k, ORANGE), (br - 17 * k, DARK)):
            c = cov(db - rad)
            if c > 0: out = [out[k] * (1 - c) + col[k] * c for k in range(3)] + [max(out[3], c)]
        # bolt, 2x2 supersampled
        hit = 0
        for oy in (.25, .75):
            for ox in (.25, .75):
                if in_poly((x + ox - bx) / k, (y + oy - by) / k, BOLT): hit += 1
        if hit: c = hit / 4.0; out = [out[k] * (1 - c) + ORANGE[k] * c for k in range(3)] + [max(out[3], c)]
    return tuple(out)

def render(n):
    global SMALL
    SMALL = n <= 256
    ss = max(1, 512 // n) if n < 512 else 1
    rows = []
    for y in range(n):
        row = bytearray()
        for x in range(n):
            ar = ag = ab = aa = 0.0
            for sy in range(ss):
                for sx in range(ss):
                    r, g, b, a = master(int((x * ss + sx) * 512 / (n * ss)), int((y * ss + sy) * 512 / (n * ss)))
                    ar += r * a; ag += g * a; ab += b * a; aa += a
            k = ss * ss
            row += bytes([round(ar / aa), round(ag / aa), round(ab / aa), round(255 * aa / k)]) if aa > 0 else b'\0\0\0\0'
        rows.append(bytes(row))
    return rows

def png(n):
    raw = b''.join(b'\0' + r for r in render(n))
    def ch(t, d): c = struct.pack('>I', len(d)) + t + d; return c + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', n, n, 8, 6, 0, 0, 0)) + ch(b'IDAT', zlib.compress(raw, 9)) + ch(b'IEND', b'')

out = 'src-tauri/icons/'
cache = {}
def P(n):
    if n not in cache: cache[n] = png(n)
    return cache[n]
for f, n in {'32x32.png': 32, '64x64.png': 64, '128x128.png': 128, '128x128@2x.png': 256, 'icon.png': 512}.items():
    open(out + f, 'wb').write(P(n))
ico = [(s, P(s)) for s in (16, 24, 32, 48, 64, 128, 256)]
hdr = struct.pack('<HHH', 0, 1, len(ico)); off = 6 + 16 * len(ico); ent = b''; data = b''
for s, p in ico:
    ent += struct.pack('<BBBBHHII', s % 256, s % 256, 0, 0, 1, 32, len(p), off + len(data)); data += p
open(out + 'icon.ico', 'wb').write(hdr + ent + data)
open('src/logo.png', 'wb').write(P(96))  # sidebar logo (shown ~36 px): small-size art
print('ok')
