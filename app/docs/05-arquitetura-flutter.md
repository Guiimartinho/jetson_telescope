# 05 — Arquitetura do app (Flutter)

Flutter e Dart, uma base de código, **Android primeiro**; iPhone depois, pela mesma base.
Segue as regras do projeto (`docs/11`): Ports & Adapters na fronteira, testes desde o início,
só dependência livre ou grátis.

## 1. Ambiente nesta máquina (conferido em 2026-10-09)

| Item | Estado |
|---|---|
| Flutter | 3.41.9 estável, Dart 3.11.5, em `E:\Softwares\flutter` (já no PATH) |
| Android SDK | em `E:\Softwares`, plataforma `android-37`, build-tools 35.0.0 |
| Java | Temurin 17 (`JAVA_HOME` definido) |
| Android Studio | instalado em `D:\Android` |
| Alvos prontos | Windows (desktop), Chrome e Edge (web) |

Pendências antes de compilar para Android:

1. **Aceitar as licenças do SDK:** `flutter doctor --android-licenses` (é uma aceitação de
   termos; precisa ser feita pelo dono da máquina).
2. **Um aparelho:** celular Android com depuração USB, ou um emulador (o `flutter doctor` não
   achou nenhum dos dois).
3. **Espaço em disco:** o `C:` tem 12 GB livres, e os caches do Gradle e do Pub vão para lá
   por padrão. Apontar `GRADLE_USER_HOME` e `PUB_CACHE` para `E:` antes do primeiro build.

Até lá, o app roda como **janela do Windows** contra o software da Jetson em modo simulador —
é assim que a maior parte do desenvolvimento acontece.

## 2. Camadas

```
 telas (widgets)          o que o usuário vê; sem regra de negócio
      |
 estado (controladores)   um por área: conexão, observar, atlas, plano, galeria, aparelho
      |
 domínio                  tipos e regras puras: Alvo, Sessão, EstadoDoTelescópio, Plano
      |
 porta: TelescopeApi      a interface que o app enxerga
      |
 adapters                 HttpTelescope (REST + WebSocket)  |  FakeTelescope (demo e testes)
```

A porta `TelescopeApi` é o equivalente, no app, das portas `Mount`/`Focuser` da Jetson: as
telas não sabem se do outro lado há um telescópio, o simulador ou o falso. O **modo
demonstração** e os testes de tela usam o mesmo `FakeTelescope`.

## 3. Organização do projeto

```
app/
├── docs/                     este plano
├── lib/
│   ├── main.dart
│   ├── core/                 tema, tradução, erros, utilitários
│   ├── domain/               modelos e regras puras
│   ├── data/                 TelescopeApi + adapters, descoberta, armazenamento local
│   └── features/
│       ├── connect/          descoberta, pareamento, primeiro uso
│       ├── observe/          prévia, goto, empilhamento, modo Pro
│       ├── atlas/            catálogo, ficha do alvo
│       ├── plan/             fila da noite, linha do tempo
│       ├── gallery/          sessões, estúdio, exportar
│       └── device/           montagem, foco, rede, sistema
├── assets/icons/             SVGs exportados do ui_kit (gerados, não editados à mão)
├── test/                     unidade, telas (golden), contrato
└── integration_test/         o app inteiro contra o simulador
```

## 4. Escolhas técnicas

Todas livres. A coluna "por quê" é o critério; trocar uma delas não muda o plano.

| Necessidade | Escolha | Por quê |
|---|---|---|
| Estado | Riverpod | testável sem tela, sem código gerado obrigatório, comum no ecossistema |
| Navegação | go_router | mantido pelo time do Flutter; rotas declaradas |
| HTTP | dio | tempo limite, repetição e interceptação (token) prontos |
| WebSocket | web_socket_channel | pacote oficial do Dart |
| Achar o telescópio | um plugin de mDNS/DNS-SD | usa o serviço nativo do Android (NSD) e do iOS (Bonjour) |
| Guardar dados | preferências + SQLite | último aparelho, favoritos, cache do catálogo |
| Segredo (token) | armazenamento seguro do sistema | cofre do Android, chaveiro do iOS |
| Ícones | flutter_svg | os nossos SVGs, sem fonte de ícones |
| Gráficos | fl_chart | curva de altitude, histograma, SNR no tempo |
| Local | geolocator | latitude e longitude para a Jetson |
| QR | mobile_scanner | pareamento e entrada no WiFi do aparelho |
| Tradução | flutter_localizations + ARB | português e inglês desde a estrutura |
| Modelos | freezed + json_serializable | imutáveis, com (de)serialização gerada |

