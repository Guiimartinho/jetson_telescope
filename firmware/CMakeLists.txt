# Projeto ESP-IDF do firmware da montagem (OnStepX na FYSETC E4 / ESP32-WROOM-32E).
#
# O OnStepX é um sketch Arduino de ~66k linhas. A migração para o IDF é feita do jeito
# oficialmente suportado: `arduino-esp32` entra como COMPONENTE gerenciado do IDF (ele
# declara `idf: ">=5.3,<6.2"`, e a release 3.3.9 adicionou suporte a ESP-IDF v6.0). Assim
# ganhamos idf.py / menuconfig / partições / OTA / monitor sem reescrever o núcleo de
# controle de motor em tempo real. Ver docs/35.
cmake_minimum_required(VERSION 3.16)

# O código do OnStepX é baixado por scripts/fetch_onstepx.py (pinado num commit) para
# components/onstepx/onstepx-src/ — não é versionado aqui (66k linhas de terceiro).
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/components")

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(onstepx_telescope)

# -------------------------------------------------------------------------------------
# Atrito conhecido: arduino-esp32 3.3.x contra ESP-IDF 6.0
# -------------------------------------------------------------------------------------
# O IDF 6 fixa "-Werror" para TODOS os componentes (tools/cmake/build.cmake), sem Kconfig
# para desligar. Duas bibliotecas do arduino-esp32 emitem avisos que viram erro fatal:
#
#   LittleFS.cpp  -> missing initializer for 'esp_vfs_littlefs_conf_t::blockdev'
#                    (o struct do littlefs ganhou um campo no IDF 6; bug upstream, nada
#                     que possamos corrigir do nosso lado)
#   ssl_client.cpp-> #warning pedindo CONFIG_MBEDTLS_PSK_MODES (resolvido no sdkconfig)
#
# Rebaixamos os dois APENAS no componente de terceiro — o nosso código e o do OnStepX
# continuam compilando com -Werror. Remover quando o arduino-esp32 corrigir upstream.
idf_component_get_property(arduino_lib espressif__arduino-esp32 COMPONENT_LIB)
if(arduino_lib)
    target_compile_options(${arduino_lib} PRIVATE
        -Wno-error=missing-field-initializers
        -Wno-error=cpp
    )
endif()
