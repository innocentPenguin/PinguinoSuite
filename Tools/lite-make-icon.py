# Generates src-tauri/icons for PinguinoLite (pure python, no PIL): dark rounded tile, orange penguin silhouette with light belly.
import zlib, struct, math, sys
def shape(u, v):
    """u,v in 0..1 -> (r,g,b,a)"""
    # rounded tile
    cx, cy, hw, rr = .5, .5, .48, .2
    dx, dy = abs(u-cx)-(hw-rr), abs(v-cy)-(hw-rr)
    d = math.hypot(max(dx,0), max(dy,0)) + min(max(dx,dy),0) - rr
    if d > 0: return (0,0,0,0)
    px = (24,22,20)
    def ell(x,y,a,b,x0,y0): return ((x-x0)/a)**2+((y-y0)/b)**2 <= 1
    if ell(u,v,.20,.30,.5,.52): px=(255,153,0)          # body
    if ell(u,v,.20,.30,.5,.52) and (u<.33 or u>.67) and v<.60: pass
    if ell(u,v,.12,.21,.5,.58): px=(250,240,225)        # belly
    if ell(u,v,.15,.13,.5,.28) : px=(255,153,0)         # head
    if ell(u,v,.02,.025,.45,.26) or ell(u,v,.02,.025,.55,.26): px=(20,12,0)  # eyes
    if ell(u,v,.045,.03,.5,.33): px=(20,12,0)           # beak
    return px+(255,)
def render(n, ss=3):
    rows=[]
    for y in range(n):
        row=bytearray()
        for x in range(n):
            acc=[0,0,0,0]
            for sy in range(ss):
                for sx in range(ss):
                    r,g,b,a=shape((x+(sx+.5)/ss)/n,(y+(sy+.5)/ss)/n)
                    acc[0]+=r*a;acc[1]+=g*a;acc[2]+=b*a;acc[3]+=a
            A=acc[3]
            row+=bytes([round(acc[0]/A),round(acc[1]/A),round(acc[2]/A),round(A/(ss*ss))]) if A else b'\0\0\0\0'
        rows.append(bytes(row))
    return rows
def png(n):
    raw=b''.join(b'\0'+r for r in render(n))
    def ch(t,d): c=struct.pack('>I',len(d))+t+d; return c+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+ch(b'IHDR',struct.pack('>IIBBBBB',n,n,8,6,0,0,0))+ch(b'IDAT',zlib.compress(raw,9))+ch(b'IEND',b'')
out='src-tauri/icons/'
sizes={'32x32.png':32,'128x128.png':128,'128x128@2x.png':256,'icon.png':512}
for f,n in sizes.items(): open(out+f,'wb').write(png(n))
ico=[(s,png(s)) for s in (16,32,48,64,128,256)]
hdr=struct.pack('<HHH',0,1,len(ico)); off=6+16*len(ico); ent=b''; data=b''
for s,p in ico:
    ent+=struct.pack('<BBBBHHII',s%256,s%256,0,0,1,32,len(p),off+len(data)); data+=p
open(out+'icon.ico','wb').write(hdr+ent+data)
