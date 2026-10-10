/// Sol, Lua e planetas em baixa precisão — a mesma conta que a Jetson faz (`src/core/ephem.py`),
/// para o modo demonstração mostrar o céu de verdade sem telescópio nenhum.
///
/// Planetas e Sol: elementos keplerianos aproximados do JPL (poucos minutos de arco). Lua: a
/// série curta do Astronomical Almanac (~0,3 grau). Coordenadas em J2000.
library;

import 'dart:math' as math;

import 'models.dart';

const _obliquity = 23.43928;
const _precessionPerCentury = 1.397;

// a (UA), e, I, L, longitude do periélio, nó — valor em J2000 e variação por século
const _elements = <String, List<List<double>>>{
  'mercury': [
    [0.38709927, 0.00000037],
    [0.20563593, 0.00001906],
    [7.00497902, -0.00594749],
    [252.25032350, 149472.67411175],
    [77.45779628, 0.16047689],
    [48.33076593, -0.12534081],
  ],
  'venus': [
    [0.72333566, 0.00000390],
    [0.00677672, -0.00004107],
    [3.39467605, -0.00078890],
    [181.97909950, 58517.81538729],
    [131.60246718, 0.00268329],
    [76.67984255, -0.27769418],
  ],
  'earth': [
    [1.00000261, 0.00000562],
    [0.01671123, -0.00004392],
    [-0.00001531, -0.01294668],
    [100.46457166, 35999.37244981],
    [102.93768193, 0.32327364],
    [0.0, 0.0],
  ],
  'mars': [
    [1.52371034, 0.00001847],
    [0.09339410, 0.00007882],
    [1.84969142, -0.00813131],
    [-4.55343205, 19140.30268499],
    [-23.94362959, 0.44441088],
    [49.55953891, -0.29257343],
  ],
  'jupiter': [
    [5.20288700, -0.00011607],
    [0.04838624, -0.00013253],
    [1.30439695, -0.00183714],
    [34.39644051, 3034.74612775],
    [14.72847983, 0.21252668],
    [100.47390909, 0.20469106],
  ],
  'saturn': [
    [9.53667594, -0.00125060],
    [0.05386179, -0.00050991],
    [2.48599187, 0.00193609],
    [49.95424423, 1222.49362201],
    [92.59887831, -0.41897216],
    [113.66242448, -0.28867794],
  ],
  'uranus': [
    [19.18916464, -0.00196176],
    [0.04725744, -0.00004397],
    [0.77263783, -0.00242939],
    [313.23810451, 428.48202785],
    [170.95427630, 0.40805281],
    [74.01692503, 0.04240589],
  ],
  'neptune': [
    [30.06992276, 0.00026291],
    [0.00859048, 0.00005105],
    [1.77004347, 0.00035372],
    [-55.12002969, 218.45945325],
    [44.96476227, -0.32241464],
    [131.78422574, -0.00508664],
  ],
};

/// O que o app mostra, na ordem: (id, nome, tipo).
const solarBodies = <(String, String, String)>[
  ('moon', 'Lua', 'moon'),
  ('mercury', 'Mercúrio', 'planet'),
  ('venus', 'Vênus', 'planet'),
  ('mars', 'Marte', 'planet'),
  ('jupiter', 'Júpiter', 'planet'),
  ('saturn', 'Saturno', 'planet'),
  ('uranus', 'Urano', 'planet'),
  ('neptune', 'Netuno', 'planet'),
  ('sun', 'Sol', 'sun'),
];

double _rad(double degrees) => degrees * math.pi / 180;
double _deg(double radians) => radians * 180 / math.pi;
double _centuries(DateTime utc) => (utc.millisecondsSinceEpoch / 86400000.0 + 2440587.5 - 2451545.0) / 36525.0;

/// Posição heliocêntrica (eclíptica J2000, UA).
(double, double, double) _heliocentric(String name, double t) {
  final v = [for (final e in _elements[name]!) e[0] + e[1] * t];
  final (a, e, inc, lon, peri, node) = (v[0], v[1], v[2], v[3], v[4], v[5]);
  final w = _rad(peri - node);
  final m = _rad((lon - peri + 180) % 360 - 180);
  var ecc = m;
  for (var i = 0; i < 12; i++) {
    ecc -= (ecc - e * math.sin(ecc) - m) / (1 - e * math.cos(ecc)); // Kepler: E - e sen E = M
  }
  final x = a * (math.cos(ecc) - e);
  final y = a * math.sqrt(1 - e * e) * math.sin(ecc);
  final (o, i) = (_rad(node), _rad(inc));
  final (cw, sw, co, so, ci, si) = (math.cos(w), math.sin(w), math.cos(o), math.sin(o), math.cos(i), math.sin(i));
  return (
    (cw * co - sw * so * ci) * x + (-sw * co - cw * so * ci) * y,
    (cw * so + sw * co * ci) * x + (-sw * so + cw * co * ci) * y,
    (sw * si) * x + (cw * si) * y,
  );
}

