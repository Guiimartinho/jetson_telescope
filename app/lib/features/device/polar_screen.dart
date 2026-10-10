import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/commands.dart';
import '../../app/link.dart';
import '../../core/strings.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import '../../domain/models.dart';
import 'mount_screen.dart';

/// Alinhamento polar: quanto o eixo da montagem erra o polo celeste, e para que lado girar
/// cada parafuso. O telescópio mede reconhecendo o céu em três posições; a pessoa ajusta e
/// mede de novo, até o erro ficar pequeno.
///
/// Hoje isso existe com a montagem SIMULADA (e a tela diz). Com a de verdade, muda só de onde
/// vêm os três campos; os parafusos, aí, são os da montagem.
class PolarScreen extends ConsumerWidget {
  const PolarScreen({super.key});

  /// Um passo dos parafusos de mentira, em minutos de arco.
  static const screwStep = 10.0;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final telescope = ref.watch(telescopeProvider);
    final mount = telescope.mount;
    final polar = telescope.polar;
    final job = telescope.job;
    final commands = ref.read(commandsProvider);
    final measuring = telescope.measuringPolar;
    final failed = job != null && job.kind == 'polar' && job.failed;
    // a medida que vale mostrar: a última que terminou
    final result = (polar != null && polar.measured && !measuring) ? polar : null;

    Future<void> measure() async {
      if (!await pathIsClear(context, ref)) return;
      await commands.measurePolar();
    }

    Future<void> turn(double alt, double az) => commands.act((api) => api.adjustPolar(altArcmin: alt, azArcmin: az));

