// Trava em tempo de COMPILAÇÃO as premissas de pinagem da FYSETC E4.
//
// Os testes em tests/test_firmware_config.py leem o TEXTO da nossa Config. Isto aqui é mais
// forte: roda depois de todo o pré-processador (Config.h -> Config.defaults.h -> pinmap),
// então valida o valor que o compilador REALMENTE usou. É a diferença entre "escrevemos 22"
// e "o binário ficou com 22".
//
// Sem isto, uma regressão no patch do pinmap (que redefine SERIAL_TMC_TX para 15, o Z-MIN)
// passaria silenciosa: compilaria, gravaria, e a montagem simplesmente não andaria — o pior
// tipo de falha, porque parece um problema de hardware. Ver docs/35.

#include "src/Common.h"

// --- a fiação real dos TMC2209 na E4 (tabela de pinos oficial da FYSETC) ---
#if !defined(SERIAL_TMC_TX)
  #error "SERIAL_TMC_TX indefinido: a UART dos drivers nao foi configurada."
#endif
#if SERIAL_TMC_TX != 22
  #error "SERIAL_TMC_TX != 22. O patch do pinmap caiu? O padrao do OnStepX (GPIO15) e o Z-MIN."
#endif
#if SERIAL_TMC_RX != 21
  #error "SERIAL_TMC_RX != 21 (fiacao real da E4: MOTOR UART RX1 = GPIO21)."
#endif

// --- a UART nao pode colidir com o endstop de Z (GPIO15 = Z-MIN, compartilhado c/ Z-DIAG) ---
#if SERIAL_TMC_TX == 15 || SERIAL_TMC_RX == 15
  #error "UART dos TMC no GPIO15 = colisao com Z-MIN/Z-DIAG."
#endif

// --- mapeamento eixo -> slot fisico (X=RA, Y=DEC, E0=focalizador) ---
#if AXIS1_STEP_PIN != 27 || AXIS1_DIR_PIN != 26
  #error "AXIS1 (RA) nao esta no slot X da E4 (STEP 27 / DIR 26)."
#endif
#if AXIS2_STEP_PIN != 33 || AXIS2_DIR_PIN != 32
  #error "AXIS2 (DEC) nao esta no slot Y da E4 (STEP 33 / DIR 32)."
#endif
#if AXIS4_STEP_PIN != 16 || AXIS4_DIR_PIN != 17
  #error "AXIS4 (focalizador) nao esta no slot E0 da E4 (STEP 16 / DIR 17)."
#endif
#if SHARED_ENABLE_PIN != 25
  #error "O enable compartilhado da E4 e o GPIO25."
#endif

// --- o link com a Jetson e a serial USB (SERIAL_A = UART0 = ponte CH340), a 115200 ---
// Com SERIAL_A em OFF o pinmap ainda muda de ramo e joga a UART dos TMC para GPIO3/1.
#if SERIAL_A_BAUD_DEFAULT != 115200
  #error "SERIAL_A_BAUD_DEFAULT != 115200: e o link LX200 com a Jetson (indi_lx200_OnStep)."
#endif
// --- radio: so o ponto de acesso proprio da placa (acesso secundario). Modo estacao
//     exigiria a senha da rede de casa no firmware; Bluetooth nao e usado. ---
#if SERIAL_IP_MODE != WIFI_ACCESS_POINT || SERIAL_BT_MODE != OFF
  #error "Radio fora do previsto: so WIFI_ACCESS_POINT (acesso secundario). Ver Config.telescope.h."
#endif

// --- debug so no build de diagnostico: ele sai pela MESMA serial do LX200 ---
#if !defined(ONSTEPX_DIAG) && DEBUG != OFF
  #error "DEBUG ligado num build de produto: a saida de debug corromperia o link LX200 com a Jetson."
#endif

// --- a montagem tem de estar ativa (os dois eixos com driver definido) ---
#if !defined(MOUNT_PRESENT)
  #error "MOUNT_PRESENT indefinido: AXIS1/AXIS2_DRIVER_MODEL precisam estar configurados."
#endif

// Unidade de tradução deliberadamente sem código: só as travas acima.
