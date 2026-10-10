# App do telescópio

O controle do telescópio no celular: um app Flutter que pareia com o telescópio por QR code,
mostra o céu que ele está vendo e comanda a observação — falando só com a Jetson, por canal
cifrado, sem internet e sem nuvem.

## Estado (2026-10-10, versão 0.3.0)

| Parte | Estado |
|---|---|
| **API da Jetson** (`src/api`) | no ar para as fases 0 a 4: TLS 1.3, pareamento por QR, token, estado ao vivo, alvos, observar, câmera ao vivo, foco e montagem à mão, plano da noite, mosaico, Lua e planetas (apontar e captura planetária), alinhamento polar, galeria, estúdio, exportar, convite de celular; e o contrato da rede e da atualização, com adapters de mentira. Testada no PC, com os simuladores |
| **App: base** (`lib/core`, `domain`, `data`, `app`) | tema e modo vermelho, ícones do `ui_kit`, cliente com certificado fixado, telescópio falso (demonstração), reconexão sozinha, procura do telescópio em vários endereços, avisos com a tela apagada |
| **App: telas** | todas as 43 do projeto (`docs/08-telas.md`): conectar e parear (com a lista de telescópios na rede e o WiFi do próprio telescópio), observar (câmera ao vivo, foco, captura planetária), Atlas, planejar (fila, noite, mosaico, Lua e planetas, satélite), galeria (estúdio completo, exportar), aparelho (montagem e alinhamento polar, foco, câmera, rede e WiFi de casa, celulares, sistema, atualizações, ajuda) |
| **Os dois juntos** | o cliente Dart fala com o servidor Python de verdade (`scripts/run_app_integration.py`): 9 roteiros, inclusive rede, atualização, alinhamento polar e captura planetária |
| **Android** | o APK de release compila e sai com 25 MB (`flutter build apk --release --split-per-abi`) |
| **Num celular de verdade** | **ainda não testado** |
| **Na Jetson** | **ainda não instalado**: a API foi desenvolvida e testada no PC; o script de instalação está pronto (`scripts/jetson_setup_api.sh`) |

O que está escrito mas **não validado em aparelho** (só um celular diz se funciona): ler o QR
pela câmera, o GPS, guardar o token e a senha do WiFi no cofre do Android, entregar o arquivo
exportado ao Android (folha de compartilhar), achar o telescópio pelo anúncio na rede, os avisos
com a tela apagada (o serviço em primeiro plano e a permissão de avisos) e entrar no WiFi do
telescópio só dentro do app (o código nativo está em `android/.../MainActivity.kt`, e depende
também de a Jetson estar em modo ponto de acesso).

O que **ainda é simulado**, e a tela diz: a câmera (as fotos vêm do simulador; exposição e
ganho ficam guardados mas não mudam a imagem), o apontamento, o focalizador, o movimento manual
da montagem, o alinhamento polar e o planeta da captura planetária. A montagem real aparece no
app (ligação, posição), mas ainda não é comandada por ele.

O que **existe no app mas a Jetson ainda não faz de verdade**: trocar de rede (WiFi de casa,
WiFi próprio) e atualizar pelo app. O contrato está pronto e as telas funcionam contra os
adapters de mentira (na demonstração e no servidor do PC); na Jetson as duas rotas respondem
"ainda não habilitado", e as telas mostram e explicam. Os adapters de verdade entram com você
ao lado do aparelho.

O que **ainda não existe**: inglês; a galeria listar o que o próprio telescópio captura (hoje
mostra as sessões de referência; o resultado da captura planetária fica na imagem ao vivo e
gravado no telescópio); "a vez de comandar" entre dois celulares.

## Rodar

Tudo com o Flutter em `E:\Softwares\flutter\bin` (no PATH). A partir desta pasta:

```
flutter pub get
flutter analyze
flutter test                      # 143 testes, sem aparelho e sem rede
dart format lib test              # largura de 120 colunas (analysis_options.yaml)
```

**Ver o app sem telescópio:** ele tem um modo demonstração (a primeira tela oferece), com céu,
imagens e comandos simulados dentro do próprio app.

