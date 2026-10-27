import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import gi

gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import GLib, Gtk

import app

FAILED = False


def fail(message):
    global FAILED
    FAILED = True
    print('UI_FINAL_FALHA ' + str(message), file=sys.stderr, flush=True)
    Gtk.main_quit()


def validate(data):
    content = data['content']
    assert content['title'] == 'Central de informações'
    assert content['version'] == 'v2.4.0'
    assert content['creator'] == 'André Alves'
    assert content['role'] == 'dialog' and content['modal'] == 'true'
    assert content['labelledby'] == 'infoTitle'
    assert content['helpAria'] == 'Sobre o 4Cord'
    assert [t['text'] for t in content['tabs']] == [
        'Sobre', 'Etapas', 'Tecnologias']
    assert all(t['role'] == 'tab' for t in content['tabs'])
    assert content['sections'] == [
        'infoAbout', 'infoSteps', 'infoTech', 'infoAdvanced']

    assert data['settingsBefore'] is True
    opened = data['open']
    assert opened == {
        'visible': True, 'settingsClosed': True, 'friendsClosed': True,
        'about': True, 'steps': False, 'tech': False, 'focusClose': True,
    }, opened

    steps = data['tabSteps']
    assert steps['steps'] is True and steps['aboutHidden'] is True
    assert steps['selected'] == 'true' and steps['aboutSelected'] == 'false'
    assert steps['tabIndex'] == 0

    arrow = data['tabArrow']
    assert arrow == {'tech': True, 'selected': 'true', 'focus': True}, arrow

    advanced = data['advanced']
    assert advanced == {
        'open': True, 'tabsHidden': True, 'backVisible': True,
        'focusBack': True,
    }, advanced
    back = data['back']
    assert back == {
        'tech': True, 'advancedClosed': True, 'tabsVisible': True,
        'focusTech': True,
    }, back
    assert data['trapForward'] is True and data['trapBack'] is True
    assert data['esc'] == {'hidden': True, 'focusHelp': True}, data['esc']
    assert data['backdrop'] == {'hidden': True}, data['backdrop']

    send = data['send']
    assert send['text'] == '' and send['svg'] == 1
    assert send['aria'] == 'Enviar mensagem'
    assert send['title'] == 'Enviar mensagem'
    assert send['svgHidden'] == 'true'
    sent = data['sentResult']
    assert sent['args'] == {'channel': '100', 'content': 'teste do ícone'}
    assert sent['input'] == '' and sent['sending'] is False
    assert sent['disabled'] is False

    reload_ = data['reload']
    assert reload_['calls'] == 1
    assert reload_['toast'] == 'Mensagens sincronizadas.'
    assert reload_['hidden'] is False


def got(view, res, *_):
    try:
        val = view.run_javascript_finish(res).get_js_value()
        text = val.to_string() if val else ''
        if text and text != 'null':
            data = json.loads(text)
            if data.get('error'):
                fail(data['error'])
                return
            validate(data)
            print('UI_FINAL ' + text, flush=True)
            Gtk.main_quit()
    except Exception as e:
        fail(f'{type(e).__name__}: {e}')


def poll():
    a.win.web.run_javascript('window.__uiFinal || null', None, got, None)
    return True


