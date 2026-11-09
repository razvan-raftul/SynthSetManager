"""pa_lib – citirea și scrierea fișierelor din seturile Korg Pa3X (refăcut în oct. 2026).

Ce știe:
  containerul KORF (toate fișierele din set), cu directorul vechi (05000018) și cel nou (05010018);
  compresia OC31 (despachetare și împachetare, cu suma de control XOR);
  RAM.KMP (sample-uri, sample-uri de tobe, zone, multisample-uri) și fișierele PCM;
  referințele: sunet -> multisample/sample de tobe (după ID de 8 octeți),
               performance/STS/style/pad -> sunet (MSB/LSB/PC), performance/STS -> pad.
Formatul e descris pe larg în CITESTE-MA.md.
"""
import os
import struct
from functools import reduce

# ----------------------------------------------------------------------------- OC31

def oc31_decompress(c, n):
    """c = fluxul de după antetul 'OC31'+mărime. Întoarce (date, octeți folosiți)."""
    out = bytearray()
    ip = 0

    def br(dist, length, extra):
        nonlocal ip
        for _ in range(length):
            out.append(out[-dist - 1])
        out.extend(c[ip:ip + extra])
        ip += extra

    while ip < len(c) and len(out) < n:
        f = c[ip]; ip += 1
        if f >= 0x10:
            if f >= 0x40:
                b = c[ip]; ip += 1
                t = (f << 8) | b
                br((t >> 2) & 0x7ff, (t >> 13) + 1, b & 3)
            else:
                far = f < 0x20
                t = f & (7 if far else 0x1f)
                if t == 0:
                    L = c[ip] + (0x0a if far else 0x22); b2, b3 = c[ip + 1], c[ip + 2]; ip += 3
                elif t == 1:
                    L = (c[ip] << 8) | c[ip + 1]; b2, b3 = c[ip + 2], c[ip + 3]; ip += 4
                else:
                    L = t + 2; b2, b3 = c[ip], c[ip + 1]; ip += 2
                dist = ((b2 << 8) | b3) >> 2
                if far:
                    dist += 0x4000 + (0x4000 if f & 8 else 0)
                br(dist, L, b3 & 3)
        elif f >= 2:
            out.extend(c[ip:ip + f + 2]); ip += f + 2
        elif f == 0:
            L = c[ip] + 0x12; ip += 1
            out.extend(c[ip:ip + L]); ip += L
        else:
            L = (c[ip] << 8) | c[ip + 1]; ip += 2
            if L == 0:
                break
            out.extend(c[ip:ip + L]); ip += L
    return bytes(out), ip


def xor_sum(d):
    return reduce(lambda a, v: a ^ v, d, 0)


def oc31_unpack(chunk):
    """Bucata întreagă 'OC31'... -> date. Verifică mărimea și suma de control."""
    n = struct.unpack('<I', chunk[4:8])[0]
    d, used = oc31_decompress(chunk[8:], n)
    if len(d) != n:
        raise ValueError('OC31: lungime greșită')
    tail = chunk[8 + used:]
    # după ultima operație vine terminatorul 01 00 00 și suma XOR
    if tail[:3] == b'\x01\x00\x00' and len(tail) >= 4:
        ck = tail[3]
    else:
        ck = chunk[-1]
    if ck != xor_sum(d):
        raise ValueError('OC31: suma de control nu se potrivește')
    return d


