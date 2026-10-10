# 03 — Como o app conecta na Jetson

O app é um controle remoto com tela. Todo o trabalho pesado fica na Jetson; o celular só precisa
achá-la, falar com ela e continuar falando quando a rede oscilar. Este documento cobre a rede,
a descoberta, o pareamento e o transporte.

```
 celular (app Flutter)  ~~ WiFi ~~  Jetson (cérebro)  == USB ==  placa da montagem (músculo)
        só fala com a Jetson         API + imagem              nunca fala com o celular
```

---

## 1. Os três cenários de rede

| Cenário | Quem cria o WiFi | Internet no celular | Quando |
|---|---|---|---|
| **Casa** | o roteador; Jetson e celular entram nele | sim | bancada, quintal |
| **Campo** | a Jetson (ponto de acesso próprio) | não | observação fora de casa |
| **Os dois ao mesmo tempo** | roteador **e** Jetson | sim | conveniência; não é requisito |

### 1.1 A Jetson consegue ficar no roteador e abrir um ponto de acesso em paralelo?

**Com a placa WiFi interna e o driver que veio na Jetson, não.** Medido na nossa Orin (2026-10-09):

| | |
|---|---|
| Placa | Realtek RTL8822CE (`10ec:c822`), driver `rtl88x2ce` (o da NVIDIA) |
| Modos que ela aceita | estação, ponto de acesso, IBSS, P2P |
| Combinações simultâneas | `iw list` → **"interface combinations are not supported"** |
| Ponto de acesso permitido em | 11 canais de 2,4 GHz e 4 canais de 5 GHz (o 149 entre eles) |
| Extras | `dnsmasq-base` instalado (o hotspot do NetworkManager funciona sem instalar nada); Bluetooth ativo |

Ela faz os dois papéis, mas **um de cada vez**. Para ter os dois juntos existem três caminhos:

| Caminho | Como | Custo | Avaliação |
|---|---|---|---|
| **A. Um rádio, troca automática** | no boot a Jetson procura a rede conhecida; se não achar em ~20 s, sobe o próprio WiFi | zero | **recomendado agora.** Cobre casa e campo sem ninguém escolher modo. Não cobre "os dois juntos" |
| **B. Cabo de rede + ponto de acesso** | Ethernet no roteador, WiFi interno como AP | um cabo | os dois juntos, mas só perto do roteador. Bom para desenvolvimento |
| **C. Segundo rádio USB** | adaptador WiFi USB: um rádio fica no roteador, o outro vira AP | um adaptador **e** compilar o driver dele | os dois juntos de verdade. Candidato para a versão de produto |

**O caminho C tem um custo escondido, também medido:** o kernel da nossa Jetson não traz o
driver de **nenhum** adaptador WiFi USB comum (`mt76x2u`, `mt76x0u`, `mt7921u`, `rt2800usb`,
`ath9k_htc`, `rtl8xxxu`, `rtw88`: todos ausentes). É a mesma situação do CH340 — o driver
teria de ser compilado para o kernel da Jetson —, só que com mais módulos e um arquivo de
firmware. Se formos por aí, os adaptadores de chip **MT7612U** são os mais indicados
(`00-referencias.md` §4).

Um quarto caminho fica para o futuro: o driver do próprio Linux para esta placa passou a
declarar "estação mais ponto de acesso, num canal só" a partir do kernel 6.4, e o JetPack 7
traz o 6.8. Não é certo que funcione na Jetson (ela usa o driver do fabricante), e trocar de
JetPack é uma mudança grande demais para justificar só por isso.

**Decidido (2026-10-09): caminho A.** O ponto de acesso é o da própria Jetson, com troca
automática; o adaptador USB está descartado. A API fica indiferente ao caminho — o app nunca
precisa saber qual deles está valendo.

**Cuidado de execução:** a rede da Jetson só é alterada com o dono presente e avisado. Trocar
o modo à distância derruba a conexão de quem está trabalhando nela, e não há como voltar sem
acesso físico.

### 1.2 O que muda no campo: WiFi sem internet

Quando o celular entra num WiFi sem internet, o Android avisa e tende a mandar o tráfego pelo
4G. É a queixa mais comum nos apps de telescópio do mercado: os manuais mandam desligar os
dados móveis e a VPN (`00-referencias.md` §2). Uma página no navegador sofre com isso; um app
nativo resolve: o Android tem uma API oficial para o app se ligar a um ponto de acesso local e
**usar aquela rede só dentro dele**, enquanto o resto do celular segue no 4G. É uma das razões
concretas para o app nativo existir — e um ponto em que dá para ser melhor que os concorrentes.