def step():
    js = r'''
    window.__uiFinal = null;
    (async () => {
      try {
        const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
        const visible = (sel) => {
          const n = document.querySelector(sel);
          if (!n || n.classList.contains('hidden')) return false;
          const style = getComputedStyle(n);
          return style.display !== 'none' && style.visibility !== 'hidden'
            && n.getClientRects().length > 0;
        };
        const panel = $('#info');
        const focusables = () => [...panel.querySelectorAll(
          'button:not(:disabled):not(.hidden), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        )].filter((n) => n.offsetParent !== null);

        // Conteúdo e semântica da central de informações.
        const content = {
          title: $('#infoTitle').textContent.trim(),
          version: $('#infoVersion').textContent.trim(),
          creator: $('#creatorName').textContent.trim(),
          tabs: [...document.querySelectorAll('.infoTab')].map((b) => ({
            text: b.textContent.trim(), role: b.getAttribute('role'),
            controls: b.getAttribute('aria-controls'),
          })),
          sections: [...document.querySelectorAll('.infoSection')].map((s) => s.id),
          role: panel.getAttribute('role'),
          modal: panel.getAttribute('aria-modal'),
          labelledby: panel.getAttribute('aria-labelledby'),
          helpAria: $('#helpBtn').getAttribute('aria-label'),
        };

        // Abrir a central fecha ajustes e leva o foco ao botão fechar.
        $('#settingsBtn').click();
        const settingsBefore = visible('#settings');
        $('#helpBtn').focus();
        $('#helpBtn').click();
        const open = {
          visible: visible('#info'),
          settingsClosed: !visible('#settings'),
          friendsClosed: !visible('#friends'),
          about: visible('#infoAbout'),
          steps: visible('#infoSteps'),
          tech: visible('#infoTech'),
          focusClose: document.activeElement === $('#infoClose'),
        };

        // Abas, teclado e ARIA.
        $('#infoTabSteps').click();
        const tabSteps = {
          steps: visible('#infoSteps'),
          aboutHidden: !visible('#infoAbout'),
          selected: $('#infoTabSteps').getAttribute('aria-selected'),
          aboutSelected: $('#infoTabAbout').getAttribute('aria-selected'),
          tabIndex: $('#infoTabSteps').tabIndex,
        };
        $('#infoTabSteps').dispatchEvent(new KeyboardEvent('keydown', {
          key:'ArrowRight', bubbles:true, cancelable:true,
        }));
        const tabArrow = {
          tech: visible('#infoTech'),
          selected: $('#infoTabTech').getAttribute('aria-selected'),
          focus: document.activeElement === $('#infoTabTech'),
        };

        // Detalhes avançados: abas ocultas, foco no voltar e retorno ao
        // painel anterior sem deixar o foco em um elemento oculto.
        $('#infoAdvancedBtn').click();
        const advanced = {
          open: visible('#infoAdvanced'),
          tabsHidden: !visible('#infoTabs'),
          backVisible: visible('#infoBack'),
          focusBack: document.activeElement === $('#infoBack'),
        };
        $('#infoBack').click();
        const back = {
          tech: visible('#infoTech'),
          advancedClosed: !visible('#infoAdvanced'),
          tabsVisible: visible('#infoTabs'),
          focusTech: document.activeElement === $('#infoTabTech'),
        };

        // Tab e Shift+Tab circulam dentro do diálogo.
        const f1 = focusables();
        const first = f1[0], last = f1[f1.length - 1];
        last.focus();
        last.dispatchEvent(new KeyboardEvent('keydown', {
          key:'Tab', bubbles:true, cancelable:true,
        }));
        const trapForward = document.activeElement === first;
        first.dispatchEvent(new KeyboardEvent('keydown', {
          key:'Tab', shiftKey:true, bubbles:true, cancelable:true,
        }));
        const trapBack = document.activeElement === last;

        // Esc fecha e devolve o foco ao botão que abriu.
        document.dispatchEvent(new KeyboardEvent('keydown', {
          key:'Escape', bubbles:true, cancelable:true,
        }));
        const esc = {
          hidden: !visible('#info'),
          focusHelp: document.activeElement === $('#helpBtn'),
        };

        // Clique no fundo também fecha.
        $('#helpBtn').focus();
        $('#helpBtn').click();
        panel.dispatchEvent(new MouseEvent('click', {bubbles:true}));
        const backdrop = {hidden: !visible('#info')};

        // Botão de envio: ícone único, rótulo acessível e envio preservado.
        const sendBtn = $('#sendBtn');
        const send = {
          text: (sendBtn.textContent || '').trim(),
          svg: sendBtn.querySelectorAll('svg').length,
          aria: sendBtn.getAttribute('aria-label'),
          title: sendBtn.getAttribute('title'),
          svgHidden: sendBtn.querySelector('svg').getAttribute('aria-hidden'),
        };
        const origCall = call;
        let sent = null;
        call = (cmd, args = {}) => {
          if (cmd === 'send') {
            sent = Object.assign({}, args);
            return Promise.resolve({
              id:'9999', channel_id:args.channel,
              timestamp:new Date().toISOString(),
              author:{id:'u1', username:'u1'}, content:args.content,
            });
          }
          return origCall(cmd, args);
        };
        S.channel = {id:'100', name:'notas', dm:false};
        S.sending = false;
        $('#input').value = 'teste do ícone';
        sendBtn.click();
        await sleep(30);
        const sentResult = {
          args: sent,
          input: $('#input').value,
          sending: S.sending,
          disabled: sendBtn.disabled,
        };
        call = origCall;

        // Recarregar usa a mesma recuperação da reconexão.
        const origRecover = recoverAfterReconnect;
        let recoverCalls = 0;
        recoverAfterReconnect = async () => { recoverCalls += 1; return false; };
        S.loadingChannel = false; S.loadingOlder = false;
        S.syncing = false; S.recovering = false;
        await reloadMessages();
        const reload = {
          calls: recoverCalls,
          toast: $('#toast').textContent.trim(),
          hidden: $('#toast').classList.contains('hidden'),
        };
        recoverAfterReconnect = origRecover;

        window.__uiFinal = JSON.stringify({
          content, settingsBefore, open, tabSteps, tabArrow, advanced, back,
          trapForward, trapBack, esc, backdrop, send, sentResult, reload,
        });
      } catch (e) {
        window.__uiFinal = JSON.stringify({error:String(e && (e.stack || e))});
      }
    })();
    null
    '''
    a.win.web.run_javascript(js, None, lambda *_: None, None)
    GLib.timeout_add(1200, poll)
    return False


a = app.App(mock=True)
a.start()
GLib.timeout_add(3500, step)
Gtk.main()
if FAILED:
    sys.exit(1)
