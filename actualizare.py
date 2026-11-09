"""Actualizarea automată: la pornire se uită pe GitHub dacă e o versiune nouă.
NVDA spune doar „Se actualizează” și procentul, din 10 în 10, apoi după repornire „100 la sută. Actualizare terminată.”
"""
import ctypes, os, subprocess, sys, tempfile, time, urllib.request

DEPOZIT = 'razvan-raftul/SynthSetManager'
URL = 'https://github.com/%s/releases/download/latest/' % DEPOZIT
_dll = None


def vorbeste(text):
    global _dll
    try:
        if _dll is None:
            baza = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
            _dll = ctypes.windll.LoadLibrary(os.path.join(baza, 'nvdaControllerClient.dll'))
        if _dll.nvdaController_testIfRunning() == 0:
            _dll.nvdaController_speakText(ctypes.c_wchar_p(text))
    except Exception:
        pass


def _nr(v):
    try:
        return tuple(int(x) for x in v.strip().split('.'))
    except ValueError:
        return (0,)


def verifica(versiune):
    """Dacă pe GitHub e o versiune mai nouă: descarcă installer-ul, îl pornește și închide aplicația."""
    if not getattr(sys, 'frozen', False):
        return
    try:
        noua = urllib.request.urlopen(URL + 'version.txt', timeout=6).read().decode('utf-8', 'replace').strip()
    except Exception:
        return
    if _nr(noua) <= _nr(versiune):
        return
    vorbeste('Se actualizează')
    cale = os.path.join(tempfile.gettempdir(), 'SynthSetManager-Setup.exe')
    try:
        r = urllib.request.urlopen(URL + 'SynthSetManager-Setup.exe', timeout=30)
        total = int(r.headers.get('Content-Length') or 0)
        facut, ultim = 0, 0
        with open(cale, 'wb') as f:
            while True:
                b = r.read(256 * 1024)
                if not b:
                    break
                f.write(b)
                facut += len(b)
                if total:
                    p = facut * 90 // total // 10 * 10
                    if p >= ultim + 10:
                        ultim = p
                        vorbeste('%d la sută' % p)
    except Exception:
        return
    if ultim < 90:
        vorbeste('90 la sută')
    time.sleep(1)
    subprocess.Popen([cale, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/AUTOUPDATE'])
    os._exit(0)
