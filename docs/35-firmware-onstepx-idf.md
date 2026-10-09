# 35 — Firmware da montagem: OnStepX como projeto ESP-IDF 6

A Jetson é o cérebro (visão, plate solve, decisão); a **FYSETC E4** é o músculo de tempo
real (pulsos de passo com timing de microssegundos). Este doc registra como o firmware
dessa placa entra no projeto — e por que ele **não** foi reescrito.

---

## 1. A pergunta: "migrar o .ino 100% para o IDF"

Primeiro, o tamanho real do que se estava propondo migrar:

| | |
|---|---|
| OnStepX | **432 arquivos, 66.367 linhas** de C++ |
| `OnStepX.ino` em si | **161 linhas** (só `setup()`/`loop()`) — todo o resto está em `src/` |
| Subsistemas | `lib/` 272 arq. · `telescope/` 90 · `HAL/` 25 · `pinmaps/` 21 · `libApp/` 12 |

Reescrever 66k linhas de controle de motor em tempo real para API nativa do IDF seria um
projeto de meses, num código onde um erro sutil vira estrela riscada ou montagem batendo
no tripé. E contraria o princípio do próprio projeto (`docs/08`): *reusar controle,
construir só o pipeline de GPU*.

**Mas existe uma migração real e oficialmente suportada**, que é a que fizemos.

## 2. A migração de verdade: Arduino como componente do IDF

O `arduino-esp32` é publicado como **componente do ESP-IDF**. Os fatos que sustentam a
escolha, verificados no dia:

- `idf_component.yml` do arduino-esp32 declara: **`idf: ">=5.3,<6.2"`**.
- A release **3.3.9 (2026-06-04)** trouxe explicitamente *"feat(idf): Add support for
  ESP-IDF v6.0"*, além de correções específicas de IDF 6 (`fix(idf6)`, `fix(spi): use
  spi_ll bus/reset clock on IDF ≥ 6`).
- O IDF desta máquina é **v6.0.2**, e o target `esp32` (ESP32-WROOM-32E da E4) está presente.
- Resolvido no build: **arduino-esp32 3.3.11**.

O que se ganha, sem tocar nas 66k linhas: `idf.py`, `menuconfig`, tabela de partições
própria, **OTA**, `monitor`, e o mesmo sistema de build do resto do ecossistema Espressif.
Com `CONFIG_AUTOSTART_ARDUINO=y`, o próprio arduino-esp32 fornece o `app_main()` e chama
o `setup()`/`loop()` do OnStepX.

## 3. O que é versionado (e o que não)

Só entra no repositório o que é **decisão nossa**:

```
firmware/config/Config.telescope.h   a configuração do telescópio
firmware/scripts/fetch_onstepx.py    baixa o OnStepX PINADO + instala config + patch
firmware/{CMakeLists,sdkconfig.defaults,partitions.csv,main/,components/onstepx/}
```

A árvore do OnStepX é baixada pinada no commit `65a7518` (versão 10.28x) e fica fora do
git. Build reprodutível, repositório enxuto, e o `git diff` mostra decisões — não 66k
linhas de terceiro.

## 4. O achado que virou teste: a UART dos TMC2209

Este é o ponto onde a placa e o firmware discordam, e onde um erro **não** apareceria na
compilação — apareceria como uma montagem que não anda.

| Fonte | UART dos TMC2209 |
|---|---|
| **Tabela de pinos oficial da FYSETC** (fiação real) | **TX1 = GPIO22, RX1 = GPIO21** |
| Marlin (firmware nativo da placa) | `HARDWARE_SERIAL1_RX 21`, `TX 22` — bate |
| **Pinmap `FYSETC_E4` do OnStepX** | `SERIAL_TMC_RX 0`, **`SERIAL_TMC_TX 15`** |

E na E4, **GPIO15 é o Z-MIN, compartilhado com o Z-DIAG**. Usar o padrão do OnStepX não
alcançaria os drivers *e* colidiria com o endstop de Z.

Duas consequências práticas:

1. **Patch cirúrgico no pinmap.** `SERIAL_TMC_RX` tem guarda `#ifndef` (dá para sobrescrever
   pela Config); `SERIAL_TMC_TX` **não tem** — o pinmap o redefiniria para 15 *depois* da
   nossa Config, descartando nossa escolha em silêncio. O `fetch_onstepx.py` adiciona a
   guarda, e um teste verifica que ela está lá.
