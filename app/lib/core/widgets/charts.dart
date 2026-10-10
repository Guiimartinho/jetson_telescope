import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../domain/models.dart';
import '../format.dart';
import '../theme.dart';

/// A altitude do alvo ao longo da noite, com a linha dos 25 graus (abaixo dela a atmosfera
/// estraga a imagem) e a melhor janela destacada.
class AltitudeChart extends StatelessWidget {
  const AltitudeChart({super.key, required this.detail, this.height = 150});

  final TargetDetail detail;
  final double height;

  @override
  Widget build(BuildContext context) {
    final night = detail.night;
    if (night.length < 2) {
      return SizedBox(
        height: height,
        child: const Center(child: Text('Sem noite nas próximas 24 horas.', style: AppText.small)),
      );
    }
    final labels = [night.first.utc, night[night.length ~/ 2].utc, night.last.utc];
    return Semantics(
      label: 'Altitude do alvo durante a noite',
      child: Column(
        children: [
          SizedBox(
            height: height,
            width: double.infinity,
            // o rótulo dentro do desenho usa a mesma fonte do resto do app
            child: CustomPaint(painter: _AltitudePainter(detail, DefaultTextStyle.of(context).style)),
          ),
          const SizedBox(height: 4),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [for (final t in labels) Text(Fmt.clock(t), style: AppText.small.copyWith(fontSize: 11))],
          ),
        ],
      ),
    );
  }
}

class _AltitudePainter extends CustomPainter {
  _AltitudePainter(this.detail, this.textStyle);

  final TargetDetail detail;
  final TextStyle textStyle;
  static const _floor = 25.0;

