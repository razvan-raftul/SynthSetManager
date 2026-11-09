"""pa_transfer – mută sunete, performance-uri, style-uri și pad-uri dintr-un set de Pa3X în altul,
cu tot cu multisample-uri, sample-uri de tobe și sample-urile din PCM.

Setul sursă și setul țintă nu se ating: rezultatul e un set NOU (copie a țintei + ce s-a adus).

Folosire:
  python pa_transfer.py SURSA.SET TINTA.SET NOU.SET  element [element ...]
element:
  sunet:USER02:7            sunetul din USER02, locul 7 (numerotat de la 1, ca pe claviatură)
  sunet:USER02:7=USER03:5   îl pune în USER03 locul 5 (altfel: același loc dacă e liber, sau primul liber)
  perf:BANK01:12[=BANK16:3] performance-ul cu sunetele și pad-urile user pe care le folosește
  style:FAVORITE01:3[=FAVORITE02:1]   style-ul (cu STS) cu sunetele și pad-urile lui
  pad:USER01:2[=USER05:1]   pad-ul cu sunetele lui
Opțiuni: --peste (scrie peste un loc ocupat), --fara-sunete (la perf/style/pad nu aduce sunetele user).
"""
import os
import shutil
import struct
import sys
import pa_lib as pl

LOCURI = {'sunet': 128, 'perf': 40, 'style': 64, 'pad': 64}


