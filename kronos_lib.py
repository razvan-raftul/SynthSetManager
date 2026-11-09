"""Kronos: citire seturi (PCG + KSC/KMP/KSF), costul în MB și transferul de Programe/Combi-uri
cu tot cu multisample-uri. Pornit din Kronos Tools\\kronos_transfer.py (oct. 2026), care a mers pe Kronos.
Offseturile sunt cele din Kronos Tools\\CITESTE-MA.md.
"""
import os, re, shutil, uuid

PB = ['I-A', 'I-B', 'I-C', 'I-D', 'I-E', 'I-F', 'U-A', 'U-B', 'U-C', 'U-D', 'U-E', 'U-F', 'U-G',
      'U-AA', 'U-BB', 'U-CC', 'U-DD', 'U-EE', 'U-FF', 'U-GG']
PB_ID = {**{PB[i]: i for i in range(6)}, **{PB[6 + i]: 17 + i for i in range(14)}}
ID_PB = {v: k for k, v in PB_ID.items()}
CB = ['I-A', 'I-B', 'I-C', 'I-D', 'I-E', 'I-F', 'I-G', 'U-A', 'U-B', 'U-C', 'U-D', 'U-E', 'U-F', 'U-G']
ZONE0, OSC_STRIDE, ZONE_STRIDE, OSCMODE = 2774, 466, 22, 2558
TIMBRES, TIMBRE_SIZE = 4802, 188
P_SW1, C_SW1 = 2572, 4796
INIT_PROG = ('Init Program', 'Init EXi Program')
INIT_COMBI = ('Init Combi',)
BANCI_TIMBRE = ['U-D', 'U-C', 'U-E', 'U-F', 'U-G']


def mb(n):
    return ('%.1f' % (n / 1048576)).replace('.', ',') + ' MB'


def rd_lines(p):
    if not os.path.exists(p):
        return []
    return [l.rstrip('\r\n') for l in open(p, encoding='latin1')]


def wr_lines(p, L):
    with open(p, 'w', encoding='latin1', newline='') as f:
        f.write('\r\n'.join(L) + '\r\n')


def kchunks(b):
    o = 0; out = []
    while o + 8 <= len(b):
        n = b[o:o + 4]; l = int.from_bytes(b[o + 4:o + 8], 'big'); out.append((n, o, l)); o += 8 + l
    return out


def pname(b, p):
    return bytes(b[p:p + 24]).split(b'\0')[0].decode('latin1').strip()


# ----------------------------------------------------------------------------- găsirea seturilor

def gaseste_seturi(radacini):
    """Caută seturi Kronos (X.PCG cu X.KSC lângă) în folderele date, până la 2 niveluri."""
    out = []
    vazute = set()
    for r in radacini:
        if not os.path.isdir(r):
            continue
        for cale, dirs, files in os.walk(r):
            adanc = os.path.relpath(cale, r).count(os.sep) + (0 if cale == r else 1)
            if adanc >= 2:
                dirs[:] = []
            up = {f.upper(): f for f in files}
            for f in files:
                if f.upper().endswith('.PCG'):
                    base = f[:-4]
                    if (base + '.KSC').upper() in up:
                        p = os.path.normcase(os.path.abspath(os.path.join(cale, f)))
                        if p in vazute:
                            continue
                        vazute.add(p)
                        folder = os.path.basename(cale)
                        nume = folder if folder.lower() == base.lower() or base.lower() in folder.lower().replace(' ', '') else '%s (%s)' % (folder, base)
                        out.append(dict(id=os.path.join(cale, f), nume=nume, folder=cale, base=base))
    out.sort(key=lambda s: s['nume'].lower())
    return out


def din_id(sid):
    return os.path.dirname(sid), os.path.basename(sid)[:-4]


# ----------------------------------------------------------------------------- sample-uri

