# Componente `main`: fica deliberadamente vazio de lógica.
#
# Com CONFIG_AUTOSTART_ARDUINO=y (ver sdkconfig.defaults), o próprio arduino-esp32 fornece
# o `app_main()`, que chama `initArduino()`, `setup()` e depois `loop()` num laço. O
# `setup()`/`loop()` reais são os do OnStepX.ino, compilados no componente `onstepx`.
# Este arquivo só existe porque o IDF exige um componente `main` no projeto.
idf_component_register(
    SRCS "main.cpp"
    INCLUDE_DIRS "."
    REQUIRES onstepx
)
