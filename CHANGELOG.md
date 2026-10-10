# Changelog

Todas as mudanças notáveis do projeto. Formato baseado em
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); datas em ISO (AAAA-MM-DD).

## [Não lançado]

### App completo: o que faltava — rede, descoberta, atualização, avisos, polar e planetária (2026-10-10)
Desenvolvido e testado no PC, contra os simuladores. **Nada foi instalado na Jetson, a rede dela
não foi tocada, e nenhum celular de verdade foi usado ainda.** O APK (0.3.0) compila.

- **Alinhamento polar por três pontos (`src/control/polar_align.py`):** o método do Ekos, do NINA
  e do ASIAIR. Gira-se só a ascensão reta, reconhece-se o céu em três posições, e o eixo da
  montagem é a normal do círculo que os três campos desenham; o erro sai separado em altitude e
  azimute, que são os dois parafusos que a pessoa gira. Vale nos dois hemisférios. Modo `polar`
  no `Controller`, com a montagem de mentira `SimPolarAxis` (nasce desalinhada; os "parafusos"
  têm a folga de uma mão de verdade). Com giros de 45 graus a medida erra menos de 1,5 minuto
  de arco; com um arco estreito piora, e o teste registra isso.
- **Captura planetária (modo `planetary`):** grava centenas de quadros curtos e fica com os mais
  nítidos **conforme chegam** (uma fila de prioridade: o vídeo inteiro não caberia na memória
  da Jetson), alinha, empilha e aguça com o pipeline de `src/planetary`. Aponta antes, se
  pedido. Estado novo `CAPTURING` na máquina de estados.
- **Rede do telescópio (`src/api/network.py`):** a porta (`status`, `scan`, `join`, `set_mode`,
  `set_hotspot_psk`, `forget`) e o adapter de mentira `SimNetwork`. Duas regras do contrato: a
  troca acontece **depois** da resposta (o celular precisa ouvir "aceito" antes de a rede cair)
  e, se a rede nova não der certo, o aparelho **volta para onde estava** e conta o motivo.
  **O adapter de verdade (NetworkManager) não existe ainda:** na Jetson a rota responde
  `enabled: false`. No PC, `TELE_NETWORK=sim` liga o de mentira.
- **Atualização pelo app (`src/api/updates.py`):** a porta (`status`, `check`, `install`) e o
  `SimUpdater`. Se a instalação falha, a versão anterior continua valendo. Idem: só o adapter de
  mentira (`TELE_UPDATES=sim`); na Jetson, `enabled: false`.
- **Rotas novas:** `/observe/planetary`, `/observe/polar`, `/mount/polar/adjust`,
  `/network/scan|join|mode|hotspot`, `DELETE /network/known/{ssid}`, `/system/update` e
  `/system/update/check|install`. O estado ganhou `capture` e `polar`. Trocar a rede e
  atualizar são só do dono; a senha do WiFi próprio só vai para o dono e nunca para a auditoria.
- **Anúncio na rede no PC:** `run_console.py --advertise` anuncia `_telescope._tcp` com o pacote
  `zeroconf` (livre, opcional), para o app achar o servidor de desenvolvimento sem endereço. Na
  Jetson quem anuncia é o avahi, como antes.
- **App (0.3.0) — acha o telescópio sozinho:** quando ele não responde onde estava, o app o
  procura, ao mesmo tempo, onde a rede o anunciou (DNS-SD), no WiFi que ele mesmo cria
  (`10.42.0.1`) e pelo apelido de casa (`telescopio.local`), e guarda o endereço novo. **Endereço
  e anúncio não são identidade:** só é aceito quem apresentar o certificado pareado, e um
  candidato com outro certificado é ignorado em silêncio (não vira alarme).
- **App — telas novas e completadas:** lista de telescópios na rede (C2), entrar no WiFi do
  telescópio (C4), WiFi de casa (C8), rede completa (D5: trocar de modo com aviso, senha do
  WiFi próprio, esquecer a rede de casa), atualizações com procurar, instalar e acompanhar
  (D8), alinhamento polar (medir, ajustar, medir de novo) e "Fotografar" em Lua e planetas, com
  a variação de Observar para a captura. São 43 telas.
- **App — avisos com a tela apagada** (preferência, desligada de fábrica): enquanto há trabalho,
  um serviço em primeiro plano mantém o app ouvindo o telescópio, com um aviso fixo do que está
  acontecendo; quando o trabalho termina, falha, ou o sinal cai no meio, sai um aviso. O que a
  própria pessoa mandou parar não avisa.
- **App — o WiFi do telescópio fica guardado:** o dono recebe o nome, a senha e o endereço dele
  pela API; o app guarda (a senha, no cofre do sistema) para reencontrá-lo no campo.
- **Ícone dos avisos** gerado do símbolo do produto pelo `scripts/export_app_icons.py`, como os
  demais (vetor de uma cor, que é o que o Android usa).
- **Achados de uma revisão independente do lote, corrigidos antes de fechar:**
  - **o lado do azimute no alinhamento polar saía invertido ao sul do equador** (o azimute cresce
    do norte para o leste: olhando o polo sul, leste é azimute menor). A tela mandaria girar para
    o lado errado. Agora "leste positivo" vale nos dois hemisférios, com teste que põe o eixo
    direto no céu, sem passar pelo simulador (o teste falhava antes da correção);
  - durante a captura planetária a montagem não é mais movida, estacionada nem levada para casa
    à mão (`CAPTURING` entrou nas listas de "ocupada", no `Controller` e na API);
  - a captura guarda os melhores quadros com **teto em memória** (256 MB), não só em número, e
    um modo que termina depois de outro comando ter assumido não escreve mais no trabalho novo;
  - o alinhamento polar termina em estado válido (`STOPPED`, como o goto) e reenviar o comando
    devolve o mesmo trabalho em vez de "ocupado"; `/observe/run` não aceita `polar` nem
    `planetary` (só as rotas próprias, que conferem a montagem e o corpo);
  - no app: o prazo da troca de rede corre pelo relógio (com o telescópio mudo, esperar por
    número de perguntas viraria minutos); o serviço dos avisos não é recriado sozinho se o
    Android matar o app (o pacote quebraria); o aviso fixo desiste depois de 10 minutos sem
    sinal e não acompanha a câmera ao vivo; os avisos de sinal ocupam um lugar só; as gravações
    do pareamento vão em fila (o "esquecer" é sempre o último) e uma falha do cofre não trava a
    ligação; no máximo quatro endereços anunciados são tentados por vez, só IPv4 de rede local.
  - as portas da rede e da atualização ganharam nome (`NetworkControl`, `Updater`) e um teste
    de contrato, em que o adapter de verdade entra no dia em que existir.
