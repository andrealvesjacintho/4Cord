import os
import sys
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
            print('RESULT', text, flush=True)
            Gtk.main_quit()
    except Exception as e:
        print('POLLERR', e, flush=True)

def poll():
    a.win.web.run_javascript('window.__auditUi || null', None, got, None)
    return True

def step():
    js = r'''
    window.__auditUi = null;
    (async () => {
      try {
        const mk = (i) => ({id:String(i), channel_id:S.channel.id,
          timestamp:new Date(1700000000000+i*1000).toISOString(),
          author:{id:'u1',username:'u1'}, content:'m'+i});
        const win = (start, n) => Array.from({length:n}, (_,k)=>mk(start+k));
        const page = (start, end) => { const a=[]; for(let i=end;i>=start;i--) a.push(mk(i)); return a; };
        const ids = () => S.messages.map(m=>m.id);
        const gaps = () => { const a=ids().map(Number); const g=[];
          for(let i=1;i<a.length;i++) if(a[i]!==a[i-1]+1) g.push([a[i-1],a[i]]); return g; };
        const orig = call;
        let calls = 0;
        const setPage = (p) => { call = (cmd,args) => {
          if (cmd === 'messages') { calls++; return Promise.resolve(p); }
          return orig(cmd,args);
        }; };

        // A) reconexao longa com usuario no fim: recomeca pela pagina recente
        replaceWindow(win(1000,300), true);
        S.hasOlder = true; S.hasNewer = false; S.liveStick = true;
        setPage(page(1351,1450));
        await syncLatest();
        const gapLive = {len:S.messages.length, first:ids()[0], last:ids().at(-1),
          gaps:gaps(), hasOlder:S.hasOlder, hasNewer:S.hasNewer,
          dom:document.querySelectorAll('#msgList .msg').length};

        // B) reconexao curta com sobreposicao: completa sem buraco
        replaceWindow(win(1000,300), true);
        S.hasOlder = true; S.hasNewer = false; S.liveStick = true;
        setPage(page(1250,1349));
        await syncLatest();
        const overlap = {len:S.messages.length, first:ids()[0], last:ids().at(-1),
          gaps:gaps(), hasNewer:S.hasNewer,
          unique:new Set(ids()).size===ids().length};

        // C) reconexao longa lendo o passado: nao desloca a janela
        replaceWindow(win(1000,300), true);
        S.hasOlder = true; S.hasNewer = false; S.liveStick = false;
        document.querySelector('#msgs').scrollTop = 0;
        setPage(page(1351,1450));
        await syncLatest();
        const gapReading = {len:S.messages.length, first:ids()[0], last:ids().at(-1),
          hasNewer:S.hasNewer, gaps:gaps()};

        // D) guardas cruzados: operacoes nao se misturam
        replaceWindow(win(1000,300), true);
        S.hasOlder = true; S.loadingOlder = true;
        calls = 0;
        setPage(page(900,949));
        await syncLatest();
        const syncBlocked = calls;
        S.loadingOlder = false;
        S.syncing = true;
        calls = 0;
        await loadOlder();
        const olderBlocked = calls;
        S.syncing = false;
        S.loadingOlder = true;
        calls = 0;
        await goLatest();
        const latestBlocked = calls;
        S.loadingOlder = false;
        call = orig;

        // E) troca de canal/guild sem mensagens nao deixa spinner preso
        setMsgLoading(true);
        resetHistory(true);
        const spinnerHidden = document.querySelector('#msgLoading').classList.contains('hidden');

        // F) duas midias com a mesma URL: so a aberta no visualizador fica retida
        const png = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nKsAAAAASUVORK5CYII=';
        const b1 = mediaNode(png, {width:100,height:100,mime:'image/png'});
        const b2 = mediaNode(png, {width:100,height:100,mime:'image/png'});
        $('#msgList').appendChild(b1); $('#msgList').appendChild(b2);
        b1._reveal(); b2._reveal();
        openLightbox(png, b1);
        const mediaSpecific = {one:mediaInUse(b1), two:mediaInUse(b2)};
        closeLightbox();
        const mediaClosed = {one:mediaInUse(b1), two:mediaInUse(b2)};
        openLightbox(png);
        const mediaByUrl = {one:mediaInUse(b1), two:mediaInUse(b2)};
        closeLightbox();
        openLightbox(png, b1);
        b1._dispose();
        const mediaDisposed = {wrapCleared:lbWrap === null, two:mediaInUse(b2)};

        window.__auditUi = JSON.stringify({gapLive, overlap, gapReading,
          syncBlocked, olderBlocked, latestBlocked, spinnerHidden,
          mediaSpecific, mediaClosed, mediaByUrl, mediaDisposed});
      } catch (e) {
        window.__auditUi = JSON.stringify({error:String(e && (e.stack || e))});
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
