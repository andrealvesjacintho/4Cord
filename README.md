# 4Cord 2.4.0

![Logo do 4Cord](assets/4cord.png)

Cliente **leve** de Discord para Linux, com interface própria em HTML, CSS e
JavaScript dentro do WebKitGTK e conversa direta com a API e o gateway oficiais.
O aplicativo web do Discord não é carregado: a interface, o histórico e a mídia
são renderizados pelo próprio 4Cord.

```
UI (HTML/CSS/JS)  <->  Python (REST + gateway)  <->  Discord
```

> **Estado da publicação:** o projeto ainda não possui repositório público no
> GitHub. Por isso este README não inventa uma URL de `git clone`; os comandos
> abaixo partem da pasta do projeto baixada ou recebida. Quando o repositório
> for publicado, o comando de clonagem exibido pelo GitHub pode ser usado antes
> do `cd 4Cord` e do instalador.

## Novidades da 2.4.0

- Instalador compartilhado para **Ubuntu 26.04** e **Arch Linux**, com
  verificação de dependências nativas, ambiente virtual local e preservação da
  configuração.
- **Recuperação de mensagens após reconexão**, inclusive em DMs conhecidas, e
  botão de **recarregar mensagens** no cabeçalho.
- Botão de envio com **ícone** e rótulo acessível, no lugar do texto “ENVIAR”.
- Central de informações **?** com as abas Sobre, Etapas, Tecnologias e uma
  visão de detalhes avançados.
- Tema integrado ao GTK sem exigir GNOME; em Xfce4 e outros ambientes o
  `gsettings` do GNOME não é usado.
- Lançador e atalho `.desktop` com caminhos entre aspas, funcionando em pastas
  com espaços.

## Identidade

- Nome visível: **4Cord**.
- Ícone global: `assets/4cord.png` (256×256), gerado a partir de
  `assets/4cord-hd.png` (4096×4096).
- Lançador: `bin/4cord`.
- Atalho: `~/.local/share/applications/4cord.desktop`
  (`StartupWMClass=4cord`).
- Configuração: `~/.config/4cord/`.
- Credenciais de autenticação ficam somente na configuração local, com
  permissão restrita, e nunca são versionadas.
- Na primeira execução, a configuração anterior é copiada para o novo diretório
  sem apagar os arquivos originais. A migração é feita uma única vez e um
  arquivo de credenciais apagado no logout não é restaurado.

## Requisitos

- Linux com `/proc` (usado pelo indicador de RAM).
- Python 3 com PyGObject.
- GTK 3, WebKitGTK 4.1 (tipelib `WebKit2`) e GdkPixbuf.
- `fcntl` e as bibliotecas padrão do Python.
- `python3-venv` é recomendado. Se o `ensurepip` não existir, o instalador cria
  um ambiente sem pip, desde que não haja pacotes PyPI obrigatórios.
- `node` é opcional; é usado apenas para validar a sintaxe de `ui/app.js` nos
  testes e na instalação.

Não há dependências Python de terceiros além das bibliotecas de sistema do
GTK/WebKitGTK. O arquivo `requirements.txt` documenta essa decisão e não contém
pacotes PyPI.

### Pacotes por distribuição

| Distribuição | Pacotes |
|---|---|
| Ubuntu 26.04 | `python3 python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-gdkpixbuf-2.0` |
| Arch Linux | `python python-gobject gtk3 webkit2gtk-4.1 gdk-pixbuf2` |

O instalador reconhece os nomes acima e mostra o comando correspondente se
algum pacote estiver faltando. Ele não faz upgrade completo do sistema.

## Instalação

A partir da pasta do projeto (por exemplo, `4Cord` ou `4Cord-main`):

```bash
cd 4Cord
./install.sh --check
./install.sh
```

O primeiro comando apenas valida a distribuição e as dependências. O segundo:

1. verifica os pacotes nativos e os imports de GTK/WebKitGTK;
2. pergunta antes de executar `apt-get` ou `pacman`, caso falte alguma
   dependência;