    return SubPage(
      title: 'Alinhamento polar',
      onBack: () => context.go('/device/mount'),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(AppSpace.s2, 0, AppSpace.s2, 96),
        children: [
          const Text(
            'Para fotos longas sem arrasto, o eixo da montagem tem de apontar para o polo celeste. '
            'O telescópio mede o erro reconhecendo o céu em três posições e diz para que lado girar '
            'cada parafuso.',
            style: AppText.small,
          ),
          const SizedBox(height: AppSpace.s2),
          if (!mount.can('polar'))
            const Notice(
              bad: false,
              icon: 'info',
              title: 'Ainda não existe nesta montagem',
              text:
                  'A medida gira a montagem sozinha, e mover a montagem de verdade pelo app só é '
                  'liberado depois de testado na bancada.',
            )
          else ...[
            const Align(alignment: Alignment.centerLeft, child: SourceNote('montagem simulada')),
            const SizedBox(height: AppSpace.s2),
            if (measuring) ...[
              Panel(
                child: Row(
                  children: [
                    const Busy(),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Medindo: campo ${(polar?.step ?? 0).clamp(1, polar?.points ?? 3)} de ${polar?.points ?? 3}',
                            style: AppText.heading.copyWith(fontSize: 15),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            telescope.state == 'SOLVING' ? 'Reconhecendo o céu.' : 'Girando a ascensão reta.',
                            style: AppText.small,
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ] else if (failed) ...[
              Notice(
                title: 'Não deu para medir',
                text: S.jobError(job.error),
                actions: [AppButton('Medir de novo', tone: ButtonTone.primary, onPressed: measure)],
              ),
            ] else if (result != null) ...[
              _Result(polar: result),
              const SizedBox(height: AppSpace.s2),
              AppButton(
                'Medir de novo',
                icon: 'reticle',
                tone: ButtonTone.primary,
                big: true,
                expand: true,
                onPressed: telescope.busy ? null : measure,
              ),
              const SizedBox(height: AppSpace.s3),
              const SectionLabel('Parafusos da montagem simulada'),
              const Text(
                'Na montagem de verdade é você quem gira os parafusos. Aqui dá para girá-los pela tela, '
                'para ver o ciclo: medir, ajustar, medir de novo.',
                style: AppText.small,
              ),
              const SizedBox(height: AppSpace.s1),
              Panel(
                padding: const EdgeInsets.symmetric(horizontal: AppSpace.s2, vertical: 6),
                child: Column(
                  children: [
                    StepRow(
                      label: 'Altitude',
                      hint: 'menos baixa o eixo, mais sobe',
                      value: "${screwStep.round()}'",
                      onMinus: telescope.busy ? null : () => turn(-screwStep, 0),
                      onPlus: telescope.busy ? null : () => turn(screwStep, 0),
                    ),
                    StepRow(
                      label: 'Azimute',
                      hint: 'menos gira para oeste, mais para leste',
                      value: "${screwStep.round()}'",
                      onMinus: telescope.busy ? null : () => turn(0, -screwStep),
                      onPlus: telescope.busy ? null : () => turn(0, screwStep),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: AppSpace.s1),
              AppButton(
                'Girar o que a medida pediu',
                expand: true,
                onPressed: telescope.busy || result.stale ? null : () => turn(-result.altArcmin, -result.azArcmin),
              ),
            ] else ...[
              AppButton(
                'Medir o alinhamento',
                icon: 'reticle',
                tone: ButtonTone.primary,
                big: true,
                expand: true,
                onPressed: telescope.busy ? null : measure,
              ),
              const Padding(
                padding: EdgeInsets.only(top: 6),
                child: Text('Leva três campos: a montagem gira sozinha entre eles.', style: AppText.small),
              ),
            ],
          ],
        ],
      ),
    );
  }
}

/// A medida: o erro total e, para cada parafuso, de que lado o eixo está e quanto girar.
class _Result extends StatelessWidget {
  const _Result({required this.polar});

  final PolarState polar;

  @override
  Widget build(BuildContext context) {
    final color = polar.aligned ? AppColors.ok : AppColors.gold;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('O EIXO ERRA O POLO POR', style: AppText.label.copyWith(fontSize: 11)),
              const SizedBox(height: 4),
              Text(S.arcmin(polar.totalArcmin), style: AppText.title.copyWith(color: color, fontSize: 30)),
              const SizedBox(height: 4),
              StatusText(polar.aligned ? 'alinhado: dá para fotografar' : 'falta ajustar', color: color),
            ],
          ),
        ),
        const SizedBox(height: 8),
        _Screw(
          name: 'Altitude',
          error: polar.altArcmin,
          where: polar.altArcmin > 0 ? 'o eixo está alto demais' : 'o eixo está baixo demais',
          fix: polar.altArcmin > 0 ? 'Baixe' : 'Suba',
        ),
        const SizedBox(height: 8),
        _Screw(
          name: 'Azimute',
          error: polar.azArcmin,
          where: polar.azArcmin > 0 ? 'o eixo está a leste do polo' : 'o eixo está a oeste do polo',
          fix: polar.azArcmin > 0 ? 'Gire para oeste' : 'Gire para leste',
        ),
        if (polar.stale) ...[
          const SizedBox(height: 8),
          const Notice(
            bad: false,
            icon: 'info',
            title: 'Você mexeu nos parafusos',
            text: 'Esta medida é de antes do ajuste. Meça de novo para conferir.',
          ),
        ],
      ],
    );
  }
}

class _Screw extends StatelessWidget {
  const _Screw({required this.name, required this.error, required this.where, required this.fix});

  final String name;
  final double error;
  final String where;
  final String fix;

  @override
  Widget build(BuildContext context) {
    // abaixo de meio minuto de arco não há o que girar: é o ruído da própria medida
    final inPlace = error.abs() < 0.5;
    return Panel(
      child: Row(
        children: [
          AppIcon(inPlace ? 'check' : 'sliders', color: inPlace ? AppColors.ok : AppColors.muted),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name, style: AppText.heading.copyWith(fontSize: 15)),
                const SizedBox(height: 2),
                Text(inPlace ? 'no lugar' : where, style: AppText.small),
              ],
            ),
          ),
          if (!inPlace) Text('$fix ${S.arcmin(error)}', style: AppText.number.copyWith(fontSize: 15)),
        ],
      ),
    );
  }
}
