# 01 — Funcionalidades

Tudo o que o app terá, por área. Cada linha diz em que fase entra (ver
[`06-roadmap.md`](06-roadmap.md)) e o que a Jetson já sabe fazer:

- **pronto** — a Jetson já faz; o app só precisa mostrar e comandar;
- **parcial** — a lógica existe, falta expor ou parametrizar;
- **novo** — não existe ainda;
- **hardware** — depende de peça que ainda não temos (câmera, mecânica).

O que hoje roda sobre céu simulado continua valendo como função: o app mostra a origem do dado
("câmera simulada") em vez de esconder.

## A. Conectar e primeiro uso

| Função | Fase | Jetson |
|---|---|---|
| Achar o telescópio sozinho na rede (sem digitar IP) | 1 | parcial (nome na rede feito; falta anunciar o serviço) |
| Conectar por endereço manual ou QR code | 1 | pronto / novo (QR) |
| Reconectar sozinho e dizer a verdade sobre a conexão | 1 | pronto (WebSocket) |
| Enviar hora e local do celular (GPS) para o telescópio | 1 | novo |
| Assistente de primeiro uso: nome do aparelho, WiFi de casa, local | 4 | novo |
| Parear o celular com o aparelho (código/QR) | 4 | novo |
| Vários celulares: um comanda, os outros assistem | 4 | novo |
| Modo demonstração (sem telescópio) | 2 | pronto (simuladores) |

## B. Início

Não é uma tela à parte: é o que **Observar** mostra quando nada está rodando, mais a faixa de
estado presente em todas as telas (ver [`02-ui-ux.md`](02-ui-ux.md)).

| Função | Fase | Jetson |
|---|---|---|
| Estado geral: o que o telescópio está fazendo agora, com progresso | 1 | pronto |
| Saúde: montagem, câmera, foco, GPU, temperatura, espaço em disco | 1 | parcial (montagem e GPU prontos) |
| Atalhos: continuar a última sessão, alvo sugerido para agora | 2 | parcial |
| Botão PARAR sempre à mão | 1 | pronto |
| Condições do céu a partir da imagem (fundo, transparência) | 3 | parcial (métricas do pipeline) |

## C. Atlas (escolher o alvo)

| Função | Fase | Jetson |
|---|---|---|
| Catálogo com cerca de 14 mil objetos, busca por nome ou número | 1 | pronto |
| Filtros: tipo, visível agora, cabe no nosso campo, brilho | 1 | parcial (falta filtrar no servidor) |
| "Melhores de hoje": ranking por altitude, tamanho e brilho | 2 | parcial |
| Ficha do alvo: altitude ao longo da noite, nascer e pôr, enquadramento com o nosso sensor | 2 | parcial |
| Favoritos e histórico (o que já fotografei) | 2 | novo (guardado no celular e na Jetson) |
| Coordenadas manuais (RA/DEC) | 2 | pronto |
| Lua e planetas | 2 | parcial (modo planetário existe; falta efeméride) |
| Passagens da ISS e de satélites | 4 | parcial (rastreio existe; faltam órbitas atualizadas) |

## D. Observar

| Função | Fase | Jetson |
|---|---|---|
| Imagem ao vivo | 1 | pronto |
| Ir para o alvo e centralizar por plate solve, mostrando cada etapa | 2 | pronto em simulação; **hardware** para valer |
| Autofoco, com a curva de foco | 2 | pronto em simulação; **hardware** |
| Empilhar ao vivo: começar, pausar, parar | 2 | pronto |
| Exposição, ganho, filtro | 2 | parcial (falta parametrizar) |
| Estatísticas: SNR, FWHM, quadros aceitos e rejeitados, tempo integrado | 2 | pronto |
| Ajuste de brilho/contraste da prévia (auto e manual), histograma | 2 | pronto |
| Enquadrar com o dedo: arrastar a imagem move a montagem | 3 | **hardware** |
| Rótulos dos objetos no campo (a partir do plate solve) | 3 | parcial |
| Salvar um instantâneo no celular | 2 | pronto |

## E. Modos especiais

