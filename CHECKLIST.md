# Checklist do 4Cord 2.4.0

## Identidade e distribuição

- [x] Nome visível, título da janela e nome do aplicativo: **4Cord**.
- [x] `DEFAULT_NAME`, versão e identificadores do app atualizados.
- [x] Ícone global `assets/4cord.png` (256×256) e fonte
      `assets/4cord-hd.png` (4096×4096).
- [x] Lançador `bin/4cord` com suporte a `.venv`; `run.sh` para inicialização
      simples.
- [x] Atalho `~/.local/share/applications/4cord.desktop` com
      `StartupWMClass=4cord` e `Exec` entre aspas (funciona com espaços).
- [x] Configuração em `~/.config/4cord`; credenciais com permissão `600`.
- [x] Migração da configuração anterior sem apagar os arquivos originais,
      feita uma única vez com marcador; credenciais apagadas no logout não
      voltam.
- [x] Atalho antigo removido; referências visuais antigas eliminadas de UI,
      README, checklist, lançador e assets.
- [x] Logo `assets/4cord.png` preservada e exibida no README.
- [x] README em português com instalação, execução, testes, segurança,
      limitações e referências legadas.
- [x] Repositório Git local inicializado; nenhuma configuração, token, log ou
      `.venv` versionado.
- [x] Repositório público publicado em
      <https://github.com/andrealvesjacintho/4Cord>, branch `main`.

## Recuperação de mensagens e interface

- [x] Após `READY`/`RESUMED`, a conversa ativa é sincronizada com até 100
      mensagens recentes.
- [x] DMs conhecidas usam `GET /channels/{id}/messages?after=<último-id>`.
- [x] Recuperação limitada a uma página por DM e a 10 DMs por reconexão.
- [x] DMs ocultas, sem último ID ou com `last_message_id` não avançado são
      ignoradas.
- [x] Deduplicação por IDs vistos; mensagens recuperadas geram não lidas.
- [x] Falha em uma DM não interrompe as demais.
- [x] A ordem de recuperação é aplicada antes do limite de 10, permitindo que
      as DMs restantes avancem na reconexão seguinte.
- [x] Botão de recarregar no cabeçalho força a recuperação da conversa atual e
      atualiza a lista de DMs.
- [x] Cada reconexão do gateway usa um novo `Event` de heartbeat e encerra o
      anterior.
- [x] Botão de envio com SVG inline, `aria-label="Enviar mensagem"`, `title` e
      sem texto "ENVIAR".
- [x] Enter e clique continuam enviando; botão é reativado no `finally`.
- [x] Central de informações `?` com abas Sobre, Etapas e Tecnologias.
- [x] Aba de detalhes avançados com arquitetura, sincronização, segurança,
      desempenho e compatibilidade.
- [x] Navegação por clique e setas, foco preso ao diálogo, `Esc` e clique no
      fundo fecham; foco volta ao botão de ajuda.
- [x] Layout responsivo do modal e do botão de envio em telas estreitas.
- [x] Tema sem dependência obrigatória de GNOME: `gsettings` só em
      GNOME/Unity/Ubuntu; nos demais ambientes, apenas `Gtk.Settings`.

## Instalador compartilhado

- [x] `install.sh` reconhece Ubuntu 26.04 e Arch Linux.
- [x] Verifica pacotes nativos e imports de PyGObject/GTK/WebKitGTK/GdkPixbuf.
- [x] Explica os pacotes ausentes e mostra o comando `apt-get` ou `pacman`.
- [x] Só executa `sudo` após confirmação explícita; não faz upgrade completo.
- [x] `--check` valida sem instalar; `--skip-system-install` não pergunta.
- [x] Cria `.venv` com `--system-site-packages` e reutiliza quando válido.
- [x] Se `ensurepip` não existe e não há pacotes PyPI, cria o ambiente sem pip
      sem poluir a saída com o erro esperado.
- [x] `--recreate-venv` move um ambiente existente (válido ou inválido) para
      `.venv.bak-<data>` em vez de apagá-lo.
- [x] Instalação idempotente: a segunda execução não recria o `.venv` nem
      altera a configuração.
- [x] Preserva `~/.config/4cord` e `~/.config/trashpanda`.
- [x] Cria/atualiza `~/.local/bin/4cord` e o atalho `.desktop`.
- [x] `requirements.txt` só documenta dependências nativas reais, sem pacotes
      PyPI obrigatórios.
- [x] `.gitignore` cobre `.venv`, caches, token, configurações, logs e
      resultados locais.

## Otimizações preservadas

- [x] **A1** — janela de 300 mensagens no DOM/histórico, paginação de 50,
      ordem cronológica, scroll preservado, “carregar anteriores” e
      “voltar ao recente”, fila de mensagens ao vivo e proteção contra
      respostas assíncronas atrasadas.
- [x] **A1 reconexão** — busca até 100 mensagens e detecta sobreposição; sem
      sobreposição, recomeça pela página recente (no fim) ou sinaliza
      “voltar ao recente” (lendo o passado), sem buraco na janela.
- [x] **A1 concorrência** — carregar anteriores, voltar ao recente e
      sincronizar são mutuamente exclusivos.
