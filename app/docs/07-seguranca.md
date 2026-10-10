# 07 — Segurança e comunicação cifrada

Como o celular e a Jetson conversam sem que ninguém na rede leia, altere ou comande. A regra
número um: **não inventar criptografia.** Tudo aqui é padrão, com biblioteca madura dos dois
lados (Python na Jetson, Dart no app).

## 1. O que protegemos, e de quem

| Ameaça | Exemplo | Tratada? |
|---|---|---|
| Alguém na mesma rede lê o tráfego | visita no WiFi de casa, aparelho inseguro na rede | sim: tudo cifrado (TLS) |
| Alguém na rede comanda o telescópio | move a montagem, apaga imagens | sim: só celular pareado, com token |
| Alguém se passa pela Jetson | um impostor responde como "telescopio.local" | sim: o app só aceita o certificado que viu no pareamento |
| Alguém perto, no campo, entra no WiFi do telescópio | vizinho de acampamento | sim: senha do WiFi + as três camadas acima |
| Celular perdido | o token estava nele | sim: revogar o celular; o token fica no cofre do Android |
| Derrubar o WiFi por rádio | interferência proposital | não: nada resolve; a Jetson segue a sessão sozinha |
| Quem tem a Jetson nas mãos | abre e lê o cartão | não: é o dono |

Não há conta, nuvem nem servidor nosso. Nada sai da rede local.

## 2. As camadas

```
 4. Autorização     papel do celular (dono, operador, espectador) + "a vez" de comandar
 3. Autenticação    token do celular em cada chamada
 2. Canal           TLS 1.3 com o certificado do aparelho FIXADO no app
 1. Rede            WiFi com senha (roteador em casa; WPA2/WPA3 no WiFi do telescópio)
```

Cada camada vale sozinha. Se a senha do WiFi vazar, as outras três seguram.

## 3. A identidade do aparelho

Na primeira vez que liga, a Jetson cria e guarda (pasta com acesso só do serviço, arquivos
`0600`, nunca versionados, nunca enviados):

| Item | O que é | Para quê |
|---|---|---|
| Chave privada | ECDSA P-256 | prova que ela é ela |
| Certificado | autoassinado, validade longa | apresenta a chave pública no TLS |
| Impressão digital | SHA-256 do certificado | é o que o app fixa |
| Identificador | curto, derivado da impressão digital | nome do aparelho na rede e no QR |
| Segredo de pareamento | 128 bits aleatórios | só quem o tem pode parear |
| Senha do WiFi próprio | aleatória, por aparelho | modo campo |

Não há autoridade certificadora. A confiança nasce no pareamento, por um canal que não é a
rede: o **QR code**.

## 4. Pareamento (uma vez por celular)

O QR carrega tudo que o app precisa para confiar no aparelho antes de falar com ele:

```
tele://pair?v=1&id=tele-0b04&fp=<impressão digital>&s=<segredo>&ssid=<WiFi>&psk=<senha>
```

```
 celular                                             Jetson
    |  lê o QR (impressão digital, segredo, WiFi)       |
    |  entra no WiFi do telescópio, se for o caso        |
    |---------------- abre TLS 1.3 -------------------->|
    |<--------------- certificado ----------------------|
    |  confere: impressão digital == a do QR?            |
    |  (se não bater, para aqui: é um impostor)          |
    |---------------- POST /pair/start ---------------->|
    |<--------------- número aleatório -----------------|
    |---------------- POST /pair/finish --------------->|
    |   prova = HMAC(segredo, número + impressão + nome) |
    |                                                    |  confere a prova
    |<--------------- token do celular -----------------|  guarda só o resumo do token
    |  guarda o token e a impressão no cofre do Android  |
```

Detalhes que importam:

- **O segredo nunca trafega.** O celular prova que o conhece com um HMAC sobre um número que
  a Jetson acabou de sortear; capturar a prova não serve para nada depois.
- **A Jetson só aceita parear com a janela aberta.** Fechada por padrão. Quem abre é o dono:
  hoje por um comando na Jetson; no produto, por um botão físico. Cinco tentativas erradas
  fecham a janela, com espera crescente.
- **Onde aparece o QR.** No produto, numa etiqueta do aparelho. Enquanto é só você: o comando
  de pareamento desenha o QR no terminal (por SSH). **Nunca numa página HTTP da rede** — seria
  entregar o segredo a quem estivesse ouvindo.
