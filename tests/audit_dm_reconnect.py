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
    print('DM_AUDIT_FALHA ' + str(message), file=sys.stderr, flush=True)
    Gtk.main_quit()


def validate(data):
    a = data['resultA']
    assert a['found'] is True
    assert a['calls'] == [
        {'channel': '100', 'limit': 100},
        {'channel': '21', 'after': '200', 'limit': 100},
        {'channel': '22', 'after': '300', 'limit': 100},
    ], a['calls']
    assert a['last21'] == '203' and a['last22'] == '302'
    assert a['unread21'] == 2 and a['unread22'] == 2
    assert a['dms'] == ['21', '22', '23', '24', '26'], a['dms']
    assert a['recovering'] is False and a['syncing'] is False

    b = data['resultB']
    assert b['found'] is True
    assert b['afterCalls'] == [str(i) for i in range(30, 40)], b['afterCalls']
    assert b['count'] == 10
    assert b['secondFound'] is True
    assert b['secondAfterCalls'] == ['40', '41'], b['secondAfterCalls']
    assert b['thirdFound'] is False and b['thirdAfterCalls'] == 0
    assert b['lastCount'] == 12

    c = data['resultC']
    assert c['found'] is True
    assert c['calls'] == [{'channel': '50', 'limit': 100}], c['calls']
    assert c['last'] == '901' and c['newest'] == '901' and c['len'] == 2

    d = data['resultD']
    assert d['found'] is True
    assert d['last60'] == '600' and d['last61'] == '701'
    assert d['unread61'] == 1
    assert d['afterCalls'] == ['60', '61'], d['afterCalls']
    assert d['recovering'] is False and d['syncing'] is False


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
            print('DM_AUDIT ' + text, flush=True)
            Gtk.main_quit()
    except Exception as e:
        fail(f'{type(e).__name__}: {e}')


def poll():
    a.win.web.run_javascript('window.__dmAudit || null', None, got, None)
    return True


