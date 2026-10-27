#!/usr/bin/env bash
# 4Cord 2.4.0 — instalador compartilhado para Ubuntu 26.04 e Arch Linux.
#
# O script NÃO faz upgrade do sistema, NÃO usa sudo sem pedir confirmação e
# NÃO apaga configurações. Ele valida as dependências nativas, cria um
# ambiente virtual local e instala o atalho do menu de aplicativos.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
REQUIREMENTS="$ROOT/requirements.txt"
LAUNCHER="$ROOT/bin/4cord"
RUNNER="$ROOT/run.sh"
ICON="$ROOT/assets/4cord.png"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$DESKTOP_DIR/4cord.desktop"
USER_BIN="$HOME/.local/bin"
OS_RELEASE="${FOURCORD_OS_RELEASE_FILE:-/etc/os-release}"

RECREATE_VENV=0
SKIP_SYSTEM_INSTALL=0
CHECK_ONLY=0

usage() {
    cat <<'EOF'
Uso: ./install.sh [opções]

Opções:
  --recreate-venv      move o .venv existente para .venv.bak-<data> e cria outro
  --skip-system-install não pergunta nem executa apt/pacman; apenas informa
  --check              valida distribuição e dependências, sem instalar nada
  -h, --help           mostra esta ajuda

O instalador preserva ~/.config/4cord e ~/.config/trashpanda.
EOF
}

die() {
    printf 'ERRO: %s\n' "$*" >&2
    exit 1
}

warn() {
    printf 'AVISO: %s\n' "$*" >&2
}

for arg in "$@"; do
    case "$arg" in
        --recreate-venv) RECREATE_VENV=1 ;;
        --skip-system-install) SKIP_SYSTEM_INSTALL=1 ;;
        --check) CHECK_ONLY=1 ;;
        -h|--help) usage; exit 0 ;;
        *) die "opção desconhecida: $arg (use --help)" ;;
    esac
done

[ -f "$ROOT/app.py" ] || die "app.py não encontrado em $ROOT"
[ -f "$ROOT/ui/index.html" ] || die "ui/index.html não encontrado em $ROOT"
[ -s "$ICON" ] || die "ícone ausente ou vazio: $ICON"
[ -f "$REQUIREMENTS" ] || die "requirements.txt não encontrado"

os_value() {
    # Lê uma chave simples do os-release sem executar o arquivo.
    awk -F= -v key="$1" '
        $1 == key {
            sub(/^[^=]*=/, "")
            gsub(/^"|"$/, "")
            print
            exit
        }
    ' "$OS_RELEASE"
}

[ -r "$OS_RELEASE" ] || die "não foi possível ler $OS_RELEASE"
DISTRO_ID="$(os_value ID)"
VERSION_ID="$(os_value VERSION_ID)"
PRETTY_NAME="$(os_value PRETTY_NAME)"
PRETTY_NAME="${PRETTY_NAME:-${DISTRO_ID:-distribuição desconhecida}}"

case "$DISTRO_ID" in
    ubuntu)
        DISTRO="ubuntu"
        PACKAGES=(python3 python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-gdkpixbuf-2.0)
        if [ "$VERSION_ID" != "26.04" ]; then
            warn "$PRETTY_NAME não é a versão oficialmente suportada (Ubuntu 26.04 LTS)."
            warn "Os nomes de pacotes podem diferir; a instalação continuará, mas não foi validada."
        fi
        ;;
    arch)
        DISTRO="arch"
        PACKAGES=(python python-gobject gtk3 webkit2gtk-4.1 gdk-pixbuf2)
        ;;
    *)
        printf 'ERRO: distribuição não reconhecida: %s\n' "$PRETTY_NAME" >&2
        printf '%s\n' \
            'Este instalador só reconhece Ubuntu 26.04 e Arch Linux.' \
            'Instalação manual: garanta Python 3, PyGObject, GTK 3, WebKitGTK 4.1' \
            'e GdkPixbuf pelo gerenciador de pacotes da sua distribuição, depois' \
            'execute ./run.sh a partir do diretório do projeto.' >&2
        exit 2
        ;;
esac

printf '4Cord 2.4.0 — instalador\n'
printf 'Distribuição: %s (%s)\n' "$PRETTY_NAME" "$DISTRO"

command -v python3 >/dev/null 2>&1 || die "python3 não encontrado; instale o Python 3 da distribuição"

pkg_installed() {
    local pkg="$1"
    if [ "$DISTRO" = "ubuntu" ]; then
        dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q 'install ok installed'
    else
        pacman -Q "$pkg" >/dev/null 2>&1
    fi
}

missing=()
for pkg in "${PACKAGES[@]}"; do
    pkg_installed "$pkg" || missing+=("$pkg")
