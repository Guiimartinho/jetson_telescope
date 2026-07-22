// Testes C++ com doctest (header-only, leve — ideal p/ Jetson). Ver docs/10.
#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include "tele/control_math.hpp"

using namespace tele;

TEST_CASE("pointing_error e euclidiano") {
  CHECK(pointing_error(3.0, 4.0) == doctest::Approx(5.0));
  CHECK(pointing_error(0.0, 0.0) == doctest::Approx(0.0));
}

TEST_CASE("clamp satura nos limites") {
  CHECK(clamp(10.0, -2.0, 2.0) == 2.0);
  CHECK(clamp(-9.0, -2.0, 2.0) == -2.0);
  CHECK(clamp(1.0, -2.0, 2.0) == 1.0);
}

TEST_CASE("correction_step evita overshoot") {
  CHECK(correction_step(1000.0, 0.9, 50.0) == doctest::Approx(50.0));
  CHECK(correction_step(-1000.0, 0.9, 50.0) == doctest::Approx(-50.0));
  CHECK(correction_step(10.0, 0.5, 50.0) == doctest::Approx(5.0));
}

TEST_CASE("parabola_vertex recupera o minimo") {
  auto f = [](double x) { return (x - 6300.0) * (x - 6300.0); };  // vértice em 6300
  double v = parabola_vertex(5000, f(5000), 6300, f(6300), 7500, f(7500));
  REQUIRE_FALSE(std::isnan(v));
  CHECK(v == doctest::Approx(6300.0).epsilon(0.0001));
}

TEST_CASE("parabola degenerada retorna NaN") {
  CHECK(std::isnan(parabola_vertex(1, 1, 1, 1, 1, 1)));
}