class SampleSet:
    def __init__(s, folder, base):
        s.folder, s.base = folder, base
        s.ksc = rd_lines(os.path.join(folder, base + '.KSC'))
        s.ub = rd_lines(os.path.join(folder, base + '_UserBank.KSC'))
        s.uuid = next((l[6:].strip() for l in s.ksc if l.startswith('#uuid:')), None)
        s.kmps = [l.strip() for l in s.ksc if l and not l.startswith('#') and l.upper().endswith('.KMP')]
        s.ms, s.ds = {}, {}
        order = []
        for l in s.ub:
            m = re.match(r'#>>uuid:[0-9a-f-]+\.(MS|DS)(\d+)\.\d+\.\d+\.(.*)', l)
            if m:
                (s.ms if m.group(1) == 'MS' else s.ds)[int(m.group(2))] = m.group(3)
                if m.group(1) == 'MS':
                    order.append(int(m.group(2)))
        s.idx = dict(zip(order, s.kmps)) if len(order) == len(s.kmps) else dict(enumerate(s.kmps))
        s._ksf, s._size, s._sig = {}, {}, {}

    def has(s, i): return i in s.idx
    def next_index(s): return max(s.idx) + 1 if s.idx else 0
    def kmp_path(s, i): return os.path.join(s.folder, s.base, s.idx[i])

    def kmp_ksfs(s, i):
        if i not in s._ksf:
            out = []
            try:
                b = open(s.kmp_path(i), 'rb').read()
            except OSError:
                b = b''
            for n, o, l in kchunks(b):
                if n == b'RLP1':
                    for j in range(o + 8, o + 8 + l, 18):
                        fn = b[j + 6:j + 18].decode('latin1').strip('\0 ')
                        if fn and fn != 'SKIPPEDSAMPL':
                            out.append(fn)
            s._ksf[i] = out
        return s._ksf[i]

    def ksf_folder(s, i):
        return os.path.join(s.folder, s.base, os.path.splitext(s.idx[i])[0])

    def size(s, i):
        """Cât ocupă multisample-ul i (suma KSF-urilor), în octeți."""
        if i not in s._size:
            tot = 0
            sub = s.ksf_folder(i)
            for f in s.kmp_ksfs(i):
                try:
                    tot += os.path.getsize(os.path.join(sub, f))
                except OSError:
                    pass
            s._size[i] = tot
        return s._size[i]

    def nume_ms(s, i):
        return re.sub(r'[^ -~]', '', s.ms.get(i, '')).strip() or s.idx.get(i, '?')

    def signature(s, i):
        if i not in s._sig:
            sub = s.ksf_folder(i); sig = []
            for f in s.kmp_ksfs(i):
                p = os.path.join(sub, f)
                with open(p, 'rb') as fh:
                    sig.append((fh.read(24)[8:24], os.path.getsize(p)))
            s._sig[i] = (s.ms.get(i, '').strip(), tuple(sig))
        return s._sig[i]

    def semnaturi(s):
        out = {}
        for i in s.idx:
            if not os.path.exists(s.kmp_path(i)):
                continue
            try:
                out.setdefault(s.signature(i), i)
            except OSError:
                pass
        return out


# ----------------------------------------------------------------------------- PCG

