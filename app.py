#!/usr/bin/env python3
"""4Cord - cliente leve de Discord (GTK3 + WebKitGTK + API oficial).

Nao carrega o app web do Discord: a interface e propria e minúscula, e os
dados vem direto da API/gateway. Login acontece na pagina oficial (captcha
nativo) e as credenciais de autenticacao ficam somente em ~/.config/4cord/.
"""
import fcntl
import glob
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("WebKit2", "4.1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, WebKit2  # noqa: E402

from core.discord import Discord, DiscordError  # noqa: E402
from core.log import log, set_verbose  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
CONF_DIR = os.path.expanduser("~/.config/4cord")
# Compatibilidade: caminho usado apenas para migrar instalacoes anteriores.
LEGACY_CONF_DIR = os.path.expanduser("~/.config/trashpanda")
TOKEN_FILE = os.path.join(CONF_DIR, "token")
SETTINGS_FILE = os.path.join(CONF_DIR, "settings.json")
ICON_FILE = os.path.join(CONF_DIR, "appicon.png")
DEFAULT_ICON = os.path.join(BASE, "assets", "4cord.png")
DEFAULT_ICON_HD = os.path.join(BASE, "assets", "4cord-hd.png")
LAUNCHER = os.path.join(BASE, "bin", "4cord")
UI = os.path.join(BASE, "ui", "index.html")
VERSION = "2.4.0"
DEFAULT_NAME = "4Cord"
DESKTOP_FILE = os.path.expanduser("~/.local/share/applications/4cord.desktop")
# Nome legado reconhecido apenas para remover o atalho da versao anterior.
LEGACY_DESKTOP_FILE = os.path.expanduser("~/.local/share/applications/trashpanda.desktop")
# Marcador historico: impede migracao repetida e restauracao de credenciais.
MIGRATION_MARKER = os.path.join(CONF_DIR, ".migrated-from-trashpanda")
_SETTINGS_LOCK = threading.Lock()
_DESKTOP_LOCK = threading.Lock()


def migrate_legacy_config():
    """Copia a configuracao antiga uma unica vez, sem alterar o original.

    O marcador impede que um token apagado (logout) seja restaurado a cada
    inicializacao. Se a configuracao nova ja existe, nada e copiado.
    """
    if os.path.exists(MIGRATION_MARKER):
        return
    try:
        os.makedirs(CONF_DIR, exist_ok=True)
        legacy_present = os.path.isdir(LEGACY_CONF_DIR)
        initialized = os.path.exists(SETTINGS_FILE) or os.path.exists(TOKEN_FILE)
        if legacy_present and not initialized:
            for name in ("token", "settings.json", "appicon.png"):
                src = os.path.join(LEGACY_CONF_DIR, name)
                dst = os.path.join(CONF_DIR, name)
                if os.path.isfile(src) and not os.path.exists(dst):
                    shutil.copy2(src, dst)
                    if name in ("token", "settings.json"):
                        os.chmod(dst, 0o600)
        # O nome visivel antigo nao deve sobreviver na configuracao migrada.
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as fh:
                data = json.load(fh)
            name = data.get("name") if isinstance(data, dict) else None
            # Nome legado aceito apenas para normalizar a configuracao migrada.
            if isinstance(name, str) and name.strip().lower() == "trashpanda":
                data["name"] = DEFAULT_NAME
                save_settings(data)
        except (OSError, ValueError):
            pass
        if legacy_present or initialized:
            with open(MIGRATION_MARKER, "w", encoding="utf-8") as fh:
                fh.write("4Cord migration complete\n")
            os.chmod(MIGRATION_MARKER, 0o600)
    except Exception as e:
        log(f"migracao de configuracao falhou ({type(e).__name__}: {e})", critical=True)


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        name = data.get("name")
        # Nome legado aceito apenas para nao reaparecer na interface.
        if name in (None, "") or (isinstance(name, str) and
                                  name.strip().lower() == "trashpanda"):
            data["name"] = DEFAULT_NAME
        return data
    except Exception:
        return {}


def _settings_json(data):
    """Serializa um snapshot consistente do dicionario de configuracoes.

    As mutacoes feitas pelo app passam por update_settings() e ficam sob o
    mesmo lock, mas esta copia com retentativa protege chamadas externas que
    ainda compartilhem um dicionario mutavel.
    """
    snapshot = None
    for _ in range(50):
        try:
            snapshot = dict(data)
            break
        except RuntimeError:
            time.sleep(0.001)
    if snapshot is None:
        snapshot = dict(data)
    return json.dumps(snapshot, ensure_ascii=False)


def _write_settings_locked(data):
    payload = _settings_json(data)
    os.makedirs(CONF_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=CONF_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.chmod(tmp, 0o600)
        os.replace(tmp, SETTINGS_FILE)
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass


def save_settings(data):
    # Comandos da UI chegam em threads separadas (uma por mensagem da ponte).
    # Serializa a escrita para nunca gravar um dicionario em mutacao.
    with _SETTINGS_LOCK:
        _write_settings_locked(data)


def update_settings(data, **changes):
    """Aplica mudancas e grava sob o mesmo lock, sem perder atualizacoes."""
    with _SETTINGS_LOCK:
        data.update(changes)
        _write_settings_locked(data)


def clean_app_name(name):
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    # O nome antigo e tratado como vazio para manter a identidade 4Cord.
    if not name or name.lower() == "trashpanda":
        return DEFAULT_NAME
    return name[:40]


def icon_path(settings=None):
    settings = settings if settings is not None else load_settings()
    path = settings.get("icon")
    if path and os.path.isfile(path):
        return path
    return DEFAULT_ICON


def is_gnome_desktop():
    """Indica se a sessao atual usa a configuracao do GNOME.

    O 4Cord nao depende do GNOME: em Xfce e outros ambientes lemos apenas o
    Gtk.Settings. Assim o tema escolhido pelo usuario nao e sobrescrito por
    chaves do gsettings do GNOME. Sessoes Ubuntu com Xfce/KDE/MATE/Cinnamon
    (por exemplo, Xubuntu e Kubuntu) nao contam como GNOME.
    """
    values = " ".join(
        (os.environ.get(name) or "").lower()
        for name in ("XDG_CURRENT_DESKTOP", "DESKTOP_SESSION",
                     "XDG_SESSION_DESKTOP")
    )
    if any(name in values for name in (
            "xfce", "xubuntu", "kde", "plasma", "lxqt", "lxde", "mate",
            "cinnamon", "budgie", "sway", "i3", "openbox", "fluxbox")):
        return False
    return any(name in values for name in ("gnome", "unity", "ubuntu"))


def gnome_interface_settings():
    if not is_gnome_desktop():
        return None
    try:
        return Gio.Settings.new("org.gnome.desktop.interface")
    except Exception:
        return None


def system_prefers_dark():
    """Le a preferencia de cor do desktop, com fallback para GTK."""
    env_theme = (os.environ.get("GTK_THEME") or "").lower()
    if env_theme:
        return "dark" in env_theme
    iface = gnome_interface_settings()
    if iface is not None:
        try:
            scheme = iface.get_string("color-scheme")
            if scheme == "prefer-dark":
                return True
            if scheme == "prefer-light":
                return False
            name = iface.get_string("gtk-theme") or ""
            if name:
                return "dark" in name.lower()
        except Exception:
            pass
    try:
        st = Gtk.Settings.get_default()
        if not st:
            return False
        name = st.get_property("gtk-theme-name") or ""
        if "dark" in name.lower():
            return True
        return bool(st.get_property("gtk-application-prefer-dark-theme"))
    except Exception:
        return False


def theme_name_for(name, dark):
    """Escolhe a variante escura/clara de um tema instalado, quando existir."""
    if not name:
        return name
    if not dark or "dark" in name.lower():
        return name
    candidate = re.sub(r"light", "Dark", name, flags=re.I)
    if candidate == name:
        return name
    for base in ("~/.themes", "~/.local/share/themes", "/usr/share/themes"):
        if os.path.isdir(os.path.join(os.path.expanduser(base), candidate)):
            return candidate
    return name


def sync_gtk_theme(theme=None):
    """Alinha a barra de titulo e os controles GTK ao tema escolhido.

    O tema do aplicativo manda: dark/amoled forcam a variante escura; auto
    segue a preferencia do sistema. O nome do tema tambem e sincronizado com
    o gsettings para nao cair em HighContrast/light.
    """
    st = Gtk.Settings.get_default()
    if not st:
        return
    if theme in ("dark", "amoled"):
        dark = True
    elif theme == "auto":
        dark = system_prefers_dark()
    else:
        dark = system_prefers_dark()
    iface = gnome_interface_settings()
    if iface is not None:
        try:
            name = iface.get_string("gtk-theme")
            name = theme_name_for(name, dark)
            if name and st.get_property("gtk-theme-name") != name:
                st.set_property("gtk-theme-name", name)
        except Exception as e:
            log(f"tema: nao foi possivel ler o tema do sistema ({type(e).__name__}: {e})",
                critical=True)
    try:
        st.set_property("gtk-application-prefer-dark-theme", bool(dark))
    except Exception as e:
        log(f"tema: nao foi possivel aplicar variante escura ({type(e).__name__}: {e})", critical=True)


def apply_window_identity(win, settings=None):
    settings = settings if settings is not None else load_settings()
    win.set_title(clean_app_name(settings.get("name")))
    try:
        win.set_wmclass("4cord", "4Cord")
    except Exception:
        pass
    try:
        win.set_icon_from_file(icon_path(settings))
    except Exception as e:
        log(f"icone: nao foi possivel carregar ({type(e).__name__}: {e})", critical=True)


def _desktop_quote(value):
    """Escapa um caminho para o campo Exec do arquivo .desktop."""
    value = str(value).replace("\\", "\\\\").replace('"', '\\"')
    value = value.replace("$", "\\$").replace("`", "\\`")
    return '"' + value + '"'


def _desktop_entry_text(settings):
    name = clean_app_name(settings.get("name"))
    icon = icon_path(settings)
    return (
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Type=Application\n"
        f"Name={name}\n"
        "GenericName=Cliente leve de Discord\n"
        "Comment=Cliente leve de Discord com interface propria (texto, DMs e anexos)\n"
        f"Exec={_desktop_quote(LAUNCHER)}\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "Categories=Network;InstantMessaging;Chat;\n"
        "Keywords=discord;chat;4cord;mensagem;\n"
        "StartupWMClass=4cord\n"
        "StartupNotify=true\n"
    )


def ensure_desktop_entry(settings=None):
    """Cria/atualiza o atalho oficial do 4Cord e remove o atalho antigo."""
    settings = settings if settings is not None else load_settings()
    try:
        directory = os.path.dirname(DESKTOP_FILE)
        os.makedirs(directory, exist_ok=True)
        # Nome/icone podem ser alterados em threads diferentes; um temporario
        # por escrita evita que os.replace apague o arquivo do outro.
        with _DESKTOP_LOCK:
            fd, tmp = tempfile.mkstemp(prefix=".4cord-desktop-", dir=directory)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(_desktop_entry_text(settings))
                os.chmod(tmp, 0o644)
                os.replace(tmp, DESKTOP_FILE)
            finally:
                try:
                    if os.path.exists(tmp):
                        os.unlink(tmp)
                except OSError:
                    pass
            if os.path.isfile(LEGACY_DESKTOP_FILE):
                try:
                    os.remove(LEGACY_DESKTOP_FILE)
                except OSError:
                    pass
    except Exception as e:
        log(f"atalho: nao foi possivel atualizar ({type(e).__name__}: {e})", critical=True)


def update_desktop_entry(name=None, icon=None):
    """Mantem o atalho do menu do sistema alinhado ao nome/icone escolhidos."""
    # Le e grava sob o lock das configuracoes para nao capturar um estado
    # intermediario quando nome e icone mudam em threads diferentes.
    with _SETTINGS_LOCK:
        settings = load_settings()
        if name is not None:
            settings["name"] = clean_app_name(name)
        if icon is not None:
            settings["icon"] = icon
        ensure_desktop_entry(settings)


def js_str(value):
    try:
        return value.to_string()
    except Exception:
        pass
    try:
        return value.get_js_value().to_string()
    except Exception:
        return str(value)


def save_token(token):
    os.makedirs(CONF_DIR, exist_ok=True)
    # mkstemp cria o arquivo com 0600 desde o inicio; nao ha janela em que o
    # token fique legivel por outros usuarios antes do chmod.
    fd, tmp = tempfile.mkstemp(prefix=".token-", dir=CONF_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(token)
        os.chmod(tmp, 0o600)
        os.replace(tmp, TOKEN_FILE)
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass


def load_token():
    try:
        with open(TOKEN_FILE, encoding="utf-8") as fh:
            return fh.read().strip() or None
    except Exception:
        return None


def env_flag(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("", "0", "false", "no", "off")


def _proc_ppid(pid):
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as fh:
            data = fh.read()
        end = data.rfind(")")
        if end < 0:
            return None
        return int(data[end + 2:].split()[1])
    except Exception:
        return None


def _app_process_tree(root):
    """PIDs do 4Cord (principal + WebKit/GTK filhos), sem incluir outros apps."""
    children = {}
    for path in glob.glob("/proc/[0-9]*"):
        try:
            pid = int(os.path.basename(path))
        except ValueError:
            continue
        ppid = _proc_ppid(pid)
        if ppid is not None:
            children.setdefault(ppid, []).append(pid)
    seen = set()
    queue = [root]
    while queue:
        pid = queue.pop()
        if pid in seen:
            continue
        seen.add(pid)
        queue.extend(children.get(pid, []))
    return seen


def _proc_memory_kb(pid):
    """Retorna (KB, tipo), preferindo PSS de smaps_rollup para nao duplicar."""
    try:
        with open(f"/proc/{pid}/smaps_rollup", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("Pss:"):
                    return int(line.split()[1]), "pss"
    except Exception:
        pass
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]), "rss"
    except Exception:
        pass
    return 0, None


def ram_usage():
    """Estimativa agregada da RAM do app.

    Soma o PSS de todos os processos da arvore do 4Cord. PSS divide as paginas
    compartilhadas entre os processos, portanto nao ha dupla contagem. Quando
    um processo nao oferece smaps_rollup, usa VmRSS apenas para ele.
    """
    try:
        pids = sorted(_app_process_tree(os.getpid()))
        total = 0
        kinds = set()
        counted = 0
        for pid in pids:
            kb, kind = _proc_memory_kb(pid)
            if kind and kb > 0:
                total += kb
                kinds.add(kind)
                counted += 1
        if not counted:
            return {"ok": False, "error": "sem dados em /proc", "mb": None,
                    "processes": 0, "method": None}
        method = "PSS" if kinds == {"pss"} else ("RSS" if kinds == {"rss"} else "PSS+RSS")
        return {"ok": True, "mb": round(total / 1024.0, 1), "processes": counted,
                "method": method, "pids": counted}
    except Exception as e:
        log(f"ram: falha ao ler /proc ({type(e).__name__}: {e})", critical=True)
        return {"ok": False, "error": type(e).__name__, "mb": None,
                "processes": 0, "method": None}


# ---------------------------------------------------------------- mock
MOCK_USER = {"id": "1", "username": "voce", "global_name": "Você",
             "avatar": None, "discriminator": "0"}

MOCK_FRIENDS = [
    {"id": "rel1", "type": 1,
     "user": {"id": "2", "username": "amigo", "global_name": "Amigo",
              "avatar": None, "discriminator": "0"}},
    {"id": "rel2", "type": 1,
     "user": {"id": "4", "username": "nina", "global_name": "Nina",
              "avatar": None, "discriminator": "0"}},
    {"id": "rel3", "type": 1,
     "user": {"id": "5", "username": "bianca", "global_name": "Bianca",
              "avatar": None, "discriminator": "0"}},
]


class MockAPI:
    """Dados falsos para testar a interface e medir memoria sem conta."""

    def __init__(self):
        self.user = MOCK_USER

    def me(self):
        return MOCK_USER

    def guilds(self):
        return [
            {"id": "10", "name": "NOTES", "icon": None},
            {"id": "11", "name": "Projetos", "icon": None},
        ]

    def dms(self):
        return [
            {"id": "20", "type": 1,
             "recipients": [{"id": "2", "username": "amigo", "global_name": "Amigo",
                             "avatar": None}]},
        ]

    def friends(self):
        return MOCK_FRIENDS

    def open_dm(self, user_id):
        user = None
        for rel in MOCK_FRIENDS:
            if rel["user"]["id"] == user_id:
                user = rel["user"]
                break
        user = user or {"id": user_id, "username": "amigo", "global_name": "Amigo",
                        "avatar": None}
        cid = "20" if user_id == "2" else "dm-" + str(user_id)
        return {"id": cid, "type": 1, "recipients": [user]}

    def guild_channels(self, gid):
        return [
            {"id": "100", "name": "notas", "type": 0, "position": 0},
            {"id": "101", "name": "links", "type": 0, "position": 1},
            {"id": "102", "name": "arquivo", "type": 0, "position": 3, "parent_id": "90"},
            {"id": "90", "name": "Arquivados", "type": 4, "position": 2},
        ]

    def roles(self, gid):
        return [
            {"id": "r1", "name": "SAWS", "color": 0xf0b429, "position": 3, "hoist": True},
            {"id": "r2", "name": "dev", "color": 0xeb459e, "position": 2, "hoist": False},
            {"id": "r3", "name": "membro", "color": 0, "position": 1, "hoist": False},
        ]

    def messages(self, cid, before=None, limit=50, after=None):
        if before or after:
            return []

        def msg(mid, uid, who, text, minute, roles=None, **extra):
            author = {"id": uid, "username": who, "global_name": who,
                      "avatar": None, "discriminator": "0"}
            if uid == "2":
                author["primary_guild"] = {"tag": "SAWS", "identity_guild_id": "10"}
            if uid == "3":
                author["bot"] = True
            data = {
                "id": mid, "channel_id": cid, "author": author,
                "content": text,
                "timestamp": f"2026-10-24T21:{minute}:00.000000+00:00",
                "attachments": [],
            }
            if roles:
                data["member"] = {"roles": roles, "nick": None}
            data.update(extra)
            return data

        base = [
            msg("m1", "2", "guaxi-", "what happened to all the beans", "43",
                ["r1"], reactions=[
                    {"emoji": {"name": "🫘", "id": None}, "count": 3, "me": True},
                    {"emoji": {"name": "🔥", "id": None}, "count": 1, "me": False},
                ]),
            msg("m2", "2", "guaxi-", "here's a link https://discord.com/accessibility", "43",
                ["r1"], components=[{
                    "type": 1,
                    "components": [
                        {"type": 2, "style": 1, "label": "Example Button",
                         "custom_id": "exemplo"},
                        {"type": 2, "style": 5, "label": "Discord",
                         "url": "https://discord.com/accessibility"},
                    ],
                }]),
            msg("m3", "2", "guaxi-", "e **markdown**, `código` e emojis 🎧 continuam aqui", "44",
                ["r1"], reactions=[
                    {"emoji": {"name": "🎧", "id": None}, "count": 2, "me": False},
                ]),
            msg("m4", "1", "voce", "Boa. O layout compacto ficou como o da referência.", "47",
                ["r2"]),
            msg("m5", "3", "4Cord", "Demonstração: anexos, links e componentes preservados.", "48",
                ["r3"], attachments=[{
                    "url": "https://picsum.photos/seed/4cord/900/500",
                    "filename": "foto.jpg", "content_type": "image/jpeg",
                    "width": 900, "height": 500, "size": 12345,
                }]),
        ]
        return list(reversed(base))

    def react(self, cid, mid, emoji, remove=False):
        return None

    def interact(self, args):
        return None

    def send(self, cid, content):
        return {"id": "local", "channel_id": cid, "author": MOCK_USER,
                "content": content, "timestamp": "2026-10-24T21:50:00.000000+00:00",
                "attachments": []}

    def send_file(self, cid, content, path):
        return self.send(cid, content + f" [arquivo: {os.path.basename(path)}]")

    def typing(self, cid):
        pass

    def connect(self):
        pass

    def close(self):
        pass


# ---------------------------------------------------------------- login
LOGIN_CSS = """
window { background: #0f1015; }
#loginBody label { color: #e6e9ef; }
#loginBody label.sub { color: #8b91a1; font-size: 12px; }
#loginBody label.err { color: #ff8a8a; font-size: 12px; }
#loginBody label.ok  { color: #6fe3a8; font-size: 12px; }
#loginBody entry { background: #1a1c23; color: #e6e9ef; border: 1px solid #2a2d38;
        border-radius: 8px; padding: 10px 12px; caret-color: #5b6cff; }
#loginBody button { background: #23262f; color: #e6e9ef; border: 1px solid #2e323d;
         border-radius: 8px; padding: 9px 14px; }
#loginBody button:hover { background: #2b2f3a; }
#loginBody button.primary { background: #5b6cff; border-color: #5b6cff; color: #ffffff; font-weight: 600; }
#loginBody button.primary:hover { background: #6b79ff; }
#loginBody button.flat { background: transparent; border: none; color: #7f8dff; padding: 2px; }
"""


def scan_browser_tokens():
    """Procura credenciais do Discord no armazenamento local dos navegadores."""
    patterns = [
        "~/.mozilla/firefox/*/storage/default/https+++discord.com/ls/data.sqlite",
        "~/snap/firefox/common/.mozilla/firefox/*/storage/default/https+++discord.com/ls/data.sqlite",
        "~/.config/chromium/*/Local Storage/leveldb/*",
        "~/snap/chromium/common/chromium/*/Local Storage/leveldb/*",
        "~/.config/google-chrome/*/Local Storage/leveldb/*",
        "~/.config/discord/Local Storage/leveldb/*",
        "~/snap/discord/common/.config/discord/Local Storage/leveldb/*",
    ]
    rx = re.compile(rb"[A-Za-z0-9_-]{20,40}\.[A-Za-z0-9_-]{5,8}\.[A-Za-z0-9_-]{20,50}")
    found = []
    for pat in patterns:
        for path in glob.glob(os.path.expanduser(pat)):
            try:
                with open(path, "rb") as fh:
                    data = fh.read().replace(b"\x00", b"")
            except Exception:
                continue
            for hit in rx.findall(data):
                tok = hit.decode()
                if tok not in found:
                    found.append(tok)
    return found[:8]


class LoginWindow(Gtk.Window):
    """Login nativo do 4Cord. Sem navegador embutido."""

    def __init__(self, app):
        cfg = load_settings()
        app_name = clean_app_name(cfg.get("name"))
        super().__init__(title=app_name)
        self.app_name = app_name
        self.app = app
        self.set_default_size(470, 610)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        apply_window_identity(self, cfg)
        self._install_css()
        self._build()
        self.show_all()
        GLib.idle_add(self.auto_import)

    def _install_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(LOGIN_CSS.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _build(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_name("loginBody")
        box.set_margin_top(28)
        box.set_margin_bottom(22)
        box.set_margin_start(34)
        box.set_margin_end(34)
        self.add(box)

        pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            DEFAULT_ICON, 88, 88, True)
        logo = Gtk.Image.new_from_pixbuf(pix)
        box.pack_start(logo, False, False, 0)

        title = Gtk.Label()
        title.set_markup("<span size='xx-large' weight='bold'>" +
                         GLib.markup_escape_text(self.app_name) + "</span>")
        box.pack_start(title, False, False, 0)

        sub = Gtk.Label(label="cliente leve de Discord")
        sub.get_style_context().add_class("sub")
        box.pack_start(sub, False, False, 2)

        box.pack_start(Gtk.Separator(), False, False, 10)

        info = Gtk.Label()
        info.set_line_wrap(True)
        info.set_max_width_chars(44)
        info.set_xalign(0)
        info.set_text(
            "O Discord exige captcha no login por senha, então o 4Cord "
            "entra com o token da sua conta. O token fica apenas no seu "
            "computador, com permissão restrita.")
        info.get_style_context().add_class("sub")
        box.pack_start(info, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.entry = Gtk.Entry()
        self.entry.set_visibility(False)
        self.entry.set_placeholder_text("cole o token da conta")
        self.entry.set_activates_default(True)
        self.entry.set_hexpand(True)
        row.pack_start(self.entry, True, True, 0)

        paste_btn = Gtk.Button(label="Colar")
        paste_btn.connect("clicked", lambda *_: self.paste_clipboard())
        row.pack_start(paste_btn, False, False, 0)
        box.pack_start(row, False, False, 4)

        self.reveal = Gtk.CheckButton(label="mostrar token")
        self.reveal.connect("toggled", lambda w: self.entry.set_visibility(w.get_active()))
        box.pack_start(self.reveal, False, False, 0)

        self.enter = Gtk.Button(label="Entrar")
        self.enter.get_style_context().add_class("primary")
        self.enter.connect("clicked", lambda *_: self.do_login())
        box.pack_start(self.enter, False, False, 0)

        self.import_btn = Gtk.Button(label="Importar sessão do navegador")
        self.import_btn.connect("clicked", lambda *_: self.auto_import(force=True))
        box.pack_start(self.import_btn, False, False, 0)

        self.status = Gtk.Label(label="")
        self.status.set_line_wrap(True)
        self.status.set_max_width_chars(44)
        self.status.set_xalign(0)
        self.status.get_style_context().add_class("sub")
        box.pack_start(self.status, False, False, 4)

        help_btn = Gtk.Button(label="Como obter o token")
        help_btn.get_style_context().add_class("flat")
        help_btn.connect("clicked", lambda *_: self.show_help())
        box.pack_end(help_btn, False, False, 0)

        self.set_default(self.enter)

    def say(self, text, kind="sub"):
        ctx = self.status.get_style_context()
        for cls in ("sub", "err", "ok"):
            ctx.remove_class(cls)
        ctx.add_class(kind)
        self.status.set_text(text)

    @staticmethod
    def clean_token(raw):
        tok = (raw or "").strip().strip('"').strip("'").strip()
        if tok.lower().startswith("bearer "):
            tok = tok[7:].strip()
        return tok

    def paste_clipboard(self):
        try:
            clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            text = clip.wait_for_text()
        except Exception:
            text = None
        if text:
            self.entry.set_text(text)
            self.entry.grab_focus()
            self.say("token colado — clique em Entrar")
        else:
            self.say("a área de transferência está vazia.", "err")

    def auto_import(self, force=False):
        if getattr(self, "_scanning", False):
            return False
        self._scanning = True
        if force:
            self.say("procurando sessão nos navegadores...")
        self.import_btn.set_sensitive(False)

        def work():
            for tok in scan_browser_tokens():
                try:
                    user = Discord(tok, lambda ev: None).me()
                    GLib.idle_add(self.found_session, tok, user)
                    return
                except Exception:
                    continue
            GLib.idle_add(self.no_session, force)

        threading.Thread(target=work, daemon=True).start()
        return False

    def found_session(self, token, user):
        self._scanning = False
        self.import_btn.set_sensitive(True)
        self.entry.set_text(token)
        handle = user.get("username") or "conta"
        self.say(f"sessão encontrada: @{handle} — clique em Entrar", "ok")
        return False

    def no_session(self, force):
        self._scanning = False
        self.import_btn.set_sensitive(True)
        if force:
            self.say("nenhuma sessão do Discord encontrada nos navegadores.", "err")
        return False

    def do_login(self):
        token = self.clean_token(self.entry.get_text())
        if not token:
            self.say("cole o token primeiro.", "err")
            return
        self.enter.set_sensitive(False)
        self.say("verificando token...")

        def work():
            try:
                user = Discord(token, lambda ev: None).me()
                save_token(token)
                GLib.idle_add(self.done, token, user)
            except DiscordError as err:
                if err.status in (401, 403):
                    msg = "token inválido ou expirado. Copie novamente."
                else:
                    msg = f"o Discord recusou ({err.status}). Tente de novo."
                GLib.idle_add(self.fail, msg)
            except Exception as exc:
                GLib.idle_add(self.fail, "sem conexão com o Discord: " + type(exc).__name__)

        threading.Thread(target=work, daemon=True).start()

    def fail(self, msg):
        self.enter.set_sensitive(True)
        self.say(msg, "err")
        return False

    def done(self, token, user):
        self.app.open_main(token, user)
        try:
            self.destroy()
        except Exception:
            pass
        return False

    def show_help(self):
        dlg = Gtk.Dialog(title="Como obter o token", transient_for=self, modal=True)
        dlg.add_buttons("Fechar", Gtk.ResponseType.CLOSE)
        dlg.set_default_size(470, 330)
        area = dlg.get_content_area()
        area.set_margin_top(14)
        area.set_margin_bottom(14)
        area.set_margin_start(16)
        area.set_margin_end(16)
        lbl = Gtk.Label()
        lbl.set_line_wrap(True)
        lbl.set_selectable(True)
        lbl.set_xalign(0)
        lbl.set_text(
            "1. Abra discord.com no seu navegador e entre na conta.\n\n"
            "2. Pressione F12 e abra a aba Console.\n\n"
            "3. Cole e execute:\n"
            "     localStorage.getItem('token')\n\n"
            "4. Copie o texto entre aspas (sem as aspas) e cole no campo.\n\n"
            "Se você usa Firefox, o botão \"Importar sessão do navegador\" "
            "costuma encontrar o token sozinho.\n\n"
            "O token vale como senha: não compartilhe e não cole em sites.")
        area.add(lbl)
        dlg.show_all()
        dlg.run()
        dlg.destroy()


# ---------------------------------------------------------------- principal
class MainWindow(Gtk.Window):
    def __init__(self, app, api, token=None):
        cfg = load_settings()
        self.settings = cfg
        self.app_name = clean_app_name(cfg.get("name"))
        super().__init__(title=self.app_name)
        self.app = app
        self.api = api
        self.token = token
        self.set_default_size(1150, 740)
        self.set_position(Gtk.WindowPosition.CENTER)
        apply_window_identity(self, cfg)

        self.ucm = WebKit2.UserContentManager()
        self.ucm.register_script_message_handler("tp")
        self.ucm.connect("script-message-received::tp", self.on_message)

        self.web = WebKit2.WebView.new_with_user_content_manager(self.ucm)
        try:
            # WebKit2.Settings nao expoe corretor ortografico nesta versao;
            # o controle fica no WebContext e vale para todos os campos.
            self.web.get_context().set_spell_checking_enabled(False)
        except Exception as e:
            log(f"spellcheck: nao foi possivel desativar ({type(e).__name__})", critical=True)
        settings = self.web.get_settings()
        settings.set_enable_developer_extras(env_flag("FOURCORD_DEVTOOLS", False))
        settings.set_enable_smooth_scrolling(False)
        settings.set_enable_webgl(False)
        settings.set_enable_webaudio(False)
        settings.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER)
        self.add(self.web)
        url = "file://" + UI
        if env_flag("FOURCORD_NO_AVATARS", False):
            url += "?lean=1"
        self.web.load_uri(url)

        self.connect("destroy", self.on_destroy)
        self.show_all()

    # --- ponte JS -> Python
    def on_message(self, _manager, value):
        try:
            msg = json.loads(js_str(value))
        except Exception as e:
            log(f"ponte JS: mensagem invalida ({type(e).__name__})", critical=True)
            return
        threading.Thread(target=self.handle, args=(msg,), daemon=True).start()

    def reply(self, rid, ok, data=None, error=None):
        payload = {"id": rid, "ok": ok, "data": data, "error": error}
        self.js_call("window.tpReply(" + json.dumps(payload) + ")")

    def js_call(self, script):
        GLib.idle_add(self._run_js, script)

    def _run_js(self, script):
        if self.web:
            self.web.run_javascript(script, None, None, None)
        return False

    # --- comandos
    def handle(self, msg):
        rid = msg.get("id")
        cmd = msg.get("cmd")
        args = msg.get("args") or {}
        ch = args.get("channel")
        detail = f" cmd={cmd}"
        if ch:
            detail += f" canal={ch}"
        if cmd == "send":
            detail += f" chars={len(args.get('content') or '')}"
        log("comando" + detail)
        try:
            if cmd == "init":
                data = self.cmd_init()
            elif cmd == "channels":
                data = self.cmd_channels(args)
            elif cmd == "roles":
                data = self.api.roles(args["guild"])
            elif cmd == "messages":
                raw_limit = args.get("limit")
                try:
                    limit = int(50 if raw_limit in (None, "") else raw_limit)
                except (TypeError, ValueError):
                    limit = 50
                limit = max(1, min(100, limit))
                after = args.get("after")
                if after is not None and not str(after).isdigit():
                    after = None
                data = self.api.messages(args["channel"], args.get("before"), limit,
                                         after=after)
            elif cmd == "dms":
                data = self.api.dms()
            elif cmd == "react":
                self.api.react(args["channel"], args["message"], args["emoji"],
                               bool(args.get("remove")))
                data = None
            elif cmd == "interact":
                self.api.interact(args)
                data = None
            elif cmd == "friends":
                data = self.api.friends()
            elif cmd == "open_dm":
                data = self.api.open_dm(args["user"])
            elif cmd == "send":
                data = self.api.send(args["channel"], args.get("content", ""))
            elif cmd == "upload":
                GLib.idle_add(self.pick_and_upload, rid, args)
                return
            elif cmd == "pick_icon":
                GLib.idle_add(self.pick_icon, rid)
                return
            elif cmd == "set_app_name":
                data = self.cmd_set_app_name(args.get("name"))
            elif cmd == "set_theme":
                data = self.cmd_set_theme(args.get("theme"))
            elif cmd == "set_verbose":
                data = self.cmd_set_verbose(args.get("enabled"))
            elif cmd == "set_accent":
                data = self.cmd_set_accent(args.get("color"))
            elif cmd == "ram":
                data = ram_usage()
            elif cmd == "typing":
                self.api.typing(args["channel"])
                data = None
            elif cmd == "logout":
                data = self.cmd_logout()
            elif cmd == "open_url":
                Gtk.show_uri_on_window(self, args["url"], 0)
                data = None
            else:
                raise ValueError("comando desconhecido: " + str(cmd))
            self.reply(rid, True, data)
        except DiscordError as e:
            log(f"erro Discord{detail} -> {e.status} {e.body[:300]}", critical=True)
            if e.status in (401, 403) and cmd == "init":
                GLib.idle_add(self.app.relogin)
            body = (e.body or "").strip()
            try:
                body = json.loads(body).get("message", body)
            except Exception:
                pass
            self.reply(rid, False, None, f"Discord recusou ({e.status}): {body[:160]}")
        except Exception as e:
            log(f"erro{detail} -> {type(e).__name__}: {e}", critical=True)
            self.reply(rid, False, None, str(e))

    def cmd_init(self):
        user = self.api.me() if not isinstance(self.api, MockAPI) else self.api.user
        return {
            "version": VERSION,
            "app_name": clean_app_name(self.settings.get("name") or self.app_name),
            "icon": icon_path(self.settings) if self.settings.get("icon") else None,
            "theme": self.settings.get("theme") or "dark",
            "accent": self.settings.get("accent") or "#5b6cff",
            "verbose_logs": bool(self.settings.get("verbose_logs", False)),
            "user": user,
            "guilds": self.api.guilds(),
            "dms": self.api.dms(),
            "mock": isinstance(self.api, MockAPI),
            "gateway": bool(getattr(self.api, "connected", False)),
        }

    def cmd_channels(self, args):
        if args.get("kind") == "dm":
            return []
        return self.api.guild_channels(args["guild"])

    def pick_and_upload(self, rid, args):
        dlg = Gtk.FileChooserDialog(title="Enviar arquivo", parent=self,
                                    action=Gtk.FileChooserAction.OPEN)
        dlg.add_buttons("Cancelar", Gtk.ResponseType.CANCEL,
                        "Enviar", Gtk.ResponseType.OK)
        filt = Gtk.FileFilter()
        filt.set_name("Imagens e arquivos")
        filt.add_pattern("*")
        dlg.add_filter(filt)
        resp = dlg.run()
        path = dlg.get_filename()
        dlg.destroy()
        if resp != Gtk.ResponseType.OK or not path:
            self.reply(rid, True, None)
            return False

        def work():
            try:
                msg = self.api.send_file(args["channel"], args.get("content", ""), path)
                self.reply(rid, True, msg)
            except Exception as e:
                self.reply(rid, False, None, str(e))

        threading.Thread(target=work, daemon=True).start()
        return False

    def cmd_set_theme(self, theme):
        theme = theme if theme in ("dark", "amoled", "auto") else "dark"
        if self.settings.get("theme") != theme:
            update_settings(self.settings, theme=theme)
        GLib.idle_add(self._apply_gtk_theme, theme)
        return theme

    def _apply_gtk_theme(self, theme):
        # Varios pedidos podem chegar quase juntos; aplica sempre o valor
        # mais recente persistido, nao o argumento de um pedido antigo.
        sync_gtk_theme(self.settings.get("theme") or theme or "dark")
        return False

    def cmd_set_verbose(self, enabled):
        enabled = bool(enabled)
        update_settings(self.settings, verbose_logs=enabled)
        set_verbose(enabled)
        return enabled

    def cmd_set_accent(self, color):
        color = str(color or "").strip()
        if not re.match(r"^#[0-9a-fA-F]{6}$", color):
            color = "#5b6cff"
        color = color.lower()
        update_settings(self.settings, accent=color)
        return color

    def cmd_set_app_name(self, name):
        name = clean_app_name(name)
        self.app_name = name
        update_settings(self.settings, name=name)
        update_desktop_entry(name=name)
        GLib.idle_add(self._apply_app_name, name)
        return name

    def _apply_app_name(self, name):
        try:
            self.set_title(clean_app_name(self.settings.get("name") or name))
        except Exception:
            pass
        return False

    def pick_icon(self, rid):
        dlg = Gtk.FileChooserDialog(title="Escolher ícone", parent=self,
                                    action=Gtk.FileChooserAction.OPEN)
        dlg.add_buttons("Cancelar", Gtk.ResponseType.CANCEL,
                        "Usar imagem", Gtk.ResponseType.OK)
        filt = Gtk.FileFilter()
        filt.set_name("Imagens suportadas")
        filt.add_pixbuf_formats()
        dlg.add_filter(filt)
        resp = dlg.run()
        path = dlg.get_filename()
        dlg.destroy()
        if resp != Gtk.ResponseType.OK or not path:
            self.reply(rid, True, None)
            return False
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
            w, h = pixbuf.get_width(), pixbuf.get_height()
            scale = min(1.0, 256.0 / max(w, h)) if w and h else 1.0
            if scale < 1.0:
                pixbuf = pixbuf.scale_simple(
                    max(1, round(w * scale)), max(1, round(h * scale)),
                    GdkPixbuf.InterpType.BILINEAR)
            os.makedirs(CONF_DIR, exist_ok=True)
            pixbuf.savev(ICON_FILE, "png", [], [])
            update_settings(self.settings, icon=ICON_FILE)
            update_desktop_entry(icon=ICON_FILE)
            self.set_icon_from_file(ICON_FILE)
            self.reply(rid, True, {"icon": ICON_FILE})
        except Exception as e:
            log(f"icone: falha ao importar {type(e).__name__}: {e}", critical=True)
            self.reply(rid, False, None, "formato não suportado ou imagem inválida")
        return False

    def cmd_logout(self):
        try:
            os.remove(TOKEN_FILE)
        except Exception:
            pass
        GLib.idle_add(self.app.restart)
        return None

    # --- eventos do gateway
    def on_event(self, ev):
        t = ev.get("type")
        if t == "ready":
            data = ev.get("data") or {}
            self.js_call("window.tpEvent(" + json.dumps(
                {"type": "ready",
                 "data": {"user": data.get("user"),
                          "guild_order": data.get("guild_order") or []}}) + ")")
            return
        if t == "gateway_error":
            code = (ev.get("data") or {}).get("code")
            log(f"gateway erro fatal codigo={code}", critical=True)
            if code == 4004:
                GLib.idle_add(self.app.relogin)
            return
        self.js_call("window.tpEvent(" + json.dumps(ev) + ")")

    def on_destroy(self, *_):
        try:
            self.api.close()
        except Exception:
            pass
        if getattr(self.app, "restarting", False):
            return
        Gtk.main_quit()


# ---------------------------------------------------------------- app
class App:
    def __init__(self, mock=False, token=None):
        self.mock = mock
        self.token = token
        self.win = None
        self.login = None
        self.restarting = False
        self._iface_settings = gnome_interface_settings()
        if self._iface_settings is not None:
            try:
                self._iface_settings.connect("changed::color-scheme", self._on_system_theme)
                self._iface_settings.connect("changed::gtk-theme", self._on_system_theme)
            except Exception:
                self._iface_settings = None

    def _on_system_theme(self, *_):
        sync_gtk_theme(load_settings().get("theme") or "dark")
        return False

    def start(self):
        sync_gtk_theme(load_settings().get("theme") or "dark")
        if self.mock:
            self.open_main(None, MOCK_USER, mock=True)
        elif self.token:
            self.open_main(self.token, None)
        else:
            self.login = LoginWindow(self)

    def relogin(self):
        """Token expirou: volta para a tela de login nativa."""
        self.restarting = True
        if self.win:
            try:
                self.win.destroy()
            except Exception:
                pass
        self.win = None
        self.restarting = False
        self.token = None
        try:
            os.remove(TOKEN_FILE)
        except Exception:
            pass
        self.login = LoginWindow(self)
        return False

    def open_main(self, token, user, mock=False):
        if self.login:
            try:
                self.login.destroy()
            except Exception:
                pass
            self.login = None

        if mock:
            api = MockAPI()
        else:
            api = Discord(token, lambda ev: self.win and self.win.on_event(ev))
        self.win = MainWindow(self, api, token)
        self.win.present()
        if not mock:
            api.connect()
        return False

    def restart(self):
        self.restarting = True
        if self.win:
            try:
                self.win.destroy()
            except Exception:
                pass
        self.win = None
        self.restarting = False
        self.token = None
        self.login = LoginWindow(self)
        return False


def run_selftest(app):
    win = app.win
    if not win:
        print("SELFTEST sem_janela")
        Gtk.main_quit()
        return False

    def done(view, res, *_):
        try:
            print("SELFTEST " + view.run_javascript_finish(res).get_js_value().to_string())
        except Exception as e:
            print("SELFTEST erro " + str(e))
        Gtk.main_quit()

    win.web.run_javascript(
        "JSON.stringify({guilds:document.querySelectorAll('.guild').length,"
        "rail:!!document.querySelector('#rail'),"
        "msgs:document.querySelectorAll('.msg').length,"
        "msgAvatars:document.querySelectorAll('#msgList .avatar').length,"
        "reactions:document.querySelectorAll('.reaction').length,"
        "components:document.querySelectorAll('.compBtn').length,"
        "side:document.querySelector('#sideTitle').textContent,"
        "title:document.querySelector('#chTitle').textContent,"
        "user:document.querySelector('#meName').textContent,"
        "theme:document.documentElement.dataset.theme,"
        "conn:document.querySelector('#conn') ? document.querySelector('#conn').className : null,"
        "sendText:(document.querySelector('#sendBtn').textContent||'').trim(),"
        "sendAria:document.querySelector('#sendBtn').getAttribute('aria-label'),"
        "sendSvg:document.querySelectorAll('#sendBtn svg').length,"
        "helpBtn:!!document.querySelector('#helpBtn'),"
        "infoHidden:document.querySelector('#info').classList.contains('hidden'),"
        "error:window.__tpError || null,"
        "catchErr:window.__tpCatch || null,"
        "scroll:(()=>{const b=document.querySelector('#msgs');"
        "return b?{client:b.clientHeight,height:b.scrollHeight,top:b.scrollTop}:null;})()})",
        None, done, None)
    return False


def main():
    mock = "--mock" in sys.argv
    selftest = "--selftest" in sys.argv

    migrate_legacy_config()
    settings = load_settings()
    set_verbose(bool(settings.get("verbose_logs", False)))
    try:
        GLib.set_prgname("4cord")
        GLib.set_application_name("4Cord")
        Gdk.set_program_class("4cord")
    except Exception:
        pass
    try:
        Gtk.Window.set_default_icon_from_file(icon_path(settings))
    except Exception as e:
        log(f"icone: nao foi possivel definir o icone global ({type(e).__name__}: {e})",
            critical=True)
    ensure_desktop_entry(settings)

    os.makedirs(CONF_DIR, exist_ok=True)
    lock = open(os.path.join(CONF_DIR, "instance.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("4Cord ja esta aberto.")
        return

    token = None if mock else load_token()
    log(f"inicio v{VERSION} mock={mock} credenciais={'sim' if token else 'nao'}")
    app = App(mock=mock, token=token)
    app.start()
    if selftest:
        GLib.timeout_add(4000, run_selftest, app)
    Gtk.main()


if __name__ == "__main__":
    main()
