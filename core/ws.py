"""Cliente WebSocket minimo (RFC 6455) para o gateway do Discord.

Sem dependencias externas: socket + ssl + struct. Suporta frames
fragmentados, ping/pong, mensagens de texto e preserva bytes que chegam
junto com a resposta do handshake (o HELLO costuma vir no mesmo pacote).
"""
import base64
import json
import os
import socket
import ssl
import struct
import threading
from urllib.parse import urlparse


class WebSocket:
    def __init__(self, url, on_json, on_close=None, timeout=20):
        p = urlparse(url)
        self.host = p.hostname
        self.port = p.port or 443
        self.path = p.path + (("?" + p.query) if p.query else "")
        self.on_json = on_json
        self.on_close = on_close
        self._closed = False
        self._buf = b""
        self._lock = threading.Lock()

        raw = socket.create_connection((self.host, self.port), timeout=timeout)
        ctx = ssl.create_default_context()
        self.sock = ctx.wrap_socket(raw, server_hostname=self.host)
        self.sock.settimeout(None)
        self._handshake()

        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _handshake(self):
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "Origin: https://discord.com\r\n"
            "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise IOError("handshake sem resposta")
            buf += chunk
        head, self._buf = buf.split(b"\r\n\r\n", 1)
        status = head.split(b"\r\n", 1)[0]
        if b" 101 " not in status:
            raise IOError("handshake recusado: " + status.decode(errors="ignore"))

    def send(self, obj):
        data = json.dumps(obj, separators=(",", ":")).encode()
        self._frame(0x81, data)

    def _frame(self, first, data):
        mask = os.urandom(4)
        n = len(data)
        header = bytearray([first])
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        frame = bytes(header) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        with self._lock:
            if self._closed:
                return
            self.sock.sendall(frame)

    def _recv(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(max(4096, n - len(self._buf)))
            if not chunk:
                raise EOFError
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _pong(self, payload):
        try:
            self._frame(0x8A, payload)
        except Exception:
            pass

    def _loop(self):
        msg = b""
        code = None
        reason = ""
        try:
            while not self._closed:
                head = self._recv(2)
                fin = head[0] & 0x80
                op = head[0] & 0x0F
                ln = head[1] & 0x7F
                if ln == 126:
                    ln = struct.unpack(">H", self._recv(2))[0]
                elif ln == 127:
                    ln = struct.unpack(">Q", self._recv(8))[0]
                data = self._recv(ln) if ln else b""

                if op == 9:      # ping
                    self._pong(data)
                    continue
                if op == 10:     # pong
                    continue
                if op == 8:      # close
                    if len(data) >= 2:
                        code = struct.unpack(">H", data[:2])[0]
                        reason = data[2:].decode(errors="ignore")
                    break
                if op in (1, 2):
                    msg = data
                elif op == 0:
                    msg += data

                if fin and msg:
                    try:
                        self.on_json(json.loads(msg))
                    except Exception:
                        pass
                    msg = b""
        except Exception:
            pass
        finally:
            self._closed = True
            try:
                self.sock.close()
            except Exception:
                pass
            if self.on_close:
                try:
                    self.on_close(code, reason)
                except Exception:
                    pass

    def close(self):
        self._closed = True
        try:
            self.sock.close()
        except Exception:
            pass
