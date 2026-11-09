"""Seria Pa (Pa3X): liste, costuri în MB, transfer, raport, verificare și curățenie, peste Pa Tools."""
import os, shutil
import pa_lib as pl
import pa_transfer as pt
import pa_analiza, pa_verifica, pa_curatenie

TIPURI = {
    'sunet': ('SOUND', '.PCG', ['USER01', 'USER02', 'USER03', 'USER04', 'USERDK']),
    'perf': ('PERFORM', '.PRF', ['BANK%02d' % i for i in range(1, 17)]),
    'style': ('STYLE', '.STY', ['FAVORITE%02d' % i for i in range(1, 13)] + ['USER%02d' % i for i in range(1, 4)]),
    'pad': ('PAD', '.PAD', ['USER%02d' % i for i in range(1, 10)]),
}
NUME_TIP = {'sunet': 'sunete', 'perf': 'performance-uri', 'style': 'style-uri', 'pad': 'pad-uri'}


def gaseste_seturi(radacini):
    out, vazute = [], set()
    for r in radacini:
        if not os.path.isdir(r):
            continue
        for cale, dirs, files in os.walk(r):
            adanc = 0 if cale == r else os.path.relpath(cale, r).count(os.sep) + 1
            gasite = [d for d in dirs if d.upper().endswith('.SET')]
            for d in gasite:
                p = os.path.join(cale, d)
                k = os.path.normcase(os.path.abspath(p))
                if k not in vazute:
                    vazute.add(k)
                    out.append(dict(id=p, nume=d[:-4]))
            dirs[:] = [d for d in dirs if not d.upper().endswith('.SET')] if adanc < 1 else []
    out.sort(key=lambda s: s['nume'].lower())
    return out


class Info:
    """Un set citit, cu indexurile de care au nevoie listele și costurile."""

    def __init__(self, cale):
        self.s = pl.Set(cale)
        s = self.s
        k = s.kmp
        self.mid, self.did = s.indexuri()
        pcm = s.pcm()
        self.marime = {}
        self.ids = set()
        for i, x in enumerate(k.S):
            v = pcm.get(k.s_pcm(x))
            self.marime[i] = v[1] if v and v[2] == k.s_id(x) else 0
            self.ids.add(k.s_id(x))
        self.sunete = {(fn, e.slot): e for fn, e in s.sunete()}
        self._sm = {}

    def samples_sunet(self, fn, slot):
        key = (fn, slot)
        if key not in self._sm:
            e = self.sunete.get(key)
            if e is None:
                self._sm[key] = set()
            else:
                ms, dr = self.s.ref_sunet(e, self.mid, self.did)
                self._sm[key] = self.s.samples_sunet(ms, dr)
        return self._sm[key]

    def intrari(self, tip, banca):
        folder, ext, _ = TIPURI[tip]
        f = self.s.fisier('%s/%s%s' % (folder, banca, ext))
        if f is None:
            return []
        if tip == 'style':
            pe = {}
            for e in f.intrari:
                pe.setdefault(e.slot, []).append(e)
            return [(sl, next((e.nume for e in es if e.nume), ''), es) for sl, es in sorted(pe.items())]
        return [(e.slot, e.nume, [e]) for e in sorted(f.intrari, key=lambda x: x.slot)]

    def sunete_folosite(self, tip, banca, slot, adanc=0):
        """Sunetele user (fișier, loc) folosite de un element (cu cele ale pad-urilor lui)."""
        if tip == 'sunet':
            return {(banca, slot)}
        es = next((x[2] for x in self.intrari(tip, banca) if x[0] == slot), [])
        out = set()
        for e in es:
            d = e.date()
            for off, msb, lsb, pc in pl.refs_sunete(d):
                out.add((pl.DUPA_MSB_LSB[(msb, lsb)], pc))
            if adanc == 0:
                for off, b, sl in pl.refs_paduri(d):
                    if 0x14 <= b <= 0x1d:
                        out |= self.sunete_folosite('pad', 'USER%02d' % (b - 0x13), sl, 1)
        return out

    def samples_element(self, tip, banca, slot):
        sm = set()
        for fn, sl in self.sunete_folosite(tip, banca, slot):
            sm |= self.samples_sunet(fn, sl)
        return sm

    def cost(self, samples, tinta):
        k = self.s.kmp
        tot = 0
        for si in samples:
            if tinta is not None and si < len(k.S) and k.s_id(k.S[si]) in tinta.ids:
                continue
            tot += self.marime.get(si, 0)
        return tot


def banci(info, tip):
    folder, ext, toate = TIPURI[tip]
    exist = {f[:-len(ext)].upper() for f in info.s.lista(folder, ext)} if info else set()
    out = []
    for b in toate:
        n = len(info.intrari(tip, b)) if info and b in exist else 0
        out.append(dict(banca=b, ocupate=n))
    return out


def elemente(info, tinta, tip, banca):
    out = []
    for slot, nume, es in info.intrari(tip, banca):
        sm = info.samples_element(tip, banca, slot)
        el = dict(tip=tip, banca=banca, nr=slot, nume=nume, cost=info.cost(sm, tinta), singur=info.cost(sm, None))
        if tip != 'sunet':
            el['sunete'] = len(info.sunete_folosite(tip, banca, slot))
        out.append(el)
    return out


