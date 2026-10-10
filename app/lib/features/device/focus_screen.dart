import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/commands.dart';
import '../../app/link.dart';
import '../../core/format.dart';
import '../../core/strings.dart';
import '../../core/theme.dart';
import '../../core/widgets/charts.dart';
import '../../core/widgets/kit.dart';

/// O6 e D3 — Foco. A posição do focalizador, a nitidez de agora, os passos à mão e o autofoco
/// com a sua curva. O mesmo lugar serve a quem está observando e a quem veio pelo Aparelho;
/// [back] é para onde o "voltar" leva.
class FocusScreen extends ConsumerWidget {
  const FocusScreen({super.key, this.back = '/device'});

  final String back;

  static const _steps = [-100, -10, 10, 100];

  /// Nitidez em palavras, a partir do tamanho das estrelas (FWHM em pixels).
  static (String, Color) sharpness(double fwhmPx) {
    if (fwhmPx <= 0) return ('sem medida', AppColors.muted);
    if (fwhmPx < 3.5) return ('boa', AppColors.ok);
    if (fwhmPx < 6) return ('média', AppColors.gold);
    return ('ruim', AppColors.bad);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final telescope = ref.watch(telescopeProvider);
    final info = ref.watch(linkProvider.select((l) => l.info));
    final focus = telescope.focus;
    final commands = ref.read(commandsProvider);
    final focusing = telescope.state == 'FOCUSING';
    final job = telescope.job;
    final failedJob = (job != null && job.kind == 'focus' && job.failed) ? job : null;
    final fwhm = telescope.stack.fwhmPx;
    final (word, color) = sharpness(fwhm);
    // só há nitidez "de agora" quando a câmera está entregando imagem
    final live = telescope.previewing || telescope.stacking || focusing;
    final simulated = info == null || info.capabilities.focuser == 'sim';

    Future<void> move(int delta) => commands.act((api) => api.moveFocus(delta: delta));

    return SubPage(
      title: 'Foco',
      onBack: () => context.go(back),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(AppSpace.s2, 0, AppSpace.s2, 96),
        children: [
          if (simulated) ...[
            const Align(alignment: Alignment.centerLeft, child: SourceNote('focalizador simulado')),
            const SizedBox(height: AppSpace.s2),
          ],
          Panel(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('POSIÇÃO', style: AppText.label.copyWith(fontSize: 10)),
                          Text('${focus.position}', style: AppText.number.copyWith(fontSize: 26)),
                        ],
                      ),
                    ),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text('NITIDEZ AGORA', style: AppText.label.copyWith(fontSize: 10)),
                        Text(
                          live ? word : 'ligue a câmera',
                          style: AppText.number.copyWith(fontSize: 18, color: live ? color : AppColors.muted),
                        ),
                        if (live && fwhm > 0) Text('estrelas de ${Fmt.dec(fwhm)} px', style: AppText.small),
                      ],
                    ),
                  ],
                ),
                if (focus.atLimit) ...[
                  const SizedBox(height: 8),
                  const Text(
                    'Fim de curso: o focalizador não vai além daqui.',
                    style: TextStyle(color: AppColors.gold, fontSize: 13),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: AppSpace.s2),
          Row(
            children: [
              for (final step in _steps) ...[
                Expanded(
                  child: AppButton(
                    step > 0 ? '+$step' : '−${-step}',
                    expand: true,
                    onPressed: focusing ? null : () => move(step),
                  ),
                ),
                if (step != _steps.last) const SizedBox(width: 8),
              ],
            ],
          ),
          const SizedBox(height: 6),
          const Text('Passos para dentro (−) e para fora (+).', style: AppText.small),
          const SizedBox(height: AppSpace.s3),
          const SectionLabel('Autofoco'),
          Panel(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                FocusCurve(focus: focus),
                const SizedBox(height: 8),
                Text(
                  focus.best != null
                      ? 'Foco achado na posição ${focus.best}.'
                      : 'O telescópio varre o focalizador, mede as estrelas em cada posição e para no ponto '
                            'em que elas ficam menores.',
                  style: AppText.small,
                ),
              ],
            ),
          ),
          const SizedBox(height: AppSpace.s2),
          if (failedJob != null) ...[
            Notice(title: 'Não achei o foco', text: S.jobError(failedJob.error)),
            const SizedBox(height: AppSpace.s2),
          ],
          if (focusing && back == '/observe')
            // em Observar não há PARAR flutuante: o botão é daqui
            AppButton(
              'PARAR',
              icon: 'square',
              tone: ButtonTone.danger,
              big: true,
              expand: true,
              onPressed: commands.stop,
            )
          else if (focusing)
            const Row(
              children: [
                Busy(size: 16),
                SizedBox(width: 10),
                Expanded(child: Text('Varrendo o focalizador...', style: AppText.body)),
              ],
            )
          else
            AppButton(
              'Focar sozinho',
              icon: 'focus',
              tone: ButtonTone.primary,
              big: true,
              expand: true,
              onPressed: telescope.busy && !telescope.previewing ? null : commands.autofocus,
            ),
          if (!live && !focusing) ...[
            const SizedBox(height: AppSpace.s1),
            AppButton('Ligar a câmera ao vivo', icon: 'live', expand: true, onPressed: commands.preview),
          ],
        ],
      ),
    );
  }
}