class Pcg:
    def __init__(s, path):
        s.path = path
        s.d = bytearray(open(path, 'rb').read())
        s.top = {}; o = 0x1c
        while o + 12 <= len(s.d):
            s.top[bytes(s.d[o:o + 4])] = (o, s.gi(o + 4, 4)); o += 12 + s.gi(o + 4, 4)
        s.pbanks = s._banks(b'PRG1') if b'PRG1' in s.top else []
        s.cbanks = s._banks(b'CMB1') if b'CMB1' in s.top else []

    def gi(s, o, n): return int.from_bytes(s.d[o:o + n], 'big')

    def _banks(s, top):
        o, l = s.top[top]; out = []; c = o + 12
        while c < o + 12 + l:
            cl = s.gi(c + 4, 4)
            out.append(dict(chunk=c, len=cl, start=c + 24, count=s.gi(c + 12, 4), size=s.gi(c + 16, 4)))
            c += 12 + cl
        return out

    def prog(s, bank, i): b = s.pbanks[PB.index(bank)]; return b['start'] + i * b['size'], b['size']
    def combi(s, bank, i): b = s.cbanks[CB.index(bank)]; return b['start'] + i * b['size'], b['size']
    def is_exi_bank(s, bank): return bytes(s.d[s.pbanks[PB.index(bank)]['chunk']:][:4]) == b'MBK1'
    def prog_banks(s): return PB[:len(s.pbanks)]
    def combi_banks(s): return CB[:len(s.cbanks)]
    def count(s, tip, bank):
        L = s.pbanks if tip == 'prog' else s.cbanks
        return L[(PB if tip == 'prog' else CB).index(bank)]['count']

    def fix_checksums(s):
        for b in s.pbanks + s.cbanks:
            s.d[b['chunk'] + 11] = sum(s.d[b['chunk'] + 12:b['chunk'] + 12 + b['len']]) % 256


# ----------------------------------------------------------------------------- setul întreg

class KronosSet:
    def __init__(s, sid):
        s.id = sid
        s.folder, s.base = din_id(sid)
        s.pcg = Pcg(sid)
        s.ss = SampleSet(s.folder, s.base)
        s.U = uuid.UUID(s.ss.uuid).bytes if s.ss.uuid else None
        s._sigs = None

    def semnaturi(s):
        if s._sigs is None:
            s._sigs = s.ss.semnaturi()
        return s._sigs

    def banci(s, tip):
        P = s.pcg
        out = []
        for b in (P.prog_banks() if tip == 'prog' else P.combi_banks()):
            n = 0
            for i in range(P.count(tip, b)):
                p = (P.prog if tip == 'prog' else P.combi)(b, i)[0]
                if pname(P.d, p) not in (INIT_PROG if tip == 'prog' else INIT_COMBI):
                    n += 1
            out.append(dict(banca=b, ocupate=n, exi=(tip == 'prog' and P.is_exi_bank(b))))
        return out

    # --- ce multisample-uri user folosește un program / combi
    def ms_program(s, bank, i, aliases=()):
        P = s.pcg
        p, sz = P.prog(bank, i)
        rec = P.d[p:p + sz]
        mode = rec[OSCMODE] & 7
        ms = set(); note = []
        if mode == 3:
            return ms, note
        if mode in (2, 5):
            note.append('are tobe')
        for osc in range(2):
            for z in range(8):
                o = ZONE0 + osc * OSC_STRIDE + z * ZONE_STRIDE; r = rec[o:o + 22]
                activ = osc == 0 or mode in (1, 5)
                if r[0] == 2 and activ and 'are wave sequence' not in note:
                    note.append('are wave sequence')
                if r[0] != 1:
                    continue
                num = r[18] | (r[19] << 8)
                if (s.U and bytes(r[1:16]) == s.U[:15]) or bytes(r[1:17]) in aliases or (r[1:5] == b'KORG' and r[16] == 2):
                    ms.add(num)
                elif r[1:5] != b'KORG' and activ:
                    if 'cere sample-uri din alt set' not in note:
                        note.append('cere sample-uri din alt set')
        return ms, note

    def progs_combi(s, bank, i):
        P = s.pcg
        c, sz = P.combi(bank, i)
        out = []
        for t in range(16):
            to = c + TIMBRES + t * TIMBRE_SIZE
            st = (P.d[to + 2] >> 5) & 7
            if st in (1, 2):
                pb = ID_PB.get(P.d[to + 1])
                if pb:
                    out.append((pb, P.d[to]))
        return out

    def ms_element(s, tip, bank, i):
        if tip == 'prog':
            return s.ms_program(bank, i)
        ms = set(); note = []
        for pb, pi in s.progs_combi(bank, i):
            m, n = s.ms_program(pb, pi)
            ms |= m
            for x in n:
                if x not in note:
                    note.append(x)
        return ms, note

    def nume(s, tip, bank, i):
        P = s.pcg
        return pname(P.d, (P.prog if tip == 'prog' else P.combi)(bank, i)[0])