3. cria `.venv` com `--system-site-packages`, reutilizando o PyGObject do
   sistema;
4. instala `requirements.txt` quando existe pip (hoje o arquivo não tem pacotes
   PyPI);
5. valida o Python, o JavaScript e os testes com `py_compile`;
6. cria/atualiza `~/.local/bin/4cord` e o atalho do menu de aplicativos;
7. preserva `~/.config/4cord` e `~/.config/trashpanda`.

Se os pacotes já estiverem instalados, nenhum comando com `sudo` é executado.

### Opções do instalador

```bash
./install.sh --check              # só valida, não instala nada
./install.sh --skip-system-install # não pergunta nem executa apt/pacman
./install.sh --recreate-venv      # move o .venv existente para .venv.bak-<data>
./install.sh --help               # ajuda
```

O instalador é idempotente: executar novamente não recria um ambiente válido,
não sobrescreve a configuração e não apaga o diretório antigo. Se um `.venv`
existente estiver incompatível com o Python atual, ele só é movido com
`--recreate-venv`.

### Execução

```bash
./run.sh                 # usa .venv quando existe; senão, o python3 do sistema
./run.sh --mock          # demonstração com dados falsos
./run.sh --mock --selftest
4cord                    # se ~/.local/bin estiver no PATH
```

Também é possível abrir **4Cord** no menu de aplicativos do GNOME ou do Xfce4.
O atalho usa `Exec="<caminho com espaços>/bin/4cord"` e `Icon=<caminho do PNG>`.

### Atualização

Se o projeto foi obtido por Git, atualize a pasta com `git pull` e execute
`./install.sh` novamente. A configuração e as credenciais locais não são
alteradas pelo instalador.

## Recursos

- Servidores, canais de texto, DMs, reações e componentes interativos.
- Markdown leve, menções, links e emotes externos (exibidos como `?`).
- Anexos de imagem com capa de censura até o clique; o visualizador abre a
  imagem original.
- Temas escuro, AMOLED e automático (segue a preferência do sistema/GTK).
- Cor de destaque configurável, com contraste calculado automaticamente.
- Indicador de RAM do processo e de seus filhos, atualizado a cada 12 s.
- Log de diagnóstico com opção de detalhamento.
- Central de informações `?` com documentação, etapas, tecnologias e detalhes
  avançados.

## Recuperação de mensagens e DMs

- Ao abrir uma conversa, o 4Cord carrega a página recente e guarda o último ID
  conhecido por canal.
- Após `READY` (reconexão que perdeu a sessão) ou `RESUMED`, a conversa ativa é
  sincronizada com até 100 mensagens recentes; o mesmo vale para o botão de
  recarregar.
- DMs conhecidas são consultadas com
  `GET /channels/{id}/messages?after=<último-id>&limit=100`.
- A recuperação usa uma página por DM, no máximo 10 DMs por reconexão, e não
  abre uma segunda conexão de gateway.
- IDs já vistos são deduplicados; mensagens recuperadas em DMs geram indicador
  de não lidas.
- DMs sem último ID conhecido, DMs ocultas e conversas cujo
  `last_message_id` não avançou são ignoradas.
- Uma falha em uma DM não impede a recuperação das seguintes. Se a API não
  devolver o intervalo perdido, a conversa será atualizada quando for aberta.
- O botão de recarregar fica no cabeçalho, ao lado do indicador de conexão.

## Central de informações

O botão **?** abre um diálogo com:

- **Sobre**: identidade, criador, pontos positivos, limitações e aviso de que o
  projeto não é oficial do Discord.
- **Etapas**: resumo verificável da evolução do projeto.
- **Tecnologias**: interface, janela, comunicação, armazenamento e plataforma.
- **Detalhes avançados**: arquitetura, sincronização, configuração/segurança,
  desempenho e compatibilidade.

As abas funcionam por clique e pelas setas esquerda/direita. `Esc` fecha, o
clique no fundo também fecha, e o foco fica preso ao diálogo enquanto ele está
aberto. Ao fechar, o foco volta ao botão que abriu a central.

## Otimizações preservadas