| Função | Fase | Jetson |
|---|---|---|
| Lua e planetas (lucky imaging) | 3 | pronto |
| Mosaico: planejar a grade sobre o alvo e capturar | 3 | pronto |
| Satélite / ISS: rastreio em tempo real | 4 | pronto em simulação; **hardware** |
| Sol, com trava de segurança: só com filtro confirmado | 4 | novo |

## F. Planejar

| Função | Fase | Jetson |
|---|---|---|
| Fila de alvos da noite, com prioridade e tempo por alvo | 3 | pronto |
| Janela de cada alvo (quando está alto o bastante) | 3 | parcial |
| Noite autônoma: iniciar, acompanhar, parar | 3 | pronto |
| Linha do tempo da noite: o que foi feito, o que falta | 3 | parcial |
| Aviso no celular quando um alvo termina ou falha | 4 | novo |
| Plano de várias noites: o mesmo alvo continua na noite seguinte | 4 | novo |
| Modelos de plano reutilizáveis | 4 | novo |

O plano é uma lista livre de horários, sem grade fixa: a grade de 10 minutos é uma das queixas
mais citadas num concorrente (`00-referencias.md`).

## G. Galeria

| Função | Fase | Jetson |
|---|---|---|
| Sessões por alvo e por noite, com miniaturas | 2 | parcial |
| Ver o resultado em tela cheia, com zoom | 2 | pronto |
| Dados da sessão: integração, número de subs, FWHM e SNR ao longo do tempo | 3 | parcial |
| Baixar para o celular (JPEG; TIFF e FITS para quem processa fora) | 2 | parcial (só JPEG hoje) |
| Compartilhar pelo menu do Android | 2 | — (só no app) |
| Apagar e ver o espaço em disco | 3 | novo |

## H. Estúdio (acabamento da imagem)

O processamento roda na GPU da Jetson; o app manda os controles e recebe a prévia.

| Função | Fase | Jetson |
|---|---|---|
| Presets (natural, vívido, nebulosa, suave, H-alfa) | 2 | pronto |
| Ajustes: pretos, brancos, estiramento, saturação, cor | 2 | pronto |
| Redução de ruído por IA, deconvolução, remoção do verde | 3 | pronto |
| Reduzir ou remover estrelas | 3 | pronto |
| Antes e depois | 2 | — (só no app) |
| Cortar e girar | 3 | novo |
| Exportar em resolução cheia | 2 | pronto |

## I. Equipamento

| Função | Fase | Jetson |
|---|---|---|
| Estado da montagem: conectada, posição, rastreando, estacionada | 1 | pronto |
| Mover à mão (direcional com velocidades) | 3 | novo; **hardware** |
| Estacionar, ir para casa, ligar e desligar o rastreio | 3 | novo; **hardware** |
| Assistente de alinhamento polar por plate solve | 4 | novo; **hardware** |
| Focalizador: posição, mover passos | 3 | parcial; **hardware** |
| Câmera: ganho, offset, binning | 3 | **hardware** |
| Biblioteca de calibração: darks, flats e bias guiados | 4 | parcial (calibração existe) |
| Saúde dos drivers dos motores | 3 | parcial |
| Aquecedor anti-orvalho | 4 | novo (a placa tem a saída) |

## J. Sistema

| Função | Fase | Jetson |
|---|---|---|
| Sobre: versões do app, da Jetson e do firmware da montagem | 1 | parcial |
| Desligar e reiniciar com segurança | 2 | novo |
| Rede: modo casa/campo, WiFi de casa, nome e senha do WiFi do telescópio | 3 | novo |
| Atualizar o firmware da montagem pelo app | 4 | pronto por script na Jetson |
| Atualizar o software da Jetson | 4 | novo |
| Diagnóstico e pacote de suporte (registros) | 4 | novo |

## K. Experiência