done

imports_ok() {
    python3 - <<'PY' >/dev/null 2>&1
import fcntl  # noqa: F401
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("WebKit2", "4.1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gtk, WebKit2  # noqa: F401
PY
}

if [ "${#missing[@]}" -gt 0 ]; then
    printf '\nDependências do sistema ausentes:\n'
    printf '  - %s\n' "${missing[@]}"
    if [ "$DISTRO" = "ubuntu" ]; then
        printf '\nComando correspondente no Ubuntu (APT):\n'
        printf '  sudo apt-get update\n'
        printf '  sudo apt-get install --no-install-recommends %s\n' "${missing[*]}"
    else
        printf '\nComando correspondente no Arch Linux (pacman):\n'
        printf '  sudo pacman -S --needed %s\n' "${missing[*]}"
    fi

    if [ "$CHECK_ONLY" -eq 1 ] || [ "$SKIP_SYSTEM_INSTALL" -eq 1 ]; then
        die "instale as dependências acima e execute o instalador novamente"
    fi
    if [ ! -t 0 ]; then
        die "sem terminal interativo; execute os comandos acima e repita a instalação"
    fi
    printf '\nO instalador pode executar o comando acima agora. Ele não faz upgrade do sistema.\n'
    read -r -p "Executar a instalação das dependências? [s/N] " answer
    case "${answer,,}" in
        s|sim|y|yes)
            if [ "$(id -u)" -eq 0 ]; then
                if [ "$DISTRO" = "ubuntu" ]; then
                    apt-get update
                    apt-get install -y --no-install-recommends "${missing[@]}"
                else
                    pacman -S --needed --noconfirm "${missing[@]}"
                fi
            else
                command -v sudo >/dev/null 2>&1 || die "sudo não encontrado; execute os comandos manualmente"
                if [ "$DISTRO" = "ubuntu" ]; then
                    sudo apt-get update
                    sudo apt-get install -y --no-install-recommends "${missing[@]}"
                else
                    sudo pacman -S --needed --noconfirm "${missing[@]}"
                fi
            fi
            ;;
        *)
            die "instalação cancelada; execute os comandos acima e tente novamente"
            ;;
    esac
fi

imports_ok || die "PyGObject/GTK 3/WebKitGTK 4.1 ainda não podem ser importados pelo python3"
if [ "$CHECK_ONLY" -eq 1 ]; then
    printf 'Dependências nativas: OK\n'
    exit 0
fi

# ------------------------------ ambiente virtual
requirements_has_packages() {
    grep -Eq '^[[:space:]]*[^#[:space:]]' "$REQUIREMENTS"
}

