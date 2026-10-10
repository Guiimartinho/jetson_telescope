import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/commands.dart';
import '../../app/prefs.dart';
import '../../app/queries.dart';
import '../../core/errors.dart';
import '../../core/format.dart';
import '../../core/strings.dart';
import '../../core/theme.dart';
import '../../core/widgets/charts.dart';
import '../../core/widgets/kit.dart';
import '../../domain/models.dart';
import 'atlas_screen.dart';

/// A2 — Ficha do alvo: como ele fica no nosso campo, a altitude na noite que vem, o melhor
/// horário, e os dois botões: observar agora, ou só apontar.
class TargetScreen extends ConsumerWidget {
  const TargetScreen({super.key, required this.id});

  final String id;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(targetDetailProvider(id));
    final favorite = ref.watch(prefsProvider.select((p) => p.favorites.contains(id)));
    return SubPage(
      title: detail.valueOrNull?.target.name ?? id,
      onBack: () => context.go('/atlas'),
      actions: [
        IconAction(
          'star',
          label: favorite ? 'Tirar dos meus alvos' : 'Guardar nos meus alvos',
          color: favorite ? AppColors.gold : AppColors.muted,
          onPressed: () => ref.read(prefsProvider.notifier).toggleFavorite(id),
        ),
      ],
      child: detail.when(
        loading: () => const Busy(),
        error: (error, _) => Padding(
          padding: const EdgeInsets.all(AppSpace.s2),
          child: Notice(
            title: 'Não achei este alvo',
            text: error is ApiFailure ? S.failure(error) : null,
            actions: [AppButton('Voltar ao Atlas', onPressed: () => context.go('/atlas'))],
          ),
        ),
        data: (d) => _Body(detail: d),
      ),
    );
  }
}

class _Body extends ConsumerWidget {
  const _Body({required this.detail});

  final TargetDetail detail;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = detail.target;
    final commands = ref.read(commandsProvider);
    final (altText, altColor) = TargetRow.altitude(t);
    // `fills` é quanto do lado MENOR do campo o alvo ocupa. Acima da razão entre os lados, ele
    // não cabe nem deitado ao longo do lado maior: aí só com mosaico.
    final fills = detail.fills ?? 0;
    final sides = detail.fovDeg.last > 0 ? detail.fovDeg.first / detail.fovDeg.last : 1.0;
    final framing = fills > sides
        ? 'maior que o campo'
        : (fills > 0.9 ? 'cabe só ao longo do lado maior' : TargetRow.framing(t));
    Future<void> go(Future<Job?> Function() send) async {
      if (await send() != null && context.mounted) context.go('/observe');
    }