def cost_in_tinta(src, ms, tinta):
    """Octeții pe care i-ar adăuga multisample-urile `ms` în setul țintă (cele care nu sunt deja acolo)."""
    tot = 0
    sigs = tinta.semnaturi() if tinta else {}
    for m in ms:
        if not src.ss.has(m):
            continue
        if tinta is not None:
            try:
                if src.ss.signature(m) in sigs:
                    continue
            except OSError:
                pass
        tot += src.ss.size(m)
    return tot


def lista_elemente(src, tinta, tip, bank):
    P = src.pcg
    out = []
    for i in range(P.count(tip, bank)):
        nm = src.nume(tip, bank, i)
        if nm in (INIT_PROG if tip == 'prog' else INIT_COMBI):
            continue
        ms, note = src.ms_element(tip, bank, i)
        el = dict(tip=tip, banca=bank, nr=i, nume=nm, note=note,
                  cost=cost_in_tinta(src, ms, tinta), singur=sum(src.ss.size(m) for m in ms if src.ss.has(m)))
        if tip == 'prog':
            el['exi'] = (P.d[P.prog(bank, i)[0] + OSCMODE] & 7) == 3
        out.append(el)
    return out


def rezumat_cost(src, tinta, elemente):
    """Costul fiecărui element bifat, totalul împreună și ce împart între ele."""
    per = []
    toate = set()
    for e in elemente:
        ms, note = src.ms_element(e['tip'], e['banca'], e['nr'])
        per.append((e, ms))
        toate |= ms
    linii = []
    for k, (e, ms) in enumerate(per):
        cu = []
        for j, (e2, ms2) in enumerate(per):
            if j != k and ms & ms2:
                cu.append('%s %03d %s' % (e2['banca'], e2['nr'], src.nume(e2['tip'], e2['banca'], e2['nr'])))
        linii.append(dict(eticheta='%s %03d %s' % (e['banca'], e['nr'], src.nume(e['tip'], e['banca'], e['nr'])),
                          cost=cost_in_tinta(src, ms, tinta), imparte=cu))
    separat = sum(l['cost'] for l in linii)
    impreuna = cost_in_tinta(src, toate, tinta)
    return dict(linii=linii, separat=separat, impreuna=impreuna)


# ----------------------------------------------------------------------------- copiere cu procent

