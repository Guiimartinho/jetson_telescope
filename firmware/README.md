# firmware — OnStepX na FYSETC E4, como projeto ESP-IDF 6

Firmware da **montagem** (o lado de tempo real). A Jetson é o cérebro; esta placa gera os
pulsos de passo. Ver `docs/35` para o porquê de cada decisão e `docs/32` para o BOM.

## O que é esta pasta

O OnStepX é um sketch Arduino de **432 arquivos / ~66.000 linhas**. Em vez de reescrevê-lo
em API nativa do IDF (meses de trabalho num código de controle de motor em tempo real, e
contra o princípio de reuso do projeto), usamos o caminho **oficialmente suportado**:
`arduino-esp32` entra como **componente gerenciado do ESP-IDF**. O núcleo compila
inalterado e ganhamos `idf.py`, `menuconfig`, tabela de partições, OTA e `monitor`.

Fica versionado aqui só o que é **decisão nossa**:

```
firmware/
├── CMakeLists.txt              projeto IDF
├── sdkconfig.defaults          alvo esp32, flash 16MB, Arduino autostart, watchdog
├── partitions.csv              16MB com ota_0/ota_1 (atualização pela rede)
├── main/                       componente mínimo + dependência do arduino-esp32
├── config/Config.telescope.h   ◄ A NOSSA CONFIGURAÇÃO (o arquivo que importa)
├── components/onstepx/         CMakeLists que compila a árvore baixada
└── scripts/fetch_onstepx.py    baixa o OnStepX pinado + instala config + aplica patch
```

Depois de editar `config/Config.telescope.h`, rode o `fetch_onstepx.py` de novo: é ele que
copia a Config para dentro da árvore que o build compila.

A árvore do OnStepX (`components/onstepx/onstepx-src/`) **não** é versionada — é baixada
pinada num commit, então o build é reprodutível sem inchar o repositório.

## Construir

```bash
py -3.11 firmware/scripts/fetch_onstepx.py     # 1. baixa o OnStepX + config + patch

# 2. ambiente do IDF (Windows PowerShell)
. "$env:USERPROFILE\esp\v6.0\esp-idf\export.ps1"

cd firmware
idf.py set-target esp32
idf.py build                                   # gera build/onstepx_telescope.bin
```

Verificação rápida da árvore, sem compilar: `py -3.11 firmware/scripts/fetch_onstepx.py --check`

## Gravar

Com a placa na fonte de 12–24V **e** o cabo USB num host com driver CH340 (o PC tem; a
Jetson passa a ter depois de `scripts/jetson_install_ch341.sh`):

```bash
idf.py -p COMxx erase-flash flash        # apaga tudo, grava bootloader + partições + app
```

**O primeiro flash tem de ser por USB, não pela página web de fábrica.** A placa vem com
Marlin + ESP3D (WiFi `MARLIN_ESP`), e a atualização por aquela página troca só o app: o
bootloader (ESP-IDF 3.2.3) e a tabela de partições de fábrica ficariam, sob um app de IDF 6
compilado para outra tabela. Pelo USB vai o conjunto coerente — e, se algo der errado, o
modo download da ROM continua acessível pelo mesmo cabo.

Antes do primeiro flash, guarde o firmware de fábrica (fica em `backup/`, fora do git):

```bash
python -m esptool --port COMxx --baud 921600 read-flash 0 ALL backup/fysetc_e4_factory.bin
python -m esptool --port COMxx write-flash 0 backup/fysetc_e4_factory.bin   # voltar ao Marlin
```

## Link com a Jetson: serial USB

O `SERIAL_A` do OnStepX é a UART0, a mesma da ponte CH340. O caminho é um cabo só:

```
Jetson USB-A (qualquer porta) -> /dev/telescope-mount -> indi_lx200_OnStep (LX200, 115200) -> IndiMount
```

Na Jetson, `sudo bash scripts/jetson_setup_mount.sh` deixa tudo automático: compila o módulo
`ch341` que o kernel do JetPack 6 não traz, desativa a regra udev do `brltty` (que no Ubuntu
22.04 derruba o CH340 logo depois de ele aparecer), cria o nome fixo `/dev/telescope-mount`
e instala o `telescope-indi.service`, que sobe quando a placa é plugada e cai quando ela
sai. O console conecta, envia hora e local, e reconecta sozinho. Ver `docs/35` §9.

Teste de vida, de qualquer terminal serial a 115200: enviar `:GVP#` devolve `On-Step#`.

## Gravar e diagnosticar pela Jetson

A placa não precisa voltar ao PC. Compile aqui, copie os quatro binários (`bootloader.bin`,
`partition-table.bin`, `ota_data_initial.bin`, `onstepx_telescope.bin`) para a Jetson e:

```bash
sudo bash scripts/jetson_flash_mount.sh <pasta_dos_bins>      # para o INDI, grava, religa
```

Build de diagnóstico de bancada — confere se cada TMC2209 responde na UART e narra a
inicialização pela serial:

```bash
idf.py -DONSTEPX_DIAG=ON build          # voltar ao normal: idf.py -DONSTEPX_DIAG=OFF build
# na Jetson:
sudo bash scripts/jetson_flash_mount.sh <bins_diag> --keep-indi-stopped
python3 scripts/mount_bootlog.py 25     # procure "motor driver device detected" em cada eixo
```

O diagnóstico **não** é firmware de produto: o debug sai pela mesma serial do LX200 e imprime
a senha do WiFi. Regrave o build normal ao terminar.

## WiFi da placa: acesso secundário

A placa também sobe um ponto de acesso próprio, `OnStep-Telescopio` (LX200 sobre TCP em
`192.168.0.1:9999`), para celular e depuração. A Jetson não passa por ele.

A senha fica em `config/Config.local.h`, **fora do git**. O `fetch_onstepx.py` gera o
arquivo com uma senha aleatória na primeira vez e nunca o sobrescreve; a Config recusa
compilar sem ele. Para trocar a senha: edite o arquivo, rode o fetch e regrave com
`erase-flash` (o OnStepX guarda o WiFi na NVS no primeiro boot e ignoraria o valor novo).

## Antes de ligar motores, preencha

Em `config/Config.telescope.h`:
- `AXIS1/2_STEPS_PER_DEGREE` — hoje é um valor **provisório**; medir na mecânica real.
- `AXIS1/2_REVERSE` e `AXIS4_STEPS_PER_MICRON` — só se descobrem com a mecânica montada.

## Testes

Rodam com o resto do projeto (`pytest`), sem placa e sem toolchain:

```bash
py -3.11 -m pytest tests/test_firmware_config.py -v
```

Eles validam a config contra a **tabela de pinos oficial da FYSETC**: UART dos TMC na
fiação real (GPIO21/22), ausência de colisão com o endstop de Z, mapeamento eixo↔slot,
corrente abaixo do nominal dos motores e coerência entre passos/grau e a fórmula.
Foi um erro dessa classe que o bring-up revelou — agora é regressão automatizada.