2. **I2C e UART dos TMC são mutuamente exclusivos nesta placa**, porque GPIO21/22 são os
   pinos padrão de I2C do ESP32. Custo zero para nós: não usamos I2C — quem fornece hora e
   local é a Jetson, via INDI.

## 5. Poda: só o que é alcançável na E4

O OnStepX suporta ~19 placas e 5 famílias de MCU. Nada disso é alcançável no nosso alvo —
são `#if defined(...)` que nunca fecham. `firmware/scripts/prune_onstepx.py` remove esse
peso de forma **declarativa e em camadas**, para a migração poder ser feita aos poucos:

| Camada | O que sai | Por que é seguro |
|---|---|---|
| **1** | HAL de atmel/STM32/Teensy/mbed/arduinoM0 + 17 pinmaps de outras placas | `HAL/HAL.h` escolhe a família por `#if defined(ESP32)`; `PINMAP=FYSETC_E4` escolhe o pinmap. O resto é inalcançável **por construção** |
| **2** | encoder, CAN, expansor de GPIO, ethernet cabeada, Bluetooth | desligados pela nossa Config — verificar com build |
| **3** | fontes alternativas de tempo/calendário | `TIME_LOCATION_SOURCE=OFF` (hora vem da Jetson) — mais invasivo |

A camada 1, aplicada: **−33 arquivos, −3.645 linhas** (66.237 → 62.592).

A poda é reaplicada automaticamente num re-download
(`fetch_onstepx.py --prune-tier N`), então nunca se perde. E o manifesto tem rede de
segurança: uma lista `PROTEGIDO` que nenhuma regra pode violar, coberta por testes — sem
ela, um glob mal escrito apagaria justamente o pinmap da nossa placa ou o HAL do ESP32.

**Regra de método:** aplicar uma camada, reconstruir, confirmar verde, só então a próxima.
Nunca pular para a 3.

## 6. Atrito real: arduino-esp32 3.3.x × ESP-IDF 6.0

O primeiro build falhou — e vale registrar **onde**, porque não foi no nosso código nem no
OnStepX: foram duas bibliotecas do próprio `arduino-esp32`, com avisos promovidos a erro
pelo `-Werror` que o IDF 6 fixa para todos os componentes (`tools/cmake/build.cmake`, sem
Kconfig para desligar).

| Erro | Causa | O que fizemos |
|---|---|---|
| `LittleFS.cpp`: `missing initializer for 'esp_vfs_littlefs_conf_t::blockdev'` | o struct do littlefs ganhou um campo no IDF 6 — bug upstream | `-Wno-error=missing-field-initializers` **só** nesse componente |
| `ssl_client.cpp`: `#warning` pedindo `CONFIG_MBEDTLS_PSK_MODES` | a lib pede uma opção do mbedTLS | ligamos a opção — fazer o que o aviso pede, não silenciá-lo |

O rebaixamento é aplicado **apenas** ao componente de terceiro; o nosso código e o do
OnStepX continuam sob `-Werror`. Remover quando o upstream corrigir.

Antes disso houve um erro mais simples, também instrutivo: `REQUIRES arduino` falhou com
*"Failed to resolve component 'arduino'"* — o gestor de componentes prefixa o namespace, e
o nome correto é **`espressif__arduino-esp32`**.

### A política de warnings que ficou

O mesmo atrito reapareceu dentro do OnStepX (`StepDir.cpp`: `'--' em tipo volatile`,
depreciado no C++20) e no próprio `Arduino.h` (`comparison of unsigned '< 0'`). Caçar aviso
por aviso em código que não mantemos — ou pior, forkar as fontes para silenciá-los — é
trabalho perdido e some na próxima atualização. A regra adotada:

> **Código de terceiro avisa; não aborta.** `-Wno-error` nos componentes `onstepx` e
> `tmc2209`. Os avisos continuam no log. **O nosso código e o do IDF seguem sob `-Werror`.**

A fronteira é explícita e está no `CMakeLists.txt` de cada componente, com o motivo escrito.

## 6b. O que o build ensinou sobre a configuração

Três erros vieram da *nossa* Config — e são exatamente o tipo de coisa que só a compilação
revela:

