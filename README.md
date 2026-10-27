# 4Cord 2.4.0

![Logo do 4Cord](assets/4cord.png)

Cliente leve de Discord para Linux, com interface própria em HTML/CSS/JavaScript
dentro do WebKitGTK e comunicação direta com a API e o gateway oficiais. O
aplicativo web do Discord não é carregado.

- **Criador:** André Alves
- **Repositório:** <https://github.com/andrealvesjacintho/4Cord>
- **Branch principal:** `main`

## Recursos

- Servidores, canais de texto, DMs, reações e componentes interativos.
- Markdown leve, menções, links e emotes externos.
- Anexos de imagem com capa de censura e visualizador.
- Temas escuro, AMOLED e automático; cor de destaque configurável.
- Histórico limitado a 300 mensagens por conversa e cache de 1000 IDs vistos.
- Reconexão do gateway com recuperação da conversa ativa e de DMs conhecidas.
- Botão de recarregar mensagens e indicador de não lidas.
- Indicador de RAM do processo, log de diagnóstico e central de informações `?`.
- Compatibilidade com Ubuntu/Debian, Arch Linux, GNOME e Xfce4.

## Requisitos

- Linux com `/proc`.
- Python 3 com PyGObject.
- GTK 3, WebKitGTK 4.1 (`WebKit2`) e GdkPixbuf.
- `python3-venv` recomendado. Se `ensurepip` não existir, o instalador pode
  criar o ambiente sem pip, pois não há dependências PyPI.
- `node` é opcional e serve apenas para validar `ui/app.js` nos testes.

### Pacotes por distribuição

| Distribuição | Pacotes |
|---|---|
| Ubuntu/Debian | `python3 python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-gdkpixbuf-2.0` |
| Arch Linux | `python python-gobject gtk3 webkit2gtk-4.1 gdk-pixbuf2` |

O instalador mostra o comando correspondente caso falte algum pacote e só usa
`sudo` depois de pedir confirmação. Ele não faz upgrade completo do sistema.

## Instalação

```bash
git clone https://github.com/andrealvesjacintho/4Cord.git
cd 4Cord
./install.sh --check
./install.sh
```

O `--check` apenas valida a distribuição e as dependências. A instalação
completa cria `.venv` com acesso aos módulos do sistema, preserva
`~/.config/4cord`, atualiza o atalho do menu e não sobrescreve configurações.

Também é possível usar uma pasta baixada como ZIP. Nesse caso, entre nela antes
de executar o instalador.

### Opções do instalador

```bash
./install.sh --check               # apenas valida
./install.sh --skip-system-install # não executa apt/pacman
./install.sh --recreate-venv       # recria o ambiente virtual
./install.sh --help
```

## Execução

```bash
./run.sh                  # usa .venv quando disponível
./run.sh --mock           # demonstração com dados falsos
./run.sh --mock --selftest
4cord                     # se ~/.local/bin estiver no PATH
```

O 4Cord também pode ser aberto pelo menu de aplicativos do GNOME ou Xfce4.

## Login e segurança

- O login usa um token de conta, não senha ou OAuth. O token fica em
  `~/.config/4cord/token`, com permissão `600`; o diretório de configuração usa
  permissão `700`.
- O token não é gravado no código, no README nem no log e não é enviado ao
  JavaScript/WebView nem ao `localStorage`.
- O cache visual do WebView guarda apenas tema, cor, avatares, largura da barra
  e IDs de navegação.
- O log não registra conteúdo de mensagens; formatos de token são redigidos.
- O importador de sessão procura credenciais apenas nos armazenamentos locais
  de navegadores conhecidos e as valida somente na API do Discord. Nada é
  enviado a terceiros.
- Não há telemetria própria. O `.gitignore` exclui token, configurações, logs,
  caches, bancos locais e o ambiente virtual.

O token fica em texto simples no disco: quem tiver acesso à conta do usuário
pode lê-lo. Não compartilhe o arquivo `~/.config/4cord/token`.

## Reconexão e DMs

