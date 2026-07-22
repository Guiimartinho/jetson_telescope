cmake_minimum_required(VERSION 3.16)
project(tele_cpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)   # p/ o clangd achar os headers

# CMake 4 removeu compat com subprojetos de CMake < 3.5 (ex.: doctest 2.4.11).
set(CMAKE_POLICY_VERSION_MINIMUM 3.5 CACHE STRING "compat subprojetos antigos")

# doctest — framework de testes header-only, leve (ideal p/ Jetson).
include(FetchContent)
FetchContent_Declare(
  doctest
  GIT_REPOSITORY https://github.com/doctest/doctest.git
  GIT_TAG v2.4.11
)
FetchContent_MakeAvailable(doctest)

enable_testing()

add_executable(tele_tests tests/test_control_math.cpp)
target_include_directories(tele_tests PRIVATE include)
target_link_libraries(tele_tests PRIVATE doctest::doctest)

# MinGW: linkar o runtime estaticamente para o exe rodar sem DLLs externas.
if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
  target_link_options(tele_tests PRIVATE -static -static-libgcc -static-libstdc++)
endif()

add_test(NAME tele_tests COMMAND tele_tests)
