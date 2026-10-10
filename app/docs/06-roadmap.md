# 06 — Roteiro

O app segue a filosofia do projeto: **tirar o risco primeiro, com o que já temos.** As fases 0 a
2 não dependem de câmera nem de mecânica — rodam contra os simuladores e contra a montagem que
já está conectada. Cada fase termina com algo que se abre no celular e se confere.

**O foco agora é a API.** Ela é o que tudo o mais consome; o app só existe depois que há com
quem falar. E ela nasce protegida: TLS e pareamento entram na fase 0, não no fim.

Há duas trilhas em paralelo: a **Jetson** (a API) e o **app** (Flutter).

## Fase 0 — Fundação: a API protegida e o esqueleto do app

| Trilha | Entrega |
|---|---|
| Ambiente | aceitar as licenças do Android SDK; caches do Gradle e do Pub no `E:`; um celular Android em modo depuração |
| Jetson | servidor da API v1 na porta 8443; identidade do aparelho (chave, certificado, segredo); pareamento por QR com janela; `/info` e `/state`; WebSocket cifrado; anúncio do serviço na rede |
| App | `flutter create` em `app/`; tema e modo vermelho; ícones exportados por script; porta `TelescopeApi` com o `FakeTelescope`; cliente com certificado fixado; CI (`analyze` + `test`) |
| Risco a matar | no Android: usar o WiFi do telescópio só dentro do app. Protótipo nativo curto, antes das telas |

**Pronto quando:** o app, num celular Android, lê o QR, pareia com a Jetson de verdade e mostra
o estado ao vivo por canal cifrado; um servidor com outro certificado é recusado; o CI fica verde.

## Fase 1 — Conectar e ver

| Trilha | Entrega |
|---|---|
| App | telas C1–C5, C7, C9, O1, A1, D1, D9 e os elementos X1–X6 (`08-telas.md`): achar o aparelho, reconectar, início com a imagem ao vivo, Atlas, estado da montagem, enviar hora e local |
| Jetson | `/site`; `/targets` com filtro e paginação; `/system`; imagem ao vivo pela API |

**Pronto quando:** abrir o app e, sem tocar em nada, ver "montagem conectada" e a imagem ao
vivo; a hora e o local enviados pelo celular são lidos de volta na placa da montagem.

## Fase 2 — Observar e rever

| Trilha | Entrega |
|---|---|
| App | telas O2–O8, A2–A4, G1–G3, G5, D7: goto com etapas, empilhar, parar, estatísticas, ficha do alvo, favoritos, galeria, estúdio básico, exportar, desligar |
| Jetson | `/observe/*` com parâmetros e trabalhos; `/sessions`; `/render` com presets; detalhe do alvo; mensagens do WebSocket por tipo |

**Pronto quando:** a "noite rápida" inteira acontece pelo celular (escolher, apontar, empilhar,
salvar), com a câmera ainda simulada e isso dito na tela.

**Este é o MVP:** fases 0 a 2.

## Fase 3 — Planejar e cuidar do aparelho

| Trilha | Entrega |
|---|---|
| App | telas P1–P5, G4, D2–D5: fila e noite autônoma, mosaico, Lua e planetas, montagem à mão, foco, câmera, rede |
| Jetson | `/plan`, `/mosaic`, `/mount/*`, `/focuser`; **modo campo** (WiFi próprio com troca automática); quadros JPEG pelo WebSocket, codificados por hardware |
| Depende de | mecânica montada, para validar movimento; **o modo campo só é ligado com você presente** |

**Pronto quando:** uma noite autônoma de vários alvos é planejada e acompanhada pelo celular;
e o telescópio funciona longe do roteador, com o celular no WiFi dele.

## Fase 4 — Acabamento

Telas C6, C8, D6, D8, D10: assistente de primeiro uso, WiFi de casa pelo app, celulares
pareados, atualizações, ajuda. Avisos com a tela apagada; alinhamento polar; satélites.

## Backlog (fora do roteiro por enquanto)