- **Para o repositório e o CI:** o teste do anúncio na rede não abre rede (o anunciador de
  verdade é trocado por um de mentira); os ícones PNG gerados são conferidos pelo desenho, não
  pelos bytes do compressor, que mudam de um sistema para outro; e os arquivos gerados ficam
  sempre com LF (`.gitattributes`), senão a conferência falharia num checkout do Windows.
- **Documentação posta em dia:** o `README.md` da raiz deixou de dizer "fase de planejamento" e
  ganhou a seção "Estado atual"; `TASKS.md` ganhou o Milestone G (app e API); o inventário do app
  (`app/docs/01-funcionalidades.md`) diz, função por função, o que ficou feito, o que é simulado
  e o que não foi feito; `docs/33` explica que o console virou a reserva do app.
- **Testes:** 577 da Jetson, 143 do app, e 9 dos dois lados juntos
  (`scripts/run_app_integration.py`, agora com rede, atualização, polar e planetária).
- **Não validado em aparelho:** entrar no WiFi do telescópio pelo app, a busca na rede, os
  avisos e o serviço em primeiro plano. Estão escritos conforme a documentação do Android e dos
  pacotes, e compilam; só um celular diz se funcionam.
- **Ainda não:** os adapters de verdade da rede e da atualização na Jetson; comandar a montagem
  real (o alinhamento polar depende disso); a galeria listar o que o próprio telescópio captura
  (hoje só as sessões de referência); inglês.
- Detalhes: `app/README.md`, `app/docs/03` §8, `04` §10, `05` §10, `06` "Onde estamos", `07` §15,
  `08` "Como ficou".

### App completo: fases 3 e 4 na API e no app (2026-10-10)
Desenvolvido e testado no PC, contra os simuladores. **Nada foi instalado na Jetson; nenhum
celular de verdade foi usado ainda.** O APK (0.2.0) compila.

- **`Controller`, modos novos:** `preview` (câmera ao vivo sem empilhar, com a nitidez medida em
  cada quadro), `focus` (autofoco como trabalho, publicando a curva posição × FWHM; sem estrelas
  termina como `focus_failed` em vez de fingir) e `plan` (a fila da noite na ordem do dono, com
  o que aconteceu em cada item; `skip` pula o alvo, falha num alvo não derruba a noite). Estado
  novo `PREVIEW` na máquina de estados.
- **Montagem e foco à mão (simulados):** `mount:jog` com **prazo** — o movimento manual só dura
  enquanto o comando é renovado; se o celular some com o dedo no botão, a montagem para sozinha.
  Estacionar, casa, rastreio; passos do focalizador com fim de curso. `PARAR` também para o
  movimento manual. **A montagem real continua só leitura pela API** (`501 not_supported`): o
  movimento não é liberado sem validar na bancada.
- **Cada alvo com o seu campo no simulador:** antes, todo alvo desconhecido mostrava o campo de
  Andrômeda; agora o campo sai das coordenadas reais do alvo.
- **Rotas novas da API:** `/mount/slew|stop|park|unpark|home|tracking`, `/focuser`, `/camera`,
  `/observe/preview`, `/observe/focus`, `/observe/body`, `/solar`, `/plan` (ler, guardar,
  `start`, `skip`, `stop`), `/mosaic`, `/clients/invite`, `PATCH /clients/{id}`, `PUT /device`,
  `/network`, `/sessions/{id}/export` (JPEG, TIFF de 16 bits, FITS) e `DELETE /sessions/{id}`.
  O estado ganhou `focus`, `night`, os ajustes da câmera e o que a montagem deixa fazer.
- **Plano da noite (`src/api/plan.py`):** a fila fica guardada na Jetson; para cada item ela
  calcula quando começa e termina nesta noite e diz por que algum não cabe (não sobe, passa do
  amanhecer, desce antes do fim).
- **Mosaico:** a grade de painéis no céu (`core/mosaic.panel_grid_radec`), com sobreposição e a
  correção de ascensão reta perto do polo.
- **Lua, planetas e Sol (`src/core/ephem.py`):** posições em baixa precisão, sem dependência nem
  internet (elementos do JPL; série curta para a Lua). Conferidas contra a efeméride do astropy:
  planetas dentro de 0,15 grau, Lua dentro de 0,6. O Sol só é apontado com o filtro confirmado.
- **Convite para outro celular:** um dono gera um código de **uso único**, com o papel que
  escolher (dono, operador, visitante). O convite tem o seu próprio segredo, sorteado na hora:
  o segredo do aparelho (o da etiqueta) nunca viaja pela API. Mudar papel recusa tirar o último
  dono.
- **App (0.2.0), telas novas:** câmera ao vivo com enquadrar, focar e ajustar (O3), foco com a
  curva do autofoco (O6, D3), montagem (D2), câmera (D4), rede (D5), celulares pareados com
  convite por QR (D6), atualizações (D8), ajuda (D10), nome do telescópio (C6), plano da noite e
  noite em andamento (P1 a P3), mosaico (P4), Lua, planetas, Sol e satélite (P5), "mais ajustes"
  do estúdio (G4) e exportar (G5). São 81 testes do app.
- **Achados pelos testes de tela e corrigidos:** o aviso (toast) cobria o botão de voltar; a
  folha de papéis não rolava em tela pequena; na câmera ao vivo o PARAR ficava abaixo dos
  ajustes, fora da tela.
