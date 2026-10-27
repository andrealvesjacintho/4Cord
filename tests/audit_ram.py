import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import gi
gi.require_version('Gtk', '3.0'); gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, GLib
import app

def snapshot():
    pids = sorted(app._app_process_tree(os.getpid()))
    manual_kb = 0
    kinds = {}
    for pid in pids:
        kb, kind = app._proc_memory_kb(pid)
        if kind and kb > 0:
            manual_kb += kb
            kinds[kind] = kinds.get(kind, 0) + 1
    return pids, manual_kb, kinds

def step():
    try:
        pids, manual_kb, kinds = snapshot()
        r = app.ram_usage()
        child = subprocess.Popen(['sleep', '20'])
        time.sleep(0.3)
        r_child = app.ram_usage()
        pids_child, _, _ = snapshot()
        child.terminate()
        child.wait()
        time.sleep(0.3)
        r_after = app.ram_usage()
        pids_after, _, _ = snapshot()
        names = []
        for pid in pids:
            try:
                with open(f'/proc/{pid}/comm', encoding='utf-8') as fh:
                    names.append(fh.read().strip())
            except OSError:
                names.append('?')
        out = {
            'processes': len(pids),
            'manual_mb': round(manual_kb / 1024.0, 1),
            'reported_mb': r.get('mb'),
            'match': r.get('mb') == round(manual_kb / 1024.0, 1),
            'method': r.get('method'),
            'kinds': kinds,
            'has_webkit_helpers': len(pids) > 1,
            'comm': names[:8],
            'child_counted': r_child.get('processes') == len(pids_child),
            'child_added': len(pids_child) == len(pids) + 1,
            'child_removed': len(pids_after) == len(pids),
            'after_mb': r_after.get('mb'),
            'no_error': bool(r.get('ok')) and bool(r_child.get('ok')) and bool(r_after.get('ok')),
        }
        print('RAM_RESULT', json.dumps(out, sort_keys=True), flush=True)
    except Exception as e:
        print('RAM_ERROR', type(e).__name__, e, flush=True)
    Gtk.main_quit()
    return False

a = app.App(mock=True); a.start()
GLib.timeout_add(3500, step)
Gtk.main()
