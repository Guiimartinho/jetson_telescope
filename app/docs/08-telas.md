# 08 — Todas as telas

O inventário completo: cada tela, o que mostra, o que o usuário pode fazer e os estados que
ela precisa tratar. Os esboços das principais estão em [`02-ui-ux.md`](02-ui-ux.md); as rotas
citadas, em [`04-api.md`](04-api.md). A coluna **Fase** segue o [`06-roadmap.md`](06-roadmap.md).

São 43 telas, 5 diálogos e 6 elementos presentes em todas elas.

## Em todas as telas

| ID | Elemento | Comportamento |
|---|---|---|
| X1 | Faixa de estado | nome do telescópio; conexão (conectado, reconectando há N s, sem conexão); atividade (parado, apontando, empilhando…); atalho do modo vermelho |
| X2 | Barra de navegação | Atlas · Planejar · **Observar** · Galeria · Aparelho |
| X3 | PARAR flutuante | aparece em qualquer destino enquanto houver trabalho rodando; um toque para tudo, sem confirmação |
| X4 | Modo vermelho | filtro sobre o app inteiro, brilho reduzido; lembra a escolha |
| X5 | Aviso de origem | "câmera simulada", "montagem simulada": some quando o dado é real |
| X6 | Erro com saída | o que aconteceu, em linguagem direta, e os botões do que fazer agora |

## C. Conectar e primeiro uso

| ID | Tela | Mostra | Ações | Estados especiais | Fase |
|---|---|---|---|---|---|
| C1 | Abertura | logo; "conectando a <nome>" | — (automático) | achou: vai para O1. Não achou em 5 s: C2 | 1 |
| C2 | Achar o telescópio | lista de aparelhos na rede, com sinal e se já está pareado; "Demonstração" | tocar num aparelho; ler QR; digitar endereço | lista vazia, com dica: "o celular está no WiFi do telescópio?" | 1 |
| C3 | Ler o QR | câmera com moldura; texto do que está acontecendo | ler; digitar o código à mão | sem permissão de câmera; QR de outro tipo | 1 |
| C4 | Entrar no WiFi do telescópio | "vou conectar este app ao WiFi <nome>" e o aviso do Android | permitir | recusou: explica e oferece tentar de novo; rede fora de alcance | 1 |
| C5 | Pareando | etapas: conferir identidade, provar o código, receber a chave | — | **identidade não confere** (possível impostor): para e explica; janela de pareamento fechada; código errado | 1 |
| C6 | Primeiro uso — nome | campo com o nome do telescópio | salvar | — | 4 |
| C7 | Primeiro uso — local e hora | mapa ou coordenadas; hora do celular | usar o GPS; digitar | sem permissão de localização: digitar à mão | 1 |
| C8 | Primeiro uso — WiFi de casa | redes que a Jetson enxerga | escolher e informar a senha; pular | senha errada; rede some; a Jetson troca de rede e o app a reencontra | 4 |
| C9 | Identidade mudou | "este telescópio não é o que você pareou" | parear de novo; cancelar | — | 1 |

Rotas: `/info`, `/pair/start`, `/pair/finish`, `/site`, `/network`.

## O. Observar

| ID | Tela | Mostra | Ações | Estados especiais | Fase |
|---|---|---|---|---|---|
| O1 | Início (parado) | saúde do aparelho; alvo sugerido para agora; continuar a última sessão | observar o sugerido; abrir a última sessão; ir ao Atlas | sem montagem; sem câmera; disco quase cheio | 1 |
| O2 | Indo para o alvo | prévia ao vivo; etapas: apontar, reconhecer o céu, centralizar, focar | PARAR; ver detalhes da etapa | falha em qualquer etapa, com as saídas daquela etapa | 2 |
| O3 | Prévia e enquadramento | imagem ao vivo em tela cheia; alvo e campo | exposição; ganho; filtro; arrastar para enquadrar; focar; empilhar | imagem toda preta ou estourada, com a dica correspondente | 2 |
| O4 | Empilhando | imagem empilhada; fotos, tempo, qualidade | PARAR; pausar; brilho; salvar instantâneo; pinça para zoom | nuvem passando (rejeições em sequência); foco piorando | 2 |
| O5 | Folha Pro | histograma com pretos e brancos; SNR e FWHM no tempo; aceitos e rejeitados, com motivo; exposição e ganho | ajustar pontos; ligar e desligar auto | — | 2 |
| O6 | Foco | curva de foco; posição atual; nitidez agora | autofoco; passo fino para dentro e para fora | curva sem mínimo (sem estrelas, fim de curso) | 2 |
| O7 | Fim da sessão | miniatura; tempo integrado; número de fotos | salvar e ir à galeria; compartilhar; continuar; descartar | — | 2 |
| O8 | Deitado | a mesma imagem em tela cheia; controles numa coluna à direita | os de O3 e O4 | — | 2 |
| O9 | Captura planetária | o planeta ao vivo; quadros recebidos e quantos estão sendo aproveitados | PARAR; no fim, gravar de novo | — | 4 |

