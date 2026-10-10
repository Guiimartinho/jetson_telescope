import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/commands.dart';
import '../../app/link.dart';
import '../../app/prefs.dart';
import '../../app/queries.dart';
import '../../core/format.dart';
import '../../core/strings.dart';
import '../../core/theme.dart';
import '../../core/widgets/charts.dart';
import '../../core/widgets/kit.dart';
import '../../domain/models.dart';
import 'live_preview.dart';
import 'preview_controls.dart';

/// Observar — onde o app abre. Uma tela, vários momentos:
///
///   * O1  parado: saúde do aparelho, alvo sugerido, continuar a última sessão;
///   * O2  indo para o alvo: prévia ao vivo e as etapas, uma a uma;
///   * O4  empilhando: a imagem crescendo, fotos, qualidade; o modo Pro abre os números;
///   * O7  fim: o que foi feito e o que fazer agora;
///   * a variação de Lua e planetas: os quadros chegando e quantos estão sendo aproveitados;
///   * O8  deitado: a imagem ocupa a tela e os controles vão para a direita.
///
/// O PARAR é sempre o botão maior, e nunca pede confirmação.
class ObserveScreen extends ConsumerStatefulWidget {
  const ObserveScreen({super.key});

  @override
  ConsumerState<ObserveScreen> createState() => _ObserveScreenState();
}

class _ObserveScreenState extends ConsumerState<ObserveScreen> {
  /// O trabalho cujo resultado a pessoa já viu e fechou: a tela volta ao início.
  String? _dismissed;

  @override
  Widget build(BuildContext context) {
    final telescope = ref.watch(telescopeProvider);
    final job = telescope.job;
    final showWork = telescope.busy || (job != null && job.id != _dismissed);
    if (!showWork) return const _Home();
    final controls = _Work(telescope: telescope, onClose: () => setState(() => _dismissed = job?.id));
    return OrientationBuilder(
      builder: (context, orientation) => orientation == Orientation.landscape
          ? Row(
              children: [
                const Expanded(child: LivePreview()),
                SizedBox(width: 320, child: SingleChildScrollView(child: controls)),
              ],
            )
          : Column(
              children: [
                const Expanded(child: LivePreview()),
                ConstrainedBox(
                  constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.5),
                  child: SingleChildScrollView(child: controls),
                ),
              ],
            ),
    );
  }
}