def copiaza_folder(src, dst, progres=None):
    fisiere = []
    tot = 0
    for cale, dirs, files in os.walk(src):
        for f in files:
            p = os.path.join(cale, f); n = os.path.getsize(p); fisiere.append((p, n)); tot += n
    facut = 0
    for p, n in fisiere:
        q = os.path.join(dst, os.path.relpath(p, src))
        os.makedirs(os.path.dirname(q), exist_ok=True)
        shutil.copy2(p, q)
        facut += n
        if progres and tot:
            progres(facut * 100 // tot)
    os.makedirs(dst, exist_ok=True)


# ----------------------------------------------------------------------------- transferul

class Transfer:
    """opt: banca_prog, banca_combi, banca_timbre (listă), sw_octava, in_loc (bool), folder_nou."""

    def __init__(t, src_id, dst_id, opt, progres=None):
        t.opt = opt
        t.progres = progres or (lambda p, m=None: None)
        t.log = []
        t.src_id, t.dst_id = src_id, dst_id
        sdir, sbase = din_id(src_id)
        ddir, dbase = din_id(dst_id)
        t.dbase = dbase
        if opt.get('in_loc'):
            t.out = ddir
        else:
            t.out = opt['folder_nou']
            if os.path.exists(t.out):
                raise ValueError('Folderul %s există deja. Alege alt nume.' % t.out)
            t.progres(0, 'Copiez setul țintă în setul nou')
            copiaza_folder(ddir, t.out, lambda p: t.progres(p * 8 // 10, None))
        t.src = SampleSet(sdir, sbase)
        t.dst = SampleSet(t.out, dbase)
        t.S = Pcg(src_id)
        t.D = Pcg(os.path.join(t.out, dbase + '.PCG'))
        t.SU = uuid.UUID(t.src.uuid).bytes
        t.DU = uuid.UUID(t.dst.uuid).bytes
        t.aliases = set()
        t.ms_map = {}
        t.new_kmp, t.new_ms, t.new_ds = [], [], []
        t.next_ds = (max(t.dst.ds) + 1) if t.dst.ds else 0
        t.next_ms = t.dst.next_index()
        t.progres(82, 'Compar sample-urile')
        t.dst_sigs = t.dst.semnaturi()
        t.placed = {}
        t.taken = set()
        t.adus = 0
        t.scrise = []        # (tip, banca, nr) scrise în țintă
        t.used_by_combi = set()
        D = t.D
        for cb in D.combi_banks():
            for ci in range(D.count('combi', cb)):
                cp, csz = D.combi(cb, ci)
                if pname(D.d, cp) in INIT_COMBI:
                    continue
                for k in range(16):
                    o = cp + TIMBRES + k * TIMBRE_SIZE
                    if D.d[o + 1] in ID_PB:
                        t.used_by_combi.add((ID_PB[D.d[o + 1]], D.d[o]))

    # --- locuri libere
    def is_free(t, bank, i):
        p, sz = t.D.prog(bank, i)
        return ((bank, i) not in t.taken and (bank, i) not in t.used_by_combi
                and pname(t.D.d, p) in INIT_PROG)

    def combi_free(t, bank, i):
        return ('C', bank, i) not in t.taken and pname(t.D.d, t.D.combi(bank, i)[0]) in INIT_COMBI

    @staticmethod
    def _urmatorul(n, liber):
        """Următoarea poziție liberă după ultima ocupată (continuitate); altfel prima liberă."""
        ultima = -1
        for i in range(n):
            if not liber(i):
                ultima = i
        for i in range(ultima + 1, n):
            if liber(i):
                return i
        for i in range(n):
            if liber(i):
                return i
        return None

    def loc_program(t, banci, exi):
        D = t.D
        cand = [b for b in banci if b in D.prog_banks() and D.is_exi_bank(b) == exi]
        if exi:
            cand += [b for b in (['U-B'] + D.prog_banks()) if b in D.prog_banks() and D.is_exi_bank(b) and b not in cand]
        else:
            cand += [b for b in D.prog_banks() if b.startswith('U-') and not D.is_exi_bank(b) and b not in cand]
        for b in cand:
            i = t._urmatorul(D.count('prog', b), lambda k, b=b: t.is_free(b, k))
            if i is not None:
                return b, i
        raise ValueError('Nu mai e niciun loc liber pentru program (%s).' % ('EXi' if exi else 'HD-1'))

    # --- multisample-uri
    def need_ms(t, si):
        src, dst = t.src, t.dst
        if si in t.ms_map:
            return t.ms_map[si]
        if not src.has(si):
            t.log.append('    Atenție: multisample-ul %d nu există în setul sursă, nu poate fi adus.' % si); return None
        if not os.path.exists(src.kmp_path(si)):
            t.log.append('    Atenție: lipsește fișierul %s din setul sursă; zona rămâne neschimbată.' % src.idx[si])
            t.ms_map[si] = None; return None
        sig = src.signature(si)
        if not sig[1]:
            empty = [i for s2, i in t.dst_sigs.items() if not s2[1]]
            if empty:
                t.ms_map[si] = empty[0]; return empty[0]
        if sig in t.dst_sigs:
            t.ms_map[si] = t.dst_sigs[sig]
            t.log.append('    multisample-ul "%s" există deja în țintă, nu l-am mai copiat.' % src.nume_ms(si))
            return t.ms_map[si]
        di = t.next_ms; t.next_ms += 1
        stem = os.path.splitext(src.idx[si])[0]
        pref = stem[:5]
        newstem = pref + '%03d' % di
        k = 0
        while (os.path.exists(os.path.join(t.out, t.dbase, newstem + '.KMP')) or
               os.path.exists(os.path.join(t.out, t.dbase, newstem))):
            k += 1; newstem = ('N%d' % k + pref)[:5] + '%03d' % di
        sfold = src.ksf_folder(si); dfold = os.path.join(t.out, t.dbase, newstem)
        os.makedirs(dfold, exist_ok=True)
        ksfs = src.kmp_ksfs(si)
        for f in ksfs:
            b = bytearray(open(os.path.join(sfold, f), 'rb').read()); old = None
            for n, o, l in kchunks(b):
                if n == b'SNO1':
                    old = int.from_bytes(b[o + 8:o + 12], 'big'); b[o + 8:o + 12] = t.next_ds.to_bytes(4, 'big')
            open(os.path.join(dfold, f), 'wb').write(b)
            t.adus += len(b)
            t.new_ds.append('#>>uuid:%s.DS%d.1.0.%s' % (dst.uuid, t.next_ds, src.ds.get(old, b[8:24].decode('latin1'))))
            t.next_ds += 1
        kb = bytearray(open(src.kmp_path(si), 'rb').read())
        for n, o, l in kchunks(kb):
            if n == b'MNO1':
                kb[o + 8:o + 12] = di.to_bytes(4, 'big')
        open(os.path.join(t.out, t.dbase, newstem + '.KMP'), 'wb').write(kb)
        t.new_kmp.append(newstem + '.KMP')
        t.new_ms.append('#>>uuid:%s.MS%d.1.0.%s' % (dst.uuid, di, src.ms.get(si, sig[0])))
        t.ms_map[si] = di
        t.log.append('    multisample-ul "%s" copiat (%d sample-uri, %s).' % (src.nume_ms(si), len(ksfs), mb(src.size(si))))
        return di

    # --- program
    def pregateste_program(t, sb, si):
        S = t.S
        ps, sz = S.prog(sb, si)
        rec = bytearray(S.d[ps:ps + sz]); exi = (rec[OSCMODE] & 7) == 3
        if not exi:
            mode = rec[OSCMODE] & 7
            if mode in (2, 5):
                t.log.append('    Atenție: e program de tobe; drum kit-ul nu se aduce automat.')
            for osc in range(2):
                for z in range(8):
                    o = ZONE0 + osc * OSC_STRIDE + z * ZONE_STRIDE; r = rec[o:o + 22]
                    if r[0] == 2 and (osc == 0 or mode in (1, 5)):
                        t.log.append('    Atenție: oscilatorul %d zona %d folosește wave sequence; nu se aduce automat.' % (osc + 1, z + 1))
                    if r[0] != 1:
                        continue
                    num = r[18] | (r[19] << 8)
                    if bytes(r[1:16]) == t.SU[:15]:
                        if bytes(r[1:17]) != t.SU and not t.aliases:
                            t.aliases.add(bytes(r[1:17]))
                            t.log.append('    (cere setul înrudit %s; îl tratez ca pe setul sursă, după același număr, cum a mers la Ramon)' % uuid.UUID(bytes=bytes(r[1:17])))
                        n2 = t.need_ms(num)
                        if n2 is None:
                            continue
                        rec[o + 1:o + 17] = t.DU; rec[o + 18] = n2 & 0xff; rec[o + 19] = n2 >> 8
                    elif r[1:5] == b'KORG' and r[16] == 2:
                        n2 = t.need_ms(num)
                        if n2 is None:
                            continue
                        rec[o + 1:o + 17] = t.DU; rec[o + 17] = 0; rec[o + 18] = n2 & 0xff; rec[o + 19] = n2 >> 8
                    elif r[1:5] != b'KORG':
                        t.log.append('    Atenție: oscilatorul %d zona %d cere sample-uri din alt set, care lipsesc.' % (osc + 1, z + 1))
        if t.opt.get('sw_octava'):
            rec[P_SW1] = 3; rec[P_SW1 + 1] = 4
        return rec, exi

    def exista_identic(t, rec, exi):
        D = t.D
        for b2 in D.prog_banks():
            if D.is_exi_bank(b2) != exi:
                continue
            for j in range(D.count('prog', b2)):
                q, sz = D.prog(b2, j)
                if D.d[q:q + sz] == rec:
                    return b2, j
        return None

    def copy_program(t, sb, si, banci, motiv):
        if (sb, si) in t.placed:
            return t.placed[(sb, si)]
        nm = pname(t.S.d, t.S.prog(sb, si)[0])
        t.log.append('%s %s %03d "%s":' % (motiv, sb, si, nm))
        rec, exi = t.pregateste_program(sb, si)
        same = t.exista_identic(rec, exi)
        if same:
            t.log.append('    există deja identic în țintă pe %s %03d, îl folosesc pe acela.' % same)
            t.placed[(sb, si)] = same
            return same
        db, di = t.loc_program(banci, exi)
        pd, sz = t.D.prog(db, di); t.D.d[pd:pd + sz] = rec
        t.placed[(sb, si)] = (db, di); t.taken.add((db, di))
        t.scrise.append(('prog', db, di))
        t.log.append('    pus pe %s %03d%s.' % (db, di, ' (EXi)' if exi else ''))
        return db, di

    def copy_combi(t, sb, si):
        S, D = t.S, t.D
        cs, sz = S.combi(sb, si); rec = bytearray(S.d[cs:cs + sz])
        t.log.append('Combi %s %03d "%s":' % (sb, si, pname(rec, 0)))
        for k in range(16):
            to = TIMBRES + k * TIMBRE_SIZE
            st = (rec[to + 2] >> 5) & 7
            if st not in (1, 2):
                continue
            pb, pi = ID_PB.get(rec[to + 1]), rec[to]
            if pb is None:
                continue
            nb, ni = t.copy_program(pb, pi, t.opt.get('banca_timbre') or BANCI_TIMBRE, '  timbrul %d folosește programul' % (k + 1))
            rec[to + 1] = PB_ID[nb]; rec[to] = ni
        if t.opt.get('sw_octava'):
            rec[C_SW1] = 3; rec[C_SW1 + 1] = 4
        db = t.opt.get('banca_combi', 'U-A')
        banci = [db] + [b for b in D.combi_banks() if b.startswith('U-') and b != db]
        for b in banci:
            di = t._urmatorul(D.count('combi', b), lambda k, b=b: t.combi_free(b, k))
            if di is not None:
                break
        else:
            raise ValueError('Nu mai e niciun loc liber pentru combi.')
        t.taken.add(('C', b, di))
        dc, _ = D.combi(b, di); D.d[dc:dc + sz] = rec
        t.scrise.append(('combi', b, di))
        t.log.append('  combi-ul pus pe %s %03d.' % (b, di))

    # --- scrierea
    def scrie(t):
        D = t.D
        D.fix_checksums()
        open(os.path.join(t.out, t.dbase + '.PCG'), 'wb').write(D.d)
        if t.new_kmp:
            dst = t.dst
            K = dst.ksc[:]
            li = max(i for i, l in enumerate(K) if l and not l.startswith('#') and l.upper().endswith('.KMP'))
            K[li + 1:li + 1] = t.new_kmp
            us = [i for i, l in enumerate(K) if l.startswith('#>User.')]
            ui = us[-1] if us else li + len(t.new_kmp)
            K[ui + 1:ui + 1] = ['#>User.0.2.' + k for k in t.new_kmp]
            wr_lines(os.path.join(t.out, t.dbase + '.KSC'), K)
            B = dst.ub[:] or ['#KORG Script Version 1.0', '#v2']
            ms_l = [i for i, l in enumerate(B) if re.match(r'#>>uuid:.*\.MS\d+\.', l)]
            mi = ms_l[-1] if ms_l else len(B) - 1
            B[mi + 1:mi + 1] = t.new_ms
            dl = [i for i, l in enumerate(B) if re.match(r'#>>uuid:.*\.DS\d+\.', l)]
            pos = (dl[-1] + 1) if dl else mi + 1 + len(t.new_ms)
            B[pos:pos] = t.new_ds
            for i, l in enumerate(B):
                m = re.match(r'#>uuid:([0-9a-f-]+)\.(\d+)\.(\d+)\.(.*)', l)
                if m:
                    B[i] = '#>uuid:%s.%d.%d.%s' % (m.group(1), t.next_ms, t.next_ds, m.group(4))
            wr_lines(os.path.join(t.out, t.dbase + '_UserBank.KSC'), B)

    def verifica(t):
        """Recitește setul scris: fiecare zonă user a programelor puse trebuie să ducă la același sample ca la sursă."""
        dst2 = SampleSet(t.out, t.dbase)
        D2 = Pcg(os.path.join(t.out, t.dbase + '.PCG'))
        rau = 0
        inv = {v: k for k, v in t.placed.items()}
        for (b, i), (sb, si) in inv.items():
            p, sz = D2.prog(b, i); rec = D2.d[p:p + sz]
            sp, _ = t.S.prog(sb, si); srec = t.S.d[sp:sp + sz]
            if (rec[OSCMODE] & 7) == 3:
                continue
            for osc in range(2):
                for z in range(8):
                    o = ZONE0 + osc * OSC_STRIDE + z * ZONE_STRIDE
                    if rec[o] != 1 or bytes(rec[o + 1:o + 17]) != t.DU:
                        continue
                    n = rec[o + 18] | (rec[o + 19] << 8)
                    ns = srec[o + 18] | (srec[o + 19] << 8)
                    try:
                        ok = dst2.has(n) and t.src.has(ns) and dst2.signature(n)[1] == t.src.signature(ns)[1]
                    except OSError:
                        ok = False
                    if not ok:
                        rau += 1
                        t.log.append('Problemă: %s %03d oscilatorul %d zona %d nu duce la sample-ul corect.' % (b, i, osc + 1, z + 1))
        return rau

    def ruleaza(t, elemente):
        try:
            return t._ruleaza(elemente)
        except Exception:
            if not t.opt.get('in_loc'):
                shutil.rmtree(t.out, ignore_errors=True)
            else:
                for k in t.new_kmp:
                    try:
                        os.remove(os.path.join(t.out, t.dbase, k))
                        shutil.rmtree(os.path.join(t.out, t.dbase, os.path.splitext(k)[0]), ignore_errors=True)
                    except OSError:
                        pass
            raise

    def _ruleaza(t, elemente):
        n = len(elemente)
        for k, e in enumerate(elemente):
            t.progres(85 + k * 10 // max(n, 1), None)
            if e['tip'] == 'prog':
                t.copy_program(e['banca'], e['nr'], [t.opt.get('banca_prog', 'U-A')], 'Program')
            else:
                t.copy_combi(e['banca'], e['nr'])
        t.progres(96, 'Scriu setul')
        t.scrie()
        t.progres(98, 'Verific')
        rau = t.verifica()
        t.log.append('')
        t.log.append('Sample-uri aduse: %s.' % mb(t.adus))
        t.log.append('Verificare: ' + ('toate zonele duc la sample-urile corecte.' if not rau else '%d probleme.' % rau))
        if t.opt.get('sw_octava') and t.scrise:
            t.log.append('SW1 și SW2 sunt puse pe octavă la tot ce am adus.')
        t.log.append('Setul este în: ' + t.out)
        return t.log