Rotas: `/state`, `/observe/*`, `/preview.mjpg`, `/histogram`, `/focuser`, WebSocket.

## A. Atlas

| ID | Tela | Mostra | Ações | Estados especiais | Fase |
|---|---|---|---|---|---|
| A1 | Lista | busca; filtros (Hoje, tipo, cabe no campo); alvos com miniatura, altitude e observação | buscar; filtrar; abrir; favoritar | nada visível agora; busca sem resultado | 1 |
| A2 | Ficha do alvo | foto com a moldura do nosso sensor; altitude na noite; melhor horário; tamanho e brilho; sessões anteriores | observar agora; pôr no plano; favoritar | abaixo do horizonte; maior que o campo (sugere mosaico); perto demais da Lua | 2 |
| A3 | Coordenadas | campos RA e DEC, com conferência de formato | apontar; salvar como alvo próprio | coordenada abaixo do horizonte | 2 |
| A4 | Meus alvos | favoritos e já fotografados, com o total integrado em cada um | abrir; remover | lista vazia, com convite | 2 |

Rotas: `/targets`, `/targets/{id}`, `/targets/{id}/thumb`.

## P. Planejar

| ID | Tela | Mostra | Ações | Estados especiais | Fase |
|---|---|---|---|---|---|
| P1 | Plano da noite | fila com horário, alvo e tempo; trechos livres; regras gerais | adicionar; reordenar; iniciar a noite | plano vazio; itens que não cabem na noite | 3 |
| P2 | Item do plano | alvo; duração ou número de fotos; exposição e filtro; altitude mínima | salvar; remover | alvo nunca chega à altitude mínima | 3 |
| P3 | Noite em andamento | linha do tempo: feito (com miniatura), em curso, por fazer; motivo de cada alvo pulado | PARAR a noite; pular este alvo; abrir a imagem | amanhecendo; alvo pulado por nuvem ou por falha | 3 |
| P4 | Mosaico | mapa do alvo com a grade de painéis | linhas e colunas; sobreposição; mandar para o plano | grade grande demais para uma noite | 3 |
| P5 | Modos especiais | Lua e planetas; satélite; Sol | escolher; cada um abre a sua variação de Observar | Sol: só continua depois de confirmar o filtro | 3–4 |

Rotas: `/plan`, `/plan/start`, `/plan/stop`, `/mosaic`.

## G. Galeria

| ID | Tela | Mostra | Ações | Estados especiais | Fase |
|---|---|---|---|---|---|
| G1 | Sessões | grade com miniatura, alvo, data e tempo integrado | abrir; selecionar várias; filtrar por alvo | galeria vazia | 2 |
| G2 | Sessão | imagem grande; métricas (subs, integração, FWHM e SNR no tempo); condições da noite | abrir no estúdio; baixar; compartilhar; apagar | arquivo ausente na Jetson | 2 |
| G3 | Estúdio | imagem com antes e depois; presets; controles | brilho, cor, ruído; mais ajustes; desfazer | prévia demorando: mostra a anterior e o indicador | 2 |
| G4 | Mais ajustes | deconvolução; remoção do verde; reduzir e remover estrelas; pretos e brancos | ajustar; voltar ao preset | — | 3 |
| G5 | Exportar | formato (JPEG, TIFF, FITS); tamanho | salvar no celular; compartilhar | sem espaço no celular | 2 |

Rotas: `/sessions`, `/sessions/{id}`, `/sessions/{id}/image`, `/sessions/{id}/render`, `/render/presets`.

## D. Aparelho