- **Segundo celular.** Um celular já pareado, com papel de dono, gera um QR novo, de uso único,
  na própria tela. O outro lê e está pareado, sem etiqueta e sem SSH.
- **Sem câmera.** O mesmo conteúdo pode ser digitado como um código longo. É o plano B.

## 5. Depois de pareado: toda conexão

1. O app abre TLS 1.3 com a Jetson (`https://` e `wss://`, porta 8443).
2. Confere a impressão digital do certificado contra a guardada. Diferente: recusa e avisa.
3. Manda o token no cabeçalho `Authorization: Bearer …`, inclusive ao abrir o WebSocket.
4. A Jetson procura o resumo do token, identifica o celular e o papel, e registra o uso.

Nada de cookie, nada de sessão no servidor além do WebSocket aberto.

### Por que não depende do relógio

No campo a Jetson pode ligar achando que é o ano 2000. Um TLS comum quebraria: certificado
"ainda não válido". Aqui a confiança é a **chave fixada**, não as datas do certificado, então
o app conecta com qualquer relógio — e é por essa conexão que ele acerta a hora da Jetson
(`03-conexao.md` §5).

## 6. Tokens, papéis e a vez de comandar

| | |
|---|---|
| Token | 256 bits aleatórios, opaco. Um por celular |
| Na Jetson | fica só o resumo (SHA-256), com nome do celular, papel, data de criação e último uso |
| No celular | no armazenamento seguro do sistema (cofre do Android) |
| Validade | sem prazo; morre quando revogado |
| Revogar | pela tela "Celulares pareados" de um dono, ou por comando na Jetson |

Papéis: **dono** (tudo, inclusive parear, rede, atualizar, desligar), **operador** (observar,
planejar, galeria), **espectador** (só ver). Hoje só existe o dono; os outros já ficam no
desenho para o produto.

**A vez:** só um celular comanda por vez. Quem pede primeiro recebe a vez por um prazo curto,
renovado enquanto o app está em uso. Os demais veem tudo e podem pedir a vez; o dono pode
tomá-la.

## 7. Outras proteções da API

- **Entrada conferida** em toda rota: tipo, faixa e tamanho. Fora disso, erro com código.
- **Comando com identificador:** repetir depois de uma queda não executa duas vezes.
- **Limite de tentativas** no pareamento e nas falhas de autenticação.
- **Registro de auditoria:** quem comandou o quê e quando, guardado na Jetson.
- **Confirmação no app** antes do que move ou apaga: é proteção contra o dedo, não contra
  ataque, mas fecha a lista.

## 8. O WiFi do telescópio (modo campo)

Nome com o identificador do aparelho, senha aleatória de fábrica (vai no QR, para o Android
entrar sem digitar) e cifra WPA2, com WPA3 onde o celular suportar — a placa da Jetson anuncia
suporte. O app usa esse WiFi **só dentro dele**: o resto do celular continua no 4G
(`03-conexao.md` §1.2).

A Jetson passa a ser ponto de acesso só quando esse trabalho for feito **e combinado**: mexer
na rede dela à distância corta o acesso de quem está conectado.

## 9. E as páginas de hoje?

O console, o painel e o estúdio respondem por HTTP, sem senha, para quem estiver na rede. Isso
serve à bancada. Quando a API protegida entrar, **os comandos por HTTP aberto são desligados**
(as páginas viram só leitura ou passam a exigir o mesmo token). Deixar a porta dos fundos
aberta anularia a da frente.

## 10. Recuperação

| Situação | Saída |
|---|---|
| Perdi o celular | outro celular dono revoga; ou um comando na Jetson |
| Perdi todos os celulares | reinício de fábrica (comando hoje, botão no produto): apaga os tokens e sorteia novo segredo de pareamento |
| Troquei a Jetson ou regravei o cartão | identidade nova; todos os celulares pareiam de novo, e o app avisa que a impressão digital mudou |

## 11. Escolhas técnicas

| Peça | Escolha | Onde |
|---|---|---|
| Canal | TLS 1.3 | `ssl` do Python (servidor web); `SecurityContext` do Dart |
| Fixação do certificado | comparar o SHA-256 do certificado recebido | `badCertificateCallback` no cliente HTTP e no WebSocket do Dart |
| Chave do aparelho | ECDSA P-256 | gerada com a biblioteca `cryptography` (livre) |
| Prova do pareamento | HMAC-SHA-256 | biblioteca padrão dos dois lados |
| Aleatórios | gerador seguro do sistema | `secrets` (Python), `Random.secure` (Dart) |
| Token no celular | armazenamento seguro | cofre do Android / chaveiro do iOS |
| Comparações de segredo | em tempo constante | `hmac.compare_digest` |

