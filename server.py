"""Synth Set Manager – server local. Pagina se deschide în Chrome; tot lucrul se face aici, pe calculator."""
import json, os, sys, threading, time, traceback, uuid as uuidmod, webbrowser, subprocess, socket
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

AICI = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AICI)
import kronos_lib as kl
import pa_ops as po


def _versiune():
    try:
        return open(os.path.join(AICI, 'versiune.txt'), encoding='utf-8').read().strip()
    except OSError:
        return '0.0.0'


def _documente():
    try:
        import ctypes
        b = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, b)
        if b.value:
            return b.value
    except Exception:
        pass
    return os.path.join(os.path.expanduser('~'), 'Documents')


VERSIUNE = _versiune()
LUCRU = os.path.join(_documente(), 'Claude working')
PA_IMPLICIT = os.path.join(LUCRU, 'Korg Pa Manager')
KRONOS_IMPLICIT = os.path.join(LUCRU, 'Kronos')
SETARI_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'SynthSetManager')
SETARI_F = os.path.join(SETARI_DIR, 'setari.json')
PORTURI = range(8765, 8776)


def setari_implicite():
    k = [KRONOS_IMPLICIT]
    d = os.path.join(os.path.expanduser('~'), 'Desktop', 'KRONOS CEAMAKITO')
    if os.path.isdir(d):
        k.append(d)
    return dict(kronos_dirs=k, pa_dirs=[PA_IMPLICIT], kronos_out=KRONOS_IMPLICIT, pa_out=PA_IMPLICIT)


def citeste_setari():
    s = setari_implicite()
    try:
        s.update(json.load(open(SETARI_F, encoding='utf-8')))
    except Exception:
        pass
    return s