def rezumat_cost(info, tinta, alese):
    per = []
    toate = set()
    for e in alese:
        sm = info.samples_element(e['tip'], e['banca'], e['nr'])
        per.append((e, sm)); toate |= sm
    nume = {}
    for e in alese:
        nume[(e['tip'], e['banca'], e['nr'])] = next((x[1] for x in info.intrari(e['tip'], e['banca']) if x[0] == e['nr']), '')
    linii = []
    for k, (e, sm) in enumerate(per):
        cu = ['%s %d %s' % (e2['banca'], e2['nr'] + 1, nume[(e2['tip'], e2['banca'], e2['nr'])])
              for j, (e2, sm2) in enumerate(per) if j != k and sm & sm2]
        linii.append(dict(eticheta='%s %d %s' % (e['banca'], e['nr'] + 1, nume[(e['tip'], e['banca'], e['nr'])]),
                          cost=info.cost(sm, tinta), imparte=cu))
    return dict(linii=linii, separat=sum(l['cost'] for l in linii), impreuna=info.cost(toate, tinta))


def _sabloane(src, dst):
    """Pentru un set țintă gol: antetele fișierelor se iau din sursă."""
    for folder in ('SOUND', 'PERFORM', 'STYLE', 'PAD', 'PCM', 'MULTISMP'):
        ext = {'SOUND': '.PCG', 'PERFORM': '.PRF', 'STYLE': '.STY', 'PAD': '.PAD', 'PCM': '.PCM', 'MULTISMP': '.KMP'}[folder]
        L = src.lista(folder, ext)
        if L:
            f = src.fisier('%s/%s' % (folder, L[0]))
            dst.sabloane_korf[folder] = f.korf
    f = src.fisier('MULTISMP/RAM.KMP')
    if f and f.intrari:
        e = f.intrari[0]
        dst.sablon_kmp = (e.tip, e.banca, e.slot, e.ver, e.chunk_tip, f.korf)


def transfer(sursa, tinta, alese, opt, progres):
    """opt: in_loc, nou (cale), gol (țintă goală), peste, cu_sunete, banca (dict tip -> bancă sau '')."""
    if opt.get('in_loc'):
        cale = tinta
    else:
        cale = opt['nou']
        if os.path.exists(cale):
            raise ValueError('Setul %s există deja. Alege alt nume.' % os.path.basename(cale))
        if opt.get('gol'):
            os.makedirs(cale)
        else:
            progres(0, 'Copiez setul țintă în setul nou')
            from kronos_lib import copiaza_folder
            copiaza_folder(tinta, cale, lambda p: progres(p * 6 // 10, None))
    try:
        return _transfer(sursa, cale, alese, opt, progres)
    except Exception:
        if not opt.get('in_loc') and os.path.isdir(cale):
            shutil.rmtree(cale, ignore_errors=True)
        raise


def _transfer(sursa, cale, alese, opt, progres):
    progres(62, 'Citesc seturile')
    src = pl.Set(sursa)
    dst = pl.Set(cale)
    if opt.get('gol'):
        _sabloane(src, dst)
    tr = pt.Transfer(src, dst, peste=opt.get('peste', False), cu_sunete=opt.get('cu_sunete', True))
    n = len(alese)
    for k, e in enumerate(alese):
        progres(65 + k * 25 // max(n, 1), None)
        b = (opt.get('banca') or {}).get(e['tip']) or ''
        la = (b, None) if b else None
        if e['tip'] == 'sunet':
            tr.sunet(e['banca'], e['nr'], la)
        elif e['tip'] == 'perf':
            tr.perf(e['banca'], e['nr'], la)
        elif e['tip'] == 'style':
            tr.style(e['banca'], e['nr'], la)
        elif e['tip'] == 'pad':
            tr.pad(e['banca'], e['nr'], la)
    tr.gata()
    progres(92, 'Scriu setul')
    dst.salveaza()
    progres(96, 'Verific setul')
    R, erori, lipsa = pa_verifica.verifica(cale)
    J = list(tr.jurnal)
    J.append('')
    J.extend(R)
    J.append('Setul este în: ' + cale)
    return J


def raport(cale):
    return pa_analiza.analiza(cale)


def verifica(cale):
    R, erori, lipsa = pa_verifica.verifica(cale)
    for k in sorted(lipsa):
        R.append('%s folosit de: %s' % (k, ', '.join(sorted(lipsa[k]))))
    return R


def curatenie(cale, alese, opt, progres):
    scoate = ['scoate:%s:%d' % (e['banca'], e['nr'] + 1) for e in alese if e['tip'] == 'sunet']
    if opt.get('in_loc'):
        tmp = cale.rstrip('\\/') + '.tmp-curatenie'
        if os.path.exists(tmp):
            shutil.rmtree(tmp)
        progres(10, 'Curăț')
        J = pa_curatenie.curata(cale, tmp, scoate)
        # copiem înapoi doar fișierele schimbate (curata scrie în tmp toată structura)
        progres(80, 'Scriu în set')
        for folder in ('SOUND', 'PCM', 'MULTISMP'):
            a = os.path.join(tmp, folder)
            if not os.path.isdir(a):
                continue
            for f in os.listdir(a):
                shutil.copy2(os.path.join(a, f), os.path.join(cale, folder, f))
        shutil.rmtree(tmp)
        dest = cale
    else:
        dest = opt['nou']
        progres(10, 'Copiez și curăț')
        J = pa_curatenie.curata(cale, dest, scoate)
    progres(95, 'Verific')
    R, erori, lipsa = pa_verifica.verifica(dest)
    return J + [''] + R + ['Setul este în: ' + dest]