Fica de fora, de propósito: protocolo próprio de cifra, senha curta sem troca de chave
adequada, e qualquer coisa que dependa de internet.

## 12. Testes

Rodam sem aparelho, contra o telescópio falso com TLS ligado:

- parear com segredo errado falha, e a quinta tentativa fecha a janela;
- parear com a janela fechada falha;
- servidor com **outro** certificado: o app recusa (é o teste do impostor);
- token revogado recebe "não autorizado" na chamada seguinte e derruba o WebSocket;
- relógio da Jetson no ano 2000: a conexão funciona;
- espectador não consegue comandar; dois celulares disputando a vez se comportam como descrito;
- nenhum segredo aparece em registro, em mensagem de erro ou em arquivo versionado.

## 13. Como ficou na implementação (2026-10-09)

- **Identidade:** `src/api/identity.py`. Fica em `~/.config/telescope/identity` (ou
  `TELE_IDENTITY_DIR`), arquivos `0600`, gravados de uma vez (escreve ao lado e troca). O
  certificado vale de 2000 a 2099: a confiança é a chave fixada, não as datas.
- **O comando do dono:** `python3 -m src.api.cli pair | clients | revoke <id> | reset --yes | info`.
  Roda em outro processo que o serviço; os dois conversam pela pasta da identidade (quem
  consegue escrever ali já é o dono). `pair` abre a janela por 5 minutos e desenha o QR no
  terminal; `reset` tira todos os celulares e sorteia outro segredo.
- **Uma janela, um celular:** a janela se fecha sozinha quando um celular pareia. Cinco provas
  erradas fecham a janela e fazem esperar 30 s, dobrando a cada vez.
- **No app:** o cliente nasce **sem raízes confiáveis** e só com TLS 1.3. Assim todo certificado
  cai no nosso teste (a impressão digital do QR), e nem um certificado válido de verdade,
  emitido para outro, passa. O token vai para o cofre do sistema.
- **Corpo de requisição limitado a 64 KiB** antes de qualquer outra coisa: as rotas de
  pareamento não pedem token, e sem limite qualquer um na rede encheria a memória da Jetson.
- **Auditoria:** `audit.jsonl` na pasta da identidade; `GET /logs` mostra os últimos eventos.
- **Console web só leitura:** com `--api` (ou `TELE_API=1`) os comandos por HTTP aberto e pelo
  WebSocket do console são recusados, e a página avisa. `--open-commands` os mantém, para a
  bancada.
- **Ficou para depois, de propósito:** os papéis além do dono e "a vez de comandar" (um usuário
  só, por enquanto); o convite por QR para um segundo celular; e o limite de tentativas nas
  falhas de token — com 256 bits aleatórios não há o que adivinhar, e um limite ali só serviria
  para alguém bloquear o dono.
- **Testes:** `tests/test_api_security.py`, `test_api_routes.py`, `test_api_tls.py` (TLS de
  verdade, impostor, TLS 1.2 recusado), `test_api_cli.py`; no app, `test/app_test.dart`
  (impostor, revogado, janela fechada) e `test/integration` contra o servidor de verdade.

## 14. O que entrou com as fases 3 e 4 (2026-10-10)

- **Convite para outro celular (`POST /clients/invite`, só dono).** O convite sorteia um segredo
  **novo, de uso único**, que vale por poucos minutos e dá o papel que o dono escolheu. É esse
  segredo que vai no QR mostrado na tela do dono. Consequências que os testes travam:
  - o segredo **do aparelho** (o da etiqueta) nunca viaja pela API, nem aparece no convite;
  - com só um convite valendo, quem tem o segredo do aparelho **não** entra (e não vira dono):
    cada segredo dá o seu papel, um não vale no lugar do outro;
  - um convite, um celular; um convite novo cancela o anterior; ele vence sozinho;
  - o registro de auditoria guarda quem convidou e com que papel, nunca o código.
- **Papéis em uso:** dono, operador (observa e comanda), visitante (só acompanha). Toda rota que
  move ou muda algo exige operador; administrar celulares, nome, energia e apagar exige dono.
  Mudar o papel recusa tirar o **último dono** (`409 last_owner`): sem dono, ninguém mais
  administra o aparelho pelo app.