| Erro | O que estava errado | Correção |
|---|---|---|
| `FileVersionConfig is undefined` | faltava declarar a versão do formato do Config | `#define FileVersionConfig 6` |
| `SERIAL_B isn't defined, SERIAL_B_BAUD_DEFAULT should be OFF` | eu tinha posto o WiFi em `SERIAL_B`; a E4 **só expõe SERIAL_A** | `SERIAL_B_BAUD_DEFAULT OFF` + o canal de rede é **`SERIAL_RADIO`** |
| `fatal error: TMC2209.h: No such file` | o OnStepX **não embute** o driver dos TMC — faz `#include <TMC2209.h>` | biblioteca `hjd1964/TMC2209` virou o componente `firmware/components/tmc2209/` |

O terceiro é o mais fácil de tropeçar: no Arduino IDE essa dependência é invisível (o
Library Manager a instala), e só aparece quando se sai dele.

## 7. Testes (sem placa, sem toolchain)

`tests/test_firmware_config.py` — **23 testes** que rodam na suíte normal do projeto. Eles
comparam a nossa Config com a **tabela de pinos oficial da FYSETC**, embutida no teste como
verdade de campo:

- UART dos TMC em GPIO21/22, e **não** colidindo com Z-MIN nem com pino de motor;
- mapeamento eixo↔slot (RA→X, DEC→Y, foco→E0) e enable compartilhado no GPIO25;
- corrente `IRUN` dentro da faixa segura de cada motor;
- coerência entre `STEPS_PER_DEGREE` e a fórmula documentada;
- `SERIAL_A` ligado (senão o pinmap muda de ramo e ignora nossa UART);
- link com a Jetson pela serial USB, num baud que o INDI aceita; rádio só como ponto de
  acesso secundário, nenhuma credencial no arquivo versionado e log do IDF em `WARN` (§8.1);
- o arquivo de segredos local: gerado com senha aleatória e nunca sobrescrito;
- o patch do pinmap aplicado (pula se a árvore não foi baixada).

**Validado que têm dentes:** injetando o valor do OnStepX (`SERIAL_TMC_TX 15`), dois testes
falham na hora. Um teste que não falha quando deveria não é teste.

### A trava mais forte: `config_assert.cpp`

Os testes em pytest leem o **texto** da Config. `firmware/components/onstepx/config_assert.cpp`
é mais forte: roda **depois de todo o pré-processador** (Config.h → Config.defaults.h →
pinmap), então valida o valor que o compilador *realmente usou* — a diferença entre
"escrevemos 22" e "o binário ficou com 22". Ele trava:

- `SERIAL_TMC_TX == 22` e `SERIAL_TMC_RX == 21`, e nenhum deles no GPIO15 (Z-MIN/Z-DIAG);
- AXIS1 no slot X (27/26), AXIS2 no Y (33/32), AXIS4 no E0 (16/17), enable compartilhado no 25;
- `MOUNT_PRESENT` definido (senão os eixos não estão configurados);
- `SERIAL_A` a 115200, e o rádio só como ponto de acesso (`SERIAL_IP_MODE` em
  `WIFI_ACCESS_POINT`, `SERIAL_BT_MODE` em `OFF`).

Fica do **nosso** lado da fronteira de warnings, então continua sob `-Werror`.

**Também validado com dentes:** injetando `SERIAL_TMC_TX 15` na Config, o build **para** com
exatamente as duas mensagens escritas ali. Uma regressão no patch do pinmap não chega ao
binário — e essa é a falha que mais assusta, porque compilaria, gravaria, e a montagem
simplesmente não andaria, parecendo defeito de hardware.

## 8. Primeiro flash na placa real (2026-10-09)

A fonte de 12V chegou e a placa foi gravada pelo USB do PC (ponte CH340, COM24).

| | |
|---|---|
| Chip | ESP32-D0WD-V3 rev 3.1, cristal de 40 MHz |
| Flash | **16 MB confirmados na placa** (fabricante `a1`, device `4018`) — o build assumia isso sem ter medido |
| Firmware de fábrica | Marlin bugfix-2.0.x (FYSETC_E4) + ESP3DLib sobre ESP-IDF 3.2.3, tabela `default_16MB` |
| Backup de fábrica | dump integral de 16.777.216 bytes em `firmware/backup/` (fora do git) |
| Gravação | `erase-flash` (30 s) + bootloader, partições, otadata e app, com hash verificado |
| Binário | `onstepx_telescope.bin` = **1.054.576 bytes**, 66% livres na partição de 3 MB. Um build só-serial, sem a pilha WiFi, mede 373.808 |

