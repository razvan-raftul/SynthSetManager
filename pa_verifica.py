"""pa_verifica – verifică un set de Pa3X înainte să fie încărcat pe claviatură.

Folosire:  python pa_verifica.py "Setul.SET"
Verifică: că toate fișierele se citesc și se despachetează (suma de control OC31), că zonele și
sample-urile de tobe arată spre sample-uri care există, că fiecare sample din RAM.KMP își are datele
în PCM (același ID), mărimea totală (256 MB), și ce
referințe la sunete și pad-uri user duc spre locuri goale.
"""
import os
import sys
from collections import defaultdict
import pa_lib as pl


def verifica(cale):
    s = pl.Set(cale)
    R = []
    erori = 0
    w = R.append
    w(f'Verificare: {s.nume}')
    # 1. fișierele
    for folder, ext in (('SOUND', '.PCG'), ('PERFORM', '.PRF'), ('STYLE', '.STY'), ('PAD', '.PAD'), ('MULTISMP', '.KMP')):
        for fn in s.lista(folder, ext):
            try:
                for e in s.fisier(f'{folder}/{fn}').intrari:
                    e.date()
            except Exception as ex:
                erori += 1
                w(f'EROARE în {folder}/{fn}: {ex}')
    k = s.kmp
    pcm = s.pcm()
    # 2. KMP intern
    for i, m in enumerate(k.M):
        for zi in k.m_zone(m):
            if zi >= len(k.Z):
                erori += 1; w(f'EROARE: multisample-ul {k.m_nume(m)} arată spre o zonă care nu există')
                break
            r = k.z_sample(k.Z[zi])
            if r and r[1] and r[0] >= len(k.S):
                erori += 1; w(f'EROARE: multisample-ul {k.m_nume(m)} arată spre un sample care nu există')
                break
    for x in k.D:
        for v in k.d_samples(x):
            if v >= len(k.S):
                erori += 1; w(f'EROARE: sample-ul de tobe {k.d_nume(x)} arată spre un sample care nu există')
                break
    # 3. date PCM
    fara = []
    for i, x in enumerate(k.S):
        v = pcm.get(k.s_pcm(x))
        if v is None or v[2] != k.s_id(x):
            fara.append(i)
    if fara:
        erori += 1
        w(f'EROARE: {len(fara)} sample-uri din RAM.KMP nu au datele în fișierele PCM ({pl.mb(0)} recuperabili).'.replace(f' ({pl.mb(0)} recuperabili)', ''))
        mid, did = s.indexuri()
        fs = set(fara)
        for fn, e in s.sunete():
            ms, dr = s.ref_sunet(e, mid, did)
            sm = s.samples_sunet(ms, dr)
            n = len(sm & fs)
            if n:
                w(f'   afectat: {fn} {e.slot + 1} {e.nume}, îi lipsesc {n} din {len(sm)} sample-uri')
    ids_kmp = set(k.s_id(x) for x in k.S)
    orfane = [v for v in pcm.values() if v[2] not in ids_kmp]
    if orfane:
        w(f'De curățat: {len(orfane)} sample-uri în PCM pe care RAM.KMP nu le folosește, {pl.mb(sum(v[1] for v in orfane))}.')
    tot = s.marime_pcm()
    w(f'Sample-uri: {len(k.S)}, {pl.mb(tot)} din 256 MB.')
    if tot > pl.MAX_RAM:
        erori += 1; w('EROARE: setul trece de 256 MB.')
    # 5. referințe goale
    are = {(fn, e.slot) for fn, e in s.sunete()}
    pads = {(pl.banca_pad(fn[:-4]), e.slot) for fn in s.lista('PAD', '.PAD') for e in s.fisier('PAD/' + fn).intrari}
    lipsa = defaultdict(set)
    for folder, ext in (('PERFORM', '.PRF'), ('STYLE', '.STY'), ('PAD', '.PAD')):
        for fn in s.lista(folder, ext):
            for e in s.fisier(f'{folder}/{fn}').intrari:
                d = e.date()
                for off, msb, lsb, pc in pl.refs_sunete(d):
                    b = pl.DUPA_MSB_LSB[(msb, lsb)]
                    if (b, pc) not in are:
                        lipsa[f'{b} {pc + 1}'].add(f'{fn[:-4]} {e.slot + 1}')
                for off, b, sl in pl.refs_paduri(d):
                    if 0x14 <= b <= 0x1d and (b, sl) not in pads:
                        lipsa[f'pad USER{b - 0x13:02d} {sl + 1}'].add(f'{fn[:-4]} {e.slot + 1}')
    if lipsa:
        w(f'Locuri goale folosite de performance-uri, style-uri sau pad-uri: {len(lipsa)} (sună cu ce e pe claviatură în locul acela sau deloc).')
    w('Rezultat: ' + ('fără erori.' if not erori else f'{erori} probleme.'))
    return R, erori, lipsa


if __name__ == '__main__':
    R, erori, lipsa = verifica(sys.argv[1])
    print('\n'.join(R))
    if '--detalii' in sys.argv:
        for k2 in sorted(lipsa):
            print(f'  {k2} folosit de: ' + ', '.join(sorted(lipsa[k2])))
