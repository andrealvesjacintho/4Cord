# Testes e comparações A/B

Todos os testes usam `--mock` ou dados temporários. Os que abrem a interface
devem rodar com `HOME` e `XDG_CONFIG_HOME` isolados para não tocar na
configuração real:

```bash
AUDIT_HOME="$(mktemp -d)"
HOME="$AUDIT_HOME" XDG_CONFIG_HOME="$AUDIT_HOME/.config" \
  python3 tests/audit_ui.py
```

## Regressão e auditoria

```bash
python3 -m py_compile app.py core/*.py tests/*.py
node --check ui/app.js

HOME="$AUDIT_HOME" XDG_CONFIG_HOME="$AUDIT_HOME/.config" \
  python3 tests/audit_ui.py
HOME="$AUDIT_HOME" XDG_CONFIG_HOME="$AUDIT_HOME/.config" \
  python3 tests/audit_initial_load.py
HOME="$AUDIT_HOME" XDG_CONFIG_HOME="$AUDIT_HOME/.config" \
  python3 tests/audit_sync_e2e.py
HOME="$AUDIT_HOME" XDG_CONFIG_HOME="$AUDIT_HOME/.config" \
  python3 tests/audit_ram.py
python3 tests/audit_settings.py
python3 tests/audit_api.py
HOME="$AUDIT_HOME" XDG_CONFIG_HOME="$AUDIT_HOME/.config" \
  python3 tests/audit_dm_reconnect.py
HOME="$AUDIT_HOME" XDG_CONFIG_HOME="$AUDIT_HOME/.config" \
  python3 tests/audit_ui_final.py
HOME="$AUDIT_HOME" XDG_CONFIG_HOME="$AUDIT_HOME/.config" \
  python3 tests/audit_login_close.py
python3 tests/audit_install.py
```

- `audit_ui.py`: reconexão longa com e sem sobreposição, leitura de histórico
  antigo, guardas entre operações, spinner e retenção de mídia com URL
  duplicada.
- `audit_initial_load.py`: mensagem ao vivo durante a carga inicial do canal
  não é perdida nem duplicada.
- `audit_sync_e2e.py`: confirma que o backend recebe `limit=100` e que a janela
  não fica com buraco; o fake rejeita `after` na conversa ativa.
- `audit_ram.py`: compara o PSS agregado com a soma manual e verifica a
  inclusão/remoção de um processo filho.
- `audit_settings.py`: migração única, logout sem ressurreição do token,
  permissões `600` e gravações concorrentes de configuração.
- `audit_api.py`: URLs REST de `before`/`after`, limite `1..100`, validação de
  `after` na ponte, heartbeat novo por conexão e detecção de GNOME/Xfce.
- `audit_dm_reconnect.py`: conversa ativa, DMs conhecidas com `after`,
  deduplicação, limite de 10 DMs, segunda passada e falha isolada.
- `audit_ui_final.py`: central de informações, abas, ARIA, foco, `Esc`, clique
  no fundo, ícone de envio e recarga manual.
- `audit_login_close.py`: fechar a janela de login encerra o processo e libera
  o `instance.lock`, em vez de deixar uma instância invisível em execução.
- `audit_install.py`: instalação em cópia temporária com HOME isolado,
  idempotência, `--check`, dependências ausentes, caminho Arch, distribuição
  não suportada, `--recreate-venv` e preservação de configuração.

O teste do instalador cria cópias do projeto em diretórios temporários e não
altera o `.venv`, a configuração real, o menu de aplicativos nem `~/.local/bin`
do usuário. Ele não executa `apt-get`/`pacman`; apenas verifica as mensagens e
os códigos de saída.

## Comparações A/B

Os scripts A/B comparam o 4Cord com uma cópia de referência do cliente anterior
(`--appdir`). Essa cópia não faz parte do repositório e não estava disponível na
etapa final; os números do README são medições históricas, não uma nova
execução.

```bash
python3 tests/ab_measure.py --appdir "$PWD" --out /tmp/4cord-new.json
python3 tests/ab_media.py --appdir "$PWD" --out /tmp/media-new.json
python3 tests/ab_logs.py --appdir "$PWD" \
  --logfile /tmp/4cord-home/.config/4cord/log.txt --out /tmp/log-new.json
```

Para comparar, use outra cópia do cliente antigo em `--appdir` e um `HOME`
isolado. O modo mock não valida o CDN real do Discord nem uma conta real.

## Observações

- As medições são reais desta máquina; PSS/CPU variam alguns MB/segundos.
- O modo mock não valida o CDN real do Discord nem uma conta real.
- O Arch Linux com Xfce4 ainda precisa de validação manual em um ambiente real.
- Os scripts não alteram o código do app; apenas criam configuração nos HOMEs
  usados.
