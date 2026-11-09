"""pa_curatenie – face un set NOU, curățat: scoate sunetele cerute (dacă sunt) și apoi tot ce nu mai
folosește niciun sunet (multisample-uri, sample-uri de tobe, zone, sample-uri și datele lor din PCM).

Folosire:
  python pa_curatenie.py SET.SET NOU.SET [scoate:USER01:5 ...]
Setul vechi rămâne neatins. Sample-urile rămase își păstrează fișierul PCM, dar locurile din fiecare
fișier se renumerotează în ordine (0, 1, 2...), ca la seturile salvate de claviatură.
"""
import os
import shutil
import struct
import sys
import pa_lib as pl


def curata(cale, nou, scoate=()):
    if os.path.exists(nou):
        raise SystemExit(f'{nou} există deja.')
    shutil.copytree(cale, nou)
    s = pl.Set(nou)
    J = []
    for t in scoate:
        _, b, n = t.split(':')
        b = b.upper(); sl = int(n) - 1
        rel = f'SOUND/{b}.PCG'
        F = s.fisier(rel)
        e = F.dupa_slot(sl) if F else None
        if e is None:
            J.append(f'Nu există sunet la {b} {sl + 1}.')
            continue
        F.intrari.remove(e)
        s.modificate.add(rel)
        J.append(f'Scos sunetul {b} {sl + 1} {e.nume}.')
    k = s.kmp
    ms_fol, dr_fol = set(), set()
    for fn, e in s.sunete():
        ms, dr = s.ref_sunet_toate(e)
        ms_fol.update(ms); dr_fol.update(dr)
    # ce sample-uri rămân
    s_fol = set()
    for mi in ms_fol:
        s_fol.update(k.samples_ms(mi))
    for di in dr_fol:
        s_fol.update(k.d_samples(k.D[di]))
    inainte = s.marime_pcm()
    # PCM: scoatem ce nu mai trebuie și renumerotăm locurile
    pcm = s.pcm()
    pastrez = {}
    for si in sorted(s_fol):
        key = k.s_pcm(k.S[si])
        v = pcm.get(key)
        if v and v[2] == k.s_id(k.S[si]):
            pastrez[key] = True
    loc_nou = {}
    for fn in s.lista('PCM', '.PCM'):
        f = int(fn[3:5]) - 1
        rel = 'PCM/' + fn
        F = s.fisier(rel)
        vechi = list(F.intrari)
        F.intrari = []
        for e in sorted(vechi, key=lambda x: x.slot):
            if (f, e.slot) in pastrez:
                loc_nou[(f, e.slot)] = (f, len(F.intrari))
                e.slot = len(F.intrari)
                F.intrari.append(e)
        if [ (x.slot, x.nume) for x in F.intrari] != [(x.slot, x.nume) for x in vechi]:
            s.modificate.add(rel)
    # KMP nou
    harta_s = {}
    S2 = []
    for si in sorted(s_fol):
        x = bytearray(k.S[si])
        key = k.s_pcm(x)
        if key in loc_nou:
            x[92], x[93] = loc_nou[key]
        harta_s[si] = len(S2)
        S2.append(x)
    Z2, M2 = [], []
    for mi in sorted(ms_fol):
        m = bytearray(k.M[mi])
        prima = len(Z2)
        for zi in k.m_zone(m):
            z = bytearray(k.Z[zi])
            r = k.z_sample(z)
            if r and r[1]:
                z[0:2] = struct.pack('>H', harta_s[r[0]])
            Z2.append(z)
        m[26:28] = struct.pack('>H', prima)
        M2.append(m)
    D2 = []
    for di in sorted(dr_fol):
        x = bytearray(k.D[di])
        for j in range(4):
            v = struct.unpack('>H', x[2 * j:2 * j + 2])[0]
            if v != 0xffff:
                x[2 * j:2 * j + 2] = struct.pack('>H', harta_s[v])
        D2.append(x)
    J.append(f'Multisample-uri: {len(k.M)} -> {len(M2)}; sample-uri de tobe: {len(k.D)} -> {len(D2)}; sample-uri: {len(k.S)} -> {len(S2)}.')
    k.S, k.Z, k.M, k.D = S2, Z2, M2, D2
    s.modificate.add('MULTISMP/RAM.KMP')
    s._pcm = None
    dupa = sum(len(e.chunk) for fn in s.lista('PCM', '.PCM') for e in s.fisier('PCM/' + fn).intrari)
    J.append(f'Sample-uri în RAM: {pl.mb(inainte)} -> {pl.mb(dupa)}, eliberat {pl.mb(inainte - dupa)}.')
    s.salveaza()
    return J


if __name__ == '__main__':
    a = sys.argv[1:]
    print('\n'.join(curata(a[0], a[1], a[2:])))