- **Movimento manual com prazo (homem-morto).** `POST /mount/slew` leva `hold_ms` (até 2 s). O
  app renova o comando enquanto o dedo está no botão; se as renovações param — soltou, o app
  fechou, o sinal caiu —, a montagem para sozinha. `PARAR` também encerra o movimento manual.
  A montagem **real** ainda não é comandada pela API (`501 not_supported`).
- **Sol.** `POST /observe/body` com `sun` só é aceito com `filter_confirmed`, e a confirmação
  fica na auditoria. Vale revisar quando o apontamento for real: a confirmação é de quem usa,
  não uma verificação do aparelho.
- **Rede.** Trocar de rede à distância corta o acesso se der errado, e só é ligado depois de
  testado na bancada (ver §15: o contrato já existe, o adapter de verdade não).
- **Ficou para depois:** "a vez de comandar" entre dois celulares (hoje dois operadores podem
  comandar ao mesmo tempo; o comando mais novo interrompe o anterior).

## 15. Rede, descoberta, atualização e avisos (2026-10-10)

- **Endereço e anúncio não são identidade.** O app passou a procurar o telescópio pareado em
  vários lugares: o último endereço, os que a rede anunciou (DNS-SD), o do WiFi que ele mesmo
  cria e o apelido de casa. Qualquer um na rede pode anunciar o identificador de qualquer
  telescópio, e qualquer aparelho pode estar num endereço conhecido. Por isso:
  - cada candidato é conferido pelo **certificado fixado**, antes de qualquer conversa. Quem não
    passa não recebe nada — nem o token, que só viaja depois do aperto de mão;
  - um candidato com outro certificado é **ignorado em silêncio**. O alarme de "identidade
    trocada" continua valendo só para o endereço em que o telescópio de verdade já respondeu;
  - a tela diz "anunciado em tal endereço: conferindo a identidade", e não "achado";
  - anunciar é de graça, então há teto: no máximo quatro endereços anunciados são tentados por
    vez, só IPv4 de rede local, e um anúncio novo dispara uma tentativa por segundo, não uma
    por anúncio. Sem isso, qualquer um na rede faria o app abrir conexões sem parar.
  Testes: `app/test/screens4_test.dart` (o impostor que anuncia o identificador do pareado; os
  anúncios em excesso).
- **O que fica guardado no celular é gravado em fila.** Guardar o endereço novo ou o WiFi do
  telescópio pode estar no meio do caminho quando alguém manda esquecer: em fila, o "esquecer"
  é sempre o último, e nada do aparelho esquecido volta a ser escrito. Uma falha do cofre do
  sistema não derruba a ligação; só não fica guardado.
- **O WiFi do próprio telescópio.** `GET /network` entrega a senha dele **só ao dono**. O app a
  guarda no cofre do sistema, junto do token, para reencontrar o telescópio no campo; some com
  "Esquecer este telescópio". Operador e visitante veem o nome da rede, não a senha. Na tela a
  senha fica escondida até pedirem.
- **Trocar de rede** é só do dono, pergunta antes (derruba a conexão) e deixa rastro na
  auditoria: quem, para qual rede. **A senha nunca vai para a auditoria.** A senha do WiFi de
  casa vai para o telescópio pelo canal cifrado e fica guardada nele, não no celular.
- **Atualizar** é só do dono e não começa com trabalho rodando. O contrato exige que uma
  instalação que falha deixe a versão anterior valendo. **Fica para o adapter de verdade:**
  conferir a assinatura do que é instalado — hoje não há o que conferir, porque nada é baixado.
- **Avisos com a tela apagada.** Desligados de fábrica; ligar pede a permissão de avisos do
  Android. O texto aparece na tela bloqueada, então leva só o que já é público para quem vê o
  telescópio: o alvo, a contagem de fotos, "terminou" ou "falhou". Nenhum endereço, nome de rede
  ou segredo. O serviço em primeiro plano existe só enquanto há trabalho, sai com o app, não é
  recriado sozinho se o Android matar o processo, e desiste depois de 10 minutos sem sinal (o
  telescópio pode ter ficado sem bateria: o celular não fica acordado a noite toda por isso).
- **Não validado em aparelho:** a busca na rede, o WiFi só dentro do app, o cofre com a senha
  do WiFi, os avisos. O que os testes cobrem é a lógica; o comportamento do Android, não.