def step():
    js = r'''
    window.__dmAudit = null;
    (async () => {
      try {
        const mk = (id, ch) => ({id:String(id), channel_id:String(ch),
          timestamp:new Date(1700000000000 + Number(id) * 1000).toISOString(),
          author:{id:'u1',username:'u1'}, content:'m' + id});
        const channel = (id, last) => ({id:String(id), type:1,
          last_message_id:last == null ? null : String(last),
          recipients:[{id:'u' + id, username:'user' + id}]});
        const orig = call;
        const calls = [];
        let dmsPayload = [];
        let activePayload = [];
        const afterPayload = new Map();
        const failures = new Set();

        call = (cmd, args = {}) => {
          if (cmd === 'dms') {
            calls.push({cmd:'dms'});
            return Promise.resolve(dmsPayload.map((ch) => Object.assign({}, ch)));
          }
          if (cmd === 'messages') {
            calls.push({cmd:'messages', args:Object.assign({}, args)});
            const cid = String(args.channel);
            if (args.after != null) {
              if (failures.has(cid)) {
                return Promise.reject(new Error('falha simulada em ' + cid));
              }
              const rows = afterPayload.get(cid) || [];
              return Promise.resolve(rows.map((m) => Object.assign({}, m)));
            }
            return Promise.resolve(activePayload.map((m) => Object.assign({}, m)));
          }
          return orig(cmd, args);
        };

        const messageCalls = () => calls.filter((c) => c.cmd === 'messages');
        const afterCalls = () => messageCalls().filter((c) => c.args.after != null);
        const resetCalls = () => { calls.length = 0; };

        // A) conversa ativa + DMs conhecidas: usa after, deduplica e respeita
        // last_message_id, DM oculta e DM sem ultimo ID conhecido.
        S.kind = 'guild';
        S.channel = {id:'100', name:'notas', dm:false};
        S.dms = [
          channel(21, 205), channel(22, 305), channel(23, 150),
          channel(24, null), channel(25, 405), channel(26, 505),
        ];
        S.hiddenDMs = new Set(['25']);
        S.lastByChannel = new Map([
          ['100', '1100'], ['21', '200'], ['22', '300'],
          ['23', '150'], ['25', '400'],
        ]);
        S.seen.clear();
        replaceWindow(Array.from({length:101}, (_, k) => mk(1000 + k, 100)), true);
        S.seen.add('201');
        dmsPayload = S.dms.map((ch) => Object.assign({}, ch));
        activePayload = [mk(1101, 100), mk(1100, 100)];
        afterPayload.clear();
        afterPayload.set('21', [mk(203, 21), mk(202, 21), mk(201, 21)]);
        afterPayload.set('22', [mk(302, 22), mk(301, 22)]);
        failures.clear();
        resetCalls();
        const foundA = await recoverAfterReconnect();
        const callsA = messageCalls().map((c) => Object.assign({}, c.args));
        const resultA = {
          found: foundA,
          calls: callsA,
          last21: S.lastByChannel.get('21'),
          last22: S.lastByChannel.get('22'),
          unread21: S.unread['21'] || 0,
          unread22: S.unread['22'] || 0,
          dms: S.dms.map((ch) => ch.id),
          recovering: S.recovering,
          syncing: S.syncing,
        };

        // B) limite de 10 DMs por reconexao e segunda passada sem refetch.
        S.kind = 'dm';
        S.channel = null;
        S.dms = Array.from({length:12}, (_, k) => channel(30 + k, 105));
        S.lastByChannel = new Map(S.dms.map((ch) => [ch.id, '100']));
        S.hiddenDMs = new Set();
        S.seen.clear();
        resetHistory(true);
        dmsPayload = S.dms.map((ch) => Object.assign({}, ch));
        activePayload = [];
        afterPayload.clear();
        S.dms.forEach((ch, k) => afterPayload.set(ch.id, [mk(2000 + k, ch.id)]));
        failures.clear();
        resetCalls();
        const foundB = await recoverAfterReconnect();
        const callsB = afterCalls().map((c) => c.args.channel);
        const bLast = new Map(S.lastByChannel);
        resetCalls();
        const foundB2 = await recoverAfterReconnect();
        const callsB2 = afterCalls().map((c) => c.args.channel);
        resetCalls();
        const foundB3 = await recoverAfterReconnect();
        const callsB3 = afterCalls().length;
        const resultB = {
          found: foundB,
          afterCalls: callsB,
          count: callsB.length,
          secondFound: foundB2,
          secondAfterCalls: callsB2,
          thirdFound: foundB3,
          thirdAfterCalls: callsB3,
          lastCount: bLast.size,
        };

        // C) DM ativa nao e recuperada por after: usa a sincronizacao da
        // conversa aberta, que busca a pagina recente.
        S.kind = 'dm';
        S.channel = {id:'50', name:'amigo', dm:true};
        S.dms = [channel(50, 909)];
        S.hiddenDMs = new Set();
        S.lastByChannel = new Map([['50', '900']]);
        S.seen.clear();
        replaceWindow([mk(900, 50)], true);
        dmsPayload = S.dms.map((ch) => Object.assign({}, ch));
        activePayload = [mk(901, 50), mk(900, 50)];
        afterPayload.clear();
        failures.clear();
        resetCalls();
        const foundC = await recoverAfterReconnect();
        const resultC = {
          found: foundC,
          calls: messageCalls().map((c) => Object.assign({}, c.args)),
          last: S.lastByChannel.get('50'),
          len: S.messages.length,
          newest: S.newest,
        };

        // D) falha em uma DM nao impede as seguintes.
        S.kind = 'dm';
        S.channel = null;
        S.dms = [channel(60, 605), channel(61, 705)];
        S.lastByChannel = new Map([['60', '600'], ['61', '700']]);
        S.hiddenDMs = new Set();
        S.seen.clear();
        resetHistory(true);
        dmsPayload = S.dms.map((ch) => Object.assign({}, ch));
        activePayload = [];
        afterPayload.clear();
        afterPayload.set('60', [mk(601, 60)]);
        afterPayload.set('61', [mk(701, 61)]);
        failures.clear();
        failures.add('60');
        resetCalls();
        const foundD = await recoverAfterReconnect();
        const resultD = {
          found: foundD,
          last60: S.lastByChannel.get('60'),
          last61: S.lastByChannel.get('61'),
          unread61: S.unread['61'] || 0,
          afterCalls: afterCalls().map((c) => c.args.channel),
          recovering: S.recovering,
          syncing: S.syncing,
        };

        call = orig;
        window.__dmAudit = JSON.stringify({resultA, resultB, resultC, resultD});
      } catch (e) {
        window.__dmAudit = JSON.stringify({error:String(e && (e.stack || e))});
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
