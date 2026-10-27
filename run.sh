#!/usr/bin/env bash
# Inicia o 4Cord a partir da raiz do projeto.
# Prefere o ambiente virtual criado pelo install.sh; caso ele não exista,
# usa o Python 3 do sistema sem instalar nada.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -x "$DIR/.venv/bin/python" ]; then
    PY="$DIR/.venv/bin/python"
else
    PY="$(command -v python3)"
fi
exec "$PY" "$DIR/app.py" "$@"