class Transfer:
    def __init__(self, src, dst, peste=False, cu_sunete=True):
        self.src, self.dst = src, dst
        self.peste = peste
        self.cu_sunete = cu_sunete
        self.jurnal = []
        self.adus_mb = 0
        self.fara_date = set()     # sample-uri fără date în PCM-ul sursei, puse ca zone goale
        k = dst.kmp
        self.d_mid, self.d_did = dst.indexuri()
        self.d_sid = {}
        for i, x in enumerate(k.S):
            self.d_sid.setdefault(k.s_id(x), i)
        self.s_mid, self.s_did = src.indexuri()
        self.map_sample = {}
        self.map_ms = {}
        self.map_drum = {}
        self.map_sunet = {}     # (fișier, slot) sursă -> (fișier, slot) țintă
        self.map_pad = {}       # (bancă, slot) sursă -> (bancă, slot) țintă
        self.sfarsit = self._sfarsit_ram()
        self._pcm_marimi = None

    def log(self, t):
        self.jurnal.append(t)

    # ------------------------------------------------------------------ memorie și PCM
    def _sfarsit_ram(self):
        k = self.dst.kmp
        pcm = self.dst.pcm()
        end = 0
        for x in k.S:
            v = pcm.get(k.s_pcm(x))
            L = v[1] if v else 0
            end = max(end, k.s_baza(x) + L)
        return end

    def _fisier_pcm(self):
        """Fișierul PCM cel mai puțin plin (RAM01..RAM99) și următorul slot liber."""
        if self._pcm_marimi is None:
            self._pcm_marimi = {}
            for (f, sl), v in self.dst.pcm().items():
                m = self._pcm_marimi.setdefault(f, [0, -1])
                m[0] += v[1]
                m[1] = max(m[1], sl)
        best = None
        for f in range(99):
            m = self._pcm_marimi.get(f, [0, -1])
            if m[1] >= 255:
                continue
            if best is None or m[0] < best[1][0]:
                best = (f, m)
        f, m = best
        return f, m[1] + 1

    def copiaza_sample(self, si):
        if si in self.map_sample:
            return self.map_sample[si]
        sk = self.src.kmp
        x = sk.S[si]
        sid = sk.s_id(x)
        if sid in self.d_sid:                       # există deja în țintă
            self.map_sample[si] = self.d_sid[sid]
            return self.d_sid[sid]
        v = self.src.pcm().get(sk.s_pcm(x))
        if v is None or v[2] != sid:
            raise ValueError(f'sample-ul {sk.s_nume(x)} nu are datele în PCM-ul sursei')
        nume, L, _, e = v
        f, sl = self._fisier_pcm()
        rel = 'PCM/RAM%02d.PCM' % (f + 1)
        F = self.dst.fisier(rel, creeaza=True)
        F.intrari.append(pl.Intrare(nume, 6, f, sl, 0, 0, 0, e.chunk_tip, e.chunk))
        self.dst.modificate.add(rel)
        self._pcm_marimi.setdefault(f, [0, -1])
        self._pcm_marimi[f][0] += L
        self._pcm_marimi[f][1] = sl
        self.dst.pcm()[(f, sl)] = (nume, L, bytes(e.chunk[:8]), F.intrari[-1])
        baza = (self.sfarsit + 63) // 64 * 64
        nx = pl.muta_adrese(x, baza - sk.s_baza(x))
        nx[92], nx[93] = f, sl
        self.sfarsit = baza + L
        dk = self.dst.kmp
        dk.S.append(nx)
        ni = len(dk.S) - 1
        self.d_sid[sid] = ni
        self.map_sample[si] = ni
        self.adus_mb += L
        self.dst.modificate.add('MULTISMP/RAM.KMP')
        return ni

    def copiaza_ms(self, mi):
        if mi in self.map_ms:
            return self.map_ms[mi]
        sk, dk = self.src.kmp, self.dst.kmp
        m = sk.M[mi]
        mid = sk.m_id(m)
        if mid in self.d_mid:
            self.map_ms[mi] = self.d_mid[mid]
            return self.d_mid[mid]
        zone = []
        for zi in sk.m_zone(m):
            z = bytearray(sk.Z[zi])
            r = sk.z_sample(z)
            if r and r[1]:
                x = sk.S[r[0]]
                v = self.src.pcm().get(sk.s_pcm(x))
                if v is None or v[2] != sk.s_id(x):
                    # sample fără date în PCM-ul sursei (tace și acolo): zona rămâne goală
                    self.fara_date.add(sk.s_nume(x))
                    z[0:2] = b'\xff\xff'
                else:
                    z[0:2] = struct.pack('>H', self.copiaza_sample(r[0]))
            zone.append(z)
        prima = len(dk.Z)
        dk.Z.extend(zone)
        nm = bytearray(m)
        nm[26:28] = struct.pack('>H', prima)
        dk.M.append(nm)
        ni = len(dk.M) - 1
        self.d_mid[mid] = ni
        self.map_ms[mi] = ni
        self.dst.modificate.add('MULTISMP/RAM.KMP')
        return ni

    def copiaza_tobe(self, di):
        if di in self.map_drum:
            return self.map_drum[di]
        sk, dk = self.src.kmp, self.dst.kmp
        x = sk.D[di]
        did = sk.d_id(x)
        if did in self.d_did:
            self.map_drum[di] = self.d_did[did]
            return self.d_did[did]
        nx = bytearray(x)
        for k in range(4):
            v = struct.unpack('>H', x[2 * k:2 * k + 2])[0]
            if v != 0xffff:
                nx[2 * k:2 * k + 2] = struct.pack('>H', self.copiaza_sample(v))
        dk.D.append(nx)
        ni = len(dk.D) - 1
        self.d_did[did] = ni
        self.map_drum[di] = ni
        self.dst.modificate.add('MULTISMP/RAM.KMP')
        return ni

    # ------------------------------------------------------------------ locuri
    def _loc(self, rel, slot_dorit, maxim, nume_nou=None):
        F = self.dst.fisier(rel, creeaza=True)
        ocupate = {e.slot: e for e in F.intrari}
        if slot_dorit is not None and (slot_dorit not in ocupate or self.peste):
            return F, slot_dorit
        if slot_dorit is not None and nume_nou is not None and ocupate[slot_dorit].nume == nume_nou and self.peste:
            return F, slot_dorit
        for s in range(maxim):
            if s not in ocupate:
                return F, s
        raise ValueError(f'{rel} e plin')

    @staticmethod
    def _pune(F, e, slot):
        F.intrari = [x for x in F.intrari if x.slot != slot]
        e.slot = slot
        F.intrari.append(e)
        F.intrari.sort(key=lambda x: x.slot)

    # ------------------------------------------------------------------ sunete
    def sunet(self, fn, slot, la=None):
        key = (fn, slot)
        if key in self.map_sunet:
            return self.map_sunet[key]
        F = self.src.fisier('SOUND/%s.PCG' % fn)
        e = F.dupa_slot(slot) if F else None
        if e is None:
            raise ValueError(f'în sursă nu există sunet la {fn} {slot + 1}')
        # același sunet există deja în țintă (aceleași date și nume)? atunci îl folosim pe acela
        if la is None:
            for dfn, de in self.dst.sunete():
                if de.nume == e.nume and de.chunk == e.chunk:
                    self.map_sunet[key] = (dfn, de.slot)
                    self.log(f'Sunetul {e.nume} există deja în țintă la {dfn} {de.slot + 1}, nu l-am mai copiat.')
                    return self.map_sunet[key]
        tfn, tslot = la if la else (fn, slot)
        if tfn not in pl.BANCI_SUNET:
            raise ValueError(f'banca de sunete {tfn} nu e cunoscută')
        rel = 'SOUND/%s.PCG' % tfn
        T, tslot = self._loc(rel, tslot, LOCURI['sunet'])
        ms, dr = self.src.ref_sunet(e, self.s_mid, self.s_did)
        for mi in ms:
            self.copiaza_ms(mi)
        for di in dr:
            self.copiaza_tobe(di)
        ne = e.copie()
        ne.banca = pl.BANCI_SUNET[tfn][0]
        ne.tip = 4
        self._pune(T, ne, tslot)
        self.dst.modificate.add(rel)
        self.map_sunet[key] = (tfn, tslot)
        self.log(f'Sunetul {e.nume}: din {fn} {slot + 1} în {tfn} {tslot + 1}.')
        return self.map_sunet[key]

    # ------------------------------------------------------------------ referințe
    def _remapeaza(self, d):
        """Aduce sunetele (și pad-urile) user folosite și schimbă referințele în date."""
        d = bytearray(d)
        if self.cu_sunete:
            for off, msb, lsb, pc in pl.refs_sunete(bytes(d)):
                fn = pl.DUPA_MSB_LSB[(msb, lsb)]
                F = self.src.fisier('SOUND/%s.PCG' % fn)
                if F is None or F.dupa_slot(pc) is None:
                    continue                      # lipsește și în sursă: rămâne cum e
                tfn, tslot = self.sunet(fn, pc)
                _, m2, l2 = pl.BANCI_SUNET[tfn]
                d[off] = m2; d[off + 1] = l2; d[off + 3] = tslot
            for off, b, sl in pl.refs_paduri(bytes(d)):
                if 0x14 <= b <= 0x1d:
                    r = self.pad_ref(b, sl)
                    if r:
                        d[off], d[off + 2] = r
        return bytes(d)

    def pad_ref(self, banca, slot):
        key = (banca, slot)
        if key in self.map_pad:
            return self.map_pad[key]
        fn = 'USER%02d' % (banca - 0x13)
        F = self.src.fisier('PAD/%s.PAD' % fn)
        if F is None or F.dupa_slot(slot) is None:
            return None
        tb, ts = self.pad(fn, slot)
        self.map_pad[key] = (tb, ts)
        return self.map_pad[key]

    # ------------------------------------------------------------------ perf / style / pad
    def pad(self, fn, slot, la=None):
        F = self.src.fisier('PAD/%s.PAD' % fn)
        e = F.dupa_slot(slot) if F else None
        if e is None:
            raise ValueError(f'în sursă nu există pad la {fn} {slot + 1}')
        tfn, tslot = la if la else (fn, slot)
        rel = 'PAD/%s.PAD' % tfn
        T, tslot = self._loc(rel, tslot, LOCURI['pad'])
        self.map_pad[(pl.banca_pad(fn), slot)] = (pl.banca_pad(tfn), tslot)
        ne = e.copie()
        ne.banca = pl.banca_pad(tfn)
        d = e.date()
        nd = self._remapeaza(d)
        if nd != d:
            ne.pune_date(nd)
        self._pune(T, ne, tslot)
        self.dst.modificate.add(rel)
        self.log(f'Pad-ul {e.nume}: din {fn} {slot + 1} în {tfn} {tslot + 1}.')
        return pl.banca_pad(tfn), tslot

    def perf(self, fn, slot, la=None):
        F = self.src.fisier('PERFORM/%s.PRF' % fn)
        e = F.dupa_slot(slot) if F else None
        if e is None:
            raise ValueError(f'în sursă nu există performance la {fn} {slot + 1}')
        tfn, tslot = la if la else (fn, slot)
        rel = 'PERFORM/%s.PRF' % tfn
        T, tslot = self._loc(rel, tslot, LOCURI['perf'])
        ne = e.copie()
        ne.banca = pl.banca_perf(tfn)
        d = e.date()
        nd = self._remapeaza(d)
        if nd != d:
            ne.pune_date(nd)
        self._pune(T, ne, tslot)
        self.dst.modificate.add(rel)
        self.log(f'Performance-ul {e.nume}: din {fn} {slot + 1} în {tfn} {tslot + 1}.')

    def style(self, fn, slot, la=None):
        F = self.src.fisier('STYLE/%s.STY' % fn)
        es = [e for e in F.intrari if e.slot == slot] if F else []
        if not es:
            raise ValueError(f'în sursă nu există style la {fn} {slot + 1}')
        tfn, tslot = la if la else (fn, slot)
        rel = 'STYLE/%s.STY' % tfn
        T, tslot = self._loc(rel, tslot, LOCURI['style'])
        T.intrari = [x for x in T.intrari if x.slot != tslot]
        for e in es:
            ne = e.copie()
            ne.banca = pl.banca_style(tfn)
            ne.slot = tslot
            d = e.date()
            nd = self._remapeaza(d)
            if nd != d:
                ne.pune_date(nd)
            T.intrari.append(ne)
        T.intrari.sort(key=lambda x: (x.slot, x.tip))
        self.dst.modificate.add(rel)
        nume = next((e.nume for e in es if e.nume), '')
        self.log(f'Style-ul {nume}: din {fn} {slot + 1} în {tfn} {tslot + 1}.')

    def gata(self):
        tot = self.dst.marime_pcm()
        self.log(f'Sample-uri aduse: {pl.mb(self.adus_mb)}. Setul nou ocupă {pl.mb(tot)} din 256 MB.')
        if self.fara_date:
            self.log('Sample-uri fără date în setul sursă (tac și acolo), puse ca zone goale: ' + ', '.join(sorted(self.fara_date)))
        if tot > pl.MAX_RAM:
            self.log('ATENȚIE: setul nou trece de 256 MB, Pa3X nu-l va încărca întreg. Trebuie scos ceva.')


