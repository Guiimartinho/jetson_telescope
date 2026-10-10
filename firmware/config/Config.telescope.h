// =====================================================================================
// Config do OnStepX para o NOSSO telescópio — FYSETC E4 (ESP32-WROOM-32E) + OpenAstroExplorer
// =====================================================================================
// Instalado na raiz da árvore do OnStepX por scripts/fetch_onstepx.py (src/Common.h faz
// `#include "../Config.h"`). Só definimos o que nos interessa; `src/Config.defaults.h`
// preenche o resto. Ver docs/35 (firmware) e docs/32 (BOM da montagem).
//
// Este arquivo é versionado; a árvore do OnStepX não é. Toda decisão nossa está aqui.
#pragma once

// Versão do formato deste arquivo de configuração. Sem isto o OnStepX emite
// `#warning "FileVersionConfig is undefined, assuming version 5"` — que, com o -Werror do
// IDF 6, vira erro fatal. Tem de acompanhar `FirmwareVersionConfig` do OnStepX.ino.
#define FileVersionConfig                6

// -------------------------------------------------------------------------------------
// 1. PLACA
// -------------------------------------------------------------------------------------
// Mapeamento físico confirmado na tabela de pinos oficial da FYSETC:
//   slot X  -> AXIS1 (RA)   STEP 27 / DIR 26      slot Z  -> AXIS3 (rotator, não usado)
//   slot Y  -> AXIS2 (DEC)  STEP 33 / DIR 32      slot E0 -> AXIS4 (focalizador) STEP 16 / DIR 17
//   ENABLE é COMPARTILHADO por todos os drivers no GPIO25.
#define PINMAP                        FYSETC_E4

// -------------------------------------------------------------------------------------
// 2. CANAIS DE COMUNICAÇÃO
// -------------------------------------------------------------------------------------
// SERIAL_A = UART0 = ponte USB CH340. É O LINK COM A JETSON:
//   cabo USB-A -> /dev/ttyUSB0 -> indi_lx200_OnStep (LX200 a 115200) -> IndiMount.
// O mesmo cabo grava e depura a placa. A Jetson precisa do módulo `ch341`, que o kernel do
// JetPack 6 não traz: scripts/jetson_install_ch341.sh. Ver docs/35.
// ATENÇÃO: manter != OFF também escolhe o ramo do pinmap que deixa SERIAL_TMC_RX
// sobrescrevível (o ramo OFF força a UART dos TMC para GPIO3/1, os pinos do USB).
#define SERIAL_A_BAUD_DEFAULT      115200

// O pinmap da E4 define APENAS SERIAL_A (a placa não expõe uma segunda UART de hardware);
// `src/pinmaps/Validate.h` recusa a compilação se SERIAL_B_BAUD_DEFAULT != OFF sem SERIAL_B.
#define SERIAL_B_BAUD_DEFAULT          OFF

// Rádio: PONTO DE ACESSO próprio da placa — um acesso SECUNDÁRIO (celular, depuração) que
// funciona em campo sem roteador. O link da Jetson continua sendo o cabo (SERIAL_A), que é
// o mais seguro. É o SERIAL_RADIO, não um "SERIAL_B", que sobe o servidor LX200 sobre TCP
// (porta 9999, em 192.168.0.1). Modo estação ficou de fora de propósito: exigiria a senha
// da rede de casa dentro do firmware.
#define SERIAL_RADIO     WIFI_ACCESS_POINT
#define AP_SSID        "OnStep-Telescopio"

// A senha do AP NÃO mora neste arquivo (ele é versionado): vem de config/Config.local.h,
// fora do git, gerado por scripts/fetch_onstepx.py. Sem ele a compilação para aqui — nunca
// sai um firmware com a senha padrão do OnStepX ("password").
#if __has_include("Config.local.h")
  #include "Config.local.h"
#endif
#ifndef AP_PASSWORD
  #error "AP_PASSWORD indefinida: rode firmware/scripts/fetch_onstepx.py (ele gera config/Config.local.h)."
#endif