  @override
  void paint(Canvas canvas, Size size) {
    final night = detail.night;
    final top = math.max(60.0, night.map((p) => p.altDeg).reduce(math.max) + 8);
    const bottom = -10.0;
    final start = night.first.utc.millisecondsSinceEpoch;
    final span = math.max(1, night.last.utc.millisecondsSinceEpoch - start);
    double x(DateTime t) => (t.millisecondsSinceEpoch - start) / span * size.width;
    double y(double alt) => size.height - (alt.clamp(bottom, top) - bottom) / (top - bottom) * size.height;

    // a melhor janela, como faixa ao fundo
    if (detail.bestFrom != null && detail.bestTo != null) {
      canvas.drawRect(
        Rect.fromLTRB(x(detail.bestFrom!), 0, x(detail.bestTo!), size.height),
        Paint()..color = const Color(0x1433DDC4),
      );
    }
    final grid = Paint()
      ..color = AppColors.line
      ..strokeWidth = 1;
    canvas.drawLine(Offset(0, y(0)), Offset(size.width, y(0)), grid); // o horizonte
    final floor = Paint()
      ..color = AppColors.gold.withValues(alpha: 0.7)
      ..strokeWidth = 1;
    for (var dx = 0.0; dx < size.width; dx += 9) {
      canvas.drawLine(Offset(dx, y(_floor)), Offset(math.min(dx + 5, size.width), y(_floor)), floor);
    }
    final path = Path()..moveTo(x(night.first.utc), y(night.first.altDeg));
    for (final p in night.skip(1)) {
      path.lineTo(x(p.utc), y(p.altDeg));
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = AppColors.accent
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.2
        ..strokeJoin = StrokeJoin.round,
    );
    final label = TextPainter(
      text: TextSpan(
        text: '25°',
        style: textStyle.copyWith(color: AppColors.gold.withValues(alpha: 0.9), fontSize: 10, height: 1),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    label.paint(canvas, Offset(size.width - label.width - 2, y(_floor) - label.height - 1));
  }

  @override
  bool shouldRepaint(_AltitudePainter old) => old.detail != detail;
}

/// A curva do autofoco: o tamanho das estrelas em cada posição do focalizador. O foco é o
/// fundo do "V". Mostra onde o focalizador está agora e onde o autofoco achou o foco.
class FocusCurve extends StatelessWidget {
  const FocusCurve({super.key, required this.focus, this.height = 150});

  final FocusState focus;
  final double height;

  @override
  Widget build(BuildContext context) {
    final measured = focus.curve.where((p) => p.fwhmPx != null).length;
    return Semantics(
      label: 'Curva de foco',
      child: SizedBox(
        height: height,
        width: double.infinity,
        child: focus.curve.isEmpty
            ? const Center(
                child: Text(
                  'A curva aparece aqui quando o autofoco rodar.',
                  textAlign: TextAlign.center,
                  style: AppText.small,
                ),
              )
            : CustomPaint(
                painter: _FocusPainter(focus, DefaultTextStyle.of(context).style),
                child: measured == 0
                    ? const Center(child: Text('Nenhuma estrela para medir.', style: AppText.small))
                    : null,
              ),
      ),
    );
  }
}

class _FocusPainter extends CustomPainter {
  _FocusPainter(this.focus, this.textStyle);

  final FocusState focus;
  final TextStyle textStyle;

  @override
  void paint(Canvas canvas, Size size) {
    final curve = focus.curve;
    final positions = [...curve.map((p) => p.position), focus.position];
    final lo = positions.reduce(math.min).toDouble();
    final hi = math.max(positions.reduce(math.max).toDouble(), lo + 1);
    final sizes = [for (final p in curve) ?p.fwhmPx];
    final top = sizes.isEmpty ? 10.0 : sizes.reduce(math.max) * 1.15;
    double x(num position) => 6 + (position - lo) / (hi - lo) * (size.width - 12);
    double y(double fwhm) => size.height - 6 - (fwhm / top).clamp(0.0, 1.0) * (size.height - 16);

    canvas.drawLine(
      Offset(0, size.height - 6),
      Offset(size.width, size.height - 6),
      Paint()
        ..color = AppColors.line
        ..strokeWidth = 1,
    );
    if (focus.best case final int best) {
      canvas.drawLine(
        Offset(x(best), 0),
        Offset(x(best), size.height - 6),
        Paint()
          ..color = AppColors.ok.withValues(alpha: 0.7)
          ..strokeWidth = 1.5,
      );
    }
    final line = Paint()
      ..color = AppColors.accent
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..strokeJoin = StrokeJoin.round;
    final dot = Paint()..color = AppColors.accent;
    final ordered = [...curve]..sort((a, b) => a.position.compareTo(b.position));
    Path? path;
    for (final p in ordered) {
      final fwhm = p.fwhmPx;
      if (fwhm == null) {
        // sem estrela para medir: um traço no alto, não um zero inventado
        canvas.drawLine(Offset(x(p.position) - 4, 6), Offset(x(p.position) + 4, 6), Paint()..color = AppColors.gold);
        path = null;
        continue;
      }
      final point = Offset(x(p.position), y(fwhm));
      if (path == null) {
        path = Path()..moveTo(point.dx, point.dy);
      } else {
        path.lineTo(point.dx, point.dy);
        canvas.drawPath(path, line);
      }
      canvas.drawCircle(point, 3, dot);
    }
    // onde o focalizador está agora
    canvas.drawCircle(Offset(x(focus.position), size.height - 6), 5, Paint()..color = AppColors.text);
  }

  @override
  bool shouldRepaint(_FocusPainter old) => old.focus != focus;
}

/// Histograma de luminância (barras). Para o modo Pro.
class HistogramBars extends StatelessWidget {
  const HistogramBars(this.bins, {super.key, this.height = 64});

  final List<double> bins;
  final double height;

  @override
  Widget build(BuildContext context) => Semantics(
    label: 'Histograma da imagem',
    child: SizedBox(
      height: height,
      width: double.infinity,
      child: CustomPaint(painter: _HistogramPainter(bins)),
    ),
  );
}

class _HistogramPainter extends CustomPainter {
  _HistogramPainter(this.bins);

  final List<double> bins;

  @override
  void paint(Canvas canvas, Size size) {
    if (bins.isEmpty) return;
    final width = size.width / bins.length;
    final paint = Paint()..color = AppColors.violet;
    for (var i = 0; i < bins.length; i++) {
      final h = bins[i].clamp(0.0, 1.0) * size.height;
      canvas.drawRect(Rect.fromLTWH(i * width, size.height - h, math.max(1, width - 1), h), paint);
    }
  }

  @override
  bool shouldRepaint(_HistogramPainter old) => old.bins != bins;
}