### A1 — janela de histórico

- No máximo **300 mensagens** no DOM e no histórico em memória por conversa.
- Ordem cronológica preservada e scroll mantido ao carregar mensagens antigas.
- Botão **carregar anteriores** usa paginação de 50 mensagens.
- Quando o limite empurra mensagens recentes para fora, aparece
  **voltar ao recente**; o usuário não é deslocado enquanto lê o passado.
- Mensagens ao vivo que chegam durante uma carga são enfileiradas e aplicadas
  depois, sem duplicar nem perder eventos.
- Requisições antigas são descartadas por número de navegação; trocar de canal
  rapidamente não mistura históricos.
- Na reconexão, busca até **100 mensagens** para detectar sobreposição. Se o
  intervalo perdido for maior que uma página, recomeça pela página mais recente
  quando o usuário está no fim; se ele está lendo o passado, apenas sinaliza
  “voltar ao recente”. Assim não surge um buraco no meio da janela.
- Carregar anteriores, voltar ao recente e sincronizar são mutuamente
  exclusivos.

### A2 — cache de IDs vistos

- Cache limitado a **1000 IDs**, com remoção dos mais antigos.
- IDs da janela ativa e IDs pendentes de uma carga não são removidos.
- A retenção não depende só do DOM: mensagens fora da janela continuam
  elegíveis para deduplicação dentro do limite do cache.

### A3 — miniaturas inline

- Imagens de anexos do CDN do Discord são pedidas com `width`/`height`
  reduzidos; o visualizador sempre usa a URL original.
- Se a miniatura falhar, a imagem inline tenta a URL original; se ela também
  falhar, aparece um link de arquivo.
- URLs fora do CDN do Discord continuam usando a original.
- A capa de censura e a revelação por clique são preservadas.

### A4 — liberação de mídia fora da tela

- Um único `IntersectionObserver` compartilhado, com raiz em `#msgs`, cobre as
  mídias reveladas.
- Ao sair da tela, a mídia volta à capa e o `src` é removido, liberando a
  decodificação.
- A mídia aberta no visualizador não é descarregada; ao fechar, a verificação
  de tela é refeita.
- A retenção é feita pelo nó aberto, não pela URL. Duas mídias com a mesma URL
  não ficam ambas decodificadas por causa do visualizador.
- A capa é mantida no DOM, permitindo revelar novamente sem recriar o nó.

### A7 — log discreto por padrão

- Por padrão, só erros e eventos críticos são gravados.
- **Ajustes → Log detalhado** ativa comandos, REST e eventos rotineiros.
- Credenciais de autenticação e formatos semelhantes são redigidos antes da
  escrita.
- Arquivo em `~/.config/4cord/log.txt`, com rotação em 512 KB e permissão
  `600` (inclusive no arquivo rotacionado).

### A10 — corretor ortográfico

- O corretor do WebKit é desativado explicitamente no `WebContext`.
- Os campos de mensagem, busca de amigos e nome do app usam
  `spellcheck="false"`, `autocorrect="off"` e `autocapitalize="off"`.
- Digitação, envio e anexos continuam funcionando normalmente.

### Gateway e heartbeat

- Cada reconexão usa uma nova conexão WebSocket e um novo `Event` de heartbeat.
- O heartbeat da conexão anterior é encerrado antes de iniciar o próximo, para
  não deixar threads antigas vivas nem gerar heartbeats duplicados.

## Ajustes e indicadores

- **Cor de destaque**: seletor de cor com persistência em
  `~/.config/4cord/settings.json` e cache visual em `localStorage`. O texto e o
  primeiro plano são calculados para manter contraste em cores claras/escuras.
- **RAM**: mostra o PSS agregado da árvore de processos do 4Cord. Quando um
  processo não oferece `smaps_rollup`, usa `VmRSS` apenas para ele; nesse caso o
  total pode superestimar páginas compartilhadas e a UI indica `RAM ~`. O valor
  é atualizado a cada 12 s; a consulta não se sobrepõe.
