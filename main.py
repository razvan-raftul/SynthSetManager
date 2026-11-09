"""Synth Set Manager – pornirea (din exe sau cu python main.py)."""
import os, sys, traceback

try:
    import server
    server.main()
except SystemExit:
    raise
except Exception:
    d = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'SynthSetManager')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'erori.txt'), 'a', encoding='utf-8') as f:
        f.write(traceback.format_exc() + '\n')
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, 'Synth Set Manager nu a pornit. Detaliile sunt în %APPDATA%\\SynthSetManager\\erori.txt', 'Synth Set Manager', 0)
    except Exception:
        pass