def oc31_pack(d, chain=48):
    """Date -> bucata 'OC31' (LZ în stilul Korg: literale, potriviri, 01 00 00 + XOR)."""
    n = len(d)
    out = bytearray()
    head = {}
    prev = [-1] * n
    MAXD = 0xc000

    def ins(i):
        if i + 3 <= n:
            k = d[i:i + 3]
            prev[i] = head.get(k, -1)
            head[k] = i

    def best(i):
        if i + 3 > n:
            return 0, 0
        j = head.get(d[i:i + 3], -1)
        bl = bd = c = 0
        lim = min(n - i, 0xffff)
        while j >= 0 and c < chain:
            dist = i - j
            if dist > MAXD:
                break
            if i + bl < n and d[j + bl] == d[i + bl]:
                L = 3
                while L < lim and d[j + L] == d[i + L]:
                    L += 1
                if (L >= 4 or dist - 1 < 2048) and L > bl:
                    bl, bd = L, dist
                if L == lim:
                    break
            j = prev[j]; c += 1
        return bl, bd

    def emit_lits(a, b):
        L = b - a
        if L == 0:
            return
        if 4 <= L <= 17:
            out.append(L - 2)
        elif 18 <= L <= 273:
            out.extend((0, L - 0x12))
        else:
            out.append(1); out.extend(struct.pack('>H', L))
        out.extend(d[a:b])

    def enc_match(L, dist):
        D = dist - 1
        if 3 <= L <= 8 and D < 2048:
            t = ((L - 1) << 13) | (D << 2)
            return bytearray(((t >> 8) & 0xff, t & 0xff))
        if D < 0x4000:
            if L <= 33:
                ob = bytearray((0x20 | (L - 2),))
            elif L <= 289:
                ob = bytearray((0x20, L - 0x22))
            else:
                ob = bytearray((0x21,)) + struct.pack('>H', L)
            v = D << 2
            return ob + bytearray((v >> 8, v & 0xff))
        D2 = D - 0x4000; hb = 0
        if D2 >= 0x4000:
            D2 -= 0x4000; hb = 8
        if L <= 9:
            ob = bytearray((0x10 | hb | (L - 2),))
        elif L <= 0x109:
            ob = bytearray((0x10 | hb, L - 0x0a))
        else:
            ob = bytearray((0x11 | hb,)) + struct.pack('>H', L)
        v = D2 << 2
        return ob + bytearray((v >> 8, v & 0xff))

    pend = None
    lit_start = 0
    i = 0
    start = True
    while i < n:
        L, dist = best(i)
        if L:
            rem = n - (i + L)
            if 0 < rem < 4:
                L2 = L - (4 - rem)
                if L2 >= 4 or (L2 == 3 and dist - 1 < 2048):
                    L = L2
                else:
                    L = 0
        if L and start and i - lit_start < 4:
            L = 0
        ob = None
        if L:
            ob = enc_match(L, dist)
            if (ob[0] & 0xf0) == 0x10 and ob[-1] == 0 and ob[-2] == 0:
                L = 0
        if L:
            nl = i - lit_start
            if pend is not None:
                if nl <= 3:
                    pend[-1] |= nl; out.extend(pend); out.extend(d[lit_start:i])
                else:
                    out.extend(pend); emit_lits(lit_start, i)
            else:
                emit_lits(lit_start, i)
            pend = ob
            start = False
            for k in range(i, i + L):
                ins(k)
            i += L
            lit_start = i
        else:
            ins(i); i += 1
    nl = n - lit_start
    if pend is not None:
        if 0 < nl <= 3:
            pend[-1] |= nl; out.extend(pend); out.extend(d[lit_start:n])
        else:
            out.extend(pend); emit_lits(lit_start, n)
    else:
        emit_lits(lit_start, n)
    out.extend(b'\x01\x00\x00')
    out.append(xor_sum(d))
    return b'OC31' + struct.pack('<I', n) + bytes(out)


# ----------------------------------------------------------------------------- containerul KORF

HDR_TYPE = 0x01000114
KORF_TYPE = 0x02000018
DIR_OLD = 0x05000018
DIR_NEW = 0x05010018
INDEX_TYPE = 0xfe000018


class Intrare:
    """O intrare din fișier: nume, tip, bancă, slot, versiune + bucata de date (cum e pe disc)."""

    def __init__(self, nume, tip, banca, slot, ver=0, x6=0, x7=0, chunk_tip=0, chunk=b'', coada=b''):
        self.nume = nume
        self.tip = tip
        self.banca = banca
        self.slot = slot
        self.ver = ver
        self.x6 = x6
        self.x7 = x7
        self.chunk_tip = chunk_tip
        self.chunk = chunk          # conținutul bucății (adesea 'OC31...')
        self.coada = coada          # cei 4 octeți de la capătul intrării noi (păstrați)

    def date(self):
        if self.chunk[:4] == b'OC31':
            return oc31_unpack(self.chunk)
        return self.chunk

    def pune_date(self, d):
        if self.chunk[:4] == b'OC31':
            self.chunk = oc31_pack(d)
        else:
            self.chunk = bytes(d)

    def copie(self):
        return Intrare(self.nume, self.tip, self.banca, self.slot, self.ver, self.x6, self.x7,
                       self.chunk_tip, self.chunk, self.coada)

    def __repr__(self):
        return f'<{self.nume!r} tip {self.tip} banca {self.banca:#x} slot {self.slot}>'