- **Carregamento**: indicadores discretos ao abrir canal, carregar anteriores,
  sincronizar reconexão e voltar ao recente. Botões são desativados durante a
  operação e sempre reativados no `finally`.
- **Tema**: escuro/AMOLED forçam a variante escura do GTK; automático segue a
  preferência do sistema. Em GNOME, Unity ou Ubuntu com GNOME o app consulta
  `org.gnome.desktop.interface`; em Xfce4, Xubuntu, Kubuntu e outros ambientes
  usa apenas `Gtk.Settings`, sem sobrescrever o tema do desktop.
- **Envio**: o botão usa um SVG inline, `aria-label="Enviar mensagem"` e
  `title`; Enter e clique continuam com o mesmo comportamento.

## Compatibilidade

- **Ubuntu 26.04 LTS com GNOME**: instalação completa, execução e testes
  automatizados realizados nesta máquina.
- **Arch Linux**: nomes de pacotes, detecção e comando `pacman` implementados e
  verificados com simulação; não havia ambiente Arch disponível para validar a
  instalação real.
- **Xfce4**: o código não depende de GNOME e o caminho de tema sem `gsettings`
  foi testado; a execução real em uma sessão Xfce4 ainda é uma validação manual
  pendente.
- **Wayland/X11**: a janela usa GTK 3/WebKitGTK; o ambiente desta validação foi
  Wayland com GNOME.
- **Conta real e CDN do Discord**: não validados nesta etapa. Os testes usam
  `--mock`, mídia local e URLs sintéticas.

## Segurança e privacidade

- O token fica em `~/.config/4cord/token`, com permissão `600`; configurações e
  log também usam permissão restrita.
- O token não é gravado no código, no README nem no log. Ainda assim, fica em
  texto simples no disco: quem tiver acesso à conta do usuário pode lê-lo.
- O log não registra o conteúdo das mensagens; no máximo comando, canal,
  tamanho do texto e erros HTTP/gateway. Formatos de token são redigidos.
- Não há telemetria própria. O importador opcional procura uma sessão nos
  armazenamentos locais de navegadores conhecidos e só envia dados à API do
  Discord.
- `.gitignore` exclui `.venv`, caches, token, `settings.json`, logs e resultados
  locais. Antes de publicar, confira `git status` e o histórico para garantir
  que nenhuma credencial foi versionada.

## Estrutura

```
4Cord/
├── app.py                 # janela GTK, identidade, configuração, comandos
├── core/
│   ├── discord.py         # REST, gateway, upload, after/reconexão
│   ├── log.py             # log crítico/detalhado, redação de credenciais
│   └── ws.py              # WebSocket
├── ui/
│   ├── index.html         # interface e central de informações
│   ├── app.css            # temas, acento, spinner, mídia, modal
│   └── app.js             # histórico, DMs, mídia, ajustes, ajuda
├── assets/
│   ├── 4cord.png          # ícone global 256×256
│   └── 4cord-hd.png       # fonte 4096×4096
├── bin/4cord              # lançador com suporte a .venv
├── run.sh                 # inicialização simples
├── install.sh             # instalador Ubuntu/Arch
├── requirements.txt       # dependências Python documentadas (sem PyPI)
├── tests/                 # regressão, auditoria, instalador e A/B
├── .gitignore
├── README.md
├── CHECKLIST.md
└── RELATORIO-AUDITORIA-4CORD.txt
```

## Testes

Validação básica:

```bash
python3 -m py_compile app.py core/*.py tests/*.py
node --check ui/app.js
./run.sh --mock --selftest
```

Testes de regressão e auditoria, com `HOME` isolado para não tocar na
configuração real:

```bash
AUDIT_HOME="$(mktemp -d)"
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
python3 tests/audit_install.py
```

- `audit_ui.py`: reconexão longa com e sem sobreposição, leitura de histórico
  antigo, guardas entre operações, spinner e retenção de mídia.