// ------------------------------------------------------------------ O1: parado
class _Home extends ConsumerWidget {
  const _Home();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final link = ref.watch(linkProvider);
    final telescope = ref.watch(telescopeProvider);
    final info = link.info;
    final suggestion = ref.watch(suggestedTargetProvider);
    final sessions = ref.watch(sessionsProvider);
    final mount = telescope.mount;
    final disk = telescope.system.diskFreeGb;
    return ListView(
      padding: const EdgeInsets.all(AppSpace.s2),
      children: [
        const Text('Pronto para observar', style: AppText.title),
        const SizedBox(height: AppSpace.s2),
        if (info != null && !info.clockSynced && !link.demo) ...[
          Notice(
            bad: false,
            icon: 'clock',
            title: 'O telescópio ainda não sabe a hora e o local',
            text: 'Sem isso ele não sabe o que está acima do horizonte. Leva um toque.',
            actions: [AppButton('Enviar agora', tone: ButtonTone.primary, onPressed: () => context.go('/device/site'))],
          ),
          const SizedBox(height: AppSpace.s2),
        ],
        // C8, no primeiro uso: quem pareou pelo WiFi do telescópio pode querer deixá-lo no de casa
        if (ref.watch(prefsProvider.select((p) => p.offerHomeWifi)) && !link.demo) ...[
          Notice(
            bad: false,
            icon: 'wifi',
            title: 'Quer pôr o telescópio no WiFi de casa?',
            text:
                'Ele está no WiFi próprio, que não tem internet. Em casa é mais prático deixá-lo no '
                'roteador: o celular não precisa trocar de rede para falar com ele.',
            actions: [
              AppButton('Configurar', tone: ButtonTone.primary, onPressed: () => context.go('/device/network/home')),
              AppButton('Agora não', onPressed: () => ref.read(prefsProvider.notifier).setOfferHomeWifi(false)),
            ],
          ),
          const SizedBox(height: AppSpace.s2),
        ],
        if (mount.isReal && !mount.connected) ...[
          Notice(
            title: 'A montagem não está respondendo',
            text: mount.error ?? 'Confira o cabo USB entre o telescópio e a montagem, e a energia dela.',
          ),
          const SizedBox(height: AppSpace.s2),
        ],
        if (disk != null && disk < 5) ...[
          Notice(
            bad: false,
            title: 'Pouco espaço no telescópio',
            text: 'Restam ${Fmt.dec(disk)} GB. Apague sessões antigas antes de uma noite longa.',
          ),
          const SizedBox(height: AppSpace.s2),
        ],
        _Health(telescope: telescope, info: info),
        const SizedBox(height: AppSpace.s3),
        const SectionLabel('Bom para agora'),
        suggestion.when(
          loading: () => const Panel(child: SizedBox(height: 96, child: Busy())),
          error: (_, _) => const Panel(child: Text('Não consegui consultar o catálogo agora.', style: AppText.small)),
          data: (target) => target == null
              ? Panel(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Nada alto no céu que caiba no campo agora.', style: AppText.body),
                      const SizedBox(height: AppSpace.s1),
                      AppButton('Ver o Atlas', icon: 'atlas', onPressed: () => context.go('/atlas')),
                    ],
                  ),
                )
              : _Suggested(target: target),
        ),
        const SizedBox(height: AppSpace.s1),
        AppButton('Câmera ao vivo', icon: 'live', expand: true, onPressed: () => ref.read(commandsProvider).preview()),
        const Padding(
          padding: EdgeInsets.only(top: 4),
          child: Text('Para enquadrar e focar à mão, sem empilhar.', style: AppText.small),
        ),
        const SizedBox(height: AppSpace.s3),
        if (sessions.valueOrNull?.firstOrNull case final Session last) ...[
          const SectionLabel('Continuar'),
          Panel(
            onTap: () => context.go('/gallery/${last.id}'),
            child: Row(
              children: [
                SizedBox.square(
                  dimension: 52,
                  child: LazyImage(load: ref.watch(sessionThumbProvider(last.id).future), placeholder: 'album'),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(last.target, maxLines: 1, overflow: TextOverflow.ellipsis, style: AppText.heading),
                      const SizedBox(height: 2),
                      Text(
                        '${last.frames} fotos'
                        '${last.integrationS == null ? '' : ' · ${Fmt.duration(last.integrationS!)} integrados'}',
                        style: AppText.small,
                      ),
                    ],
                  ),
                ),
                const AppIcon('chevron', size: 18, color: AppColors.muted),
              ],
            ),
          ),
        ],
        const SizedBox(height: AppSpace.s3),
      ],
    );
  }
}

/// Saúde do aparelho em uma olhada. O que é simulado está escrito, não disfarçado.
class _Health extends StatelessWidget {
  const _Health({required this.telescope, required this.info});

  final TelescopeState telescope;
  final TelescopeInfo? info;

  @override
  Widget build(BuildContext context) {
    final mount = telescope.mount;
    final camera = telescope.camera;
    final system = telescope.system;
    return Panel(
      padding: const EdgeInsets.symmetric(horizontal: AppSpace.s2, vertical: 8),
      child: Column(
        children: [
          InfoLine(
            icon: 'mount',
            label: 'Montagem',
            value: !mount.isReal ? 'simulada' : (mount.connected ? 'conectada' : 'desconectada'),
            color: !mount.isReal ? AppColors.gold : (mount.connected ? AppColors.ok : AppColors.bad),
          ),
          InfoLine(
            icon: 'camera',
            label: 'Câmera',
            value: camera.isReal ? (camera.connected ? 'conectada' : 'desconectada') : 'simulada',
            color: camera.isReal ? (camera.connected ? AppColors.ok : AppColors.bad) : AppColors.gold,
          ),
          InfoLine(
            icon: 'chip',
            label: 'Processamento',
            value: telescope.backend.isEmpty ? '—' : (telescope.usesGpu ? 'GPU' : 'CPU'),
            color: telescope.usesGpu ? AppColors.ok : AppColors.muted,
          ),
          if (system.tempC != null)
            InfoLine(icon: 'thermo', label: 'Temperatura', value: '${Fmt.dec(system.tempC!, 0)} °C'),
          if (system.diskFreeGb != null)
            InfoLine(icon: 'disk', label: 'Espaço livre', value: '${Fmt.dec(system.diskFreeGb!, 0)} GB'),
        ],
      ),
    );
  }
}

