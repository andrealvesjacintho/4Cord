"""Log simples em arquivo para diagnostico do 4Cord.

Por padrao grava apenas erros e eventos criticos. O log detalhado pode ser
ativado em Ajustes. Nunca registra credenciais de autenticacao nem o conteudo
das mensagens: no maximo comando, canal, tamanho do texto e erros HTTP/gateway.
"""
import os
import re
import threading
import time

CONF_DIR = os.path.expanduser("~/.config/4cord")
LOG_FILE = os.path.join(CONF_DIR, "log.txt")
MAX_BYTES = 512 * 1024
_lock = threading.Lock()
_verbose = False

# Redige formatos parecidos com credenciais do Discord antes da escrita.
_TOKEN_RX = re.compile(r"(mfa\.[A-Za-z0-9_-]{20,}|[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{20,})")


def set_verbose(enabled):
    """Liga/desliga os registros detalhados (o padrao e somente criticos)."""
    global _verbose
    _verbose = bool(enabled)


def is_verbose():
    return _verbose


def log(text, critical=False):
    """Escreve uma linha de diagnostico.

    critical=True e usado para erros/falhas relevantes e sempre e gravado.
    Textos rotineiros (comandos, REST bem-sucedido, gateway) so aparecem com
    o log detalhado ativado.
    """
    if not (critical or _verbose):
        return
    try:
        os.makedirs(CONF_DIR, exist_ok=True)
        line = time.strftime("%Y-%m-%d %H:%M:%S ") + str(text) + "\n"
        line = _TOKEN_RX.sub("[token]", line)
        with _lock:
            try:
                if os.path.getsize(LOG_FILE) > MAX_BYTES:
                    rotated = LOG_FILE + ".1"
                    os.replace(LOG_FILE, rotated)
                    os.chmod(rotated, 0o600)
            except OSError:
                pass
            # Cria o log ja com 0600; ele pode conter caminhos e detalhes
            # internos, mesmo sem credenciais.
            fd = os.open(LOG_FILE, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as fh:
                try:
                    os.fchmod(fh.fileno(), 0o600)
                except OSError:
                    pass
                fh.write(line)
    except Exception:
        pass