| ID | Tela | Mostra | Ações | Estados especiais | Fase |
|---|---|---|---|---|---|
| D1 | Visão geral | montagem, foco, câmera, rede e sistema, cada um com o seu estado em uma linha | abrir cada área | qualquer item com problema sobe para o topo | 1 |
| D2 | Montagem | conectada ou não; posição; rastreando; estacionada; saúde dos drivers | direcional com três velocidades; PARAR; estacionar; casa; rastreio | desconectada, com o motivo; movimento só depois de confirmar que o caminho está livre | 3 |
| D3 | Foco | posição; passo | -100, -10, +10, +100; ir para posição | fim de curso | 3 |
| D4 | Câmera | modelo; ganho; offset; temperatura | ajustar | câmera simulada | 3 |
| D5 | Rede | modo atual (em casa ou WiFi próprio); nome e senha do WiFi do telescópio; WiFi de casa | trocar de modo; mudar a senha; esquecer a rede de casa | **trocar de modo derruba esta conexão**: o app avisa antes e reencontra o aparelho depois | 3 |
| D6 | Celulares pareados | lista com nome, papel e último uso | adicionar (gera QR); revogar; mudar papel | revogar o próprio celular pede confirmação dupla | 4 |
| D7 | Sistema | versões; temperatura; disco; tempo ligado | reiniciar; desligar; exportar registros | desligar com sessão rodando pede confirmação | 2 |
| D8 | Atualizações | versão do software e do firmware da montagem | atualizar | durante a atualização: não desligar; falha volta à versão anterior | 4 |
| D9 | Preferências do app | idioma; modo vermelho automático à noite; modo Pro; unidades; vibração e som | ajustar | — | 1 |
| D10 | Ajuda e sobre | guia rápido; glossário; licenças; versão do app | — | — | 4 |
| D11 | Alinhamento polar | o erro do eixo: total, e por parafuso (altitude e azimute) com o lado a girar | medir; medir de novo; na montagem simulada, girar os parafusos | medida que não fecha; medida velha depois de mexer nos parafusos; montagem real: ainda não | 4 |

Rotas: `/mount`, `/mount/*`, `/focuser`, `/drivers`, `/network`, `/network/*`, `/system`, `/system/*`, `/logs`.

## Diálogos

| ID | Quando | Texto e saídas |
|---|---|---|
| Q1 | antes do primeiro movimento da noite | "A montagem vai se mover. O caminho está livre?" — Mover / Cancelar |
| Q2 | apagar sessão | "Apagar <alvo>, <tempo>? Não dá para desfazer." — Apagar / Manter |
| Q3 | desligar com trabalho rodando | "Há uma sessão em andamento. Salvar e desligar?" — Salvar e desligar / Voltar |
| Q4 | trocar de rede | "O telescópio vai trocar de WiFi e esta conexão vai cair por alguns segundos." — Trocar / Cancelar |
| Q5 | Sol | "Apontar para o Sol sem filtro destrói o sensor. O filtro solar está na frente?" — Sim, está / Cancelar |

O PARAR nunca abre diálogo.

## Ordem de construção das telas

| Fase | Telas |
|---|---|
| 1 | X1–X6, C1–C5, C7, C9, O1, A1, D1, D9 |
| 2 | O2–O8, A2–A4, G1–G3, G5, D7 |
| 3 | P1–P5, G4, D2–D5 |
| 4 | C6, C8, D6, D8, D10, D11, O9 |

## Como ficou (2026-10-10)

As 43 telas existem. Onde a tela construída difere da tabela:

| Tela | Como ficou |
|---|---|
| C2 | a lista mostra quem se anuncia como telescópio na rede (DNS-SD) e se é o pareado. Não há "sinal": o anúncio não traz essa medida. Tocar no pareado manda procurar agora; nos outros, leva a ler o código deles. "Digitar endereço" não existe: o endereço vem no QR, e depois o app o acha sozinho |
| C4 | chega-se a ela por C2 (telescópio pareado sem resposta) ou por D5. Além de recusado e fora de alcance, trata o celular que não entra em WiFi pelo app: mostra o nome e a senha para entrar à mão |
| C8 | não é um passo obrigatório do primeiro uso: quem pareou pelo WiFi do telescópio recebe **um** convite em Observar, e a tela fica sempre em D5. Rede aberta ou já guardada entra sem senha |
| D5 | a senha do WiFi próprio só aparece para o dono, e escondida até pedirem. Quem não é dono vê como o telescópio está ligado e não troca |
| D8 | procurar, ver o que muda, instalar com barra de andamento, reinício, e a falha dizendo em que versão ficou. Não instala com trabalho rodando |
| D9 | ganhou "Avisar com a tela apagada" (pede a permissão de avisos do Android). Idioma, modo vermelho automático e unidades não entraram |
| D11, O9 | novas: não estavam no inventário |
| P5 | cada corpo tem "Apontar" e "Fotografar" (a captura planetária); o Sol só tem "Apontar" |

No aparelho de verdade, D5 e D8 mostram e explicam: trocar de rede e atualizar pelo app ainda
não estão habilitados na Jetson (`04-api.md` §10).