class _Suggested extends ConsumerWidget {
  const _Suggested({required this.target});

  final Target target;

  @override
  Widget build(BuildContext context, WidgetRef ref) => Panel(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            SizedBox.square(
              dimension: 72,
              child: LazyImage(
                load: ref.watch(targetThumbProvider(target.id).future),
                placeholder: _typeIcon(target.type),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${target.id}  ${target.name == target.id ? '' : target.name}'.trim(),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: AppText.heading,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${S.targetType(target.type)} · alto agora (${Fmt.degrees(target.altDeg)})',
                    style: AppText.small,
                  ),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpace.s2),
        AppButton(
          'Observar este alvo',
          icon: 'reticle',
          tone: ButtonTone.primary,
          big: true,
          expand: true,
          onPressed: () => ref.read(commandsProvider).observe(target.id),
        ),
        const SizedBox(height: AppSpace.s1),
        AppButton('Ver a ficha', expand: true, onPressed: () => context.go('/atlas/target/${target.id}')),
      ],
    ),
  );
}

String _typeIcon(String type) => switch (type) {
  'galaxy' => 'galaxy',
  'cluster' => 'cluster',
  _ => 'nebula',
};

// ------------------------------------------------- O2, O4 e O7: com trabalho
class _Work extends ConsumerWidget {
  const _Work({required this.telescope, required this.onClose});

  final TelescopeState telescope;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final job = telescope.job;
    final pro = ref.watch(prefsProvider.select((p) => p.proMode));
    final info = ref.watch(linkProvider.select((l) => l.info));
    final commands = ref.read(commandsProvider);
    final open = telescope.busy;
    final stacking = telescope.stacking;
    final previewing = telescope.previewing;
    final activity = S.activity(telescope.state);
    final title = (job?.target?.isNotEmpty ?? false)
        ? job!.target!
        : (stacking
              ? 'Empilhando'
              : (previewing ? 'Câmera ao vivo' : '${activity[0].toUpperCase()}${activity.substring(1)}'));
    return Padding(
      padding: const EdgeInsets.all(AppSpace.s2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(title, maxLines: 1, overflow: TextOverflow.ellipsis, style: AppText.title),
              ),
              if (info != null && !info.capabilities.cameraIsReal) const SourceNote('câmera simulada'),
            ],
          ),
          const SizedBox(height: AppSpace.s1),
          if (telescope.planetary && telescope.capture != null)
            _CaptureNumbers(capture: telescope.capture!, stacking: stacking)
          else if (stacking || telescope.stack.accepted > 0)
            _StackNumbers(telescope: telescope, pro: pro),
          // O3: com a câmera ao vivo, o que se ajusta antes de fotografar. Os dois botões que
          // decidem (empilhar, parar) ficam em cima: os ajustes são longos, e o PARAR não pode
          // depender de rolar a tela.
          if (previewing) ...[
            Row(
              children: [
                Expanded(
                  child: AppButton(
                    'Empilhar',
                    icon: 'layers',
                    tone: ButtonTone.primary,
                    big: true,
                    expand: true,
                    onPressed: () => commands.stack(exposureS: telescope.camera.exposureS, gain: telescope.camera.gain),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: AppButton(
                    'PARAR',
                    icon: 'square',
                    tone: ButtonTone.danger,
                    big: true,
                    expand: true,
                    onPressed: commands.stop,
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpace.s2),
            const PreviewControls(),
          ],
          if (job != null && job.steps.isNotEmpty && !(stacking && !pro && !telescope.planetary) && !previewing) ...[
            const SizedBox(height: 4),
            _Steps(job: job),
          ],
          if (job != null && job.kind != 'stack' && telescope.pointing.unit == 'arcmin' && !stacking)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                "Erro de apontamento: ${Fmt.dec(telescope.pointing.error, 2)}'"
                '${info != null && !info.capabilities.gotoIsReal ? '  (apontamento simulado)' : ''}',
                style: AppText.small,
              ),
            ),
          const SizedBox(height: AppSpace.s2),
          if (open && !previewing)
            AppButton(
              'PARAR',
              icon: 'square',
              tone: ButtonTone.danger,
              big: true,
              expand: true,
              onPressed: commands.stop,
            )
          else if (!open && job != null)
            _Outcome(job: job, telescope: telescope, onClose: onClose),
        ],
      ),
    );
  }
}