Peças que o Flutter não cobre e pedem configuração ou código nativo Android:

- **usar o WiFi do telescópio só dentro do app** quando ele não tem internet (`03-conexao.md`
  §1.2), pela API de conexão a ponto de acesso local do Android 10 em diante;
- **liberar HTTP para a rede local:** o Android 9 em diante bloqueia HTTP sem cifra por padrão;
  a exceção é declarada na configuração de segurança de rede do app;
- **serviço em primeiro plano** com notificação, para acompanhar uma noite longa com a tela
  apagada (fase 4).

## 5. Imagem ao vivo

Primeira versão: ler o MJPEG e pintar cada quadro num widget que troca a imagem sem piscar
(mantém o quadro anterior até o novo estar decodificado). Segunda versão: quadros JPEG pelo
WebSocket, com o app dizendo o ritmo que aguenta. Zoom e arraste são do app, sobre o último
quadro; a Jetson não é consultada a cada gesto.

## 6. Testes

| Tipo | O que cobre | Roda onde |
|---|---|---|
| Unidade | domínio, análise de mensagens, regras de reconexão | CI, sem aparelho |
| Tela (golden) | cada tela nos estados principais, tema normal e vermelho | CI |
| Contrato | `HttpTelescope` e `FakeTelescope` contra o mesmo roteiro | CI |
| Integração | o app inteiro contra o software da Jetson em simulador | PC de desenvolvimento |
| Aparelho | celular de verdade contra a Jetson de verdade | manual, por fase |

Bug vira teste que falha antes da correção, como no resto do projeto.

## 7. Entrega

- **CI no GitHub Actions** (grátis): `flutter analyze`, `flutter test`, e o APK como artefato.
- **Distribuição sem custo:** APK nas *releases* do GitHub; F-Droid é uma opção por o projeto
  ser livre. **A conferir antes de entregar a outras pessoas:** a verificação de
  desenvolvedores do Android começa pelo Brasil, e as fontes divergem sobre quando a
  instalação direta de APK passa a exigi-la. Existe uma conta gratuita de distribuição
  limitada (até 20 aparelhos). Instalar pelo cabo, no desenvolvimento, não é afetado
  (`00-referencias.md` §3).
- **Lojas** (quando for publicar): a Google Play cobra uma taxa única de registro; a App Store
  exige a assinatura anual do programa de desenvolvedores da Apple e um Mac para compilar. São
  taxas de publicação, não software pago — mas são custo, e ficam como decisão explícita.

## 8. iPhone, depois

O código Dart é o mesmo. O que muda: permissão de rede local e declaração dos serviços Bonjour
no `Info.plist`, exceção para HTTP em rede local, e a compilação num Mac. Nada no plano impede;
só não é a prioridade.

## 9. O que mudou ao construir (2026-10-09)

A tabela do §4 era o plano. Construindo, quatro escolhas ficaram mais simples — menos
dependência, e a parte de segurança num lugar só:

| Plano | Ficou | Por quê |
|---|---|---|
| dio + web_socket_channel | `HttpClient` e `WebSocket` do próprio Dart (`dart:io`) | o certificado fixado mora no `HttpClient`; com um cliente só, HTTP, WebSocket e a imagem ao vivo passam todos pelo mesmo teste de identidade |
| freezed + json_serializable | modelos escritos à mão (`lib/domain/models.dart`) | são poucos e simples; sem etapa de geração de código para rodar |
| fl_chart | desenho próprio (`CustomPainter`) | um gráfico de linha e um de barras, no visual do produto |
| ARB + tradução gerada | vocabulário comum em `lib/core/strings.dart`; textos de tela ainda no código | a estrutura completa de tradução entra junto com o inglês (backlog) |