- Ao abrir uma conversa, o 4Cord guarda o último ID conhecido por canal.
- Após `READY`/`RESUMED`, a conversa ativa é sincronizada com até 100 mensagens
  recentes; o botão de recarregar faz o mesmo manualmente.
- DMs conhecidas usam `GET /channels/{id}/messages?after=<último-id>&limit=100`.
- A recuperação usa uma página por DM, no máximo 10 DMs por reconexão, e
  deduplica IDs já vistos.
- Uma falha em uma DM não bloqueia as seguintes.

## Compatibilidade

- **Ubuntu 26.04 com GNOME:** instalação, execução e testes automatizados
  realizados nesta máquina.
- **Arch Linux:** detecção, nomes de pacotes e comando `pacman` implementados e
  verificados por simulação; falta validar a instalação em uma máquina Arch.
- **Xfce4:** o código não depende de GNOME; falta validar em uma sessão real.
- **Wayland/X11:** a janela usa GTK 3/WebKitGTK; a validação ocorreu em Wayland.
- **Conta real e CDN do Discord:** não validados nesta etapa. Os testes usam
  `--mock`, mídia local e URLs sintéticas.

## Testes

```bash
python3 -m py_compile app.py core/*.py tests/*.py
node --check ui/app.js
./run.sh --mock --selftest
python3 tests/audit_api.py
python3 tests/audit_settings.py
python3 tests/audit_install.py
```

Testes que abrem uma janela devem usar `HOME` isolado para não tocar na
configuração real. Os comandos completos e a cobertura de cada teste estão em
[`tests/README.md`](tests/README.md). O relatório técnico completo está em
[`RELATORIO-AUDITORIA-4CORD.txt`](RELATORIO-AUDITORIA-4CORD.txt) e o checklist
de aceitação em [`CHECKLIST.md`](CHECKLIST.md).

## Limitações

- Arch Linux e Xfce4 ainda não foram validados em instalação real.
- O instalador não executou `apt-get`/`pacman` de verdade neste ambiente, pois
  as dependências já estavam presentes.
- O comportamento real do CDN do Discord e a recuperação de DMs com uma conta
  real ainda precisam de validação manual.
- As medições A/B são históricas e não foram repetidas.
- Quando `smaps_rollup` não está disponível, o fallback de RAM pode
  superestimar páginas compartilhadas; a interface mostra `RAM ~`.

## Estrutura

```
4Cord/
├── app.py              # janela GTK, login, configuração e comandos
├── core/               # REST, gateway, WebSocket e log
├── ui/                 # interface HTML, CSS e JavaScript
├── assets/             # ícones 256×256 e 4096×4096
├── bin/4cord           # lançador
├── run.sh              # execução local
├── install.sh          # instalador Ubuntu/Arch
├── requirements.txt    # dependências Python (sem PyPI)
├── tests/              # testes de regressão e auditoria
└── README.md
```

## Compatibilidade com o nome anterior

O nome antigo **TrashPanda** aparece somente onde é necessário para reconhecer
instalações existentes:

- `~/.config/trashpanda/`: origem da migração, lida uma vez e nunca apagada.
- `trashpanda.desktop`: atalho antigo removido ao criar o atalho novo.
- `.migrated-from-trashpanda`: marcador que impede migração repetida e
  restauração de token apagado no logout.
- O namespace interno `tp` do cache e da ponte JavaScript-Python é mantido por
  compatibilidade com preferências existentes.

Essas referências não são usadas como identidade visual.

## Desinstalação

```bash
rm -rf ~/.config/4cord
rm -f ~/.local/share/applications/4cord.desktop
rm -f ~/.local/bin/4cord
```

Depois, remova a pasta do projeto. A configuração antiga em
`~/.config/trashpanda/` é preservada de propósito.

## Desenvolvimento

Antes de enviar mudanças, rode `py_compile`, `node --check` e os testes de
auditoria. Não inclua credenciais, configurações locais, logs, caches ou
resultados de testes com dados privados no repositório. Para publicar, faça um
commit descritivo e use `git push origin main`; não reescreva o histórico.
