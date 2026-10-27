import argparse, json, os, sys, time
parser = argparse.ArgumentParser()
parser.add_argument('--appdir', required=True)
parser.add_argument('--logfile', required=True)
parser.add_argument('--out', required=True)
parser.add_argument('--verbose', action='store_true')
args = parser.parse_args()
sys.path.insert(0, args.appdir)
import gi
gi.require_version('Gtk', '3.0'); gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, GLib
import app as target

def step():
    js = r'''
    (async () => {
      for (let i = 0; i < 20; i++) {
        await call('send', {channel: S.channel.id, content: 'log ' + i});
      }
      window.__logDone = true;
      return 'done';
    })()
    '''
    a.win.web.run_javascript(js, None, lambda *_: None, None)
    GLib.timeout_add(1600, finish)
    return False

def finish():
    path = args.logfile
    try:
        data = open(path, 'rb').read()
    except FileNotFoundError:
        data = b''
    result = {
        'appdir': args.appdir,
        'logfile': path,
        'exists': os.path.exists(path),
        'bytes': len(data),
        'lines': data.count(b'\n'),
        'has_comando': b'comando' in data,
        'has_send': b'cmd=send' in data,
    }
    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(result, fh, indent=2, sort_keys=True)
    print(json.dumps(result, sort_keys=True), flush=True)
    Gtk.main_quit()
    return False

if args.verbose:
    target.set_verbose(True)
a = target.App(mock=True); a.start()
GLib.timeout_add(3500, step)
Gtk.main()