- **Os dois lados juntos:** `scripts/run_app_integration.py` agora cobre também a fase 3 (câmera
  ao vivo, foco, movimento manual com prazo, autofoco, plano e noite, convite, exportar): o
  cliente Dart contra o servidor Python de verdade.
- **Ícones:** `minus` e `arrow` no `ui_kit` (49 no total).
- **Ainda não:** achar o telescópio sozinho na rede (mDNS no app), trocar de rede pelo app (modo
  campo, WiFi de casa), atualizar pelo app, avisos com a tela apagada, alinhamento polar, captura
  planetária em vídeo, e comandar a montagem real.
- Detalhes: `app/README.md`, `app/docs/04-api.md` §9, `06` "Onde estamos", `07` §14.

### API protegida do app (v1) e o app Flutter, fases 0 a 2 (2026-10-09)
Desenvolvido e testado no PC, contra os simuladores. **Nada foi instalado na Jetson** e a rede
dela não foi tocada; **nenhum celular de verdade foi usado ainda.**

- **API v1 (`src/api`, `py -3.11 run_console.py --api`):** HTTPS e WSS na porta 8443, só TLS 1.3,
  com certificado do próprio aparelho (ECDSA P-256, autoassinado); pareamento por QR com janela
  aberta pelo dono, prova por HMAC (o segredo nunca trafega) e token de 256 bits guardado só
  como resumo. Rotas: aparelho, hora e local, alvos (busca, filtros, ficha com a noite),
  observar, imagem ao vivo, galeria, estúdio, sistema, auditoria. Servidor em FastAPI (livre).
- **Comando do dono:** `py -3.11 -m src.api.cli pair | clients | revoke | reset | info`. O QR é
  desenhado no terminal; nunca numa página da rede.
- **Trabalhos acompanháveis:** o `Controller` passou a publicar de qual comando é o estado
  (`job`) e como terminou (`outcome`: `ok`, `stopped`, `not_converged`, `error`). Reenviar o
  mesmo comando não executa duas vezes.
- **Modo novo `observe`:** aponta, centraliza e empilha num comando só (a "noite rápida" do
  app), para a sequência seguir na Jetson se o celular perder o sinal. `goto` aceita coordenadas.
- **Console web só leitura com a API ligada:** comando por HTTP aberto ao lado de uma API
  protegida seria a porta dos fundos. `--open-commands` os mantém, para a bancada.
- **Corrigido — o atlas não tinha a Nebulosa de Órion.** O filtro de tipos usava
  `"Cluster+Nebula"`, mas o OpenNGC escreve `"Star cluster + Nebula"`: 67 objetos ficavam de
  fora, entre eles M42 e a Roseta. O catálogo também passou a guardar o número Messier (a busca
  por "M31" não achava nada, porque o objeto se chama `NGC0224`).
- **Hora e local do celular chegam à montagem (`MountLink.update_site`):** o local tem versão,
  e quem envia é sempre a thread do link. Assim o dado não se perde se chegar no meio de uma
  reconexão, e não há duas threads falando INDI ao mesmo tempo. Um local recusado não derruba o
  link.
- **Catálogo rápido:** altitude de todos os objetos numa conta vetorizada (`altitudes_deg`):
  filtrar 12 mil objetos leva dezenas de milissegundos (a ficha do astropy levaria segundos).
- **App Flutter (`app/`):** tema e modo vermelho; ícones exportados do `ui_kit`
  (`scripts/export_app_icons.py`, 21 ícones novos desenhados lá); cliente com o certificado
  fixado, sem raízes confiáveis; telescópio falso para o modo demonstração e os testes; ligação
  que reconecta sozinha; telas de conectar e parear, início, observar, Atlas e ficha,
  coordenadas, meus alvos, galeria, estúdio, aparelho, sistema, local e hora, preferências.
- **Os dois lados amarrados:** respostas reais da API gravadas como arquivos de teste do app
  (`scripts/export_api_fixtures.py`), com um teste que falha se a API mudar sem regravar; a prova
  do pareamento conferida byte a byte em Dart; e `scripts/run_app_integration.py`, que sobe o
  servidor, pareia e roda o cliente Dart contra ele (impostor recusado, goto acompanhado pelo
  canal cifrado, revogação derrubando o canal).
- **Android:** permissões, abertura escura nos dois temas (o padrão abria com tela branca) e o
  código nativo para usar o WiFi do telescópio só dentro do app — este último **escrito e não
  validado em aparelho**.
- **Pronto para a Jetson, não executado:** `scripts/jetson_setup_api.sh` e
  `deploy/jetson/telescope-console.api.conf` (liga a API e anuncia o serviço na rede; não mexe
  na rede da Jetson).
- Detalhes: `app/README.md`, `app/docs/04-api.md` §8, `05` §9, `06` "Onde estamos", `07` §13.

### Plano do app do celular (2026-10-09)
- **Pasta `app/` criada, só com o plano** (ainda sem código): app em **Flutter**, Android
  primeiro e iPhone depois pela mesma base, pensado como produto. O app fala só com a Jetson.
- `app/docs/01..06`: todas as funcionalidades por área (com fase e o que a Jetson já faz),
  UI/UX para uso noturno com esboço de cada tela, conexão (casa, campo, descoberta,
  pareamento), contrato da API v1, arquitetura Flutter e roteiro em fases. `app/docs/00`
  reúne o que os apps concorrentes fazem.
