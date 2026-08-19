"""Standalone PNG reader - NO Blender, NO PIL. Ground truth pixel sampling."""
import zlib, struct, sys

def read_png(path):
    d = open(path,'rb').read()
    assert d[:8] == b'\x89PNG\r\n\x1a\n', "not a png"
    pos = 8; idat = b''; w=h=bd=ct=None; ilace=None
    while pos < len(d):
        ln = struct.unpack('>I', d[pos:pos+4])[0]
        typ = d[pos+4:pos+8]
        data = d[pos+8:pos+8+ln]
        if typ == b'IHDR':
            w,h,bd,ct,comp,filt,ilace = struct.unpack('>IIBBBBB', data)
        elif typ == b'IDAT':
            idat += data
        elif typ == b'IEND':
            break
        pos += 12+ln
    assert ilace == 0, "interlaced unsupported"
    nch = {0:1,2:3,3:1,4:2,6:4}[ct]
    bpp_bits = bd*nch
    bpp = max(1, bpp_bits//8)
    stride = (w*bpp_bits + 7)//8
    raw = zlib.decompress(idat)
    out = bytearray()
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]; p+=1
        line = bytearray(raw[p:p+stride]); p+=stride
        if f == 1:
            for i in range(bpp, stride): line[i] = (line[i]+line[i-bpp]) & 255
        elif f == 2:
            for i in range(stride): line[i] = (line[i]+prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i-bpp] if i>=bpp else 0
                line[i] = (line[i] + ((a+prev[i])>>1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i-bpp] if i>=bpp else 0
                b = prev[i]; c = prev[i-bpp] if i>=bpp else 0
                pa=abs(b-c); pb=abs(a-c); pc=abs(a+b-2*c)
                pr = a if (pa<=pb and pa<=pc) else (b if pb<=pc else c)
                line[i] = (line[i]+pr) & 255
        out += line
        prev = line
    return w,h,bd,nch,bytes(out)

def px(path, x=None, y=None):
    w,h,bd,nch,data = read_png(path)
    if x is None: x = w//2
    if y is None: y = h//2
    stride = (w*bd*nch)//8
    if bd == 8:
        o = y*stride + x*nch
        vals = list(data[o:o+nch])
        return w,h,bd,nch,vals,'#%02X%02X%02X'%tuple(vals[:3])
    elif bd == 16:
        o = y*stride + x*nch*2
        vals = [struct.unpack('>H', data[o+i*2:o+i*2+2])[0] for i in range(nch)]
        return w,h,bd,nch,vals,'#%02X%02X%02X'%tuple(v>>8 for v in vals[:3])

if __name__ == '__main__':
    for f in sys.argv[1:]:
        w,h,bd,nch,vals,hx = px(f)
        import os
        print(f"{os.path.basename(f):46} {w}x{h} {bd}bit ch={nch}  centre={vals}  {hx}")