O boot sobe com o bootloader do IDF 6.0.2, flash DIO a 80 MHz e CPU a 240 MHz. A placa
passa a responder comandos **7,7 s** depois do reset (cerca de 15 s no primeiro boot após um
`erase-flash`, enquanto o OnStepX inicializa a NVS). Teste de fumaça LX200 pela serial, só
com consultas (nada move):

```
:GVP# -> On-Step#        :GVN# -> 10.28x#
:GU#  -> nNpHvEo160#     parado, sem goto, fora do park, em casa, GEM, erro 0
:GR#  -> 12:39:56#       :GD#  -> +90*00:00#     casa de GEM: apontando o polo
:FA#  -> 1               focalizador presente
```

Fora dos comandos o canal fica em silêncio: 0 bytes espontâneos, inclusive durante 26 s em
que um cliente WiFi entrou no AP, consultou a placa e saiu. O log do boot (ROM e bootloader)
sai pela mesma UART0, então o INDI tem de conectar depois de a placa subir.

O acesso secundário também foi testado de ponta a ponta: um PC entrou no AP
`OnStep-Telescopio` e `:GVP#` pela porta TCP 9999 devolveu `On-Step#`.

### 8.1 Correção de rumo: o link é o cabo

Em setembro, ao descobrir que o kernel do JetPack 6 não traz o driver CH340, a Config foi
virada para WiFi e isso foi documentado como decisão. Era um desvio em volta de um problema
de dez minutos: o módulo `ch341` é do kernel mainline e compila fora da árvore contra os
headers que o JetPack já instala (`scripts/jetson_install_ch341.sh`). O plano combinado era
o cabo, e ele é o link melhor:

```
Jetson USB-A -> /dev/ttyUSB0 -> indi_lx200_OnStep (LX200, 115200) -> IndiMount
```

Sem roteador no caminho, sem jitter de rádio, e o mesmo cabo grava e depura a placa.

**O WiFi fica, como acesso secundário.** A placa sobe um ponto de acesso próprio
(`SERIAL_RADIO WIFI_ACCESS_POINT`, SSID `OnStep-Telescopio`, LX200 sobre TCP na porta 9999 de
`192.168.0.1`) para celular e depuração; funciona em campo sem roteador. A Jetson não passa
por ele. Três cuidados vieram junto:

- **Senha fora do git.** Ela mora em `firmware/config/Config.local.h`, ignorado pelo git e
  gerado com valor aleatório pelo `fetch_onstepx.py`. A Config versionada recusa compilar
  sem ela, então nunca sai um firmware com a senha padrão do OnStepX (`password`).
- **Modo estação ficou de fora de propósito:** exigiria a senha da rede de casa dentro do
  firmware. Uma trava de compilação impede que ele volte por um default.
- **Log do IDF em `WARN`.** O console divide a UART0 com o `SERIAL_A`. Em `INFO` o WiFi
  imprime uma linha a cada cliente que entra ou sai do AP; no meio de uma resposta LX200
  isso corromperia a leitura do INDI. O log do bootloader é configuração à parte e continua
  completo.

Trocar a senha exige regravar com `erase-flash`: o OnStepX grava as configurações de WiFi na
NVS no primeiro boot e passa a ignorar o valor compilado.

A segunda armadilha fica registrada no script: no Ubuntu 22.04 a regra udev do `brltty`
(leitor braille) reivindica o ID `1a86:7523` e derruba o `ttyUSB0` segundos depois de ele
aparecer. Sem mascarar a regra, o driver "funciona e some".

### 8.2 O que a bancada desmentiu

Este doc dizia que a E4 "não se alimenta pelo USB: comprovado por não enumerar". O sintoma
foi observado; a causa não tinha sido provada. Com os 12V ligados a placa continuou sem
aparecer no `lsusb` da Jetson (que não depende de driver nenhum) e enumerou na hora no PC.
Na Jetson a causa era a ligação física do cabo: refeita, a placa enumerou na hora. Fica a
regra: "não enumerou" é um sintoma com várias causas possíveis, e escrever "comprovado"
exige ter eliminado as outras. O diagnóstico que separa as hipóteses é ler o estado das
portas direto no hub (`lsusb -v` no hub): "energizada, sem conexão" aponta para o caminho
físico, não para driver nem para suspensão.