/// "42 fotos · nitidez boa". No modo Pro, os números do ofício e o histograma.
class _StackNumbers extends ConsumerWidget {
  const _StackNumbers({required this.telescope, required this.pro});

  final TelescopeState telescope;
  final bool pro;

  /// Nitidez em palavras, a partir do tamanho das estrelas (FWHM em pixels).
  static (String, Color) sharpness(double fwhmPx) {
    if (fwhmPx <= 0) return ('—', AppColors.muted);
    if (fwhmPx < 3.5) return ('boa', AppColors.ok);
    if (fwhmPx < 6) return ('média', AppColors.gold);
    return ('ruim', AppColors.bad);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final stack = telescope.stack;
    final (word, color) = sharpness(stack.fwhmPx);
    final total = stack.accepted + stack.rejected;
    // muitas rejeições seguidas: nuvem passando, vento, ou o foco foi embora
    final manyRejected = total >= 10 && stack.rejected / total > 0.4;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: AppSpace.s2,
          runSpacing: 4,
          children: [
            Text('${stack.accepted} fotos', style: AppText.number.copyWith(fontSize: 18)),
            if (stack.integrationS != null)
              Text(Fmt.duration(stack.integrationS!), style: AppText.number.copyWith(fontSize: 18)),
            Text('nitidez $word', style: AppText.number.copyWith(fontSize: 18, color: color)),
          ],
        ),
        if (manyRejected)
          const Padding(
            padding: EdgeInsets.only(top: 6),
            child: Text(
              'Muitas fotos rejeitadas: pode ser nuvem passando, vento ou o foco.',
              style: TextStyle(color: AppColors.gold, fontSize: 13),
            ),
          ),
        if (pro) ...[
          const SizedBox(height: AppSpace.s1),
          Row(
            children: [
              _Metric('SNR', Fmt.dec(stack.snr)),
              _Metric('FWHM', '${Fmt.dec(stack.fwhmPx)} px'),
              _Metric('Aceitas', '${stack.accepted}'),
              _Metric('Rejeitadas', '${stack.rejected}'),
            ],
          ),
          const SizedBox(height: AppSpace.s1),
          ref
              .watch(histogramProvider(stack.accepted ~/ 5))
              .maybeWhen(data: (bins) => HistogramBars(bins), orElse: () => const SizedBox(height: 64)),
        ],
      ],
    );
  }
}

/// A variação de Lua e planetas: quantos quadros já chegaram e quantos estão sendo aproveitados.
class _CaptureNumbers extends StatelessWidget {
  const _CaptureNumbers({required this.capture, required this.stacking});

  final CaptureState capture;
  final bool stacking;

  @override
  Widget build(BuildContext context) {
    final percent = (capture.keep * 100).round();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          capture.done || stacking
              ? '${capture.kept} quadros aproveitados'
              : '${capture.frames} de ${capture.total} quadros',
          style: AppText.number.copyWith(fontSize: 18),
        ),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(3),
          child: LinearProgressIndicator(
            value: capture.done ? 1 : capture.progress,
            minHeight: 6,
            color: AppColors.accent,
            backgroundColor: AppColors.elev,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          capture.done
              ? 'Os $percent% mais nítidos de ${capture.total}, empilhados.'
              : (stacking
                    ? 'Empilhando os ${capture.kept} mais nítidos.'
                    : 'Ficando com os ${capture.kept} mais nítidos até agora ($percent% do total).'),
          style: AppText.small,
        ),
      ],
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Expanded(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label.toUpperCase(), style: AppText.label.copyWith(fontSize: 10)),
        const SizedBox(height: 2),
        Text(value, style: AppText.number),
      ],
    ),
  );
}

