# Biblioteca Arduino TMC2209 (hjd1964/TMC2209) — dependência EXTERNA do OnStepX.
#
# O OnStepX não embute o driver dos TMC: `src/lib/axis/motor/stepDir/tmc/legacy/tmc2209/`
# faz `#include <TMC2209.h>`. No Arduino IDE você instalaria pelo Library Manager; aqui ela
# vira um componente do IDF. Baixada pinada por scripts/fetch_onstepx.py. Ver docs/35.

set(TMC_ROOT "${CMAKE_CURRENT_LIST_DIR}/tmc2209-src")

if(NOT EXISTS "${TMC_ROOT}/src/TMC2209.cpp")
    message(FATAL_ERROR
        "Biblioteca TMC2209 ausente em ${TMC_ROOT}.\n"
        "Rode:  py -3.11 firmware/scripts/fetch_onstepx.py")
endif()

idf_component_register(
    SRCS "${TMC_ROOT}/src/TMC2209.cpp"
    INCLUDE_DIRS "${TMC_ROOT}/src"
    REQUIRES espressif__arduino-esp32
)

# Biblioteca Arduino de terceiro: os avisos dela não são acionáveis para nós.
# Mesma politica do componente onstepx: biblioteca Arduino de terceiro avisa, nao aborta.
target_compile_options(${COMPONENT_LIB} PRIVATE
    -Wno-error
    -Wno-unused-variable
)