**Contra o software da Jetson, no PC** (o falso mais fiel: mesmo código, mesma API):

```
# na raiz do repositório
py -3.11 run_console.py --api          # console na 8080; API do app em https://<ip>:8443
py -3.11 -m src.api.cli pair           # abre a janela de pareamento e desenha o QR
```

Para as telas de rede e de atualização terem com o que falar no PC, ligue os adapters de
mentira; e, para o app achar o servidor sem endereço, o anúncio na rede (pede `pip install
zeroconf`):

```
$env:TELE_NETWORK = "sim"; $env:TELE_UPDATES = "sim"      # PowerShell; vale só nesta janela
py -3.11 run_console.py --api --advertise
```

O app lê o QR (ou recebe o código colado) e está pareado. `py -3.11 -m src.api.cli --help`
mostra os outros comandos do dono: `clients`, `revoke`, `reset`, `info`.

**Os dois lados juntos, de uma vez** (sobe o servidor, pareia, roda e derruba):

```
py -3.11 scripts/run_app_integration.py
```

**Gerar o APK.** O cache do Gradle ocupa cerca de 4 GB e fica no `E:`:

```
$env:GRADLE_USER_HOME = "E:\Softwares\.gradle"      # PowerShell; vale só nesta janela
flutter build apk --release --target-platform android-arm64 --split-per-abi
# build/app/outputs/flutter-apk/app-arm64-v8a-release.apk  (26 MB, Android 7 ou mais novo)
```