def _walk(b, p, end):
    out = []
    while p + 8 <= end:
        t, s = struct.unpack('>II', b[p:p + 8])
        out.append((p, t, s))
        p += 8 + s
    return out


class Fisier:
    """Un fișier din set (PCG, PRF, STY, PAD, PCM, KMP...)."""

    def __init__(self, cale=None):
        self.cale = cale
        self.korf = b'\x0b\x00\x00\x00\x00\x00\x00KORF\x00'
        self.intrari = []
        self.dir_nou = False
        if cale:
            self.citeste(cale)

    def citeste(self, cale):
        b = open(cale, 'rb').read()
        t, s = struct.unpack('>II', b[:8])
        if t != HDR_TYPE:
            raise ValueError(f'{cale}: nu e fișier Korg (antet {t:08x})')
        dirs = []
        datas = []
        for p, t, s in _walk(b, 8, 8 + s):
            c = b[p + 8:p + 8 + s]
            if t == KORF_TYPE:
                self.korf = c
            elif t == DIR_OLD:
                for i in range(0, len(c), 24):
                    e = c[i:i + 24]
                    dirs.append((e[:16].split(b'\0')[0].decode('latin1'), e[18], e[19], e[20], e[21], e[22], e[23], b''))
            elif t == DIR_NEW:
                self.dir_nou = True
                q = 0
                while q < len(c):
                    L = struct.unpack('>H', c[q:q + 2])[0]
                    dirs.append(self._intrare_noua(c[q + 2:q + 2 + L]))
                    q += 2 + L
            elif t == INDEX_TYPE:
                pass
            else:
                datas.append((t, c))
        if len(dirs) != len(datas):
            raise ValueError(f'{cale}: {len(dirs)} nume dar {len(datas)} bucăți de date')
        for (nm, tip, banca, slot, ver, x6, x7, coada), (t, c) in zip(dirs, datas):
            self.intrari.append(Intrare(nm, tip, banca, slot, ver, x6, x7, t, c, coada))

    @staticmethod
    def _intrare_noua(e):
        nr = struct.unpack('>H', e[:2])[0]
        q = 2
        nume = ''
        tip = banca = slot = ver = x6 = 0
        for _ in range(nr):
            tag, L = struct.unpack('>HH', e[q:q + 4])
            v = e[q + 4:q + 4 + L]
            q += 4 + L
            if tag == 2:
                nume = v.split(b'\0')[0].decode('latin1')
            elif tag == 0:
                tip, banca, slot = v[0], v[1], v[2]
            elif tag == 1:
                ver, x6 = v[0], (v[1] if len(v) > 1 else 0)
        return (nume, tip, banca, slot, ver, x6, 0, e[q:])

    def scrie(self, cale):
        """Scrie mereu cu directorul vechi (îl citesc toate versiunile de Pa3X)."""
        parts = [struct.pack('>II', KORF_TYPE, len(self.korf)) + self.korf]
        dd = b''.join(e.nume.encode('latin1', 'replace')[:16].ljust(16, b'\0') +
                      bytes((0, 0, e.tip, e.banca, e.slot, e.ver, e.x6, e.x7)) for e in self.intrari)
        parts.append(struct.pack('>II', DIR_OLD, len(dd)) + dd)
        for e in self.intrari:
            parts.append(struct.pack('>II', e.chunk_tip, len(e.chunk)) + e.chunk)
        # indexul de la final: offseturile bucăților începând cu directorul
        off = 8 + len(parts[0])
        offs = []
        for p in parts[1:]:
            offs.append(off)
            off += len(p)
        idx = b'KBEG' + b''.join(struct.pack('>I', o) for o in offs) + b'KEND' + struct.pack('>I', len(offs))
        parts.append(struct.pack('>II', INDEX_TYPE, len(idx)) + idx)
        body = b''.join(parts)
        data = struct.pack('>II', HDR_TYPE, len(body)) + body
        os.makedirs(os.path.dirname(cale) or '.', exist_ok=True)
        with open(cale, 'wb') as f:
            f.write(data)
        return len(data)

    def dupa_slot(self, slot):
        for e in self.intrari:
            if e.slot == slot:
                return e
        return None