---

## 2. Achar o telescópio (descoberta)

O usuário não deve digitar IP. O app tenta, nesta ordem, e para no primeiro que responder em
`GET /api/v1/info`:

1. **Último endereço que funcionou** (guardado no celular).
2. **DNS-SD / mDNS**: a Jetson anuncia o serviço `_telescope._tcp` com nome, identificador e
   versão da API; o app lista os telescópios encontrados. Já existe o apelido
   `telescopio.local` (`docs/33`), e o anúncio do serviço é instalado por
   `scripts/jetson_setup_api.sh` (ver §8 para como ficou no app).
3. **`telescopio.local`** direto, se a busca por serviço falhar.
4. **Aviso por UDP**: o app pergunta "tem telescópio aí?" para a rede inteira e a Jetson
   responde. Cobre os casos em que o mDNS não funciona — o Android não resolve nomes `.local`
   com VPN ativa nem pelos dados móveis.
5. **Endereço fixo do modo campo**: `10.42.0.1`, o gateway do hotspot do NetworkManager.
6. **Manual**: digitar o IP, ou ler um **QR code** do aparelho.

O QR code serve a dois propósitos: no formato padrão de WiFi (`WIFI:S:…;T:WPA;P:…;;`) o Android
entra na rede do telescópio sem ninguém digitar senha; e o mesmo código carrega o identificador
e o código de pareamento (seção 3).

**Bluetooth LE** fica como evolução para a primeira configuração (mandar a senha do WiFi de
casa para a Jetson sem passar pelo modo campo). A Jetson tem Bluetooth ativo; exige um serviço
GATT na Jetson e permissões no app. Não é necessário para a primeira versão.

---

## 3. Pareamento e segurança

Qualquer aparelho na mesma rede poderia ler o tráfego, mover a montagem ou apagar imagens. Por
isso a proteção entra **desde a primeira versão da API**, não depois: colocar segurança por
cima de um protocolo já em uso é sempre mais caro e mais falho.

Em resumo: o celular lê um **QR code** do aparelho, confere a identidade dele, prova que tem o
código e recebe um token. Daí em diante toda conversa é **cifrada (TLS 1.3)**, com o
certificado da Jetson fixado no app e o token em cada chamada. Um app nativo resolve assim o
HTTPS em rede local, coisa que o navegador não consegue sem instalar certificado no celular.

O desenho completo — ameaças, pareamento passo a passo, tokens, papéis, recuperação e testes —
está em [`07-seguranca.md`](07-seguranca.md).

---

## 4. Transporte: três canais, uma porta

| Canal | Para quê | Hoje | No app |
|---|---|---|---|
| **HTTPS (REST)** | perguntas e comandos: catálogo, iniciar/parar, configurações, arquivos | existe em HTTP aberto, espalhado em três servidores (8000, 8010, 80/8080) | uma porta só, cifrada (8443), caminhos `/api/v1/…` |
| **WebSocket cifrado** | estado em tempo real e eventos empurrados pela Jetson; comandos rápidos | existe na 8081, aberto (`docs/33`) | mesmo canal, em `/api/v1/ws` na porta única |
| **Imagem ao vivo** | a prévia e o empilhamento | MJPEG em `/stream.mjpg` | MJPEG na primeira versão; depois quadros JPEG pelo WebSocket, para controlar ritmo e fila |

Vídeo comprimido (H.264/WebRTC) está fora: a Orin Nano não tem codificador de vídeo por
hardware. Ela tem codificador **JPEG** por hardware, e a prévia de um telescópio muda devagar —
JPEG empurrado resolve.

O contrato completo está em [`04-api.md`](04-api.md).

---

## 5. Hora e local vêm do celular

Hoje a cadeia é: a Jetson sabe a hora e o lugar e os envia à montagem a cada conexão
(`docs/35`). No campo falta o primeiro elo: sem internet não há NTP, e sem GPS a Jetson não
sabe onde está. **O celular sabe as duas coisas.** Ao conectar, o app envia hora UTC e
coordenadas do GPS em `POST /api/v1/site`; a Jetson acerta o próprio relógio se estiver sem
sincronismo e repassa à montagem.

```
celular (GPS + relógio) -> Jetson -> montagem
```

A Jetson tem um relógio de hardware (`rtc0`), sincronizado enquanto há internet. Se ele segura
a hora com a Jetson totalmente sem energia depende de bateria de backup — a confirmar na nossa
unidade. O envio pelo celular torna isso irrelevante.