// -------------------------------------------------------------------------------------
// 3. UART DOS DRIVERS TMC2209  — O PONTO MAIS DELICADO DESTA PLACA
// -------------------------------------------------------------------------------------
// A E4 tem os 4 TMC2209 soldados, com a UART fisicamente ligada em:
//        MOTOR UART:  TX1 = GPIO22    RX1 = GPIO21        (tabela de pinos oficial FYSETC)
// O pinmap FYSETC_E4 do OnStepX, porém, assume outra fiação e usa GPIO0/GPIO15 — e GPIO15
// é o Z-MIN (compartilhado com Z-DIAG) nesta placa. Usar o padrão do OnStepX NÃO alcança
// os drivers e ainda colide com o endstop de Z.
//
// SERIAL_TMC_RX tem guarda `#ifndef` no pinmap, então basta definir aqui. SERIAL_TMC_TX
// NÃO tem guarda — por isso scripts/fetch_onstepx.py aplica um patch cirúrgico que adiciona
// o `#ifndef` (o patch é verificado por teste: tests/test_firmware_config.py).
//
// CONSEQUÊNCIA ACEITA: GPIO21/22 são os pinos padrão de I2C do ESP32. Nesta placa,
// I2C e UART dos TMC são mutuamente exclusivos. Não usamos I2C (sem GPS/RTC — quem dá a
// hora é a Jetson), então o custo é zero para nós.
#define SERIAL_TMC_RX                   21
#define SERIAL_TMC_TX                   22

// -------------------------------------------------------------------------------------
// 4. MONTAGEM
// -------------------------------------------------------------------------------------
// OpenAstroExplorer: equatorial com contrapeso -> GEM (precisa de meridian flip).
#define MOUNT_TYPE                     GEM

// -------------------------------------------------------------------------------------
// 5. EIXOS
// -------------------------------------------------------------------------------------
// Fórmula:  passos/grau = (passos_motor_por_volta * microsteps * reducao) / 360
// Motor 17HS4401: 1,8° => 200 passos/volta.
//
// TODO(mecanica): a REDUÇÃO abaixo é PROVISÓRIA — vem da leitura de docs/32 ("RA por
// correia, 9:1 em dois estágios"), não de medição. Quando a montagem estiver montada,
// medir de verdade (comandar N graus, contar a rotação real) e corrigir. O teste
// tests/test_firmware_config.py garante que o número e a fórmula não se separem.
#define AXIS1_DRIVER_MODEL         TMC2209   // RA  — slot X
#define AXIS1_DRIVER_MICROSTEPS         16
#define AXIS1_STEPS_PER_DEGREE       720.0   // (200 * 16 * 81) / 360  [reducao 81:1 PROVISORIA]
#define AXIS1_DRIVER_IRUN             1000   // mA. Com UART a corrente e por software:
                                             // 1,0 A no 17HS4401 (nominal 1,7 A) roda frio e
                                             // silencioso — a montagem quase nao pede torque.
#define AXIS1_REVERSE                  OFF   // TODO(bring-up): inverter se o eixo andar ao contrario

#define AXIS2_DRIVER_MODEL         TMC2209   // DEC — slot Y
#define AXIS2_DRIVER_MICROSTEPS         16
#define AXIS2_STEPS_PER_DEGREE       720.0   // (200 * 16 * 81) / 360  [PROVISORIA — DEC e worm]
#define AXIS2_DRIVER_IRUN             1000   // mA
#define AXIS2_REVERSE                  OFF   // TODO(bring-up)

// Focalizador no slot E0 (o 4o driver que sobra). Motor 35HS42 (NEMA 14, 1,0 A nominal).
#define AXIS4_DRIVER_MODEL         TMC2209
#define AXIS4_DRIVER_MICROSTEPS         16
#define AXIS4_DRIVER_IRUN              600   // mA — motor menor, carga leve
#define AXIS4_STEPS_PER_MICRON         0.5   // TODO(bring-up): medir no focalizador real

// -------------------------------------------------------------------------------------
// 6. DIVERSOS
// -------------------------------------------------------------------------------------
#define STATUS_LED                      ON   // GPIO13 (FAN0 na E4) — diagnostico visual
#define TIME_LOCATION_SOURCE           OFF   // sem GPS/RTC: hora e local vem da Jetson (INDI)

// -------------------------------------------------------------------------------------
// 7. DIAGNÓSTICO DE BANCADA — só com:  idf.py -DONSTEPX_DIAG=ON build
// -------------------------------------------------------------------------------------
// Sem MOTOR_DRIVER_DETECT o OnStepX escreve nos TMC2209 às cegas: um pino de UART errado não
// vira erro, vira micropasso e corrente errados. Este build confere, no boot, se cada driver
// responde, e narra a inicialização inteira pela serial.
// NUNCA é o firmware de produto: o debug sai pela MESMA serial do LX200 e corromperia o link
// com a Jetson. config_assert.cpp recusa um build normal com DEBUG ligado.
#ifdef ONSTEPX_DIAG
  #define DEBUG                    VERBOSE
  #define SERIAL_DEBUG_BAUD         115200
  #define MOTOR_DRIVER_DETECT
  #define AXIS1_DRIVER_STATUS           ON   // deixa ler as flags do driver por :GXU1#
  #define AXIS2_DRIVER_STATUS           ON
  #define AXIS4_DRIVER_STATUS           ON
#endif
