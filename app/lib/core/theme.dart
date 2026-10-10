import 'package:flutter/material.dart';

/// As cores do produto — as mesmas do `ui_kit` das páginas da Jetson.
abstract final class AppColors {
  static const bg = Color(0xFF04060C);
  static const surface = Color(0xFF0A0F1B);
  static const surface2 = Color(0xFF0D1526);
  static const elev = Color(0x0AFFFFFF);
  static const line = Color(0x2196ACD6);
  static const text = Color(0xFFE9EEFB);
  static const muted = Color(0xFF8492B0);
  static const dim = Color(0xFF59677F);
  static const accent = Color(0xFF33DDC4);
  static const accentDeep = Color(0xFF1A9D8C);
  static const onAccent = Color(0xFF032018);
  static const gold = Color(0xFFF5B95C);
  static const violet = Color(0xFF9AA2FF);
  static const ok = Color(0xFF49D17E);
  static const bad = Color(0xFFFF5D6C);
}

/// Grade de 8 e os dois raios do produto.
abstract final class AppSpace {
  static const s1 = 8.0;
  static const s2 = 16.0;
  static const s3 = 24.0;
  static const radius = 14.0;
  static const radiusSmall = 11.0;

  /// Alvos de toque: 48 no mínimo; 64 nas ações principais (uso com uma mão, de luva).
  static const touch = 48.0;
  static const touchMain = 64.0;
}

abstract final class AppText {
  static const title = TextStyle(fontSize: 22, fontWeight: FontWeight.w700, height: 1.2);
  static const heading = TextStyle(fontSize: 16, fontWeight: FontWeight.w700, height: 1.25);
  static const body = TextStyle(fontSize: 15, height: 1.4);
  static const small = TextStyle(fontSize: 13, height: 1.35, color: AppColors.muted);

  /// Rótulo de seção: pequeno, espaçado, em maiúsculas.
  static const label = TextStyle(fontSize: 11, fontWeight: FontWeight.w600, letterSpacing: 1.4, color: AppColors.muted);

  /// Números de telemetria: algarismos de largura fixa, para não "dançarem" ao mudar.
  static const number = TextStyle(
    fontSize: 15,
    fontWeight: FontWeight.w600,
    fontFeatures: [FontFeature.tabularFigures()],
  );
}

ThemeData buildTheme() {
  const scheme = ColorScheme.dark(
    surface: AppColors.surface,
    primary: AppColors.accent,
    onPrimary: AppColors.onAccent,
    secondary: AppColors.gold,
    onSecondary: AppColors.bg,
    error: AppColors.bad,
    onSurface: AppColors.text,
    outline: AppColors.line,
  );
  final base = ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    colorScheme: scheme,
    scaffoldBackgroundColor: AppColors.bg,
    canvasColor: AppColors.bg,
    splashFactory: NoSplash.splashFactory, // sem clarões
    highlightColor: Colors.transparent,
    dividerColor: AppColors.line,
  );
  return base.copyWith(
    textTheme: base.textTheme.apply(bodyColor: AppColors.text, displayColor: AppColors.text),
    pageTransitionsTheme: const PageTransitionsTheme(
      builders: {
        TargetPlatform.android: FadeUpwardsPageTransitionsBuilder(),
        TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
        TargetPlatform.windows: FadeUpwardsPageTransitionsBuilder(),
      },
    ),
    sliderTheme: const SliderThemeData(
      activeTrackColor: AppColors.accent,
      inactiveTrackColor: AppColors.line,
      thumbColor: AppColors.accent,
      overlayColor: Color(0x2233DDC4),
      trackHeight: 3,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.elev,
      hintStyle: const TextStyle(color: AppColors.dim),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppSpace.radiusSmall),
        borderSide: const BorderSide(color: AppColors.line),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppSpace.radiusSmall),
        borderSide: const BorderSide(color: AppColors.line),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppSpace.radiusSmall),
        borderSide: const BorderSide(color: AppColors.accent),
      ),
    ),
  );
}

/// Modo vermelho: o app inteiro em tons de vermelho escuro, para não estragar a visão noturna.
/// Leva a luminância de cada ponto para o canal vermelho, já com o brilho reduzido.
const ColorFilter redModeFilter = ColorFilter.matrix(<double>[
  0.254, 0.499, 0.097, 0, 0, //
  0, 0, 0, 0, 0, //
  0, 0, 0, 0, 0, //
  0, 0, 0, 1, 0, //
]);
