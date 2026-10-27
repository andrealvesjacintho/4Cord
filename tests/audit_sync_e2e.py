import json, os, sys
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import gi
gi.require_version('Gtk', '3.0'); gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, GLib
import app

CH = '100'
def mk(i):
    return {'id': str(i), 'channel_id': CH,
            'timestamp': '2026-10-25T12:00:00.000000+00:00',
            'author': {'id': 'u1', 'username': 'u1'}, 'content': 'm%d' % i}

seen_limits = []
def fake(cid, before=None, limit=50, after=None):
    assert after is None, "sincronização da conversa ativa não deve usar after"
    seen_limits.append(limit)
    if before:
        return []
    start = 1450
    return [mk(i) for i in range(start, start - limit, -1)]

def got(view, res, *_):
    try:
        val = view.run_javascript_finish(res).get_js_value()
        text = val.to_string() if val else ''
        if text and text != 'null':
            print('E2E', text, flush=True)
            print('BACKEND_LIMITS', json.dumps(seen_limits), flush=True)
            Gtk.main_quit()
    except Exception as e:
        print('POLLERR', e, flush=True)

def poll():
    a.win.web.run_javascript('window.__e2e || null', None, got, None)
    return True

def step():
    a.win.api.messages = fake
    js = r'''
    window.__e2e = null;
    (async () => {
      try {
        const mk = (i) => ({id:String(i), channel_id:S.channel.id,
          timestamp:new Date(1700000000000+i*1000).toISOString(),
          author:{id:'u1',username:'u1'}, content:'m'+i});
        replaceWindow(Array.from({length:300},(_,k)=>mk(1000+k)), true);
        S.hasOlder = true; S.hasNewer = false; S.liveStick = true;
        await syncLatest();
        const ids = S.messages.map(m=>m.id).map(Number);
        const gaps = [];
        for (let i=1;i<ids.length;i++) if (ids[i] !== ids[i-1]+1) gaps.push([ids[i-1],ids[i]]);
        window.__e2e = JSON.stringify({len:S.messages.length, first:String(ids[0]),
          last:String(ids[ids.length-1]), gaps, hasOlder:S.hasOlder,
          hasNewer:S.hasNewer, dom:document.querySelectorAll('#msgList .msg').length});
      } catch (e) { window.__e2e = JSON.stringify({error:String(e && (e.stack||e))}); }
    })();
    null
    '''
    a.win.web.run_javascript(js, None, lambda *_: None, None)
    GLib.timeout_add(900, poll)
    return False

a = app.App(mock=True); a.start()
GLib.timeout_add(3500, step)
Gtk.main()