def citeste_element(t):
    tip, rest = t.split(':', 1)
    la = None
    if '=' in rest:
        rest, dest = rest.split('=')
        b, s = dest.split(':')
        la = (b.upper(), int(s) - 1)
    b, s = rest.split(':')
    return tip.lower(), b.upper(), int(s) - 1, la


def copiaza_set(src_cale, dst_cale):
    if os.path.exists(dst_cale):
        raise SystemExit(f'{dst_cale} există deja; aleg alt nume ca să nu scriu peste nimic.')
    shutil.copytree(src_cale, dst_cale)


def ruleaza(sursa, tinta, nou, elemente, peste=False, cu_sunete=True):
    copiaza_set(tinta, nou)
    src = pl.Set(sursa)
    dst = pl.Set(nou)
    tr = Transfer(src, dst, peste=peste, cu_sunete=cu_sunete)
    for t in elemente:
        tip, b, s, la = citeste_element(t)
        if tip == 'sunet':
            tr.sunet(b, s, la)
        elif tip == 'perf':
            tr.perf(b, s, la)
        elif tip == 'style':
            tr.style(b, s, la)
        elif tip == 'pad':
            tr.pad(b, s, la)
        else:
            raise SystemExit('tip necunoscut: ' + tip)
    tr.gata()
    scrise = dst.salveaza()
    tr.log('Fișiere scrise în setul nou: ' + ', '.join(scrise))
    return tr.jurnal


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    j = ruleaza(a[0], a[1], a[2], a[3:], peste='--peste' in sys.argv, cu_sunete='--fara-sunete' not in sys.argv)
    print('\n'.join(j))