def arbore(d, p0=0, adanc=0, out=None):
    """Înregistrările interne (tip 4 octeți, lungime 4 octeți), recursiv."""
    out = [] if out is None else out
    p = 0
    while p + 8 <= len(d):
        t, s = struct.unpack('>II', d[p:p + 8])
        c = d[p + 8:p + 8 + s]
        out.append((adanc, t, p0 + p + 8, c))
        if (t & 0xffff) == 0 and _se_imparte(c):
            arbore(c, p0 + p + 8, adanc + 1, out)
        p += 8 + s
    return out


def _se_imparte(c):
    p = 0
    while p + 8 <= len(c):
        s = struct.unpack('>I', c[p + 4:p + 8])[0]
        if s > len(c) - p - 8:
            return False
        p += 8 + s
    return p == len(c) and len(c) >= 8


# ----------------------------------------------------------------------------- KMP

SAMPLE_LEN, DRUM_LEN, ZONA_LEN, MS_LEN = 99, 48, 20, 166
ADRESE = [7] + [11 + 4 * k for k in range(8)] + [44, 48, 52, 56]   # câmpuri adresă (bază + relativ)


def nume_din(b):
    return b.split(b'\0')[0].decode('latin1').rstrip()


class KMP:
    def __init__(self, d=None):
        self.ver = b'\x00\x03'
        self.S, self.D, self.Z, self.M = [], [], [], []
        if d is not None:
            self.ver = d[:2]
            ns, nd, nz, nm = struct.unpack('>HHHH', d[2:10])
            p = 10
            for lst, n, L in ((self.S, ns, SAMPLE_LEN), (self.D, nd, DRUM_LEN), (self.Z, nz, ZONA_LEN), (self.M, nm, MS_LEN)):
                for _ in range(n):
                    lst.append(bytearray(d[p:p + L])); p += L
            if p != len(d):
                raise ValueError('RAM.KMP: lungime neașteptată')

    def bytes(self):
        return (self.ver + struct.pack('>HHHH', len(self.S), len(self.D), len(self.Z), len(self.M)) +
                b''.join(bytes(x) for x in self.S + self.D + self.Z + self.M))

    # --- câmpuri
    @staticmethod
    def s_id(s): return bytes(s[84:92])
    @staticmethod
    def s_nume(s): return nume_din(bytes(s[68:84]))
    @staticmethod
    def s_pcm(s): return s[92], s[93]
    @staticmethod
    def s_baza(s): return struct.unpack('>I', s[7:11])[0]
    @staticmethod
    def d_id(x): return bytes(x[40:48])
    @staticmethod
    def d_nume(x): return nume_din(bytes(x[12:28]))
    @staticmethod
    def d_samples(x):
        return [v for v in struct.unpack('>HHHH', bytes(x[:8])) if v != 0xffff]
    @staticmethod
    def m_id(m): return bytes(m[158:166])
    @staticmethod
    def m_nume(m): return nume_din(bytes(m[2:26]))
    @staticmethod
    def m_zone(m):
        f = struct.unpack('>H', m[26:28])[0]
        return range(f, f + m[156])
    @staticmethod
    def z_sample(z):
        """(index sample, e din RAM?) ; None dacă zona e goală."""
        v = struct.unpack('>H', z[:2])[0]
        if v == 0xffff:
            return None
        return v, z[2] == 1

    def samples_ms(self, mi):
        out = []
        for zi in self.m_zone(self.M[mi]):
            r = self.z_sample(self.Z[zi])
            if r and r[1]:
                out.append(r[0])
        return out


