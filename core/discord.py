"""Camada de acesso ao Discord: REST v9 + gateway (WebSocket)."""
import json
import mimetypes
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from urllib.parse import quote

from .log import log
from .ws import WebSocket

API = "https://discord.com/api/v9"
GATEWAY = "wss://gateway.discord.gg/?v=10&encoding=json"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/156.0.0.0 Safari/537.36")

# codigos de fechamento em que reconectar nao adianta
FATAL_CLOSE = {4004, 4010, 4011, 4012, 4013, 4014}


class DiscordError(Exception):
    def __init__(self, status, body):
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body[:200]}")


class Discord:
    def __init__(self, token, on_event):
        self.token = token
        self.on_event = on_event          # chamado da thread do gateway
        self.ws = None
        self.seq = None
        self.user = None
        self.session_id = None
        self.resume_url = None
        self.connected = False
        self._resume = False
        self._stop = False
        self._fatal = False
        self._was_ready = False
        self._hb_stop = threading.Event()
        self._hb_thread = None
        self._last_ack = time.time()
        self._thread = None

    # ---------------- REST ----------------
    def _request(self, method, path, body=None, raw_body=None, content_type=None,
                 timeout=25, retry=True):
        headers = {
            "Authorization": self.token,
            "User-Agent": UA,
            "Accept": "*/*",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        }
        data = None
        if raw_body is not None:
            data = raw_body
            headers["Content-Type"] = content_type
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = resp.read()
                log(f"REST {method} {path} -> {resp.status}")
                return json.loads(payload) if payload else None
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="ignore")
            log(f"REST {method} {path} -> {e.code} {text[:300]}", critical=True)
            if e.code == 429 and retry:
                try:
                    wait = float(json.loads(text).get("retry_after", 1.0))
                except Exception:
                    wait = 1.0
                time.sleep(min(wait, 10))
                return self._request(method, path, body, raw_body, content_type,
                                     timeout, retry=False)
            raise DiscordError(e.code, text)
        except Exception as e:
            log(f"REST {method} {path} -> erro {type(e).__name__}: {e}", critical=True)
            raise

    def me(self):
        return self._request("GET", "/users/@me")

    def guilds(self):
        return self._request("GET", "/users/@me/guilds")

    def dms(self):
        return self._request("GET", "/users/@me/channels")

    def friends(self):
        rels = self._request("GET", "/users/@me/relationships") or []
        return [r for r in rels if r.get("type") == 1 and r.get("user")]

    def open_dm(self, user_id):
        return self._request("POST", "/users/@me/channels", {
            "recipient_id": user_id,
        })

    def guild_channels(self, guild_id):
        return self._request("GET", f"/guilds/{guild_id}/channels")

    def roles(self, guild_id):
        return self._request("GET", f"/guilds/{guild_id}/roles")

    def messages(self, channel_id, before=None, limit=50, after=None):
        q = f"?limit={limit}"
        if before:
            q += f"&before={before}"
        elif after:
            # Recuperacao de mensagens perdidas durante uma desconexao.
            q += f"&after={after}"
        return self._request("GET", f"/channels/{channel_id}/messages{q}")

    def react(self, channel_id, message_id, emoji, remove=False):
        if not emoji:
            raise ValueError("emoji ausente")
        path = (f"/channels/{channel_id}/messages/{message_id}/reactions/"
                f"{quote(str(emoji), safe='')}/@me")
        return self._request("DELETE" if remove else "PUT", path)

    def interact(self, args):
        if not self.session_id:
            raise ValueError("sessão do gateway indisponível")
        app_id = args.get("application_id")
        custom_id = args.get("custom_id")
        if not app_id or not custom_id:
            raise ValueError("componente sem identificação")
        payload = {
            "type": 3,
            "nonce": str(int(time.time() * 1000)) + "000",
            "channel_id": args.get("channel"),
            "message_id": args.get("message"),
            "application_id": app_id,
            "session_id": self.session_id,
            "message_flags": 0,
            "data": {
                "component_type": int(args.get("component_type") or 2),
                "custom_id": custom_id,
            },
        }
        if args.get("guild"):
            payload["guild_id"] = args["guild"]
        if args.get("values"):
            payload["data"]["values"] = args["values"]
        return self._request("POST", "/interactions", payload)

    def send(self, channel_id, content):
        log(f"send canal={channel_id} chars={len(content or '')}")
        return self._request("POST", f"/channels/{channel_id}/messages", {
            "content": content,
            "nonce": str(int(time.time() * 1000)) + "000",
            "tts": False,
        })

    def send_file(self, channel_id, content, path):
        boundary = "----4Cord" + uuid.uuid4().hex
        payload = {"content": content or "", "tts": False}
        filename = os.path.basename(path)
        ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        body = bytearray()
        body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                 f'name="payload_json"\r\nContent-Type: application/json\r\n\r\n'
                 f"{json.dumps(payload)}\r\n").encode()
        body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                 f'name="files[0]"; filename="{filename}"\r\n'
                 f"Content-Type: {ctype}\r\n\r\n").encode()
        with open(path, "rb") as fh:
            body += fh.read()
        body += f"\r\n--{boundary}--\r\n".encode()

        log(f"upload canal={channel_id} arquivo={filename}")
        return self._request("POST", f"/channels/{channel_id}/messages",
                             raw_body=bytes(body),
                             content_type=f"multipart/form-data; boundary={boundary}",
                             timeout=120)

    def typing(self, channel_id):
        try:
            self._request("POST", f"/channels/{channel_id}/typing", {}, timeout=10)
        except Exception:
            pass

    # ---------------- gateway ----------------
    def connect(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop = False
        self._fatal = False
        self._thread = threading.Thread(target=self._connect_loop, daemon=True)
        self._thread.start()

    def _gateway_url(self):
        if self._resume and self.resume_url:
            base = self.resume_url.rstrip("/")
            if "?" not in base:
                base += "/?v=10&encoding=json"
            return base
        return GATEWAY

    def _connect_loop(self):
        backoff = 2
        while not self._stop and not self._fatal:
            url = self._gateway_url()
            self._resume = bool(self.session_id and self.seq is not None)
            log("gateway conectando" + (" (retomar sessao)" if self._resume else ""))
            try:
                self.ws = WebSocket(url, self._on_gateway, self._on_ws_close)
                self.ws.thread.join()
            except Exception as e:
                log(f"gateway falha ao conectar: {type(e).__name__}: {e}", critical=True)
            self.connected = False
            self._hb_stop.set()
            self._emit_status()
            if self._stop or self._fatal:
                break
            if self._was_ready:
                backoff = 2
                self._was_ready = False
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)

    def _on_ws_close(self, code=None, reason=""):
        log(f"gateway fechado codigo={code} motivo={reason[:120]}",
            critical=(code not in (None, 1000)))
        self.connected = False
        self._hb_stop.set()
        if code in FATAL_CLOSE:
            self._fatal = True
            self.on_event({"type": "gateway_error",
                           "data": {"code": code, "fatal": True}})
        self._emit_status()

    def _emit_status(self):
        try:
            self.on_event({"type": "gateway",
                           "data": {"connected": self.connected}})
        except Exception:
            pass

    def _on_gateway(self, msg):
        op = msg.get("op")
        d = msg.get("d")

        if op == 10:  # hello
            interval = float(d.get("heartbeat_interval", 41250)) / 1000.0
            log(f"gateway HELLO intervalo={interval:.1f}s")
            self._start_heartbeat(interval)
            if self._resume and self.session_id and self.seq is not None:
                self._send({"op": 6, "d": {
                    "token": self.token,
                    "session_id": self.session_id,
                    "seq": self.seq,
                }})
                log("gateway RESUME enviado")
            else:
                self._identify()

        elif op == 11:  # heartbeat ACK
            self._last_ack = time.time()

        elif op == 1:  # servidor pedindo heartbeat
            self._send({"op": 1, "d": self.seq})

        elif op == 7:  # reconnect
            log("gateway pediu reconexao (op 7)")
            self._resume = True
            try:
                self.ws.close()
            except Exception:
                pass

        elif op == 9:  # invalid session
            log("gateway sessao invalida (op 9)", critical=True)
            self._resume = False
            self.session_id = None
            self.seq = None
            try:
                self.ws.close()
            except Exception:
                pass

        elif op == 0:  # evento
            if msg.get("s") is not None:
                self.seq = msg.get("s")
            t = msg.get("t")

            if t == "READY":
                self.user = d.get("user")
                self.session_id = d.get("session_id")
                self.resume_url = d.get("resume_gateway_url")
                self.connected = True
                self._resume = False
                self._was_ready = True
                log("gateway READY user=" + str((self.user or {}).get("username")) +
                    " guilds=" + str(len(d.get("guilds", []))) +
                    " dms=" + str(len(d.get("private_channels", []))))
                self.on_event({"type": "ready", "data": {
                    "user": self.user,
                    "guilds": d.get("guilds", []),
                    "guild_order": [g.get("id") for g in d.get("guilds", [])],
                    "private_channels": d.get("private_channels", []),
                }})
                self._emit_status()

            elif t == "RESUMED":
                self.connected = True
                self._resume = False
                self._was_ready = True
                log("gateway RESUMED")
                self.on_event({"type": "resumed", "data": {}})
                self._emit_status()

            elif t in ("MESSAGE_CREATE", "MESSAGE_UPDATE", "MESSAGE_DELETE",
                       "MESSAGE_DELETE_BULK", "TYPING_START", "CHANNEL_CREATE"):
                self.on_event({"type": t.lower(), "data": d})

    def _identify(self):
        log("gateway IDENTIFY")
        self._last_ack = time.time()
        self._send({
            "op": 2,
            "d": {
                "token": self.token,
                "capabilities": 16381,
                "properties": {
                    "os": "Linux",
                    "browser": "Chrome",
                    "device": "",
                    "system_locale": "pt-BR",
                    "browser_user_agent": UA,
                    "browser_version": "156.0.0.0",
                    "os_version": "",
                    "referrer": "",
                    "referring_domain": "",
                    "release_channel": "stable",
                    "client_build_number": 350000,
                },
                "presence": {"status": "online", "since": 0,
                             "activities": [], "afk": False},
                "compress": False,
            },
        })

    def _start_heartbeat(self, interval):
        """Inicia um heartbeat novo e encerra o da conexao anterior.

        Cada conexao recebe um Event proprio. Reutilizar o mesmo Event numa
        reconexao podia deixar a thread antiga viva ou criar heartbeats
        duplicados depois de varias quedas.
        """
        old_stop = self._hb_stop
        old_stop.set()
        stop = threading.Event()
        self._hb_stop = stop
        self._last_ack = time.time()
        self._hb_thread = threading.Thread(
            target=self._heartbeat, args=(interval, stop), daemon=True)
        self._hb_thread.start()

    def _heartbeat(self, interval, stop):
        while not stop.wait(interval):
            if time.time() - self._last_ack > interval * 2.5:
                log("gateway sem ACK; forcando reconexao", critical=True)
                self._resume = True
                try:
                    self.ws.close()
                except Exception:
                    pass
                return
            self._send({"op": 1, "d": self.seq})

    def _send(self, obj):
        try:
            if self.ws:
                self.ws.send(obj)
        except Exception as e:
            log(f"gateway envio falhou: {type(e).__name__}", critical=True)

    def close(self):
        self._stop = True
        self._hb_stop.set()
        if self.ws:
            self.ws.close()