- [x] **A2** — cache de IDs vistos limitado a 1000, com IDs ativos e
      pendentes isentos de remoção; deduplicação preservada.
- [x] **A3** — miniaturas `width`/`height` para anexos do CDN do Discord,
      fallback para a original e visualizador sempre com a URL original.
- [x] **A4** — capa de censura mantida, descarregamento de mídia revelada
      fora da tela, retenção apenas do nó aberto no visualizador (mesmo com
      URL duplicada) e re-revelação.
- [x] **A7** — log padrão somente crítico, opção de log detalhado em Ajustes,
      redação de token, rotação de arquivo e permissão `600`.
- [x] **A10** — corretor do WebKit desativado explicitamente e atributos
      `spellcheck`/`autocorrect` nos campos; digitação e envio preservados.

## Indicadores e ajustes

- [x] Indicadores discretos de carregamento ao abrir canal, carregar
      anteriores, sincronizar e voltar ao recente.
- [x] Botões desativados durante operações e sempre reativados no `finally`.
- [x] Seletor de cor de destaque com persistência e contraste calculado.
- [x] Indicador de RAM acima do perfil, PSS agregado e atualização a cada 12 s.
- [x] Tema escuro/AMOLED/automático integrado ao GTK em GNOME e compatível com
      Xfce4 sem usar `gsettings`.

## Testes executados

- [x] `python3 -m py_compile app.py core/*.py tests/*.py`.
- [x] `node --check ui/app.js`.
- [x] `./run.sh --mock --selftest`: 5 mensagens, 3 reações, 2 componentes,
      `sendText=""`, `sendAria="Enviar mensagem"`, `sendSvg=1`, sem erro JS.
- [x] `audit_ui.py`: 100 mensagens no cenário de intervalo longo, 300 no
      cenário com sobreposição, zero buracos, guardas eficazes e mídia com URL
      duplicada liberada.
- [x] `audit_initial_load.py`: mensagem ao vivo enfileirada e exibida no fim,
      sem duplicata; segundo caso com apenas uma cópia.
- [x] `audit_sync_e2e.py`: backend recebeu `limit=100`; janela final
      `1351..1450`, sem buracos.
- [x] `audit_ram.py`: 203,1 MB em 9 processos, igual à soma manual; filho
      incluído e removido.
- [x] `audit_settings.py`: migração única, logout, permissões `600`, 960
      gravações concorrentes sem erro e dicionário mutado sem exceção.
- [x] `audit_api.py`: URLs REST, `limit=0→1`, `limit=500→100`, `after` inválido
      vira `None`, heartbeat novo e detecção de GNOME/Xfce.
- [x] `audit_dm_reconnect.py`: conversa ativa sem `after`; DMs 21/22 com
      `after` e duas mensagens novas; limite de 10; segunda passada recuperou
      as duas restantes; terceira não refez chamadas; DM ativa sem `after`;
      falha isolada.
- [x] `audit_ui_final.py`: modal, ARIA, abas, foco preso, `Esc`, fundo, ícone
      de envio, envio e recarga.
- [x] `audit_install.py`: duas instalações completas, configuração/token
      preservados, `--check`, dependências ausentes, caminho Arch,
      distribuição não suportada, `--recreate-venv` e idempotência.
- [x] Varredura de segredos no conteúdo versionável: nenhum token, mfa ou
      credencial real encontrado; configuração local fora do repositório.

## Resultados resumidos

| Cenário | Resultado |
|---|---|
| Instalação Ubuntu em cópia temporária | 0 (duas vezes) |
| `--check` com dependências presentes | 0 |
| Dependências ausentes | erro com comandos, sem instalação |
| Caminho Arch simulado | erro com `pacman` e 4 pacotes |
| Distribuição não suportada | código 2 |
| Recuperação de DMs | 10 + 2, depois 0; sem duplicatas |
| Janela de reconexão | 100 msgs, `1351..1450`, sem buraco |
| RAM | 203,1 MB, igual à soma |
| Configuração concorrente | 960 gravações, 0 erros |

## Pendências e limitações

- [x] Publicar no GitHub em repositório público, branch `main`, com o commit
      local preservado e remoto `origin` configurado.
- [ ] Validar instalação real em Arch Linux com Xfce4. O caminho Arch e o tema
      sem GNOME foram testados por simulação/código, não em sessão real.
- [ ] Validar miniaturas, recuperação de DMs e reconexão com uma conta real do
      Discord e o CDN real.
- [ ] Repetir as medições A/B; a cópia de referência não estava disponível.
- [ ] Executar `apt-get`/`pacman` de verdade pelo instalador; as dependências já
      estavam presentes e não havia sudo não interativo.
- [x] Documentar que o corretor já vinha desativado neste ambiente; a
      desativação explícita foi confirmada.
- [x] Documentar que a configuração antiga permanece como cópia de segurança
      e que a migração é única.
- [x] Documentar que o fallback `VmRSS` pode superestimar o total quando
      `smaps_rollup` não está disponível.
- [x] Documentar que processos reparentados/efêmeros podem faltar em uma
      leitura específica do indicador de RAM.