- `audit_initial_load.py`: mensagem ao vivo durante a carga inicial do canal.
- `audit_sync_e2e.py`: repasse de `limit=100` e janela sem buraco.
- `audit_ram.py`: PSS agregado e inclusão/remoção de processo filho.
- `audit_settings.py`: migração única, logout, permissões `600` e gravações
  concorrentes.
- `audit_api.py`: URLs REST de `before`/`after`, limite `1..100`, validação da
  ponte, heartbeat novo por conexão e detecção de GNOME/Xfce.
- `audit_dm_reconnect.py`: recuperação da conversa ativa, DMs conhecidas,
  deduplicação, limite de 10, segunda passada e falha isolada.
- `audit_ui_final.py`: central de informações, abas, foco, `Esc`, fundo, ícone
  de envio e botão de recarregar.
- `audit_install.py`: instalação completa em cópia temporária, idempotência,
  `--check`, dependências ausentes, caminho Arch, distribuição não suportada,
  `--recreate-venv` e preservação da configuração.

### Resultados desta etapa

- `audit_dm_reconnect.py`: conversa ativa sincronizada sem `after`; DMs com
  `after=200` e `after=300`; duas mensagens novas em cada uma; limite de 10
  DMs; segunda passada recuperou as duas restantes; terceira não refez chamadas;
  DM ativa não usou `after`; falha simulada em uma DM não bloqueou a seguinte.
- `audit_ui_final.py`: modal com `role=dialog`, abas e ARIA corretos, foco preso,
  `Esc` e fundo fechando, foco devolvido ao botão, ícone de envio com
  `aria-label="Enviar mensagem"`, envio e recarregamento funcionando.
- `audit_api.py`: caminhos `?limit=...`, `&before=...` e `&after=...`; `limit=0`
  vira 1 e `limit=500` vira 100; `after` inválido vira `None`; heartbeat antigo
  encerrado e evento novo criado; Xfce não é tratado como GNOME.
- `audit_install.py`: primeira e segunda instalação retornaram 0; configuração
  e token preservados; nenhum `.venv.new.*` restante; `--check` não criou
  ambiente nem atalho; dependências ausentes retornaram erro com comandos;
  caminho Arch mostrou `pacman` e os quatro pacotes; distribuição não suportada
  retornou 2; `--recreate-venv` preservou o `.venv` antigo em backup.
- `audit_ui.py`: janela final com 100 mensagens no cenário de intervalo longo,
  300 no cenário com sobreposição, zero buracos, guardas bloqueando chamadas
  concorrentes e mídia com URL duplicada liberada corretamente.
- `audit_initial_load.py`: mensagem ao vivo enfileirada e exibida no fim, sem
  duplicata; segundo caso manteve apenas uma cópia.
- `audit_sync_e2e.py`: backend recebeu `limit=100`; janela final `1351..1450`,
  sem buracos.
- `audit_ram.py`: 203,1 MB em 9 processos, igual à soma manual; processo filho
  incluído e removido.
- `audit_settings.py`: migração única, token não restaurado após logout,
  permissões `600`, 960 gravações concorrentes sem erro e dicionário mutado sem
  exceção.
- `--mock --selftest`: 5 mensagens, 3 reações, 2 componentes, `sendText=""`,
  `sendAria="Enviar mensagem"`, `sendSvg=1`, sem erro JS.

### Comparações A/B

Os scripts A/B comparam o 4Cord com uma cópia de referência do cliente
anterior. Essa cópia não faz parte deste repositório e não estava disponível
nesta etapa; os números abaixo são medições históricas da auditoria anterior,
não uma nova execução.

| Métrica | Original | 4Cord |
|---|---:|---:|
| Nós no DOM após 1500 mensagens | 1505 | **300** |
| Mensagens em memória | 1505 | **300** |
| IDs no cache | 1505 | **1000** |
| Injeção JS | 6,61–6,72 s | **3,55–3,76 s** |
| CPU da árvore (delta) | 7,11–7,17 s | **4,02–4,23 s** |
| PSS final | 241,8–252,5 MB | **222,1–233,9 MB** |
| Altura do scroll | 31.953 px | **6.352 px** |
| Imagens com `src` fora da tela | 31 | **0** |
| Capas disponíveis para re-revelar | 0 | **31** |
| Log padrão após 20 envios | 1309 bytes | **ausente, 0 bytes** |