- **Medido na Orin:** a placa WiFi interna (RTL8822CE, driver `rtl88x2ce`) faz estação e
  ponto de acesso, mas **não os dois ao mesmo tempo** (`iw list`: "interface combinations are
  not supported"). O plano parte de troca automática casa/campo; um segundo rádio USB fica
  como opção.
- Ambiente conferido: Flutter 3.41.9 e Android SDK presentes; faltam as licenças do SDK e um
  aparelho de teste.

### O console como app: nome na rede, ícone na tela inicial e tempo real (2026-10-09)
- **`http://telescopio.local`, sem IP nem porta.** Apelido mDNS publicado por um serviço
  pequeno (`telescope-mdns`) — a Jetson não muda de nome — e console também na porta 80
  (a 8080 continua). Instalação: `sudo bash scripts/jetson_setup_app.sh`.
- **O apelido é registro de endereço, não CNAME.** O CNAME era mais simples e foi a primeira
  versão; testado, o resolvedor mDNS do Windows o ignora. Os registros A são publicados por
  interface, só em redes de verdade (o avahi anunciava também o IP da ponte do docker), e
  republicados quando o IP muda.
- **Ícone e manifesto:** o console vai para a tela inicial do celular com o logo do `ui_kit`.
  O PNG é desenhado da mesma geometria do SVG, dentro da zona segura dos ícones "maskable".
- **Canal em tempo real (WebSocket, porta 8081):** a Jetson empurra o estado no instante em
  que ele muda (`FrameHub.wait_change()`), e recebe comandos pelo mesmo canal. A página só
  volta a consultar se o canal cair ou se a lib `websockets` faltar.
- Verificado na Orin a partir de um PC da rede, inclusive num Chrome de verdade (headless):
  cabeçalho em "GPU", "montagem conectada" e canal "tempo real".
- **Limite conhecido:** no Android, instalar em tela cheia exige HTTPS; por HTTP o Chrome
  cria um atalho com o ícone que abre no navegador. No iPhone abre em tela cheia. Não foi
  testado em celular.
- Testes: +27 (`test_console_app.py` 14, `test_mdns_alias.py` 13). Doc `docs/33`.

### Link automático Jetson ↔ montagem + drivers dos motores validados (2026-10-09)
- **Do plugar até a montagem pronta, nenhum passo manual.** `scripts/jetson_setup_mount.sh`
  instala: regra udev → **`/dev/telescope-mount` em qualquer porta USB**; e
  `telescope-indi.service`, amarrado ao dispositivo, que sobe quando a placa aparece e cai
  quando o cabo sai. Arquivos versionados em `deploy/jetson/`.
- **`IndiMount` fecha as duas lacunas do teste manual:** configura porta e baud da serial
  antes do `CONNECT` (o INDI abre a 9600 por padrão) e ganhou `set_site_and_time()` — o
  OnStepX acorda em 2000-01-01, lat/long 0, e sem hora e local um goto por RA/DEC erra.
  Falha de conexão vira `ConnectionError` claro e imediato, não timeout mudo.
- **`MountLink` (`src/control/mount_link.py`):** mantém a montagem conectada sozinha —
  conecta quando o indiserver aparece, reenvia hora e local a cada reconexão, percebe a
  queda do cabo pelo socket fechado e volta a tentar. Ligado por `TELE_MOUNT=indi` (o serviço
  da Jetson define; PC e CI seguem nos simuladores).
- **Console:** `/api/state` ganhou `mount` e o cabeçalho mostra "montagem conectada /
  desconectada / simulada".
- **`IndiClient`:** `alive` (o servidor fechou a conexão?) e `wait_change()` (espera a
  resposta a um comando nosso sem se enganar com um `Alert` antigo).
- **Verificado na Orin:** hora, fuso e coordenadas lidos de volta pelo WiFi da própria placa;
  a casa da montagem passou a apontar o polo **sul** celeste ao receber a latitude; INDI
  parado e religado, o link voltou sozinho; no **reboot da Jetson**, "montagem conectada"
  antes de 30 s de boot sem tocar em nada; e, com o **cabo trocado de porta USB**, o INDI
  parou e voltou sozinho e o console reconectou em cerca de 2 s.
- **Drivers TMC2209 validados no hardware.** O OnStepX só confere os drivers sob
  `MOTOR_DRIVER_DETECT`; sem isso um pino de UART errado não vira erro. Novo build de
  diagnóstico (`idf.py -DONSTEPX_DIAG=ON build`): os três eixos reportaram
  `motor driver device detected` em GPIO21/22 — a correção de pinagem de setembro está
  confirmada na placa. `config_assert.cpp` recusa um build de produto com `DEBUG` ligado.
- **Gravação pela própria Jetson** (`scripts/jetson_flash_mount.sh`, `scripts/mount_bootlog.py`):
  o diagnóstico entrou e o firmware de produto voltou pelo mesmo cabo do link. A placa não
  precisa mais voltar ao PC.
- **Fix: as telas mostravam "CPU" com tudo parado.** O hub só recebia o campo `backend`
  quando um modo rodava; ocioso ficava vazio, e console e painel caíam no padrão "CPU" com o
  pipeline em CuPy/GPU. O `Controller` agora publica o estado inicial (IDLE + backend real).
- Testes: +19 (`test_mount_link.py` 15, `test_console.py` 2, `test_firmware_config.py` 1,
  `test_controller.py` 1), contra um servidor INDI falso que agora imita o
  `indi_lx200_OnStep` (só conecta com porta e baud certos; acorda sem hora nem local; pode
  "morrer" e voltar). **260 verdes** + 5 pulados. Doc `docs/35` §9–10.
- **Em aberto:** os modos do painel (GOTO, agendador, rastreio) ainda usam os simuladores —
  trocar pela montagem real exige a mecânica; calibração (passos/grau, sentido, limites).

### Primeiro flash do OnStepX na E4 + link serial com a Jetson (2026-10-09)
- **A controladora está gravada e viva.** Fonte de 12V na bancada; placa lida pelo USB do PC
  (ponte CH340): ESP32-D0WD-V3 rev 3.1, **16 MB de flash confirmados na placa**. Antes de
  qualquer escrita, **backup integral do firmware de fábrica** (Marlin bugfix-2.0.x sobre
  ESP-IDF 3.2.3; 16.777.216 bytes em `firmware/backup/`, fora do git). Depois `erase-flash`
  e gravação de bootloader + partições + app, com hash verificado.
- **Teste de fumaça LX200 pela serial** (só consultas): `:GVP#` → `On-Step#`, versão
  `10.28x`, em casa apontando o polo, focalizador presente. Pronta para comandos 7,7 s após
  o reset. Binário: **1.054.576 bytes** (66% livres).
- **Correção de rumo — o link da Jetson é o cabo, como era o plano.** Em setembro, ao ver
  que o kernel do JetPack 6 não traz o driver CH340, o link foi virado para WiFi e isso foi
  documentado como decisão. O problema real custava dez minutos:
  `scripts/jetson_install_ch341.sh` compila o módulo `ch341` do kernel mainline para o
  kernel em execução e mascara a regra udev do `brltty`, que no Ubuntu 22.04 derruba o
  CH340 segundos depois de ele aparecer. Instalado e carregado na Orin.
- **O WiFi da placa fica, como acesso secundário:** ponto de acesso próprio
  (`OnStep-Telescopio`, LX200 sobre TCP em `192.168.0.1:9999`). A senha mora em
  `firmware/config/Config.local.h`, **fora do git**, gerada aleatória pelo
  `fetch_onstepx.py`; a Config versionada recusa compilar sem ela, então nunca sai um
  firmware com a senha padrão do OnStepX. Modo estação ficou de fora de propósito (exigiria
  a senha da rede de casa no firmware) e uma trava de compilação impede que volte.
  Verificado de ponta a ponta: um PC entrou no AP e `:GVP#` pela TCP 9999 devolveu `On-Step#`.
- **Log do IDF em `WARN`.** O console divide a UART0 com o canal LX200; em `INFO` o WiFi
  imprimiria uma linha a cada cliente do AP, no meio das respostas que o INDI lê.
  Verificado: 0 bytes espontâneos na serial enquanto um cliente entrava e saía do AP.
- **O que a bancada desmentiu:** `docs/35` dizia que a E4 "não se alimenta pelo USB:
  comprovado por não enumerar". Com os 12V ligados ela continuou fora do `lsusb` da Jetson
  (que não depende de driver) e enumerou na hora no PC. O sintoma era real; a causa não
  estava provada, e a da Jetson segue em aberto.
- Testes: `test_firmware_config.py` passou de 17 para 22 (link serial num baud do INDI,
  rádio só como AP, nenhuma credencial versionada, log em `WARN`, arquivo de segredos gerado
  e nunca sobrescrito) + duas travas novas em `config_assert.cpp`. `.gitattributes` força LF
  nos `.sh` (com `autocrlf` eles quebrariam na Jetson).
- **Link validado na Jetson, de ponta a ponta, sem mudar uma linha do nosso código:**
  `1a86:7523` → `ch341` → `/dev/ttyUSB0` (aberto pelo usuário comum) → `indi_lx200_OnStep`
  a 115200 → `IndiMount.get_radec()` devolveu RA 12,77 h / DEC +90°, a casa da GEM. Abrir a
  porta não reinicia a placa. A não-enumeração anterior na Jetson era a ligação do cabo.
- **Em aberto:** `IndiMount` precisa configurar porta e baud da serial (hoje feito à mão; o
  INDI abre a 9600); a Jetson tem de enviar hora e local na conexão (a montagem reporta
  `UTC 2000-01-01` e lat/long 0 — sem isso um goto por RA/DEC erra); **validar a UART dos
  TMC2209 no hardware** — `:GXU1#` devolve `0` porque o monitoramento vem desligado e a
  detecção só existe sob `MOTOR_DRIVER_DETECT`, então hoje um pino de UART errado não
  viraria erro. Doc `docs/35` §8–9.

### Firmware da montagem: OnStepX como projeto ESP-IDF 6 (2026-09-08)
- **`firmware/`**: projeto ESP-IDF 6 completo para a **FYSETC E4** (ESP32-WROOM-32E) —
  `CMakeLists`, `sdkconfig.defaults`, `partitions.csv` (16MB com OTA), componente `main`,
  componente `onstepx` e scripts. Doc `docs/35`.
- **Migração pelo caminho oficial, não por reescrita.** O OnStepX tem **432 arquivos /
  66.367 linhas** (o `.ino` em si são 161). Reescrevê-lo em API nativa do IDF seria meses
  num código de tempo real, e contra o princípio de reuso (`docs/08`). Em vez disso,
  `arduino-esp32` entra como **componente gerenciado do IDF** — ele declara
  `idf: ">=5.3,<6.2"` e a release 3.3.9 adicionou suporte a IDF 6.0. Resolvido: 3.3.11.
- **Poda em camadas** (`scripts/prune_onstepx.py`): remove o que não é alcançável na E4.
  Camada 1 aplicada — **−33 arquivos, −3.645 linhas** (HAL de atmel/STM32/Teensy/mbed/
  arduinoM0 + 17 pinmaps de outras placas). Camadas 2 e 3 declaradas para aplicar aos poucos,
  cada uma com build verde antes da seguinte.
- **Achado que virou teste — a UART dos TMC2209.** A tabela de pinos oficial da FYSETC (e o
  Marlin) põem a UART dos drivers em **GPIO21/22**; o pinmap `FYSETC_E4` do OnStepX usa
  **GPIO15**, que nesta placa é o **Z-MIN/Z-DIAG**. O padrão não alcançaria os drivers e
  colidiria com o endstop. Corrigido na nossa Config + patch que torna `SERIAL_TMC_TX`
  sobrescrevível (o pinmap o redefinia sem guarda, descartando nossa escolha em silêncio).
- **Atrito arduino-esp32 × IDF 6** documentado e resolvido cirurgicamente: `-Werror` do IDF 6
  transformava dois avisos de bibliotecas do Arduino em erro fatal. Rebaixados **só** nesse
  componente (`LittleFS`), e o do mbedTLS resolvido fazendo o que o aviso pedia
  (`CONFIG_MBEDTLS_PSK_MODES`). Nosso código e o do OnStepX seguem sob `-Werror`.
- **A árvore do OnStepX não é versionada** — baixada pinada no commit `65a7518` (v10.28x)
  por `scripts/fetch_onstepx.py`, que instala a Config, aplica o patch e poda. Build
  reprodutível sem 66k linhas de terceiro no `git diff`.
- **Build VERDE no ESP-IDF v6.0.2** (alvo `esp32`): `onstepx_telescope.bin` = **1.063.440
  bytes**, 66% livres na partição de 3 MB. Outros erros achados e corrigidos pelo caminho:
  `SERIAL_B` não existe na E4 (o canal de rede é `SERIAL_RADIO`), `FileVersionConfig`
  ausente, e o OnStepX **não embute** o driver dos TMC (`<TMC2209.h>` é lib externa — virou
  o componente `firmware/components/tmc2209/`).
- **Política de warnings explícita:** `-Wno-error` **apenas** nos componentes de terceiro
  (`onstepx`, `tmc2209`) — o OnStepX é escrito para o toolchain Arduino e dispara avisos
  reais mas não acionáveis (`volatile--` do C++20, `unsigned < 0` dentro do `Arduino.h`).
  Nosso código e o do IDF seguem sob `-Werror`.
- Testes: **+26** (`test_firmware_config.py` 17, `test_firmware_prune.py` 9), sem placa nem
  toolchain, mais `config_assert.cpp` — travas de pinagem verificadas **após o
  pré-processador** (o valor que o compilador usou, não o texto da Config). **Ambos
  verificados com dentes**: injetando `SERIAL_TMC_TX 15`, dois testes falham e o **build
  para** com as mensagens escritas.
- ⛔ **Gravar continua bloqueado por uma fonte 12V** — a E4 não se alimenta pelo USB (não
  enumera nem na Jetson nem no PC). Ver `docs/34`.

### Prontidão de campo: arranque do Atlas + operação offline (2026-09-08)
- **Atlas abria em 78,8 s** no Orin (2ª chamada: 0,27 s) — no celular, lê como travado. Causa
  dominante: o **astropy tentava BAIXAR a tabela IERS** (~70 s), mais 6,6 s de carga do OpenNGC
  e 1,7 s da 1ª transformação de coordenada. `catalog.configure_astropy_offline()`
  (`auto_download=False` **+ `auto_max_age=None`**) + `console.warm_cache()` numa thread no
  arranque do serviço → **3,07 s no pior caso, 0,28 s aquecido**.
- **Elimina uma dependência de rede escondida:** `docs/33` promete campo sem internet, mas o
  cálculo de visibilidade saía para a rede a cada boot do serviço. Agora não sai.
- **Armadilha coberta por teste:** desligar só o `auto_download` **quebra** o cálculo
  (`ValueError ... predictive values ... more than 30.0 days old` — o caso real do Orin). O teste
  `test_altitude_still_works_offline` falhou primeiro e forçou a segunda trava. Trocar lento por
  quebrado teria sido pior.
- **`usermod -aG dialout`** na Jetson: `/dev/ttyUSB*` não abriria para o `indi_lx200_OnStep`
  (que roda como usuário) quando a controladora da montagem for plugada — pré-requisito do Milestone F.
- Testes: +5 (`test_catalog.py` 3, `test_console.py` 2). **210 verdes** (GPU) + 5 pulados;
  16/16 dos módulos tocados verificados no próprio Orin (aarch64, Py3.10, astropy 6.1.7). Doc `docs/34`.

### T7/T21/T22 — CI + git, catálogo do céu, mais alvos reais (2026-07-21)
- **T22 catálogo**: `src/core/catalog.py` (OpenNGC/pyongc, ~14k objetos) — `find()` (RA/DEC p/ GOTO),
  `Rig` (FOV+mag limite), `framable()` (1868 capturáveis c/ nosso rig), `visible()` (altitude); `run_catalog.py`.
  GOTO aponta em QUALQUER alvo. Doc `docs/26`.
- **T21 alvos**: baixados/processados M51 (galáxia) + NGC2244 (Roseta) do MILAN → Estúdio com 3 alvos reais.
  Script ganhou `--mono` + `remove_hot_pixels` (`gpu/calibration`, testado) — corrige "walking noise" sem darks. `docs/27`.
- **T7 CI**: `git init` + commit inicial (main, 148 arquivos), `.github/workflows/ci.yml` (pytest `-m "not
  hardware"` + CTest), `.gitignore` + `requirements.txt` completos. **166 testes verdes no modo CI.**
- Deconvolução Richardson-Lucy + denoise (`postproc/deconv.py`) + preset H-alpha no estúdio. Doc `docs/25`.

### Painel: foto real visível + correção do congelamento (2026-07-21)
- **Modo "Dados reais (M67)"** no painel (`capture/real_source.py` `RealFitsSource` + `_run_realdata`):
  empilha a FOTO REAL do M67 ao vivo (registro por estrelas reais + lucky imaging), tornando o dado do
  T15 visível na UI. Relaxa o gate de FWHM (PSF real ~10px). Validado: 30 subs, SNR ~7,8x.
- **Fix (congelamento):** um modo que terminava SOZINHO (sem Parar) deixava o painel preso no último
  estado (STACKING) → botões pareciam mortos. `Controller._run_mode` ganhou `finally` que leva a IDLE/
  STOPPED ao fim de qualquer modo (`run_stack` continua sem forçar estado, p/ o agendador compor).
- Página visual de validação (artifact) com a foto real + estrelas detectadas + tabela dos modos.
- Testes: +3 (foto real source, modo realdata, regressão de congelamento). **143 verdes + 5 pulados.**

### T16 — Auto-find celeste em malha fechada RA/DEC (2026-07-21)
- **`control/autofind_radec.py`** `close_loop_goto`: o "apontar sozinho" em coordenadas celestes —
  slew→plate-solve→sync até centralizar (~2 iters). `angular_sep_arcmin` (haversine). Amarra T13+T14.
- Dublês `SimRaDecMount`/`SimRaDecSolver` (análogos celestes de SimMount/SimSolver); `IndiMount` ganhou
  `goto/sync/position` em GRAUS (converte p/ as HORAS do INDI) → o MESMO laço serve sim e hardware.
- Painel: botão **GOTO (RA/DEC)** (`run_app.py`), erro em arcmin ao vivo. Validado: M42 **19,4→0,36 arcmin**.
- Testes: +7 (`test_autofind_radec.py` 6 + controller goto). **140 verdes + 5 pulados.** Doc `docs/22`.

### T14–T15 — Solver ASTAP real + validação com dados reais (2026-07-21)
- **T14** `control/solver.py`: `AstapSolver` chama o **ASTAP** de verdade (salva FITS → CLI → parseia
  o `.ini` → `WcsInfo`) + `parse_astap_result` (parser puro). `astap_bin` aceita argv-prefixo → testado
  com um **ASTAP falso** (`tests/fake_astap.py`); sem ASTAP, falha limpa (`None`). Integração real em
  `test_solver_integration.py` (marker `hardware`, pulado).
- **T15** validação do pipeline com **dados REAIS**: campo estelar de M67 (`tests/data/real_starfield_
  m67.fits`, via `scripts/fetch_real_data.py`/photutils). Detecção 60 estrelas, FWHM real ~10px, registro
  correlação **0,215→0,995**, empilhamento **σ 60→15 = √16 (4,0×)**. Pega o que o simulador esconde.
- Testes: +12 (`test_solver_astap.py` 7, `test_real_pipeline.py` 5). **133 verdes + 5 pulados.** Doc `docs/21`.
  Milestone D quase fechado — resta só **T7 (CI)**.

### T13 — Camada INDI validada sem hardware (2026-07-21)
- **`io/indi_client.py`**: cliente INDI **puro-Python** (socket + XML, stdlib) — substitui o
  `pyindi-client`, que não roda no Windows. Roda no PC de dev E na Jetson; testável na CI.
- **Adapters reescritos** sobre o cliente: `IndiCameraSource` (CCD_EXPOSURE→BLOB FITS), `IndiMount`
  (EQUATORIAL_EOD_COORD, RA/DEC nativo), `IndiFocuser` (ABS_FOCUS_POSITION), `IndiFilterWheel`
  (FILTER_SLOT/FILTER_NAME). Antes eram escafolds que levantavam `NotImplementedError`.
- **`tests/fake_indi.py`**: servidor INDI falso (imita os `indi_simulator_*`) → testa a fronteira de
  hardware inteira no Windows. `scripts/run_indi_sim.sh` sobe os simuladores reais no WSL/Jetson.
- Testes: +13 (`test_indi_client.py`, `test_indi_adapters.py`) + 4 de integração (`hardware`, pulados
  no CI). Atualizados os testes de robustez (adapters agora falham com erro de conexão claro, não stub).
  **121 testes verdes** (4 pulados). Doc `docs/20`. Milestones D/E/F em `TASKS.md`.

### T12 — Painel de controle + Noite autônoma; correção do "Parar" (2026-07-21)
- **`core/autonomous.py`** (`AutonomousNight` + `Observation`) + `run_night.py`: noite sem operador.
- **`core/controller.py`** + `run_app.py`: painel web que roda TODOS os modos (Empilhar/Auto-find/
  Agendador/Mosaico/Rastrear/Noite/Parar) sob demanda, em `http://localhost:8000`.
- **Fix de concorrência 1:** trocar de modo travava em `STOPPED` (terminal) → `Session.reset_state()`
  chamado por `Controller._start` após esperar o worker morrer (loop-join, sem órfão revivido).
- **Fix de concorrência 2:** o "Parar" parecia não funcionar — o worker *parava* (`state=STOPPED`),
  mas `/stats` mostrava `STACKING` para sempre. `_set_state` não empurrava o estado ao `FrameHub`.
  Corrigido: `_set_state`/`reset_state` agora chamam `_publish()`. Painel atualiza na hora.
- Testes: +regressões em `test_controller.py` (recupera de STOPPED, troca de modo, hub reflete stop).
  Doc `docs/19`. T12 fechado em `TASKS.md`.

### Fase 4 (T8–T11) — rastreamento IA em tempo real (2026-07-21)
- **T8** `control/tracking.py`: `OpticalFlowTracker` (Lucas-Kanade; cv2.cuda/VPI na Jetson).
- **T9** `control/detector.py`: `BrightObjectDetector` (CV) + `YoloTensorRTDetector` (YOLO→TensorRT
  na Jetson, **fallback CV** no PC).
- **T10** `Session.track`: laço detecção → predição de velocidade → **feed-forward** ao mount; estado `TRACKING`.
- **T11** `capture/satellite.py` (objeto em movimento) + `run_tracking.py`. Erro de rastreio **~1 px**.
- Testes: +4 (`test_tracking.py`) → **100 testes verdes**. Doc `docs/18`. T8–T11 em `TASKS.md`.

### T2–T6 — pós-processo, filtros, controles web, perfis, persistência (2026-07-21)
- **T2** `postproc/enhance.py`: remoção de gradiente (fallback) + wrapper GraXpert; `--enhance` no run_stack.
- **T3** `control/filterwheel.py`: port + Sim/INDI + `filter_for_target`; `Target.filter` trocado pelo agendador.
- **T4** controles web: `FrameHub` com fila de comandos, `GET /cmd/<ação>`, botão **Parar**; `Session._poll_commands`.
- **T5** `core/vo.py` (Value Objects imutáveis) + `core/profiles.py` (YAML) + `profiles/*.yaml`.
- **T6** `core/session_store.py`: resumo de sessão (JSON) + `Telemetry` (JSONL); resumo salvo no run_stack.
- Testes: +19 → **96 testes verdes** (na GPU). Doc `docs/17`. T2…T6 marcadas em `TASKS.md`.

### T1 — Mosaico multi-painel + plano de execução (2026-07-21)
- **`TASKS.md`**: plano ordenado até a Fase 4 (T1…T12) + bring-up de HW depois.
- **`src/core/mosaic.py`** + `run_mosaic.py`: planeja a grade de painéis e captura cada um reusando
  o `Scheduler` (auto-find→autofoco→stack→FITS/WCS por painel); `stitch_siril` costura no Siril
  (pula com mensagem clara se ausente). Testes: +3 → **77 testes verdes**. Doc `docs/16`.

### Saída FITS/WCS + UI redesenhada (2026-07-21)
- **`src/io/fits_io.py`**: `save_fits`/`load_fits` + `WcsInfo` (reuso astropy). Salva o stack como
  FITS float32 com **WCS** (RA/DEC do plate solve) e metadados (OBJECT/NCOMBINE/DATE-OBS) —
  abre no Siril/PixInsight/ASTAP. Integrado ao `run_stack` (`stack_<alvo>.fits`).
- **UI do live view redesenhada** (`server/webview.py`): painel de controle — pílula de estado
  colorida, barra de progresso da fila de alvos, SNR em destaque, badge GPU/CPU, indicador "AO VIVO".
- Testes: +3 (`test_fits.py`) → **74 testes verdes**. Doc `docs/15`.

### Otimização de GPU + benchmark (2026-07-21)
- **Warp afim** e **variância do Laplaciano** movidos para a GPU (`cupyx.scipy.ndimage`);
  stack já era CuPy. Pipeline **mantém o frame na VRAM** (calibração→warp→stack), baixando só o
  cinza 1× para a detecção — minimiza cópias Host↔Device (Entregável #1 do CLAUDE.md).
- `scripts/benchmark_gpu.py` — **speedup medido no RTX 4070**: warp **49×**, stack **41×**,
  laplaciano 9,6× em 4K.
- `cv2.cuda` indisponível no pip (CPU-only) → usamos cupyx; na Jetson o cv2.cuda compilado é alternativa.
- Testes: +4 (`test_gpu_ops.py`, warp GPU≈CPU) → **71 testes verdes (na GPU)**. Doc `docs/14`.

### Calibração completa + GPU no PC de dev (2026-07-21)
- **`gpu/calibration.py`**: `Calibrator` completo (bias/dark/flat), `build_master`,
  `build_master_flat` (normalizado), `from_frames`. Corrige bias, corrente de escuro,
  **pixels quentes** e **vinheta**. Injetável via `Session(calibrator=…)`; `run_fase1 --calibrate`.
- **Simulador**: artefatos fixos do sensor (bias/dark/hot-pixels/vinheta) + geradores
  `bias_frame()`/`dark_frame()`/`flat_frame()` (padrão OFF).
- **GPU validada no PC de dev (RTX 4070, CUDA 12.9)**: `cupy-cuda12x` instalado → toda a suíte
  e o pipeline rodam em **CuPy/GPU** (mesma família da Jetson) — de-risca o caminho GPU.
- Correção de bug: dimensões do simulador não sincronizavam com o pipeline (regressão coberta).
- Testes: +6 → **67 testes Python** verdes (agora na GPU). Doc `docs/13-calibracao.md`.

### Fase 3 (parte) — Agendador multi-alvo / Plan mode (2026-07-21)
- **`core/scheduler.py`** (`Target` + `Scheduler`): percorre uma fila de alvos sozinho
  (auto-find → autofoco → stack por alvo), por prioridade e com filtro de visibilidade.
  Falha num alvo não derruba a agenda. Entrada `run_scheduler.py` (com `--loop`).
- **State machine:** novo estado `SCHEDULING` (entre alvos), preservando o invariante de segurança.
- **`run_stack(frames=…, label=…)`**: orçamento de integração e saída (`stack_<alvo>.png`) por alvo.
- Pausas de ritmo agora só ocorrem com live view (headless/CI mais rápido).
- Testes: +4 (`tests/test_scheduler.py`) → **61 testes Python** verdes.

### Fase 2 — Autonomia (2026-07-21)
- **Auto-find (GOTO + plate solving):** laço `slew → solve → corrige → centraliza`
  (`Session.auto_find`). Validado: erro 556 → 1,6 px em 2 iterações.
- **Autofoco:** curva-V/hipérbole com *bracketing* do mínimo (`control/autofocus.py`).
  Validado: foco crítico em 6294 (real 6300).
- **Ports de controle:** `control/{mount,focuser,solver}.py` (adapters `Sim*` + escafolds
  `Indi*`/`Astap*` p/ hardware) e `capture/sky.py` (céu apontável). `run_fase2.py` (com `--loop`).
- **State Machine explícita** (`core/state.py`): IDLE/SLEWING/SOLVING/FOCUSING/STACKING/ERROR/
  STOPPED, com invariante de segurança (não empilha após slew cego) — integrada ao orquestrador.

### Fase 1 — Live Stacking MVP (2026-07-21)
- **Pipeline GPU** (o diferencial): `gpu/stacker.py` (média ponderada float32 na VRAM),
  `gpu/quality.py` (FWHM por área a meia-altura + Var. Laplaciana), `gpu/registration.py`
  (astroalign com fallback cv2), `calibration.py`, `debayer.py`.
- **Backend agnóstico** (`backend.py`): CuPy/GPU na Jetson, NumPy/CPU no PC — mesmo código.
- **Captura:** `capture/{simulator,source,ring_buffer,indi_source}.py` (roda sem câmera).
- **Live view web** (`server/webview.py`): stream MJPEG + stats, sem dependências extras.
- **Orquestrador** (`core/orchestrator.py`) + `run_fase1.py`. Validado: SNR ~9,9× em 50 frames.

### Engenharia — arquitetura & testes (2026-07-21)
- **Suíte de testes:** 57 testes Python (`pytest`: unit, propriedades/hypothesis, robustez,
  integração/contrato) + 5 casos C++ (`doctest`/CTest, `cpp/`). Todos verdes.
- **Docs de engenharia:** `docs/10` (arquitetura testável + pirâmide) e `docs/11` (decisão de
  arquitetura: Hexagonal + Pipes&Filters + State Machine; TDD sim, DDD não).
- Convenções anexadas ao `CLAUDE.md`; `.gitignore`, `pytest.ini`, `cpp/CMakeLists.txt`.

### Planejamento & pesquisa (2026-07-20 → 21)
- **Documentação de projeto** `docs/01..09`: hardware/BOM, arquitetura de dados (zero-copy),
  pipeline, roadmap, setup da Jetson, aceleração & técnicas, reusar-vs-construir, Fase 2.
- **Pesquisa de mercado (mid-2026):** compute Orin NX 16GB (dev em Orin Nano Super 8GB),
  câmera Sony IMX585 (ZWO ASI585MC), montagem ZWO AM3N, óptica ~250mm, ASTAP/cedar-solve.
- **Comparativo visual** com o DWARFLAB DWARF 3 (Artifact): placar 11×7×5 + implicações de arquitetura.
- Restrição adotada: **somente software FOSS/grátis**.