| Função | Fase |
|---|---|
| Tema escuro sempre; **modo noturno vermelho** para preservar a visão | 1 |
| Tela sempre ligada durante a observação, com brilho reduzido | 1 |
| Modo simples e modo Pro (curvas, histograma, gráficos) | 2 |
| Português e inglês | 1 (estrutura) / 4 (tradução completa) |
| Ajuda no contexto e glossário | 4 |
| Acessibilidade: contraste, texto grande, leitor de tela | 2 em diante |

## O que fica de fora

- **Conta de usuário, nuvem, rede social.** O telescópio funciona sem internet; nada depende
  de servidor nosso.
- **Processamento no celular.** A GPU está na Jetson.
- **Falar direto com a placa da montagem.** O WiFi dela é reserva de bancada, não caminho do app.

## Como ficou (2026-10-10)

As tabelas acima são o plano, com o que a Jetson sabia fazer na época. Esta é a situação do
**app com a API**, função por função. "Simulado" quer dizer que funciona de ponta a ponta contra
o simulador, e a tela diz isso; nada aqui foi testado num celular nem na Jetson.

| Área | Feito | Feito contra simulador ou adapter de mentira | Não feito |
|---|---|---|---|
| A. Conectar | parear por QR ou código; reconectar sozinho; achar o telescópio em outro endereço (anúncio na rede, WiFi próprio, apelido de casa); hora e local do celular; nome do aparelho; convidar outro celular com papel; modo demonstração | WiFi de casa pelo app; entrar no WiFi do telescópio (depende do Android e do modo campo da Jetson) | digitar endereço à mão; assistente encadeado de primeiro uso (são telas separadas); "a vez de comandar" entre dois operadores |
| B. Início | estado e progresso; saúde (montagem, câmera, processamento, temperatura, disco); alvo sugerido; continuar a última sessão; PARAR em todas as telas | — | condições do céu a partir da imagem |
| C. Atlas | catálogo e busca; filtros "hoje", tipo e "cabe no campo"; ficha com a altitude na noite, melhor horário e enquadramento; favoritos (no celular); coordenadas; Lua, planetas e Sol com efeméride própria | — | filtro por brilho; ranking além da altitude; histórico do que já foi fotografado; passagens de satélites |
| D. Observar | imagem ao vivo com zoom; estatísticas e histograma (modo Pro); exposição e ganho (ficam guardados) | apontar e centralizar; autofoco com a curva; empilhar (começar e parar); câmera ao vivo para enquadrar e focar | pausar; escolher filtro; ajuste de brilho da prévia; arrastar a imagem para mover a montagem; rótulos dos objetos; instantâneo no celular |
| E. Modos especiais | a grade do mosaico e o envio para o plano; Sol só com o filtro confirmado | captura planetária (pipeline real, quadros simulados); rastreio do que cruza o campo | — |
| F. Planejar | fila da noite com o horário de cada alvo e por que algum não cabe; reordenar; avisos com a tela apagada | noite autônoma: iniciar, acompanhar, pular, parar; linha do tempo | plano de várias noites; modelos de plano; miniaturas na linha do tempo |
| G. Galeria | sessões de referência com miniatura; imagem em tela cheia com zoom; exportar JPEG, TIFF e FITS; compartilhar pelo Android; apagar | — | sessões do próprio telescópio (dependem da câmera); FWHM e SNR ao longo da sessão |
| H. Estúdio | presets; brilho, cor e ruído; "mais ajustes" (deconvolução, verde, estrelas, pretos e brancos); antes e depois; exportar em resolução cheia | — | cortar e girar |
| I. Equipamento | estado da montagem real (só leitura) | mover à mão com prazo, estacionar, casa, rastreio; alinhamento polar; focalizador; ganho e offset | binning; calibração guiada (darks, flats); saúde dos drivers; aquecedor anti-orvalho; comandar a montagem real |
| J. Sistema | versões; temperatura e disco; tela de desligar e reiniciar | rede (casa e campo); atualizar o software do telescópio | atualizar o firmware da montagem pelo app; diagnóstico e pacote de suporte |
| K. Experiência | tema escuro e modo vermelho; modo simples e Pro; ajuda e glossário; rótulos para leitor de tela e alvos de toque grandes | — | inglês; tela sempre ligada durante a observação |
