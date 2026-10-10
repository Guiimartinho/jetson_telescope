import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/commands.dart';
import '../../app/link.dart';
import '../../core/format.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import '../device/camera_screen.dart';
import '../device/focus_screen.dart';
import '../device/mount_screen.dart';

/// O3 — Prévia e enquadramento. Com a câmera ao vivo (sem empilhar), tudo que se ajusta antes
/// de fotografar fica à mão: enquadrar (mover a montagem), focar, exposição e ganho. Daqui se
/// parte para empilhar.
class PreviewControls extends ConsumerWidget {
  const PreviewControls({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final telescope = ref.watch(telescopeProvider);
    final commands = ref.read(commandsProvider);
    final mount = telescope.mount;
    final fwhm = telescope.stack.fwhmPx;
    final (word, color) = FocusScreen.sharpness(fwhm);
    final cleared = ref.watch(pathClearedProvider);
    final canJog = mount.can('jog') && mount.parked != true;

    Widget arrow(String direction, String label, int quarterTurns) => HoldButton(
      label: label,
      size: 52,
      onHold: () => commands.act((api) => api.jog(direction, holdMs: 800), quiet: true),
      onRelease: () => commands.act((api) => api.haltMount(), quiet: true),
      child: RotatedBox(quarterTurns: quarterTurns, child: const AppIcon('arrow', size: 22)),
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Text('nitidez $word', style: AppText.number.copyWith(fontSize: 18, color: color)),
            if (fwhm > 0) ...[const SizedBox(width: 10), Text('estrelas de ${Fmt.dec(fwhm)} px', style: AppText.small)],
          ],
        ),
        if (fwhm <= 0)
          const Padding(
            padding: EdgeInsets.only(top: 4),
            child: Text(
              'Sem estrelas para medir: a imagem pode estar escura demais, estourada ou muito fora de foco.',
              style: TextStyle(color: AppColors.gold, fontSize: 13),
            ),
          ),
        const SizedBox(height: AppSpace.s2),
        const SectionLabel('Enquadrar'),
        if (!canJog)
          Text(
            mount.features.isEmpty
                ? 'Mover à mão pelo app ainda não existe nesta montagem.'
                : 'A montagem está estacionada: tire-a do repouso em Aparelho > Montagem.',
            style: AppText.small,
          )
        else if (!cleared)
          AppButton('Mover a montagem', icon: 'mount', expand: true, onPressed: () => pathIsClear(context, ref))
        else
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              arrow('W', 'Mover para o oeste', 3),
              arrow('N', 'Mover para o norte', 0),
              arrow('S', 'Mover para o sul', 2),
              arrow('E', 'Mover para o leste', 1),
            ],
          ),
        const SizedBox(height: AppSpace.s2),
        const SectionLabel('Focar'),
        Row(
          children: [
            for (final step in const [-100, -10, 10, 100]) ...[
              Expanded(
                child: AppButton(
                  step > 0 ? '+$step' : '−${-step}',
                  expand: true,
                  onPressed: () => commands.act((api) => api.moveFocus(delta: step)),
                ),
              ),
              if (step != 100) const SizedBox(width: 6),
            ],
          ],
        ),
        const SizedBox(height: 6),
        AppButton('Focar sozinho', icon: 'focus', expand: true, onPressed: () => context.go('/observe/focus')),
        const SizedBox(height: AppSpace.s2),
        const SectionLabel('Câmera'),
        const CameraControls(showOffset: false),
        if (!telescope.camera.applied)
          const Padding(
            padding: EdgeInsets.only(top: 4),
            child: Text(
              'Câmera simulada: exposição e ganho ficam guardados, mas ainda não mudam a imagem.',
              style: AppText.small,
            ),
          ),
        const SizedBox(height: AppSpace.s1),
      ],
    );
  }
}
