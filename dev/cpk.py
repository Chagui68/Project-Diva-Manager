"""CRI CPK reader (game archives): list files and extract them. Files inside are often AES-encrypted.
Run: python dev\cpk.py <archivo.cpk> [regex]"""
import struct, sys, re

def decrypt_utf(b):
    if b[:4] == b'@UTF':
        return b
    out = bytearray(b); m = 0x655f
    for i in range(len(out)):
        out[i] ^= m & 0xff
        m = (m * 0x4115) & 0xffffffff
    return bytes(out)

def parse_utf(b):
    b = decrypt_utf(b)
    assert b[:4] == b'@UTF', b[:4]
    tsize, rows_off, str_off, data_off, name_off, ncol, rowlen, nrows = struct.unpack('>IIIIIHHI', b[4:32])
    base = 8
    def s(o):
        st = base + str_off + o
        return b[st:b.index(b'\0', st)].decode('utf-8', 'replace')
    p = 32
    cols = []
    readers = {0:('>B',1),1:('>b',1),2:('>H',2),3:('>h',2),4:('>I',4),5:('>i',4),6:('>Q',8),7:('>q',8),8:('>f',4),9:('>d',8)}
    def readval(t, p):
        if t in readers:
            f, n = readers[t]; return struct.unpack(f, b[p:p+n])[0], p+n
        if t == 0xA:
            return s(struct.unpack('>I', b[p:p+4])[0]), p+4
        if t == 0xB:
            o, n = struct.unpack('>II', b[p:p+8]); st = base+data_off+o
            return b[st:st+n], p+8
        raise ValueError(t)
    for _ in range(ncol):
        flags = b[p]; nm = s(struct.unpack('>I', b[p+1:p+5])[0]); p += 5
        st, t = flags & 0xf0, flags & 0x0f
        const = None
        if st in (0x30, 0x70):
            const, p = readval(t, p)
        cols.append((nm, st, t, const))
    rows = []
    for r in range(nrows):
        p = base + rows_off + r*rowlen; row = {}
        for nm, st, t, const in cols:
            if st == 0x50:
                row[nm], p = readval(t, p)
            elif st in (0x30, 0x70):
                row[nm] = const
            else:
                row[nm] = None
        rows.append(row)
    return rows

def crilayla(src):
    usize, hoff = struct.unpack('<II', src[8:16])
    res = bytearray(usize + 0x100)
    res[0:0x100] = src[hoff+0x10:hoff+0x110]
    st = {'off': len(src)-0x100-1, 'pool': 0, 'left': 0}
    def bits(n):
        out = 0; got = 0
        while got < n:
            if st['left'] == 0:
                st['pool'] = src[st['off']]; st['left'] = 8; st['off'] -= 1
            k = min(st['left'], n-got)
            out = (out << k) | ((st['pool'] >> (st['left']-k)) & ((1<<k)-1))
            st['left'] -= k; got += k
        return out
    oend = 0x100 + usize - 1; done = 0; vle = [2,3,5,8]
    while done < usize:
        if bits(1):
            bo = oend - done + bits(13) + 3; ln = 3
            for lvl in range(4):
                v = bits(vle[lvl]); ln += v
                if v != (1<<vle[lvl])-1: break
            else:
                while True:
                    v = bits(8); ln += v
                    if v != 255: break
            for _ in range(ln):
                res[oend-done] = res[bo]; bo -= 1; done += 1
        else:
            res[oend-done] = bits(8); done += 1
    return bytes(res)

def toc(path):
    f = open(path, 'rb')
    h = f.read(16); assert h[:4] == b'CPK ', h
    n = struct.unpack('<Q', h[8:16])[0]
    hdr = parse_utf(f.read(n))[0]
    to = hdr['TocOffset']
    f.seek(to); th = f.read(16); assert th[:4] == b'TOC ', th
    n = struct.unpack('<Q', th[8:16])[0]
    rows = parse_utf(f.read(n))
    return f, hdr, rows

def read_file(f, hdr, row):
    f.seek(hdr['TocOffset'] + row['FileOffset'])
    d = f.read(row['FileSize'])
    if d[:8] == b'CRILAYLA':
        d = crilayla(d)
    return d

if __name__ == '__main__':
    f, hdr, rows = toc(sys.argv[1])
    pat = re.compile(sys.argv[2]) if len(sys.argv) > 2 else None
    print({k: v for k, v in hdr.items() if not isinstance(v, bytes)})
    for r in rows:
        p = f"{r.get('DirName') or ''}/{r['FileName']}"
        if pat is None or pat.search(p):
            print(p, r['FileSize'], r.get('ExtractSize'))
