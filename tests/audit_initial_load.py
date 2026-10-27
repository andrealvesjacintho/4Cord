import json, os, sys
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import gi
gi.require_version('Gtk', '3.0'); gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, GLib
import app

def got(view, res, *_):
    try:
        val = view.run_javascript_finish(res).get_js_value()
        text = val.to_string() if val else ''
        if text and text != 'null':
            print('INIT_LOAD', text, flush=True)
            Gtk.main_quit()
    except Exception as e:
        print('POLLERR', e, flush=True)

def poll():
    a.win.web.run_javascript('window.__initLoad || null', None, got, None)
    return True

def step():
    js = r'''
    window.__initLoad = null;
    (async () => {
      try {
        const mk = (i) => ({id:String(i), channel_id:S.channel.id,
          timestamp:new Date(1700000000000+i*1000).toISOString(),
          author:{id:'u1',username:'u1'}, content:'m'+i});
        const page = (start, end) => { const a=[]; for(let i=end;i>=start;i--) a.push(mk(i)); return a; };
        const orig = call;
        let release;
        const gate = new Promise((r) => { release = r; });
        call = async (cmd, args) => {
          if (cmd === 'messages') { await gate; return page(1000, 1049); }
          return orig(cmd, args);
        };
        const p = openChannel({id:'100', name:'notas'});
        await new Promise((r) => setTimeout(r, 100));
        window.tpEvent({type:'message_create', data: mk(2000)});
        const queuedDuringLoad = S.pendingLive.length;
        release();
        await p;
        const ids = S.messages.map((m) => m.id);
        const first = {queuedDuringLoad, len:ids.length, first:ids[0],
          last:ids[ids.length-1], hasLive:ids.includes('2000'),
          liveAtEnd:ids[ids.length-1] === '2000',
          unique:new Set(ids).size === ids.length,
          loadingChannel:S.loadingChannel, pending:S.pendingLive.length,
          dom:document.querySelectorAll('#msgList .msg').length};

        // Segundo caso: a mensagem ao vivo ja veio na pagina; nao duplicar.
        let release2;
        const gate2 = new Promise((r) => { release2 = r; });
        call = async (cmd, args) => {
          if (cmd === 'messages') { await gate2; return page(1951, 2000); }
          return orig(cmd, args);
        };
        const p2 = openChannel({id:'100', name:'notas'});
        await new Promise((r) => setTimeout(r, 100));
        window.tpEvent({type:'message_create', data: mk(2000)});
        const queued2 = S.pendingLive.length;
        release2();
        await p2;
        call = orig;
        const ids2 = S.messages.map((m) => m.id);
        const second = {queuedDuringLoad:queued2, len:ids2.length,
          first:ids2[0], last:ids2[ids2.length-1],
          unique:new Set(ids2).size === ids2.length,
          count2000:ids2.filter((id) => id === '2000').length,
          loadingChannel:S.loadingChannel, pending:S.pendingLive.length,
          dom:document.querySelectorAll('#msgList .msg').length};
        window.__initLoad = JSON.stringify({first, second});
      } catch (e) {
        window.__initLoad = JSON.stringify({error:String(e && (e.stack || e))});
      }
    })();
    null
    '''
    a.win.web.run_javascript(js, None, lambda *_: None, None)
    GLib.timeout_add(900, poll)
    return False

a = app.App(mock=True); a.start()
GLib.timeout_add(3500, step)
Gtk.main()