def scrie_setari(s):
    os.makedirs(SETARI_DIR, exist_ok=True)
    json.dump(s, open(SETARI_F, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


SETARI = citeste_setari()
CACHE = {}
LOCK = threading.Lock()
JOBURI = {}
ULTIMUL_PING = [time.time()]


def kset(sid):
    key = ('k', sid)
    try:
        st = (os.path.getmtime(sid), os.path.getmtime(sid[:-4] + '.KSC'))
    except OSError:
        raise ValueError('Setul nu mai există: ' + sid)
    with LOCK:
        v = CACHE.get(key)
        if v and v[0] == st:
            return v[1]
    s = kl.KronosSet(sid)
    with LOCK:
        CACHE[key] = (st, s)
    return s


def pinfo(cale):
    key = ('p', cale)
    with LOCK:
        v = CACHE.get(key)
        if v:
            return v
    i = po.Info(cale)
    with LOCK:
        CACHE[key] = i
    return i


def goleste_cache():
    with LOCK:
        CACHE.clear()


# ----------------------------------------------------------------------------- joburi în fundal

def porneste_job(functie):
    jid = uuidmod.uuid4().hex[:10]
    job = dict(stare='lucrez', procent=0, mesaj='Pornesc', jurnal=[], eroare=None)
    JOBURI[jid] = job

    def progres(p, m=None):
        job['procent'] = max(job['procent'], min(100, int(p)))
        if m:
            job['mesaj'] = m

    def run():
        try:
            job['jurnal'] = functie(progres)
            job['procent'] = 100
            job['stare'] = 'gata'
        except Exception as e:
            job['eroare'] = str(e) or e.__class__.__name__
            job['jurnal'] = ['Eroare: ' + job['eroare']]
            try:
                os.makedirs(SETARI_DIR, exist_ok=True)
                with open(os.path.join(SETARI_DIR, 'erori.txt'), 'a', encoding='utf-8') as f:
                    f.write(time.strftime('%Y-%m-%d %H:%M ') + traceback.format_exc() + '\n')
            except Exception:
                pass
            job['stare'] = 'eroare'
        finally:
            goleste_cache()

    threading.Thread(target=run, daemon=True).start()
    return jid


def ocupat():
    return any(j['stare'] == 'lucrez' for j in JOBURI.values())


# ----------------------------------------------------------------------------- API

def nume_sigur(n):
    n = (n or '').strip()
    for c in '<>:"/\\|?*':
        n = n.replace(c, ' ')
    return n.strip(' .')


def api(cale, q, corp):
    S = SETARI
    if cale == '/api/ping':
        ULTIMUL_PING[0] = time.time()
        return dict(ok=True, app='SynthSetManager', versiune=VERSIUNE)
    if cale == '/api/setari':
        return S
    if cale == '/api/setari/salveaza':
        for k in ('kronos_dirs', 'pa_dirs'):
            if k in corp:
                S[k] = [d for d in corp[k] if d.strip()]
        for k in ('kronos_out', 'pa_out'):
            if corp.get(k):
                S[k] = corp[k]
        scrie_setari(S)
        goleste_cache()
        return S
    if cale == '/api/alege_folder':
        return dict(cale=alege_folder(corp.get('titlu', 'Alege folderul')))
    if cale == '/api/inchide':
        threading.Timer(0.5, lambda: os._exit(0)).start()
        return dict(ok=True)
    if cale == '/api/job':
        j = JOBURI.get(q.get('id', [''])[0])
        if not j:
            raise ValueError('Lucrarea nu există.')
        return j

    # ------------------------------------------------ Kronos
    if cale == '/api/kronos/seturi':
        return kl.gaseste_seturi(S['kronos_dirs'])
    if cale == '/api/kronos/banci':
        s = kset(q['set'][0])
        return s.banci(q['tip'][0])
    if cale == '/api/kronos/elemente':
        s = kset(q['set'][0])
        t = q.get('tinta', [''])[0]
        tinta = kset(t) if t else None
        return kl.lista_elemente(s, tinta, q['tip'][0], q['banca'][0])
    if cale == '/api/kronos/cost':
        s = kset(corp['sursa'])
        tinta = kset(corp['tinta']) if corp.get('tinta') else None
        return kl.rezumat_cost(s, tinta, corp['elemente'])
    if cale == '/api/kronos/transfer':
        if ocupat():
            raise ValueError('Încă lucrez la ceva. Așteaptă să termin.')
        opt = dict(sw_octava=bool(corp.get('sw_octava')), in_loc=bool(corp.get('in_loc')),
                   banca_prog=corp.get('banca_prog') or 'U-A', banca_combi=corp.get('banca_combi') or 'U-A',
                   banca_timbre=[corp['banca_timbre']] + [b for b in kl.BANCI_TIMBRE if b != corp['banca_timbre']] if corp.get('banca_timbre') else None)
        if not opt['in_loc']:
            n = nume_sigur(corp.get('nume_nou'))
            if not n:
                raise ValueError('Scrie un nume pentru setul nou.')
            opt['folder_nou'] = os.path.join(S['kronos_out'], n)
            if os.path.exists(opt['folder_nou']):
                raise ValueError('Există deja un folder cu numele %s. Alege alt nume.' % n)
        el = corp['elemente']
        if not el:
            raise ValueError('Nu ai bifat nimic.')

        def f(progres):
            t = kl.Transfer(corp['sursa'], corp['tinta'], opt, progres)
            return t.ruleaza(el)
        return dict(job=porneste_job(f))

    # ------------------------------------------------ Pa
    if cale == '/api/pa/seturi':
        return po.gaseste_seturi(S['pa_dirs'])
    if cale == '/api/pa/banci':
        s = q.get('set', [''])[0]
        return po.banci(pinfo(s) if s else None, q['tip'][0])
    if cale == '/api/pa/elemente':
        i = pinfo(q['set'][0])
        t = q.get('tinta', [''])[0]
        return po.elemente(i, pinfo(t) if t else None, q['tip'][0], q['banca'][0])
    if cale == '/api/pa/cost':
        i = pinfo(corp['sursa'])
        return po.rezumat_cost(i, pinfo(corp['tinta']) if corp.get('tinta') else None, corp['elemente'])
    if cale in ('/api/pa/transfer', '/api/pa/curatenie'):
        if ocupat():
            raise ValueError('Încă lucrez la ceva. Așteaptă să termin.')
        el = corp['elemente']
        if not el:
            raise ValueError('Nu ai bifat nimic.')
        opt = dict(in_loc=bool(corp.get('in_loc')), peste=bool(corp.get('peste')),
                   cu_sunete=corp.get('cu_sunete', True), banca=corp.get('banca') or {},
                   gol=not corp.get('tinta') and cale == '/api/pa/transfer')
        if opt['in_loc'] and opt['gol']:
            raise ValueError('Alege un set în care pun, sau fă un set nou.')
        if not opt['in_loc']:
            n = nume_sigur(corp.get('nume_nou'))
            if not n:
                raise ValueError('Scrie un nume pentru setul nou.')
            if not n.upper().endswith('.SET'):
                n += '.SET'
            opt['nou'] = os.path.join(S['pa_out'], n)
            if os.path.exists(opt['nou']):
                raise ValueError('Există deja un set cu numele %s. Alege alt nume.' % n[:-4])
        if cale == '/api/pa/transfer':
            f = lambda progres: po.transfer(corp['sursa'], corp.get('tinta'), el, opt, progres)
        else:
            f = lambda progres: po.curatenie(corp['sursa'], el, opt, progres)
        return dict(job=porneste_job(f))
    if cale in ('/api/pa/raport', '/api/pa/verifica'):
        s = corp['sursa']
        f = (lambda progres: po.raport(s)) if cale.endswith('raport') else (lambda progres: po.verifica(s))
        return dict(job=porneste_job(f))
    raise KeyError(cale)


def alege_folder(titlu):
    rez = [None]

    def run():
        try:
            import tkinter as tk
            from tkinter import filedialog
            r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)
            rez[0] = filedialog.askdirectory(title=titlu, mustexist=True) or None
            r.destroy()
        except Exception:
            rez[0] = None
    t = threading.Thread(target=run); t.start(); t.join()
    return os.path.normpath(rez[0]) if rez[0] else None


TIPURI_MIME = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8'}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _trimite(self, cod, corp, tip='application/json; charset=utf-8'):
        b = corp if isinstance(corp, bytes) else json.dumps(corp, ensure_ascii=False).encode('utf-8')
        self.send_response(cod)
        self.send_header('Content-Type', tip)
        self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(b)

    def _api(self, corp):
        u = urlparse(self.path)
        try:
            self._trimite(200, api(u.path, parse_qs(u.query), corp))
        except KeyError as e:
            self._trimite(404, dict(eroare='Nu știu: %s' % e))
        except Exception as e:
            self._trimite(400, dict(eroare=str(e) or e.__class__.__name__))

    def do_GET(self):
        u = urlparse(self.path)
        if u.path.startswith('/api/'):
            return self._api({})
        p = u.path.strip('/') or 'index.html'
        f = os.path.join(AICI, os.path.basename(p))
        if os.path.splitext(f)[1] not in TIPURI_MIME:
            return self._trimite(404, b'nu exista', 'text/plain')
        if not os.path.isfile(f):
            return self._trimite(404, b'nu exista', 'text/plain')
        self._trimite(200, open(f, 'rb').read(), TIPURI_MIME.get(os.path.splitext(f)[1], 'application/octet-stream'))

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        try:
            corp = json.loads(self.rfile.read(n) or b'{}')
        except Exception:
            corp = {}
        self._api(corp)


def deschide_in_browser(url):
    for p in (os.path.join(os.environ.get('PROGRAMFILES', r'C:\Program Files'), r'Google\Chrome\Application\chrome.exe'),
              os.path.join(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)'), r'Google\Chrome\Application\chrome.exe'),
              os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Google\Chrome\Application\chrome.exe')):
        if p and os.path.isfile(p):
            try:
                subprocess.Popen([p, url]); return
            except Exception:
                pass
    webbrowser.open(url)


def deja_pornit():
    import urllib.request
    for port in PORTURI:
        try:
            r = urllib.request.urlopen('http://127.0.0.1:%d/api/ping' % port, timeout=0.5)
            if json.loads(r.read()).get('app') == 'SynthSetManager':
                return port
        except Exception:
            pass
    return None


def paznic():
    """Se închide singur dacă pagina a fost închisă de mult (fără ping 15 minute) și nu lucrează."""
    while True:
        time.sleep(30)
        if time.time() - ULTIMUL_PING[0] > 900 and not ocupat():
            os._exit(0)


def main():
    import actualizare
    if '--actualizat' in sys.argv:
        actualizare.vorbeste('100 la sută. Actualizare terminată.')
    port = deja_pornit()
    if not port and '--actualizat' not in sys.argv:
        actualizare.verifica(VERSIUNE)
    if port:
        deschide_in_browser('http://127.0.0.1:%d/' % port)
        return
    srv = None
    for port in PORTURI:
        try:
            srv = ThreadingHTTPServer(('127.0.0.1', port), H); break
        except OSError:
            continue
    if srv is None:
        raise SystemExit('Nu am găsit niciun port liber.')
    threading.Thread(target=paznic, daemon=True).start()
    if '--fara-browser' not in sys.argv:
        deschide_in_browser('http://127.0.0.1:%d/' % port)
    srv.serve_forever()


if __name__ == '__main__':
    main()