| Item | Por que espera |
|---|---|
| **Distribuição**: lojas, APK público, regra de verificação do Android | por enquanto só o dono usa; instalar pelo cabo basta |
| **iPhone** | exige Mac e conta paga; a base de código já serve |
| **Vários celulares**: papéis, a vez de comandar, convite por QR | um usuário só; o desenho já está em `07-seguranca.md` |
| **Inglês completo** | a estrutura de tradução entra na fase 0; o texto, depois |
| **Bluetooth** para a primeira configuração | o QR resolve |
| **Acesso pela internet** | não é objetivo; se um dia for, por VPN |

## Riscos

| Risco | Como tratar |
|---|---|
| Android manda o tráfego pelo 4G quando o WiFi do telescópio não tem internet | protótipo na fase 0, antes de construir telas em cima |
| Descoberta por mDNS falha em algum aparelho ou rede | várias alternativas em sequência (`03-conexao.md` §2) |
| API mudando enquanto o app é escrito | contrato primeiro; teste de contrato contra o falso e contra a Jetson |
| Segurança deixada para depois | não deixar: TLS e pareamento na fase 0, com os testes de `07-seguranca.md` §12 |
| Imagem ao vivo pesa na CPU da Jetson | codificador JPEG por hardware (já medido: cerca de 2× mais rápido) |
| Mexer na rede da Jetson à distância corta o acesso | só com o dono presente; troca automática testada na bancada antes |
| Escopo grande | fases com critério de pronto; o MVP são as três primeiras |
| `C:` com pouco espaço para builds Android | caches no `E:` na fase 0 |

## Decisões

| Decisão | Estado |
|---|---|
| Tecnologia: Flutter, Android primeiro | decidido |
| Rede: WiFi próprio da Jetson com troca automática; sem adaptador USB | decidido |
| Distribuição | backlog |
| Segurança desde a primeira versão da API | decidido (`07-seguranca.md`) |
| **Nome** do produto e do app | **aberto** — propostas em [`09-nome.md`](09-nome.md) |
| **Servidor da API**: FastAPI (livre) em vez do servidor mínimo atual | **proposto**, aguardando o seu ok |

Sobre o servidor: são dezenas de rotas, validação de entrada, token, TLS, WebSocket e arquivos
na mesma porta — nada disso é o diferencial do projeto, e a regra da casa é reusar o que não é
diferencial (`docs/08`). Um framework consolidado também gera a descrição da API sozinho, o que
mantém o contrato e o código do app em sincronia.

## Onde estamos (2026-10-09)

| Fase | Jetson | App |
|---|---|---|
| 0 | **feito no PC:** API v1 na 8443 com identidade, TLS 1.3, pareamento por QR com janela, `/info`, `/state`, WebSocket cifrado. **Falta:** instalar na Jetson (script pronto) | **feito:** projeto Flutter, tema e modo vermelho, ícones exportados, `TelescopeApi` com o falso, cliente com certificado fixado, testes. **Falta:** CI no GitHub; o risco do WiFi só no app (código nativo escrito, não validado) |
| 1 | **feito:** `/site`, `/targets` com filtro e paginação, `/system`, imagem ao vivo | **feito:** C1, C2, C3, C5, C7, C9, O1, A1, D1, D9, X1–X6. **Parcial:** C2 sem a lista de aparelhos na rede; C4 depende do modo campo |
| 2 | **feito:** `/observe/*` com trabalhos, `/sessions`, `/render` com presets, ficha do alvo, mensagens por tipo. **Falta:** `/observe/focus` | **feito:** O2, O4, O7, O8, A2, A3, A4, G1, G2, G3, D7. **Parcial:** O5 (os números e o histograma, no modo Pro). **Falta:** O3 (exposição e ganho dependem da câmera), O6 (foco), G5 (exportar) |
| 3–4 | — | — |