def muta_adrese(s, delta):
    s = bytearray(s)
    for o in ADRESE:
        v = struct.unpack('>I', s[o:o + 4])[0]
        s[o:o + 4] = struct.pack('>I', (v + delta) & 0xffffffff)
    return s


# ----------------------------------------------------------------------------- setul

BANCI_SUNET = {  # fișier -> (octet bancă în director, MSB, LSB)
    'USER01': (0x09, 121, 64), 'USER02': (0x0a, 121, 65), 'USER03': (0x0c, 121, 66),
    'USER04': (0x0d, 121, 67), 'USERDK': (0x0b, 120, 64),
}
DUPA_MSB_LSB = {(v[1], v[2]): k for k, v in BANCI_SUNET.items()}
MAX_RAM = 256 * 1024 * 1024


def banca_pad(nume):          # USER01.PAD -> 0x14, LOCAL04.PAD -> 0x21
    n = int(nume[-2:])
    return (0x13 if nume.startswith('USER') else 0x1d) + n


def banca_style(nume):        # FAVORITE01 -> 0x14, USER01 -> 0x11 (văzut în setul Mugurel)
    return (0x10 if nume.upper().startswith('USER') else 0x13) + int(nume[-2:])


def banca_perf(nume):         # BANK01 -> 0
    return int(nume[-2:]) - 1


def mb(n):
    return f'{n / 1048576:.1f}'.replace('.', ',') + ' MB'