---

## 6. Quando a conexão cai

Vai cair: o celular bloqueia a tela, o usuário se afasta, o WiFi oscila. Regras:

- **A Jetson não depende do app.** Uma sessão iniciada continua sozinha; fechar o app não para
  nada.
- **Reconexão automática** com espera crescente (1 s, 2 s, 4 s… até 15 s), sem bloquear a tela.
- **Ao reconectar, o app pede o retrato completo** do estado e só então volta a aplicar os
  eventos. Cada evento tem número de sequência: buraco na sequência = pedir o retrato de novo.
- **Comandos têm identificador.** Reenviar o mesmo comando depois de uma queda não o executa
  duas vezes.
- **O app diz a verdade:** "conectando", "reconectando há 12 s", "telescópio ocupado por outro
  celular" — nunca um estado antigo apresentado como atual.

---

## 7. O que a Jetson precisa ganhar para isto

| Item | Estado |
|---|---|
| Apelido `telescopio.local`, porta 80, WebSocket | feito (`docs/33`) |
| API v1 numa porta só, com `/info` e capacidades | feito no PC (`src/api`); **falta instalar na Jetson** |
| Anúncio DNS-SD do serviço e resposta ao aviso por UDP | anúncio: feito no script de instalação (avahi) e, no PC, por `--advertise`. Aviso por UDP: não feito |
| `POST /api/v1/site` (hora e local do celular) | feito |
| Identidade do aparelho, TLS e pareamento por QR | feito (`07-seguranca.md` §13) |
| Modo campo: WiFi próprio com troca automática | decidido; só é ligado com o dono presente. O contrato da troca pelo app existe, com adapter de mentira (`04-api.md` §10) |
| Um controlador por vez, papéis | papéis e convite: feitos. "A vez de comandar" entre dois operadores: não feito |
| Quadros JPEG pelo WebSocket, codificados por hardware | não feito: a imagem ao vivo vai em MJPEG |

(Estado em 2026-10-10.)

---

## 8. Como ficou a descoberta e o modo campo no app (2026-10-10)

A ordem do §2 virou uma procura **em paralelo**. O app fala primeiro com o último endereço que
funcionou; se ele não responder em 1,5 s (ou falhar antes), procura ao mesmo tempo em:

| Onde | De onde vem |
|---|---|
| os endereços que a rede anunciou para o telescópio pareado | DNS-SD, serviço `_telescope._tcp` (item 2 do §2) |
| o WiFi que o próprio telescópio cria | o endereço que ele contou ao dono em `GET /network`, ou `10.42.0.1` (item 5) |
| `telescopio.local` | o apelido de casa (item 3) |

Vale o primeiro que responder **com o certificado pareado**; o endereço novo fica guardado.
Dos anunciados entram no máximo quatro, só IPv4 de rede local.
Enquanto o telescópio não responde, o app escuta os anúncios e tenta na hora em que ele aparece,
sem esperar o próximo ciclo. O aviso por UDP (item 4) não foi feito; o endereço manual é o QR.

**Modo campo.** O app conhece o WiFi do telescópio por dois caminhos: o QR (se o pareamento foi
no campo) ou o próprio telescópio, que conta nome, senha e endereço ao dono enquanto está em
casa. Longe de casa, a tela "Achar o telescópio" oferece "Entrar no WiFi do telescópio": o app
pede a rede ao Android (só para ele), e a procura acima o encontra lá.

**Trocar de rede pelo app** segue o contrato de `04-api.md` §10: o telescópio responde antes de
trocar; o app espera o prazo que ele deu, pergunta de segundo em segundo se a troca acabou, e, se
ele foi para o WiFi próprio, entra nesse WiFi para reencontrá-lo.

**O que isto ainda não prova.** Tudo acima roda nos testes contra o telescópio falso e contra o
servidor do PC. No celular faltam conferir: se o Android entrega os anúncios com o app preso ao
WiFi do telescópio; se, perdido esse WiFi, o app volta sozinho à rede de casa; e se o pedido de
WiFi é refeito sem novo aviso depois de uma troca que falhou. Na Jetson falta o adapter de rede
de verdade — o passo que só se faz com o dono ao lado (§1.1).

**A conferir quando o alvo do Android subir:** as versões mais novas do Android estão passando a
exigir uma permissão própria para o app falar com a rede local (a "proteção de rede local"). Com
o alvo de hoje o app não é afetado; antes de subir o alvo, vale conferir na documentação do
Android se a permissão já é obrigatória e pedi-la — este app só fala com a rede local.