/// As etapas do trabalho, pelo nome, com a que está em curso destacada.
class _Steps extends StatelessWidget {
  const _Steps({required this.job});

  final Job job;

  @override
  Widget build(BuildContext context) {
    // o laço de apontamento repete "apontar, reconhecer": mostra só a última volta
    final steps = job.steps.length > 4 ? job.steps.sublist(job.steps.length - 4) : job.steps;
    return Column(
      children: [
        for (final step in steps)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              children: [
                SizedBox.square(
                  dimension: 20,
                  child: switch (step.state) {
                    'done' => const AppIcon('check', size: 18, color: AppColors.ok),
                    'failed' => const AppIcon('close', size: 18, color: AppColors.bad),
                    'stopped' => const AppIcon('square', size: 16, color: AppColors.muted),
                    _ => const Busy(size: 14),
                  },
                ),
                const SizedBox(width: 10),
                Expanded(child: Text(S.step(step.name), style: AppText.body)),
                Text(
                  S.stepState(step.state),
                  style: AppText.small.copyWith(
                    color: switch (step.state) {
                      'running' => AppColors.accent,
                      'failed' => AppColors.bad,
                      _ => AppColors.muted,
                    },
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

/// O7 — o trabalho terminou: o que aconteceu e o que fazer agora.
class _Outcome extends ConsumerWidget {
  const _Outcome({required this.job, required this.telescope, required this.onClose});

  final Job job;
  final TelescopeState telescope;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final commands = ref.read(commandsProvider);
    final close = AppButton('Fechar', onPressed: onClose);
    final target = job.target;
    if (job.kind == 'polar') {
      // o alinhamento polar tem a própria tela, com a medida e o que girar
      final see = AppButton(
        'Ver o alinhamento',
        tone: ButtonTone.primary,
        onPressed: () => context.go('/device/mount/polar'),
      );
      return job.failed
          ? Notice(title: 'Não deu para medir', text: S.jobError(job.error), actions: [see, close])
          : Notice(
              bad: false,
              icon: job.state == 'done' ? 'check' : 'info',
              title: job.state == 'done' ? 'Alinhamento polar medido' : 'Medida interrompida',
              actions: [see, close],
            );
    }
    final capture = telescope.capture;
    if (job.kind == 'planetary' && capture != null && capture.done) {
      return Notice(
        bad: false,
        icon: 'check',
        title: 'Captura pronta: ${capture.kept} de ${capture.total} quadros',
        text: 'Os mais nítidos foram alinhados, empilhados e aguçados. O resultado fica guardado no telescópio.',
        actions: [
          AppButton(
            'Gravar de novo',
            tone: ButtonTone.primary,
            onPressed: () => commands.planetary(
              capture.body,
              frames: capture.total,
              keepPercent: (capture.keep * 100).round(),
              point: false, // o alvo já está no quadro
            ),
          ),
          close,
        ],
      );
    }
    if (job.failed) {
      return Notice(
        title: 'Não deu certo',
        text: S.jobError(job.error),
        actions: [
          if (target != null && !target.contains(','))
            AppButton(
              'Tentar de novo',
              tone: ButtonTone.primary,
              onPressed: () => job.kind == 'goto' ? commands.goTo(target) : commands.observe(target),
            ),
          AppButton('Escolher outro alvo', onPressed: () => context.go('/atlas')),
          close,
        ],
      );
    }
    final photos = telescope.stack.accepted;
    if (photos > 0) {
      return Notice(
        bad: false,
        icon: 'check',
        title: 'Sessão encerrada: $photos fotos',
        text: 'O resultado fica guardado no telescópio.',
        actions: [
          AppButton('Ver na galeria', tone: ButtonTone.primary, onPressed: () => context.go('/gallery')),
          AppButton('Empilhar mais', onPressed: commands.stack),
          close,
        ],
      );
    }
    if (job.kind == 'goto' && job.state == 'done') {
      return Notice(
        bad: false,
        icon: 'check',
        title: 'Alvo centralizado',
        actions: [
          AppButton('Empilhar', icon: 'layers', tone: ButtonTone.primary, onPressed: commands.stack),
          close,
        ],
      );
    }
    return Notice(bad: false, icon: 'info', title: 'Parado', actions: [close]);
  }
}
