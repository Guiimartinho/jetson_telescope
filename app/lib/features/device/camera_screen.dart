import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/commands.dart';
import '../../app/link.dart';
import '../../app/queries.dart';
import '../../core/errors.dart';
import '../../core/format.dart';
import '../../core/strings.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import '../../domain/models.dart';

/// As exposições que fazem sentido oferecer, em segundos (de planeta a céu profundo).
const exposureSteps = <double>[0.001, 0.01, 0.1, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 180, 300, 600];

String exposureLabel(double seconds) => seconds < 1
    ? '${Fmt.dec(seconds * 1000, 0)} ms'
    : '${Fmt.dec(seconds, seconds == seconds.roundToDouble() ? 0 : 1)} s';

/// O degrau da lista mais próximo, e o vizinho para cima ou para baixo.
double nextExposure(double now, int direction) {
  var index = 0;
  for (var i = 0; i < exposureSteps.length; i++) {
    if ((exposureSteps[i] - now).abs() < (exposureSteps[index] - now).abs()) index = i;
  }
  return exposureSteps[(index + direction).clamp(0, exposureSteps.length - 1)];
}

/// Os ajustes da câmera, para usar em D4 e na tela de enquadrar (O3).
class CameraControls extends ConsumerWidget {
  const CameraControls({super.key, this.showOffset = true});

  final bool showOffset;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final camera = ref.watch(telescopeProvider.select((t) => t.camera));
    final limits = ref.watch(cameraProvider).valueOrNull?.limits ?? const {};
    final commands = ref.read(commandsProvider);
    final (gainLo, gainHi) = limits['gain'] ?? (0.0, 600.0);
    final (offsetLo, offsetHi) = limits['offset'] ?? (0.0, 255.0);
    final (expLo, expHi) = limits['exposure_s'] ?? (0.001, 600.0);

    void set({double? exposureS, int? gain, int? offset}) =>
        commands.act((api) => api.setCamera(exposureS: exposureS, gain: gain, offset: offset));

    final shorter = nextExposure(camera.exposureS, -1);
    final longer = nextExposure(camera.exposureS, 1);
    return Column(
      children: [
        StepRow(
          label: 'Exposição',
          hint: 'o tempo de cada foto',
          value: exposureLabel(camera.exposureS),
          onMinus: shorter < camera.exposureS && shorter >= expLo ? () => set(exposureS: shorter) : null,
          onPlus: longer > camera.exposureS && longer <= expHi ? () => set(exposureS: longer) : null,
        ),
        StepRow(
          label: 'Ganho',
          hint: 'mais ganho, mais sinal e mais ruído',
          value: '${camera.gain}',
          onMinus: camera.gain - 10 >= gainLo ? () => set(gain: camera.gain - 10) : null,
          onPlus: camera.gain + 10 <= gainHi ? () => set(gain: camera.gain + 10) : null,
        ),
        if (showOffset)
          StepRow(
            label: 'Offset',
            hint: 'o piso do sensor, para o preto não cortar',
            value: '${camera.offset}',
            onMinus: camera.offset - 1 >= offsetLo ? () => set(offset: camera.offset - 1) : null,
            onPlus: camera.offset + 1 <= offsetHi ? () => set(offset: camera.offset + 1) : null,
          ),
      ],
    );
  }
}

/// D4 — Câmera: modelo, exposição, ganho, offset, temperatura.
class CameraScreen extends ConsumerWidget {
  const CameraScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final camera = ref.watch(telescopeProvider.select((t) => t.camera));
    final info = ref.watch(cameraProvider);
    return SubPage(
      title: 'Câmera',
      onBack: () => context.go('/device'),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(AppSpace.s2, 0, AppSpace.s2, 96),
        children: [
          if (info.hasError) ...[
            Notice(
              title: 'A câmera não respondeu',
              text: info.error is ApiFailure ? S.failure(info.error! as ApiFailure) : null,
              actions: [AppButton('Tentar de novo', onPressed: () => ref.invalidate(cameraProvider))],
            ),
            const SizedBox(height: AppSpace.s2),
          ],
          Panel(
            padding: const EdgeInsets.symmetric(horizontal: AppSpace.s2, vertical: 8),
            child: Column(
              children: [
                InfoLine(
                  icon: 'camera',
                  label: 'Câmera',
                  value: camera.isReal ? (camera.connected ? 'conectada' : 'desconectada') : 'simulada',
                  color: camera.isReal ? (camera.connected ? AppColors.ok : AppColors.bad) : AppColors.gold,
                ),
                if (camera.model.isNotEmpty) InfoLine(icon: 'info', label: 'Modelo', value: camera.model),
                InfoLine(
                  icon: 'thermo',
                  label: 'Temperatura do sensor',
                  value: camera.tempC == null ? 'sem leitura' : '${Fmt.dec(camera.tempC!)} °C',
                ),
              ],
            ),
          ),
          const SizedBox(height: AppSpace.s3),
          const SectionLabel('Ajustes'),
          const Panel(child: CameraControls()),
          if (!camera.applied) ...[
            const SizedBox(height: AppSpace.s2),
            const Notice(
              bad: false,
              icon: 'info',
              title: 'Câmera simulada',
              text:
                  'Os ajustes ficam guardados no telescópio, mas ainda não mudam a imagem: quem a desenha é o '
                  'simulador. Com a câmera de verdade, passam a valer.',
            ),
          ],
        ],
      ),
    );
  }
}

/// Para outras telas dizerem quanto dura uma captura.
String captureSummary(CameraState camera) => '${exposureLabel(camera.exposureS)} · ganho ${camera.gain}';