O critério de pronto da fase 0 ("o app, num celular Android, lê o QR, pareia com a Jetson de
verdade") ainda **não** foi cumprido: falta o celular e falta instalar na Jetson. O que está
provado é a metade de software: o cliente do app e o servidor da Jetson conversam por TLS com o
certificado fixado, e um servidor com outro certificado é recusado
(`py -3.11 scripts/run_app_integration.py`).

Decisão que estava aberta: **servidor da API em FastAPI** — adotado.

## Onde estamos (2026-10-10)

| Fase | Jetson | App |
|---|---|---|
| 0 a 2 | como acima, mais `/observe/focus` e `/observe/preview` | como acima, mais O3 (câmera ao vivo, enquadrar, exposição e ganho), O6 (foco) e G5 (exportar) |
| 3 | **feito no PC:** `/plan` com horários, noite autônoma com andamento por item, `/mosaic`, `/mount/*` e `/focuser` (simulados), `/camera`, `/solar`. **Falta:** modo campo; comandar a montagem real; quadros pelo WebSocket | **feito:** P1 a P5, G4, D2, D3, D4, D5 (D5 só mostra). **Falta:** o que depende do modo campo |
| 4 | **feito no PC:** convite de celular com papel, nome do aparelho | **feito:** C6, D6, D8 (só as versões), D10. **Falta:** C8 (WiFi de casa pelo app), atualizar pelo app, avisos com a tela apagada, alinhamento polar |

Das 41 telas, 39 existem. O que falta de verdade para o critério de pronto de cada fase é o
mesmo de antes, e não é código novo: **um celular** e **a Jetson**. O app nunca rodou num
aparelho, e a API nunca rodou na Jetson.

O que a fase 3 ensinou:

- **O PARAR tem de estar sempre à vista.** Na câmera ao vivo os ajustes são longos e o botão
  tinha ido parar abaixo da dobra; subiu para o topo dos controles.
- **Movimento manual precisa de prazo.** Sem ele, perder o sinal com o dedo no botão deixaria a
  montagem andando. O comando é renovado enquanto se segura.
- **Convite não pode entregar o segredo do aparelho.** O primeiro rascunho da rota devolvia o
  código do QR original; o que ficou sorteia um segredo só para aquele convite.

## Onde estamos (2026-10-10, depois de "o que faltava no app")

| Fase | Jetson | App |
|---|---|---|
| 0 a 2 | como acima | como acima, mais a lista de telescópios na rede (C2) e o WiFi do próprio telescópio (C4) |
| 3 | como acima, mais o **contrato** da rede (`/network/*`) com o adapter de mentira. **Falta:** o adapter de verdade (NetworkManager); comandar a montagem real; quadros pelo WebSocket | **feito:** D5 completa (trocar de modo, senha do WiFi próprio, esquecer a rede de casa) |
| 4 | **feito no PC:** captura planetária (pipeline real, quadros simulados), alinhamento polar por três pontos (geometria real, montagem simulada), o contrato da atualização com o adapter de mentira. **Falta:** o adapter de atualização de verdade | **feito:** C8, D8 com procurar e instalar, avisos com a tela apagada, alinhamento polar (D11), captura planetária (O9) |

As 43 telas existem (`08-telas.md`, "Como ficou"). O app não tem mais tela por fazer; o que
resta é de outra natureza:

1. **Provar em aparelho.** O app nunca rodou num celular, e a API nunca rodou na Jetson. Quatro
   peças dependem do comportamento do Android e só o celular confirma: o WiFi do telescópio
   dentro do app, a busca na rede, os avisos e o cofre.
2. **Trocar o que é de mentira pelo que é de verdade,** atrás das mesmas portas: a rede e a
   atualização na Jetson; a montagem, o focalizador e a câmera quando a mecânica chegar.
3. **Backlog:** inglês; a galeria com as capturas do próprio telescópio; "a vez de comandar".

O que esta leva ensinou:

- **Anúncio não é identidade.** Achar o telescópio sozinho só é seguro porque cada candidato
  passa pelo certificado antes de qualquer conversa; e um candidato falso não pode virar alarme,
  senão qualquer um na rede derruba o app com um anúncio.
- **Trocar de rede precisa de contrato, não só de rota.** "Responder antes de trocar" e "voltar
  se não der certo" são o que deixa o app esperar com calma em vez de adivinhar.
- **O que só o aparelho prova tem de estar dito.** As telas de rede e de atualização funcionam
  inteiras contra os adapters de mentira; na Jetson, hoje, elas mostram e explicam.
- **Simulador que converge não prova o lado.** O ciclo medir, girar, medir de novo fechava no
  simulador mesmo com o azimute invertido ao sul do equador, porque medida e parafuso usavam a
  mesma convenção errada. Quem achou foi uma leitura independente; o teste que ficou põe o eixo
  direto no céu do observador e confere o lado da bússola.
