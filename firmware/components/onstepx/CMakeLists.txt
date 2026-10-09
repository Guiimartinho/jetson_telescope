# Componente que compila a árvore do OnStepX baixada em onstepx-src/.
#
# A árvore NÃO é versionada (66k linhas de terceiro): `scripts/fetch_onstepx.py` a baixa
# pinada num commit e instala o nosso Config.h nela. Se ela não existir, o registro do
# componente fica vazio e o build falha com uma mensagem clara em vez de um erro críptico
# de linker. Ver docs/35.

set(ONSTEPX_ROOT "${CMAKE_CURRENT_LIST_DIR}/onstepx-src")

if(NOT EXISTS "${ONSTEPX_ROOT}/OnStepX.ino")
    message(FATAL_ERROR
        "OnStepX nao encontrado em ${ONSTEPX_ROOT}.\n"
        "Rode primeiro:  py -3.11 firmware/scripts/fetch_onstepx.py")
endif()

if(NOT EXISTS "${ONSTEPX_ROOT}/Config.h")
    message(FATAL_ERROR
        "Config.h ausente na arvore do OnStepX (src/Common.h faz #include \"../Config.h\").\n"
        "Rode:  py -3.11 firmware/scripts/fetch_onstepx.py  (ele instala firmware/config/Config.telescope.h)")
endif()

# O .ino e um arquivo C++ comum (161 linhas: setup()/loop()); o fetch o copia como .cpp
# porque o CMake nao reconhece a extensao .ino como fonte C++.
file(GLOB_RECURSE ONSTEPX_SRCS "${ONSTEPX_ROOT}/src/*.cpp")
list(APPEND ONSTEPX_SRCS "${ONSTEPX_ROOT}/OnStepX.ino.cpp")
# Travas de pinagem verificadas APOS o pre-processador (ver config_assert.cpp). Fica no
# NOSSO lado da fronteira, entao continua sob -Werror.
list(APPEND ONSTEPX_SRCS "${CMAKE_CURRENT_LIST_DIR}/config_assert.cpp")

idf_component_register(
    SRCS ${ONSTEPX_SRCS}
    # ONSTEPX_ROOT precisa estar no include path: src/Common.h faz #include "../Config.h"
    INCLUDE_DIRS "${ONSTEPX_ROOT}" "${ONSTEPX_ROOT}/src"
    # Nome do componente GERENCIADO (o gestor de componentes prefixa o namespace):
    # managed_components/espressif__arduino-esp32/ -> "espressif__arduino-esp32".
    # Usar "arduino" falha com "Failed to resolve component 'arduino'".
    #
    # tmc2209: biblioteca Arduino EXTERNA que o OnStepX inclui (<TMC2209.h>) mas não embute.
    REQUIRES espressif__arduino-esp32 tmc2209
)

# Build de diagnostico de bancada:  idf.py -DONSTEPX_DIAG=ON build   (voltar: -DONSTEPX_DIAG=OFF)
# Liga o bloco 7 de config/Config.telescope.h (deteccao dos TMC2209 + debug verboso). Nao e
# firmware de produto — ver o comentario la.
if(ONSTEPX_DIAG)
    message(WARNING "ONSTEPX_DIAG=ON: build de DIAGNOSTICO (debug na serial do LX200). Nao deixar na placa.")
    target_compile_definitions(${COMPONENT_LIB} PRIVATE ONSTEPX_DIAG)
endif()

# -------------------------------------------------------------------------------------
# Politica de warnings para CODIGO DE TERCEIRO
# -------------------------------------------------------------------------------------
# O IDF 6 fixa "-Werror" para todos os componentes. O OnStepX e escrito para o toolchain
# do Arduino (mais permissivo) e dispara avisos que sao reais mas NAO acionaveis por nos:
#
#   StepDir.cpp  '--'/'++' em tipo volatile        (depreciado no C++20; IDF 6 usa padrao novo)
#   Arduino.h    comparison of unsigned '< 0'      (dentro do proprio header do Arduino)
#
# Em vez de cacar warning por warning num codigo que nao mantemos — ou pior, forkar as
# fontes para silencia-los — rebaixamos WARNINGS-COMO-ERRO apenas neste componente. Os
# avisos continuam aparecendo no log; so nao abortam o build.
#
# O NOSSO codigo (main/) e o do IDF seguem sob -Werror. A fronteira e explicita.
target_compile_options(${COMPONENT_LIB} PRIVATE
    -Wno-error                      # terceiro: avisa, nao aborta
    -Wno-unused-variable
    -Wno-unused-but-set-variable
    -Wno-missing-field-initializers
    -Wno-write-strings
)