class Set:
    def __init__(self, cale):
        self.cale = cale
        self.nume = os.path.basename(cale.rstrip('/\\'))
        self.fisiere = {}            # 'SOUND/USER01.PCG' -> Fisier (încărcate la cerere)
        self._kmp = None
        self._kmp_f = None
        self._pcm = None
        self.modificate = set()
        self.sablon_kmp = None       # (tip, bancă, slot, ver, chunk_tip, korf) luat din sursă pentru un set gol
        self.sabloane_korf = {}      # folder -> korf luat din sursă

    # --- fișiere
    def lista(self, folder, ext):
        d = os.path.join(self.cale, folder)
        if not os.path.isdir(d):
            return []
        return sorted(f for f in os.listdir(d) if f.upper().endswith(ext))

    def fisier(self, rel, creeaza=False):
        rel = rel.replace('\\', '/')
        if rel not in self.fisiere:
            p = os.path.join(self.cale, *rel.split('/'))
            if os.path.exists(p):
                self.fisiere[rel] = Fisier(p)
            elif creeaza:
                self.fisiere[rel] = Fisier()
                k = self.sabloane_korf.get(rel.split('/')[0])
                if k:
                    self.fisiere[rel].korf = k
            else:
                return None
        return self.fisiere[rel]

    @property
    def kmp(self):
        if self._kmp is None:
            f = self.fisier('MULTISMP/RAM.KMP')
            if f is None or not f.intrari:
                self._kmp_f = None
                self._kmp = KMP()
            else:
                self._kmp_f = f
                self._kmp = KMP(f.intrari[0].date())
        return self._kmp

    def pcm(self):
        """(fișier, slot) -> (nume, mărime, id, Intrare). Citește doar antetele."""
        if self._pcm is None:
            self._pcm = {}
            for fn in self.lista('PCM', '.PCM'):
                n = int(fn[3:5]) - 1
                f = self.fisier('PCM/' + fn)
                for e in f.intrari:
                    self._pcm[(n, e.slot)] = (e.nume, len(e.chunk), bytes(e.chunk[:8]), e)
        return self._pcm

    def marime_pcm(self):
        return sum(v[1] for v in self.pcm().values())

    # --- sunete
    def sunete(self):
        """[(fișier, Intrare)] pentru toate sunetele user."""
        out = []
        for fn in self.lista('SOUND', '.PCG'):
            f = self.fisier('SOUND/' + fn)
            for e in f.intrari:
                out.append((fn[:-4], e))
        return out

    def indexuri(self):
        """ID -> primul indice (așa caută și transferul); dubluri_* țin toate indicii unui ID."""
        k = self.kmp
        mid, did = {}, {}
        self.dubluri_m, self.dubluri_d = {}, {}
        for i, m in enumerate(k.M):
            mid.setdefault(k.m_id(m), i)
            self.dubluri_m.setdefault(k.m_id(m), []).append(i)
        for i, x in enumerate(k.D):
            did.setdefault(k.d_id(x), i)
            self.dubluri_d.setdefault(k.d_id(x), []).append(i)
        return mid, did

    def ref_sunet(self, e, mid=None, did=None):
        """Multisample-urile și sample-urile de tobe din RAM folosite de un sunet."""
        if mid is None:
            mid, did = self.indexuri()
        d = e.date()
        ms, dr = set(), set()
        for i in range(len(d) - 7):
            w = d[i:i + 8]
            if w in mid:
                ms.add(mid[w])
            elif w in did:
                dr.add(did[w])
        return sorted(ms), sorted(dr)

    def ref_sunet_toate(self, e):
        """Ca ref_sunet, dar cu toți indicii care au același ID (pentru curățenie: nu scoatem dublurile)."""
        mid, did = self.indexuri()
        ms, dr = self.ref_sunet(e, mid, did)
        k = self.kmp
        ms2 = set(i for m in ms for i in self.dubluri_m[k.m_id(k.M[m])])
        dr2 = set(i for d in dr for i in self.dubluri_d[k.d_id(k.D[d])])
        return sorted(ms2), sorted(dr2)

    def samples_sunet(self, ms, dr):
        k = self.kmp
        s = set()
        for mi in ms:
            s.update(k.samples_ms(mi))
        for di in dr:
            s.update(k.d_samples(k.D[di]))
        return s

    def marime_samples(self, idx):
        pcm = self.pcm()
        tot = 0
        for si in idx:
            if si < len(self.kmp.S):
                v = pcm.get(self.kmp.s_pcm(self.kmp.S[si]))
                if v:
                    tot += v[1]
        return tot

    # --- salvare
    def salveaza(self, cale_noua=None):
        """Scrie fișierele modificate. cale_noua = alt folder (setul vechi rămâne neatins)."""
        dest = cale_noua or self.cale
        if self._kmp is not None and 'MULTISMP/RAM.KMP' in self.modificate:
            f = self._kmp_f
            if f is None:
                f = Fisier()
                if self.sablon_kmp:
                    tip, banca, slot, ver, ct, korf = self.sablon_kmp
                    f.korf = korf
                    f.intrari.append(Intrare('RAM', tip, banca, slot, ver, 0, 0, ct, b''))
                else:
                    f.intrari.append(Intrare('RAM', 5, 1, 0, 3, 0, 0, 0x11030038, b''))
                self.fisiere['MULTISMP/RAM.KMP'] = f
                self._kmp_f = f
            f.intrari[0].chunk = oc31_pack(self.kmp.bytes())
        for rel in sorted(self.modificate):
            self.fisiere[rel].scrie(os.path.join(dest, *rel.split('/')))
        return sorted(self.modificate)


# ----------------------------------------------------------------------------- referințe în date

def refs_sunete(d):
    """Pozițiile (offset MSB) ale referințelor la sunete user într-un performance/STS/style/pad
    decomprimat: [(offset, MSB, LSB, PC)]."""
    out = []
    for adanc, t, p, c in arbore(d):
        if t == 0x09000008 and len(c) == 242:
            out.append((p + 12, c[12], c[13], c[15]))
        elif t in (0x02000308, 0x02000208) and len(c) >= 48:
            for k in range(8):
                out.append((p + 6 * k + 1, c[6 * k + 1], c[6 * k + 2], c[6 * k + 3]))
    return [r for r in out if (r[1], r[2]) in DUPA_MSB_LSB]


def refs_paduri(d):
    """Referințe la pad-uri: [(offset, bancă, slot)] din înregistrările 08000008 (19 octeți)."""
    out = []
    for adanc, t, p, c in arbore(d):
        if t == 0x08000008 and len(c) == 19 and c[4] == 0x09 and c[5] != 0xff:
            out.append((p + 5, c[5], c[7]))
    return out