### 8.3 O link na Jetson, de ponta a ponta

Com a placa numa porta USB-A da Orin, sem nenhuma mudança no nosso código:

| Camada | Resultado |
|---|---|
| USB | `1a86:7523` em `usb 1-2.4`; o `ch341` assume e cria `/dev/ttyUSB0` |
| udev | o `ttyUSB0` continua de pé (a regra do `brltty` está mascarada) |
| Permissão | o usuário comum abre a porta (grupo `dialout`, `docs/34`) |
| LX200 cru | `:GVP#` → `On-Step#`, direto da Jetson |
| Reset ao abrir | **não acontece**: 0 bytes de boot ao abrir a porta, nem depois de o INDI abrir e fechar |
| INDI | `indi_lx200_OnStep` a 115200 conecta e expõe 86 propriedades, incluindo o focalizador |
| Nosso adapter | `IndiMount.get_radec()` → RA 12,77 h, DEC +90° (a casa da GEM) |

Esse teste manual expôs duas lacunas, fechadas na seção 9: o `IndiMount` não sabia configurar
a serial (o INDI abre a 9600 por padrão) e a montagem acordava sem hora nem local.

## 9. Automático: do plugar até a montagem pronta

**Papéis.** A Jetson é o cérebro: vê, decide, e é quem sabe a hora e o lugar. A placa é o
músculo: pulsos de passo em tempo real, rastreio, limites. O cabo USB é o link; o WiFi da
placa é só acesso manual de reserva. **Por que isto veio primeiro:** goto, centralização por
plate solve, rastreio e foco passam todos por essa cadeia. É a espinha do telescópio e é o
que já está em mãos, então fecha-se e testa-se antes de gastar com câmera e mecânica.

Nenhum passo é manual. Cada elo tem um dono:

| Elo | Quem faz | Onde |
|---|---|---|
| Driver da ponte USB | módulo `ch341`, carregado pelo kernel ao plugar | `scripts/jetson_install_ch341.sh` |
| Nome fixo em **qualquer** porta USB | regra udev → `/dev/telescope-mount` | `deploy/jetson/99-telescope-mount.rules` |
| INDI sobe e cai com a placa | systemd, unidade amarrada ao dispositivo (`BindsTo`) | `deploy/jetson/telescope-indi.service` |
| Configurar a serial e conectar | `IndiMount(serial_port=…, baud=…)` | `src/control/mount.py` |
| Enviar hora UTC e local | `IndiMount.set_site_and_time()` | `src/control/mount.py` |
| Manter conectado, reconectar | `MountLink` (thread; a cada reconexão reenvia hora e local) | `src/control/mount_link.py` |
| Mostrar na tela | `/api/state` → "montagem conectada" no console | `src/server/console.py` |
| Ligar a montagem real no serviço | `TELE_MOUNT=indi` (sem ela, simuladores) | `deploy/jetson/telescope-console.mount.conf` |
| Instalar tudo na Jetson | `sudo bash scripts/jetson_setup_mount.sh` (idempotente) | — |

O nome fixo casa por VID:PID, porque o CH340 não tem número de série; quem confirma que do
outro lado está o OnStepX é o handshake LX200 do driver INDI. A unidade do INDI vive
exatamente enquanto a placa está plugada, e é isso que torna a queda do cabo visível na
hora: o indiserver para, o socket do cliente fecha, o `MountLink` marca "desconectada" e
passa a tentar de novo.

### 9.1 Verificado na Orin

| Prova | Resultado |
|---|---|
| Hora e local chegaram na placa | lidos de volta pelo WiFi **dela** (canal independente): `:GC#` 10/09/26, `:GL#` hora UTC com `:GG#` +00:00, `:Gt#` −23°33′, `:Gg#` +046°37′ (o OnStep conta oeste positivo), `:GS#` tempo sideral local coerente |
| Casa da montagem | passou de DEC +90° para **−90°** depois de receber a latitude: no hemisfério sul a GEM estaciona no polo sul celeste |
| INDI parado e religado | o link caiu e voltou sozinho (`connections` 1 → 2), reenviando hora e local |
| **Cabo trocado de porta USB** | porta `1-2.4` → `1-2.2`: o INDI parou no mesmo segundo em que o cabo saiu, voltou 1 s depois de a placa enumerar na porta nova, e o console estava "conectada" de novo em cerca de 2 s. `/dev/telescope-mount` seguiu a placa |
| **Reboot da Jetson** | sem tocar em nada: `ch341` em 9,9 s, INDI em 12,1 s, console em 12,6 s, e "montagem conectada" antes de 30 s de boot |