Como tudo é HTTPS, a exceção para HTTP sem cifra citada no §4 **não foi necessária**: o
manifesto declara `usesCleartextTraffic="false"`.

**Ambiente (atualiza o §1).** `flutter build apk --debug` funcionou nesta máquina sem aceitar
licença nova: os componentes do SDK que o build pede já estavam instalados. O cache do Gradle
foi para `E:\Softwares\.gradle` (cerca de 4 GB) definindo `GRADLE_USER_HOME` só na linha de
comando; não há variável permanente, então quem compilar por outra janela ou pelo Android Studio
usa o padrão, no `C:`. O cache do Pub ficou no padrão (`C:`, pequeno). Continua faltando um
celular em modo depuração.

Outras pendências assumidas: as **fontes** são as do sistema (algarismos de largura fixa nos
números); embutir as duas fontes livres do `02-ui-ux.md` fica para o acabamento. A **descoberta
na rede** (mDNS/DNS-SD) não estava no app nesta data; entrou no dia seguinte (§10).

**Abertura escura.** O projeto Android padrão abre com uma tela branca quando o celular está no
tema claro. Aqui a abertura é o fundo do produto nos dois temas (`android/.../res/values*/styles.xml`).

**Testes de tela.** `test/harness.dart` monta o app inteiro com o telescópio falso e grava
capturas (`SCREENSHOTS=1`). Dois cuidados que os testes ensinaram e ficaram no código: cada
controle tem o seu nó de acessibilidade com a ação de tocar (antes o botão se fundia ao texto
vizinho), e as páginas ficam num contêiner de semântica próprio (sem ele, a faixa de estado
sumia do leitor de tela).

## 10. O que entrou por último (2026-10-10)

| Necessidade | Escolha | Observação |
|---|---|---|
| Achar o telescópio na rede | `nsd` 5.0.1 (MIT) | usa o serviço nativo do Android (NSD). Atrás da porta `Discovery` (`lib/data/discovery.dart`); pede a permissão `CHANGE_WIFI_MULTICAST_STATE` |
| Avisos e serviço em primeiro plano | `flutter_local_notifications` 22.3.1 (BSD) | um pacote só para as duas coisas. Atrás da porta `Alerts` (`lib/data/alerts.dart`). Exige a "dessugarização" das bibliotecas do Java no Gradle e o serviço declarado no manifesto, com o tipo "aparelho conectado" |

- **A regra do que avisar é código puro** (`lib/app/notices.dart`: `noticeFor`, `ongoingText`),
  testada sem Android. O adapter só mostra.
- **O ícone dos avisos** é o símbolo do produto, gerado pelo `scripts/export_app_icons.py` como
  vetor do Android (`res/drawable/ic_stat_telescope.xml`). O `res/raw/keep.xml` impede o
  empacotamento de entrega de descartá-lo: ele é pedido pelo nome, não por código.
- **A procura do telescópio** mora no `LinkController` (`lib/app/link.dart`): o endereço de
  sempre tem 1,5 s de vantagem, e depois os outros são tentados em paralelo. Cada tentativa é um
  cliente com o certificado fixado; os que perdem são fechados. As gravações do pareamento
  passam por uma fila só (`_store`).
- **Prazos correm pelo relógio.** A troca de rede usa temporizadores para o prazo, e cada
  pergunta ao telescópio tem o seu limite: contar voltas de um laço esticaria a espera quando
  ele some e cada pergunta demora.
- **Trocar de rede** é um caso de uso próprio (`lib/app/network_switch.dart`), usado pela tela
  de rede e pela do WiFi de casa: pedir, esperar o telescópio reaparecer, dizer como terminou.
- **Manha dos testes de tela:** a queda do canal em tempo real só chega ao app depois de uma
  volta do relógio de verdade (cancelar a escuta termina fora do tempo simulado). Os testes usam
  `Harness.loseSignal`, que já espera por isso.
- **Listas longas:** o que sai da tela deixa de existir para o teste. Cartão mais alto em Lua e
  planetas e a entrada do alinhamento polar na montagem pediram rolar antes de conferir.
