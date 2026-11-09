"""pa_analiza – raport despre un set de Pa3X: ce sunete are, cât ocupă fiecare (MB), ce sample-uri
împart, ce nu folosește nimeni, ce performance-uri, style-uri și pad-uri folosesc ce sunete.

Folosire:  python pa_analiza.py "cale\\catre\\Setul.SET" [raport.txt]
Raportul e text simplu, un rând pe element, bun de citit cu NVDA.
"""
import os
import sys
from collections import defaultdict
import pa_lib as pl


def analiza(cale):
    s = pl.Set(cale)
    k = s.kmp
    pcm = s.pcm()
    mid, did = s.indexuri()
    R = []
    w = R.append

    tot_pcm = s.marime_pcm()
    w(f'Setul {s.nume}')
    w(f'Sample-uri în RAM: {len(k.S)}, ocupă {pl.mb(tot_pcm)} din 256 MB, liber {pl.mb(max(0, pl.MAX_RAM - tot_pcm))}.')
    w(f'Multisample-uri: {len(k.M)}, sample-uri de tobe: {len(k.D)}.')
    w('')

    # --- sunete și sample-urile lor
    sunete = s.sunete()
    info = []                      # (fișier, intrare, samples)
    folosit_de = defaultdict(set)  # sample -> {indice sunet}
    for i, (fn, e) in enumerate(sunete):
        ms, dr = s.ref_sunet(e, mid, did)
        sm = s.samples_sunet(ms, dr)
        info.append((fn, e, sm, ms, dr))
        for x in sm:
            folosit_de[x].add(i)

    are = {(fn, e.slot): e.nume for fn, e in sunete}
    w(f'Sunete user: {len(sunete)}')
    for fn in sorted(set(fn for fn, e in sunete)):
        n = sum(1 for f2, e in sunete if f2 == fn)
        w(f'  {fn}: {n} sunete')
    w('')
    w('Sunetele, cu mărimea sample-urilor lor (cât ar costa aduse singure într-un set gol):')
    for i, (fn, e, sm, ms, dr) in enumerate(info):
        if not sm:
            w(f'{fn} {e.slot + 1}: {e.nume} – doar sample-uri din ROM, 0 MB')
            continue
        tot = s.marime_samples(sm)
        proprii = s.marime_samples([x for x in sm if folosit_de[x] == {i}])
        cu = sorted(set().union(*(folosit_de[x] for x in sm)) - {i})
        r = f'{fn} {e.slot + 1}: {e.nume} – {pl.mb(tot)}'
        if cu:
            r += f', din care doar ale lui {pl.mb(proprii)}; împarte sample-uri cu: ' + \
                 ', '.join(f'{info[j][0]} {info[j][1].slot + 1} {info[j][1].nume}' for j in cu)
        w(r)
    w('')

    # --- nefolosite
    toate = set(range(len(k.S)))
    nefol = sorted(toate - set(folosit_de))
    w(f'Sample-uri pe care nu le folosește niciun sunet: {len(nefol)}, {pl.mb(s.marime_samples(nefol))}.')
    ms_fol = set()
    dr_fol = set()
    for fn, e, sm, ms, dr in info:
        ms_fol.update(ms); dr_fol.update(dr)
    ms_nefol = [k.m_nume(k.M[i]) for i in range(len(k.M)) if i not in ms_fol]
    if ms_nefol:
        w(f'Multisample-uri nefolosite: {len(ms_nefol)}: ' + ', '.join(ms_nefol))
    w('')

    # --- probleme
    lipsa_pcm = [i for i, x in enumerate(k.S) if k.s_pcm(x) not in pcm or pcm[k.s_pcm(x)][2] != k.s_id(x)]
    if lipsa_pcm:
        w(f'ATENȚIE: {len(lipsa_pcm)} sample-uri din RAM.KMP nu au datele în fișierele PCM.')
        w('')

    # --- cine folosește sunetele
    def nume_ref(msb, lsb, pc):
        fn = pl.DUPA_MSB_LSB[(msb, lsb)]
        n = are.get((fn, pc))
        return f'{fn} {pc + 1} ' + (n if n else '(LIPSEȘTE din set)')

    pad_nume = {}
    for fn in s.lista('PAD', '.PAD'):
        for e in s.fisier('PAD/' + fn).intrari:
            pad_nume[(pl.banca_pad(fn[:-4]), e.slot)] = (fn[:-4], e.nume)

    def rand(titlu, d):
        are_l, lipsa = [], []
        for off, msb, lsb, pc in pl.refs_sunete(d):
            fn = pl.DUPA_MSB_LSB[(msb, lsb)]
            n = are.get((fn, pc))
            x = f'{fn} {pc + 1}' + (f' {n}' if n else '')
            (are_l if n else lipsa).append(x)
        for off, b, sl in pl.refs_paduri(d):
            if 0x14 <= b <= 0x2d:
                p = pad_nume.get((b, sl))
                fnp = ('USER%02d' % (b - 0x13)) if b <= 0x1d else ('LOCAL%02d' % (b - 0x1d))
                x = f'pad {fnp} {sl + 1}' + (f' {p[1]}' if p else '')
                (are_l if p else lipsa).append(x)
        are_l = list(dict.fromkeys(are_l)); lipsa = list(dict.fromkeys(lipsa))
        r = titlu + ': '
        r += ('folosește ' + '; '.join(are_l)) if are_l else 'nu folosește nimic user din set'
        if lipsa:
            r += '. Lipsesc din set: ' + ', '.join(lipsa)
        return r

    w('Performance-uri:')
    for fn in s.lista('PERFORM', '.PRF'):
        f = s.fisier('PERFORM/' + fn)
        for e in sorted(f.intrari, key=lambda x: x.slot):
            w(rand(f'{fn[:-4]} {e.slot + 1} {e.nume}', e.date()))
    w('')
    w('Style-uri (cu setările STS):')
    for fn in s.lista('STYLE', '.STY'):
        f = s.fisier('STYLE/' + fn)
        pe_slot = defaultdict(list)
        for e in f.intrari:
            pe_slot[e.slot].append(e)
        for sl in sorted(pe_slot):
            es = pe_slot[sl]
            nume = next((e.nume for e in es if e.nume), '')
            d = b''.join(e.date() for e in es)
            w(rand(f'{fn[:-4]} {sl + 1} {nume}', d))
    w('')
    w('Pad-uri user:')
    for fn in s.lista('PAD', '.PAD'):
        f = s.fisier('PAD/' + fn)
        for e in sorted(f.intrari, key=lambda x: x.slot):
            w(rand(f'{fn[:-4]} {e.slot + 1} {e.nume}', e.date()))
    return R


if __name__ == '__main__':
    R = analiza(sys.argv[1])
    txt = '\n'.join(R) + '\n'
    if len(sys.argv) > 2:
        open(sys.argv[2], 'w', encoding='utf-8').write(txt)
        print('Raport scris:', sys.argv[2])
    else:
        print(txt)