### 9.2 Drivers dos motores validados no hardware

`:GXU1#` devolvia `0` porque `AXISn_DRIVER_STATUS` vem `OFF`, e a detecção do driver na
inicialização só existe sob `MOTOR_DRIVER_DETECT`. Sem ela o OnStepX escreve nos TMC2209 às
cegas: um pino de UART errado **não** vira erro, vira micropasso e corrente errados. O build
de diagnóstico (`idf.py -DONSTEPX_DIAG=ON build`, bloco 7 da Config) liga as duas coisas e o
debug verboso. Resultado na placa:

```
Axis1Tmc2209StepDir legacy, HW UART driver pins rx=21, tx=22, baud=460800 bps
Axis1Tmc2209StepDir legacy, motor driver device detected          (RA,   slot X,  step 27 / dir 26)
Axis2Tmc2209StepDir legacy, motor driver device detected          (DEC,  slot Y,  step 33 / dir 32)
Axis4Tmc2209StepDir legacy, motor driver device detected          (foco, slot E0, step 16 / dir 17)
```

Os três drivers respondem nos pinos corrigidos em setembro (GPIO21/22, e não o GPIO15 do
pinmap original), cada um no seu endereço, com as correntes configuradas (1000/500 mA em RA
e DEC, 600/300 mA no foco) e nenhuma linha `ERR` ou `WRN` no boot. As flags de `:GXU` vêm
limpas.

O build de diagnóstico nunca é o firmware de produto: o debug sai pela mesma serial do LX200
(e imprime a senha do WiFi). `config_assert.cpp` recusa um build normal com `DEBUG` ligado.

### 9.3 Gravar pela própria Jetson

A placa não precisa mais voltar ao PC. O PC compila; os quatro binários vão para a Jetson; ela
grava pelo mesmo cabo do link:

```bash
sudo bash scripts/jetson_flash_mount.sh <pasta_dos_bins> [--erase] [--keep-indi-stopped]
python3 scripts/mount_bootlog.py 20      # reinicia a placa e mostra o log de boot (INDI parado)
```

O script para o `telescope-indi` durante a gravação (o driver segura a porta) e o religa no
fim; o console reconecta sozinho. Foi por esse caminho que o diagnóstico entrou e o firmware
de produto voltou.

## 10. O que falta

- **A montagem real ainda não comanda os modos do painel.** O console mostra a montagem
  conectada, mas GOTO, agendador e rastreio seguem nos simuladores (`Controller` instancia
  `SimMount`). Trocar exige a mecânica: um goto de verdade só se valida com motor e eixo.
- **Calibração mecânica**, que depende da montagem impressa: `AXIS*_STEPS_PER_DEGREE` (a
  redução real), `AXIS*_REVERSE`, limites e `AXIS4_STEPS_PER_MICRON`. Marcados com `TODO`.
- **Monitoramento dos drivers no produto.** `AXISn_DRIVER_STATUS ON` deixaria a Jetson ler
  falhas dos TMC2209, mas pode acusar carga aberta em repouso; decidir com motor ligado.
- **`MASTER_PASSWORD` do OnStepX** continua no padrão. Ela protege a página de configuração
  do WiFi, que só se alcança depois de entrar no AP (este sim com senha própria).
- **Local único.** O local padrão está em dois lugares (`console.DEFAULT_SITE` e
  `mount_link.DEFAULT_SITE`); deve virar um campo do perfil de equipamento.
- **Quando a câmera chegar**, o `telescope-indi.service` não pode continuar amarrado só à
  montagem: ou a câmera ganha um indiserver próprio, ou os drivers passam a ser ligados e
  desligados por dispositivo.

Ver `firmware/README.md` (como construir e gravar), `docs/32` (BOM) e `docs/31` (bring-up).
