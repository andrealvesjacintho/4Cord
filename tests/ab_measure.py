import argparse
import json
import os
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument('--appdir', required=True)
parser.add_argument('--out', required=True)
parser.add_argument('--messages', type=int, default=1500)
args = parser.parse_args()

sys.path.insert(0, args.appdir)
os.environ.setdefault('GDK_BACKEND', 'x11')
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, GLib
import app as target

TICKS = os.sysconf('SC_CLK_TCK')


def children_map():
    children = {}
    for name in os.listdir('/proc'):
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            with open(f'/proc/{pid}/stat', encoding='utf-8', errors='replace') as fh:
                data = fh.read()
            end = data.rfind(')')
            ppid = int(data[end + 2:].split()[1])
        except Exception:
            continue
        children.setdefault(ppid, []).append(pid)
    return children


def tree_pids(root):
    children = children_map()
    seen = set()
    queue = [root]
    while queue:
        pid = queue.pop()
        if pid in seen:
            continue
        seen.add(pid)
        queue.extend(children.get(pid, []))
    return sorted(seen)


def proc_pss_kb(pid):
    try:
        with open(f'/proc/{pid}/smaps_rollup', encoding='utf-8') as fh:
            for line in fh:
                if line.startswith('Pss:'):
                    return int(line.split()[1])
    except Exception:
        pass
    try:
        with open(f'/proc/{pid}/status', encoding='utf-8') as fh:
            for line in fh:
                if line.startswith('VmRSS:'):
                    return int(line.split()[1])
    except Exception:
        pass
    return 0


def proc_cpu_ticks(pid):
    try:
        with open(f'/proc/{pid}/stat', encoding='utf-8', errors='replace') as fh:
            data = fh.read()
        end = data.rfind(')')
        fields = data[end + 2:].split()
        return int(fields[11]) + int(fields[12])
    except Exception:
        return 0


def tree_stats(root):
    pids = tree_pids(root)
    pss = sum(proc_pss_kb(p) for p in pids)
    ticks = sum(proc_cpu_ticks(p) for p in pids)
    return {
        'pss_mb': round(pss / 1024.0, 1),
        'cpu_s': round(ticks / float(TICKS), 3),
        'processes': len(pids),
    }


t0 = time.time()
a = target.App(mock=True)
a.start()


def js_result(view, res):
    try:
        value = view.run_javascript_finish(res).get_js_value()
        return value.to_string() if value else None
    except Exception as e:
        return json.dumps({'error': type(e).__name__ + ': ' + str(e)})


def phase_boot():
    boot_stats = tree_stats(os.getpid())
    js = r'''
    (() => {
      return JSON.stringify({
        dom: document.querySelectorAll('#msgList .msg').length,
        msgs: (typeof S !== 'undefined' && S.messages) ? S.messages.length : -1,
        seen: (typeof S !== 'undefined' && S.seen) ? S.seen.size : -1,
        title: document.title,
        channel: (typeof S !== 'undefined' && S.channel) ? S.channel.id : null,
        scrollHeight: document.querySelector('#msgs').scrollHeight
      });
    })()
    '''
    a.win.web.run_javascript(js, None, lambda v, r, *_: booted(v, r, boot_stats), None)
    return False


def booted(view, res, boot_stats):
    boot = json.loads(js_result(view, res) or '{}')
    count = args.messages
    js = r'''
    (() => {
      const t0 = performance.now();
      const ch = S.channel.id;
      for (let i = 0; i < %d; i++) {
        window.tpEvent({type:'message_create', data:{
          id: 'ab' + i, channel_id: ch,
          timestamp: new Date(Date.now() + i * 1000).toISOString(),
          author: {id: 'u1', username: 'u1', global_name: 'u1'},
          content: 'mensagem de teste ' + i
        }});
      }
      const injectMs = performance.now() - t0;
      return JSON.stringify({
        injectMs: Math.round(injectMs * 10) / 10,
        dom: document.querySelectorAll('#msgList .msg').length,
        msgs: S.messages.length,
        seen: S.seen.size,
        first: S.messages.length ? S.messages[0].id : null,
        last: S.messages.length ? S.messages[S.messages.length - 1].id : null,
        scrollHeight: document.querySelector('#msgs').scrollHeight,
        scrollTop: document.querySelector('#msgs').scrollTop
      });
    })()
    ''' % count
    a.win.web.run_javascript(js, None, lambda v, r, *_: injected(v, r, boot, boot_stats), None)


def injected(view, res, boot, boot_stats):
    injected_data = json.loads(js_result(view, res) or '{}')
    GLib.timeout_add(1600, finish, boot, boot_stats, injected_data)


def finish(boot, boot_stats, injected_data):
    js = r'''
    (() => {
      const b = document.querySelector('#msgs');
      return JSON.stringify({
        dom: document.querySelectorAll('#msgList .msg').length,
        msgs: S.messages.length,
        seen: S.seen.size,
        scrollTop: b.scrollTop,
        scrollHeight: b.scrollHeight,
        clientHeight: b.clientHeight,
        atBottom: (b.scrollHeight - b.scrollTop - b.clientHeight) < 120
      });
    })()
    '''
    a.win.web.run_javascript(js, None, lambda v, r, *_: finalize(v, r, boot, boot_stats, injected_data), None)
    return False


def finalize(view, res, boot, boot_stats, injected_data):
    final_ui = json.loads(js_result(view, res) or '{}')
    final_stats = tree_stats(os.getpid())
    result = {
        'appdir': args.appdir,
        'boot': boot,
        'boot_stats': boot_stats,
        'injected': injected_data,
        'final_ui': final_ui,
        'final_stats': final_stats,
        'pss_delta_mb': round(final_stats['pss_mb'] - boot_stats['pss_mb'], 1),
        'cpu_delta_s': round(final_stats['cpu_s'] - boot_stats['cpu_s'], 3),
        'elapsed_s': round(time.time() - t0, 2),
    }
    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(result, fh, indent=2, sort_keys=True)
    print(json.dumps(result, sort_keys=True), flush=True)
    Gtk.main_quit()
    return False


GLib.timeout_add(3500, phase_boot)
Gtk.main()
