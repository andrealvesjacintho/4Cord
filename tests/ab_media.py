import argparse, json, os, sys, time
parser = argparse.ArgumentParser()
parser.add_argument('--appdir', required=True)
parser.add_argument('--out', required=True)
args = parser.parse_args()
sys.path.insert(0, args.appdir)
import gi
gi.require_version('Gtk', '3.0'); gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, GLib
import app as target

PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nKsAAAAASUVORK5CYII='
result = {}

def js_result(view, res):
    try:
        v = view.run_javascript_finish(res).get_js_value()
        return v.to_string() if v else None
    except Exception as e:
        return json.dumps({'error': type(e).__name__ + ': ' + str(e)})

def done(view, res, *_):
    result['media'] = json.loads(js_result(view, res) or '{}')
    # Teste deterministico de URL solicitada (A3), sem depender da rede.
    js = r'''
    (() => {
      const url = 'https://cdn.discordapp.com/attachments/1/2/foto.png';
      const box = mediaNode(url, {width: 200, height: 100, mime: 'image/png'});
      document.querySelector('#msgList').appendChild(box);
      box.querySelector('.mediaCover').click();
      const requested = box.querySelector('img').getAttribute('src');
      openLightbox(url);
      const viewer = document.querySelector('#lbImg').getAttribute('src');
      closeLightbox();
      box._dispose && box._dispose();
      box.remove();
      return JSON.stringify({requested, viewer});
    })()
    '''
    a.win.web.run_javascript(js, None, done2, None)

def done2(view, res, *_):
    result['thumb'] = json.loads(js_result(view, res) or '{}')
    try:
        result['spellcheck'] = a.win.web.get_context().get_spell_checking_enabled()
    except Exception as e:
        result['spellcheck'] = 'ERR ' + type(e).__name__
    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(result, fh, indent=2, sort_keys=True)
    print(json.dumps(result, sort_keys=True), flush=True)
    Gtk.main_quit()

def step():
    js = r'''
    (() => {
      const url = '%s';
      const ch = S.channel.id;
      for (let i = 0; i < 30; i++) {
        window.tpEvent({type:'message_create', data:{
          id: 'img' + i, channel_id: ch,
          timestamp: new Date(Date.now() + i * 1000).toISOString(),
          author: {id: 'u2', username: 'u2', global_name: 'u2'},
          content: '', attachments: [{url: url, filename: 'x.png',
            content_type: 'image/png', width: 200, height: 200}]
        }});
      }
      document.querySelectorAll('#msgList .mediaCover').forEach(c => c.click());
      return JSON.stringify({dom: document.querySelectorAll('#msgList .msg').length,
        covers: document.querySelectorAll('#msgList .mediaCover').length});
    })()
    ''' % PNG
    a.win.web.run_javascript(js, None, lambda *_: None, None)
    GLib.timeout_add(900, scroll_away)
    return False

def scroll_away():
    js = r'''
    (() => {
      const b = document.querySelector('#msgs');
      b.scrollTop = 0;
      b.dispatchEvent(new Event('scroll'));
      return 'top';
    })()
    '''
    a.win.web.run_javascript(js, None, lambda *_: None, None)
    GLib.timeout_add(1100, measure)
    return False

def measure():
    js = r'''
    (() => {
      const imgs = [...document.querySelectorAll('#msgList .mediaImg')];
      const boxes = [...document.querySelectorAll('#msgList .mediaBox')];
      const withSrc = imgs.filter(i => i.getAttribute('src')).length;
      const revealed = boxes.filter(b => b.classList.contains('revealed')).length;
      const covers = boxes.filter(b => b.querySelector('.mediaCover') &&
        !b.querySelector('.mediaCover').classList.contains('hidden')).length;
      return JSON.stringify({imgs: imgs.length, withSrc, revealed, covers});
    })()
    '''
    a.win.web.run_javascript(js, None, done, None)
    return False

a = target.App(mock=True); a.start()
GLib.timeout_add(3500, step)
Gtk.main()