O relatório completo, com problemas, correções, evidências e limitações, está
em [`RELATORIO-AUDITORIA-4CORD.txt`](RELATORIO-AUDITORIA-4CORD.txt). O
checklist de aceitação está em [`CHECKLIST.md`](CHECKLIST.md).

## Limitações

- O Arch Linux e o Xfce4 não foram validados em uma instalação real nesta
  etapa. O caminho Arch foi testado com simulação de pacotes ausentes; o tema
  sem GNOME foi testado em nível de código.
- O comportamento real do CDN do Discord para `width`/`height` não foi
  validado com uma conta real; os testes usaram mídia local e URLs sintéticas.
- A recuperação de DMs e a sincronização de reconexão usam dados simulados; a
  API real pode não conservar ou entregar eventos fora do alcance da sessão.
- As medições A/B são históricas e não foram repetidas nesta etapa.
- O PSS varia conforme WebKit, tema e cache; os números são desta máquina.
- Quando `smaps_rollup` não está disponível, o fallback para `VmRSS` pode
  superestimar o total por contar páginas compartilhadas mais de uma vez; a UI
  mostra `RAM ~` nesse caso.
- Processos auxiliares reparentados ou que desapareçam entre a varredura e a
  leitura de `/proc` podem não entrar em uma atualização específica do
  indicador de RAM.
- O instalador não foi testado executando `apt-get`/`pacman` de verdade, porque
  as dependências já estavam instaladas e o ambiente não tinha sudo
  não interativo.
- O projeto ainda não foi publicado no GitHub e não possui remoto configurado.

## Compatibilidade com a identidade anterior

O nome antigo aparece somente onde é necessário para reconhecer instalações
existentes e não perder dados:

- `~/.config/trashpanda/`: diretório de origem da migração. Ele é lido apenas
  na primeira execução e nunca é apagado ou alterado.
- `~/.local/share/applications/trashpanda.desktop`: atalho antigo removido
  quando o atalho `4cord.desktop` é criado/atualizado.
- `~/.config/4cord/.migrated-from-trashpanda`: marcador que impede migração
  repetida e restauração de credenciais apagadas no logout.
- O nome antigo é normalizado para **4Cord** ao carregar uma configuração
  migrada.

Essas referências não são usadas como identidade visual. O nome antigo aparece
na interface apenas na seção histórica **Etapas** e na explicação da migração da
central de informações. O namespace interno `tp` do cache local e da ponte
JavaScript-Python é mantido por compatibilidade com preferências e automações
existentes; ele não é um nome exibido ao usuário.

## Desenvolvimento e publicação

- Mantenha o comportamento e os limites atuais (300 mensagens, 1000 IDs e
  páginas de 50) sem alterações não justificadas.
- Rode `py_compile`, `node --check` e os testes de auditoria antes de enviar
  mudanças.
- Use um `HOME` isolado nos testes que iniciam a interface.
- Não inclua credenciais, configurações locais, logs, caches ou resultados de
  testes com dados privados no repositório.
- Preserve as referências legadas documentadas acima; elas são necessárias para
  migração e compatibilidade.
- Relate mudanças de comportamento e limitações de validação no README ou no
  relatório de auditoria.

O projeto está versionado localmente. Para publicar no GitHub, crie um
repositório vazio e envie a branch `main` usando o comando que o próprio GitHub
mostra após a criação. Não há URL pública real para inserir neste README nesta
etapa; quando ela existir, acrescente-a aos comandos de instalação.

## Desinstalação

Remova a configuração e o atalho locais:

```bash
rm -rf ~/.config/4cord
rm -f ~/.local/share/applications/4cord.desktop
rm -f ~/.local/bin/4cord
```

Depois, remova o diretório do projeto conforme a instalação escolhida. A
configuração anterior em `~/.config/trashpanda/` é preservada de propósito e
pode ser removida manualmente se você não precisar mais dela.