/// Vetor eclíptico J2000 -> (RA, DEC) em graus.
(double, double) _equatorial(double x, double y, double z) {
  final eps = _rad(_obliquity);
  final ye = y * math.cos(eps) - z * math.sin(eps);
  final ze = y * math.sin(eps) + z * math.cos(eps);
  return (_deg(math.atan2(ye, x)) % 360, _deg(math.atan2(ze, math.sqrt(x * x + ye * ye))));
}

/// RA/DEC geocêntricos (J2000, graus) de um planeta, ou do Sol (`sun`).
(double, double) planetRaDec(String name, DateTime utc) {
  final t = _centuries(utc);
  final (ex, ey, ez) = _heliocentric('earth', t);
  if (name == 'sun') return _equatorial(-ex, -ey, -ez);
  final (px, py, pz) = _heliocentric(name, t);
  return _equatorial(px - ex, py - ey, pz - ez);
}

/// A Lua: RA, DEC (J2000), paralaxe horizontal (graus) e fração iluminada (0 a 1).
(double ra, double dec, double parallax, double phase) moonPosition(DateTime utc) {
  final t = _centuries(utc);
  double s(double a, double b) => math.sin(_rad(a + b * t));
  double c(double a, double b) => math.cos(_rad(a + b * t));
  var lon =
      218.32 +
      481267.881 * t +
      6.29 * s(135.0, 477198.87) -
      1.27 * s(259.3, -413335.36) +
      0.66 * s(235.7, 890534.22) +
      0.21 * s(269.9, 954397.74) -
      0.19 * s(357.5, 35999.05) -
      0.11 * s(186.5, 966404.03);
  final lat =
      5.13 * s(93.3, 483202.02) + 0.28 * s(228.2, 960400.89) - 0.28 * s(318.3, 6003.15) - 0.17 * s(217.6, -407332.21);
  final parallax =
      0.9508 +
      0.0518 * c(135.0, 477198.87) +
      0.0095 * c(259.3, -413335.36) +
      0.0078 * c(235.7, 890534.22) +
      0.0028 * c(269.9, 954397.74);
  lon -= _precessionPerCentury * t; // equinócio da data -> J2000
  final (lam, beta) = (_rad(lon), _rad(lat));
  final (ra, dec) = _equatorial(math.cos(beta) * math.cos(lam), math.cos(beta) * math.sin(lam), math.sin(beta));
  final (ex, ey, _) = _heliocentric('earth', t);
  final sunLon = math.atan2(-ey, -ex);
  final elongation = math.acos((math.cos(beta) * math.cos(lam - sunLon)).clamp(-1.0, 1.0));
  return (ra, dec, parallax, (1 - math.cos(elongation)) / 2);
}

double _altitude(double raDeg, double decDeg, double lat, double lon, DateTime utc) {
  final days = utc.millisecondsSinceEpoch / 86400000.0 + 2440587.5 - 2451545.0;
  final gmst = (280.46061837 + 360.98564736629 * days) % 360;
  final hourAngle = _rad(gmst + lon - raDeg);
  final sinAlt =
      math.sin(_rad(lat)) * math.sin(_rad(decDeg)) + math.cos(_rad(lat)) * math.cos(_rad(decDeg)) * math.cos(hourAngle);
  return _deg(math.asin(sinAlt.clamp(-1.0, 1.0)));
}

double _round(double value, int digits) {
  final scale = math.pow(10, digits);
  return (value * scale).roundToDouble() / scale;
}

/// Lua, planetas e Sol, com a altitude de agora para este observador.
List<SolarBody> solarSystem(double lat, double lon, DateTime utc) => [
  for (final (id, name, kind) in solarBodies)
    if (id == 'moon')
      () {
        final (ra, dec, parallax, phase) = moonPosition(utc);
        final geocentric = _altitude(ra, dec, lat, lon, utc);
        final seen = geocentric - parallax * math.cos(_rad(geocentric)); // vista da superfície
        return SolarBody(
          id: id,
          name: name,
          kind: kind,
          raDeg: _round(ra, 3),
          decDeg: _round(dec, 3),
          altDeg: _round(seen, 1),
          phase: _round(phase, 2),
        );
      }()
    else
      () {
        final (ra, dec) = planetRaDec(id, utc);
        return SolarBody(
          id: id,
          name: name,
          kind: kind,
          raDeg: _round(ra, 3),
          decDeg: _round(dec, 3),
          altDeg: _round(_altitude(ra, dec, lat, lon, utc), 1),
        );
      }(),
];