O APK é copiado para o celular e instalado por ele (é preciso permitir "instalar apps
desconhecidos"), ou, com a depuração USB ligada, `flutter install`. A assinatura ainda é a de
desenvolvimento, e o identificador é provisório (`com.example.telescope_app`): quando o nome do
produto for decidido ele muda, e o celular vai tratar como outro app (será preciso parear de
novo). A primeira compilação às vezes falha no cache incremental do Kotlin; repetir resolve.

**Como janela do Windows** (para desenvolver sem celular): o alvo existe (`windows/`), mas
**ainda não compila nesta máquina**. O plugin de localização baixa um pacote pelo NuGet, e o
NuGet daqui não tem nenhuma fonte configurada (`Failed to install nuget package
Microsoft.Windows.CppWinRT`). Resolve-se uma vez, com a fonte oficial, e depois `flutter run -d windows`:

```
dotnet nuget add source https://api.nuget.org/v3/index.json -n nuget.org
```

Na janela do Windows não há leitor de QR: o pareamento é por "Digitar o código".

**Ver as telas** (grava PNGs em `test/screens`, a partir dos próprios testes):

```
$env:SCREENSHOTS = "1"; flutter test test/app_test.dart --update-goldens      # PowerShell
```

## O que amarra o app à Jetson

| Peça | Como fica em sincronia |
|---|---|
| Contrato da API | respostas REAIS da API gravadas em `test/fixtures` por `scripts/export_api_fixtures.py`; os testes do app as leem, e um teste da Jetson falha se a API mudar sem regravar |
| Prova do pareamento | um vetor calculado pela Jetson é conferido byte a byte em Dart |
| Ícones | uma fonte só: `src/server/ui_kit.py`. `scripts/export_app_icons.py` exporta para `assets/icons` |
| Sem emoji, sem ícone pronto | um teste varre `lib/` |

## Papéis

| Peça | Papel |
|---|---|
| **Celular (app)** | controle remoto e tela. Sabe a hora e o lugar (GPS) e os entrega à Jetson |
| **Jetson** | o cérebro: câmera, GPU, plate solve, decisão, armazenamento. Serve a API |
| **Placa da montagem** | o músculo: pulsos de passo em tempo real. Só a Jetson fala com ela, por USB |

## Organização

```
lib/
  core/        tema, textos, formatação, erros, componentes (kit) e ícones gerados
  domain/      modelos, código de pareamento e prova, estado ao vivo
  data/        a porta TelescopeApi; HttpTelescope (rede) e FakeTelescope (demonstração e testes);
               as portas do celular: cofre, WiFi do telescópio, busca na rede, avisos, localização
  app/         ligação com o telescópio (reconexão e procura), comandos, buscas, troca de rede,
               avisos, rotas
  features/    connect, shell, observe, atlas, plan, gallery, device
test/          unidade, contrato (fixtures), telas; integration/ contra o servidor de verdade
android/       projeto Android (permissões, abertura escura, WiFi do telescópio só no app,
               o serviço dos avisos)
docs/          o projeto: funcionalidades, UI/UX, conexão, API, arquitetura, roteiro, segurança, telas
```

## Decisões

| Decisão | Escolha |
|---|---|
| Tecnologia | **Flutter (Dart)**, uma base de código |
| Plataforma | **Android primeiro**; iPhone no backlog |
| Quem usa | por enquanto só o dono; o desenho já prevê produto |
| Com quem o app fala | **só com a Jetson** |
| Rede | em casa pelo roteador; no campo pelo **WiFi da própria Jetson**, com troca automática. Sem adaptador USB |
| Segurança | **TLS 1.3 com certificado fixado + pareamento por QR**, desde a primeira versão da API |
| Distribuição | backlog |
| Console web | continua existindo, como reserva; com a API ligada ele é só leitura |
| Nome | aberto — proposta: **Tucana** (`docs/09`). O identificador Android é provisório (`com.example.telescope_app`) e muda junto com o nome |

## O projeto

| Doc | Conteúdo |
|---|---|
| [`docs/00-referencias.md`](docs/00-referencias.md) | o que os apps da DWARF, Seestar e ASIAIR fazem e como conectam; limites das plataformas |
| [`docs/01-funcionalidades.md`](docs/01-funcionalidades.md) | tudo o que o app terá, por área, com fase e o que a Jetson já faz |
| [`docs/02-ui-ux.md`](docs/02-ui-ux.md) | regras de uso noturno, navegação, esboços, fluxos, sistema visual |
| [`docs/03-conexao.md`](docs/03-conexao.md) | rede (casa e campo), descoberta, transporte, hora e local |
| [`docs/04-api.md`](docs/04-api.md) | contrato da API v1: rotas, formatos, erros — e como ficou na implementação |
| [`docs/05-arquitetura-flutter.md`](docs/05-arquitetura-flutter.md) | ambiente, camadas, pacotes, testes — e o que mudou ao construir |
| [`docs/06-roadmap.md`](docs/06-roadmap.md) | fases com critério de pronto, onde estamos, backlog, riscos, decisões |
| [`docs/07-seguranca.md`](docs/07-seguranca.md) | ameaças, canal cifrado, pareamento, tokens, recuperação, testes |
| [`docs/08-telas.md`](docs/08-telas.md) | as 43 telas: o que mostram, ações, estados |
| [`docs/09-nome.md`](docs/09-nome.md) | propostas de nome e recomendação |

## Próximos passos

Do lado do app não há tela por fazer. O que falta é **provar em aparelho** e ligar o que hoje é
de mentira:

1. **O celular**: instalar o APK e percorrer a demonstração (ela tem tudo: rede, atualização,
   alinhamento polar, captura planetária; ligando "Avisar com a tela apagada" dá para conferir
   os avisos sem telescópio). Depois, parear com o servidor rodando no PC (mesmo WiFi): ler o
   QR de verdade, conferir o cofre, o GPS, a câmera e a busca na rede (`--advertise`).
2. **A Jetson**, com você presente e o cabo de rede ligado: `sudo bash scripts/jetson_setup_api.sh`
   (não mexe na rede dela) e parear.
3. **Modo campo de verdade**: o adapter de rede da Jetson (NetworkManager) atrás da mesma porta
   que o `SimNetwork` cumpre, e a prova do WiFi do telescópio só dentro do app. É o passo que
   pode cortar o acesso se der errado: só com você ao lado e o cabo ligado.
4. **Atualização de verdade**: o adapter que baixa, instala e volta atrás.
5. Quando houver mecânica e câmera: comandar a montagem real pelo app (o alinhamento polar passa
   a valer nela), aplicar exposição e ganho de verdade, e a galeria com as capturas próprias.
