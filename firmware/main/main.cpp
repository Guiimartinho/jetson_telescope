// Ponto de entrada do projeto IDF.
//
// Com CONFIG_AUTOSTART_ARDUINO=y o arduino-esp32 já provê `app_main()` e chama
// `setup()`/`loop()` — que são os do OnStepX.ino. Este arquivo existe para (a) satisfazer
// a exigência do IDF de um componente `main` com pelo menos uma fonte, e (b) travar em
// tempo de COMPILAÇÃO as premissas que, se quebradas, só apareceriam como um telescópio
// que não se move. Falhar aqui é muito mais barato que depurar no campo. Ver docs/35.

#include "sdkconfig.h"

#if !defined(CONFIG_AUTOSTART_ARDUINO)
#error "CONFIG_AUTOSTART_ARDUINO precisa estar ligado: e o arduino-esp32 que chama setup()/loop() do OnStepX."
#endif

#if !defined(CONFIG_IDF_TARGET_ESP32)
#error "Alvo errado: a FYSETC E4 usa um ESP32-WROOM-32E (target 'esp32'), nao uma variante S/C/H/P."
#endif

// Nada mais: o firmware inteiro vive no componente `onstepx`.