venv_ok() {
    [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c 'import gi' >/dev/null 2>&1
}

if [ -d "$VENV" ]; then
    if [ "$RECREATE_VENV" -eq 1 ]; then
        backup="$VENV.bak-$(date +%Y%m%d-%H%M%S)-$$"
        printf 'Movendo ambiente virtual existente para %s\n' "$backup"
        mv "$VENV" "$backup" || die "não foi possível mover o .venv antigo"
    elif ! venv_ok; then
        die "o .venv existente não funciona (Python atualizado ou ambiente incompleto). Use --recreate-venv para movê-lo de lado e criar outro."
    fi
fi

if ! venv_ok; then
    tmp_venv="$ROOT/.venv.new.$$"
    venv_log="${TMPDIR:-/tmp}/4cord-venv.$$.log"
    rm -rf "$tmp_venv"
    trap 'rm -rf "$tmp_venv"; rm -f "$venv_log"' EXIT
    printf 'Criando ambiente virtual em %s\n' "$VENV"
    # A saida do venv e capturada: quando ensurepip nao esta instalado, o
    # erro esperado nao polui o terminal; o log so aparece em caso fatal.
    if ! python3 -m venv --system-site-packages --prompt 4Cord "$tmp_venv" \
            >"$venv_log" 2>&1; then
        rm -rf "$tmp_venv"
        if requirements_has_packages; then
            cat "$venv_log" >&2
            die "não foi possível criar o ambiente virtual com pip. Instale o pacote python3-venv (Ubuntu) ou equivalente e repita."
        fi
        printf 'ensurepip indisponível; criando ambiente sem pip (não há pacotes PyPI obrigatórios).\n'
        if ! python3 -m venv --system-site-packages --without-pip --prompt 4Cord \
                "$tmp_venv" >>"$venv_log" 2>&1; then
            cat "$venv_log" >&2
            die "não foi possível criar o ambiente virtual"
        fi
    fi
    [ ! -e "$VENV" ] || die "$VENV apareceu durante a instalação; execute novamente"
    mv "$tmp_venv" "$VENV"
    rm -f "$venv_log"
    trap - EXIT
    printf 'Ambiente virtual criado.\n'
fi

if "$VENV/bin/python" -m pip --version >/dev/null 2>&1; then
    printf 'Instalando dependências Python de requirements.txt...\n'
    "$VENV/bin/python" -m pip install --disable-pip-version-check -r "$REQUIREMENTS"
else
    printf 'O ambiente virtual não possui pip; nenhum pacote PyPI é obrigatório.\n'
    if requirements_has_packages; then
        die "requirements.txt contém pacotes, mas o ambiente não tem pip. Instale python3-venv e use --recreate-venv."
    fi
fi

"$VENV/bin/python" - <<'PY' || die "o ambiente virtual não consegue importar as bibliotecas do sistema"
import fcntl  # noqa: F401
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("WebKit2", "4.1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gtk, WebKit2  # noqa: F401
print("Ambiente virtual: OK")
PY

# ------------------------------ validação do código
printf 'Validando arquivos...\n'
"$VENV/bin/python" -m py_compile "$ROOT/app.py" "$ROOT"/core/*.py "$ROOT"/tests/*.py \
    || die "falha de compilação Python"
if command -v node >/dev/null 2>&1; then
    node --check "$ROOT/ui/app.js" || die "falha na sintaxe de ui/app.js"
else
    printf 'node não encontrado; validação opcional de ui/app.js ignorada.\n'
fi

chmod +x "$LAUNCHER" "$RUNNER" "$ROOT/install.sh"

# ------------------------------ atalho e comando no PATH
mkdir -p "$USER_BIN"
user_link="$USER_BIN/4cord"
if [ -L "$user_link" ]; then
    current="$(readlink "$user_link" || true)"
    if [ "$current" = "$LAUNCHER" ]; then
        :
    elif [ ! -e "$user_link" ]; then
        ln -sfn "$LAUNCHER" "$user_link"
        printf 'Atualizado link %s -> %s\n' "$user_link" "$LAUNCHER"
    else
        warn "$user_link já aponta para $current; não foi alterado."
    fi
elif [ -e "$user_link" ]; then
    warn "$user_link já existe e não é um link do 4Cord; não foi alterado."
else
    ln -s "$LAUNCHER" "$user_link"
    printf 'Criado link %s -> %s\n' "$user_link" "$LAUNCHER"
fi

mkdir -p "$DESKTOP_DIR"
"$VENV/bin/python" - "$LAUNCHER" "$ICON" "$DESKTOP_FILE" <<'PY'
import os
import sys
import tempfile

launcher, icon, destination = sys.argv[1:4]


def quote(value):
    value = str(value).replace("\\", "\\\\").replace('"', '\\"')
    value = value.replace("$", "\\$").replace("`", "\\`")
    return '"' + value + '"'


content = (
    "[Desktop Entry]\n"
    "Version=1.0\n"
    "Type=Application\n"
    "Name=4Cord\n"
    "GenericName=Cliente leve de Discord\n"
    "Comment=Cliente leve de Discord com interface propria (texto, DMs e anexos)\n"
    f"Exec={quote(launcher)}\n"
    f"Icon={icon}\n"
    "Terminal=false\n"
    "Categories=Network;InstantMessaging;Chat;\n"
    "Keywords=discord;chat;4cord;mensagem;\n"
    "StartupWMClass=4cord\n"
    "StartupNotify=true\n"
)
fd, tmp = tempfile.mkstemp(prefix=".4cord-desktop-", dir=os.path.dirname(destination))
try:
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.chmod(tmp, 0o644)
    os.replace(tmp, destination)
finally:
    if os.path.exists(tmp):
        os.unlink(tmp)
PY

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

if [ -d "$HOME/.config/4cord" ]; then
    printf 'Configuração existente preservada: %s\n' "$HOME/.config/4cord"
fi
if [ -d "$HOME/.config/trashpanda" ]; then
    printf 'Configuração legada preservada: %s\n' "$HOME/.config/trashpanda"
fi

printf '\n4Cord 2.4.0 instalado.\n'
printf 'Inicie com:\n'
printf '  %s\n' "$RUNNER"
if [ -x "$user_link" ] || [ -L "$user_link" ]; then
    case ":$PATH:" in
        *":$USER_BIN:"*) printf '  %s\n' "4cord" ;;
        *) printf '  %s (adicione %s ao PATH para usar apenas "4cord")\n' "$user_link" "$USER_BIN" ;;
    esac
fi
printf 'Ou abra "4Cord" no menu de aplicativos (GNOME ou Xfce4).\n'
printf 'Configuração e dados ficam em %s e não são alterados pelo instalador.\n' "$HOME/.config/4cord"
printf 'Teste sem conta real: %s --mock --selftest\n' "$RUNNER"