    return ListView(
      padding: const EdgeInsets.all(AppSpace.s2),
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox.square(
              dimension: 112,
              child: LazyImage(
                load: ref.watch(targetThumbProvider(t.id).future),
                placeholder: TargetRow.typeIcon(t.type),
                radius: AppSpace.radius,
              ),
            ),
            const SizedBox(width: AppSpace.s2),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(t.id, style: AppText.title),
                  if (t.catalog.isNotEmpty && t.catalog != t.id) Text(t.catalog, style: AppText.small),
                  const SizedBox(height: 6),
                  Text(S.targetType(t.type), style: AppText.body),
                  const SizedBox(height: 6),
                  StatusText(altText, color: altColor),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpace.s2),
        if (!t.isUp) ...[
          const Notice(
            bad: false,
            icon: 'info',
            title: 'Abaixo do horizonte agora',
            text: 'Veja no gráfico a que horas ele sobe.',
          ),
          const SizedBox(height: AppSpace.s2),
        ],
        const SectionLabel('Altitude nesta noite'),
        Panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              AltitudeChart(detail: detail),
              const SizedBox(height: AppSpace.s1),
              Text(
                detail.bestFrom == null
                    ? 'Nesta noite ele não passa dos 25 graus: a imagem sai ruim tão baixo.'
                    : 'Melhor: ${Fmt.clock(detail.bestFrom!)} a ${Fmt.clock(detail.bestTo!)}',
                style: AppText.body,
              ),
            ],
          ),
        ),
        const SizedBox(height: AppSpace.s2),
        const SectionLabel('No nosso campo'),
        Panel(
          child: Row(
            children: [
              SizedBox(width: 120, height: 68, child: CustomPaint(painter: _FramingPainter(detail))),
              const SizedBox(width: AppSpace.s2),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(framing, style: AppText.heading.copyWith(fontSize: 15)),
                    const SizedBox(height: 4),
                    Text(
                      'Campo de ${Fmt.dec(detail.fovDeg.first, 2)}° x ${Fmt.dec(detail.fovDeg.last, 2)}°'
                      '${t.sizeArcmin == null ? '' : "; o alvo tem ${Fmt.dec(t.sizeArcmin!, 0)}'"}',
                      style: AppText.small,
                    ),
                    if (fills > 0.9)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(
                          fills > sides
                              ? 'Para pegá-lo inteiro será preciso um mosaico.'
                              : 'Fica justo: gire a câmera para alinhá-lo, ou faça um mosaico.',
                          style: AppText.small,
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppSpace.s2),
        Panel(
          padding: const EdgeInsets.symmetric(horizontal: AppSpace.s2, vertical: 8),
          child: Column(
            children: [
              if (t.mag != null) InfoLine(icon: 'sun', label: 'Brilho', value: 'magnitude ${Fmt.dec(t.mag!)}'),
              InfoLine(icon: 'reticle', label: 'Ascensão reta', value: Fmt.ra(t.raDeg)),
              InfoLine(icon: 'reticle', label: 'Declinação', value: Fmt.dec2(t.decDeg)),
            ],
          ),
        ),
        const SizedBox(height: AppSpace.s3),
        AppButton(
          'Observar agora',
          icon: 'reticle',
          tone: ButtonTone.primary,
          big: true,
          expand: true,
          onPressed: t.isUp ? () => go(() => commands.observe(t.id)) : null,
        ),
        const SizedBox(height: AppSpace.s1),
        AppButton('Só apontar', expand: true, onPressed: t.isUp ? () => go(() => commands.goTo(t.id)) : null),
        const SizedBox(height: AppSpace.s2),
        // para depois: o alvo entra na fila da noite, inteiro ou em mosaico
        Row(
          children: [
            Expanded(
              child: AppButton(
                'Pôr no plano',
                icon: 'list',
                expand: true,
                onPressed: () => ref.read(planEditorProvider).add(t.id),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: AppButton(
                'Mosaico',
                icon: 'grid',
                expand: true,
                onPressed: () => context.go('/plan/mosaic/${t.id}'),
              ),
            ),
          ],
        ),
        const SizedBox(height: 96),
      ],
    );
  }
}

/// O retângulo do nosso sensor e, dentro (ou transbordando), o tamanho do alvo.
class _FramingPainter extends CustomPainter {
  _FramingPainter(this.detail);

  final TargetDetail detail;

  @override
  void paint(Canvas canvas, Size size) {
    final frame = Rect.fromLTWH(0, 0, size.width, size.height).deflate(1);
    canvas.clipRect(Offset.zero & size);
    canvas.drawRRect(RRect.fromRectAndRadius(frame, const Radius.circular(6)), Paint()..color = AppColors.surface2);
    final fills = detail.fills;
    if (fills != null) {
      final diameter = fills * size.height;
      canvas.drawOval(
        Rect.fromCenter(center: frame.center, width: diameter, height: diameter * 0.72),
        Paint()..color = AppColors.accent.withValues(alpha: 0.35),
      );
    }
    canvas.drawRRect(
      RRect.fromRectAndRadius(frame, const Radius.circular(6)),
      Paint()
        ..color = AppColors.muted
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.2,
    );
  }

  @override
  bool shouldRepaint(_FramingPainter old) => old.detail != detail;
}
