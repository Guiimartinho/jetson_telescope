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
import '../device/mount_screen.dart';

String typeIcon(String type) => switch (type) {
  'galaxy' => 'galaxy',
  'cluster' => 'cluster',
  _ => 'nebula',
};

/// Planejar — a fila da noite (P1) e, quando ela está rodando, a noite em andamento (P3).
class PlanScreen extends ConsumerStatefulWidget {
  const PlanScreen({super.key});

  @override
  ConsumerState<PlanScreen> createState() => _PlanScreenState();
}

class _PlanScreenState extends ConsumerState<PlanScreen> {
  /// A noite cujo resumo a pessoa já viu e fechou.
  String? _dismissed;

  @override
  Widget build(BuildContext context) {
    final telescope = ref.watch(telescopeProvider);
    final job = telescope.job;
    // a noite rodando, ou a que acabou e ainda não foi vista
    if (job != null && job.kind == 'plan' && telescope.night.isNotEmpty && job.id != _dismissed) {
      return _Night(telescope: telescope, onClose: () => setState(() => _dismissed = job.id));
    }
    return const _Queue();
  }
}

// ---------------------------------------------------------------- P1: a fila
class _Queue extends ConsumerWidget {
  const _Queue();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final plan = ref.watch(planProvider);
    final telescope = ref.watch(telescopeProvider);
    final info = ref.watch(linkProvider.select((l) => l.info));
    final editor = ref.read(planEditorProvider);
    return plan.when(
      loading: () => const Busy(),
      error: (error, _) => Padding(
        padding: const EdgeInsets.all(AppSpace.s2),
        child: Notice(
          title: 'Não consegui ler o plano',
          text: error is ApiFailure ? S.failure(error) : null,
          actions: [AppButton('Tentar de novo', onPressed: () => ref.invalidate(planProvider))],
        ),
      ),
      data: (p) => ListView(
        padding: const EdgeInsets.fromLTRB(AppSpace.s2, AppSpace.s2, AppSpace.s2, 96),
        children: [
          const Text('Plano da noite', style: AppText.title),
          const SizedBox(height: 4),
          Text(_nightText(p), style: AppText.small),
          const SizedBox(height: AppSpace.s2),
          if (p.items.isEmpty)
            Panel(
              child: EmptyState(
                icon: 'list',
                title: 'O plano está vazio',
                text:
                    'Escolha os alvos no Atlas e toque em "Pôr no plano". O telescópio faz um depois do outro, '
                    'a noite inteira, sozinho.',
                action: AppButton('Escolher no Atlas', icon: 'atlas', onPressed: () => context.go('/atlas')),
              ),
            )
          else ...[
            for (final (n, item) in p.items.indexed) ...[
              _QueueRow(
                number: n + 1,
                item: item,
                onUp: n == 0 ? null : () => editor.move(item.id, -1),
                onDown: n == p.items.length - 1 ? null : () => editor.move(item.id, 1),
              ),
              const SizedBox(height: 8),
            ],
            if (p.nightStart != null)
              Padding(
                padding: const EdgeInsets.only(top: 4, bottom: AppSpace.s2),
                child: Text(
                  'O plano ocupa ${Fmt.duration(p.totalS)}; sobram ${Fmt.duration(p.freeS)} de noite.',
                  style: AppText.small,
                ),
              ),
            if (info != null && !info.capabilities.cameraIsReal) ...[
              const Align(
                alignment: Alignment.centerLeft,
                child: SourceNote('câmera simulada: as fotos saem mais rápido que numa noite real'),
              ),
              const SizedBox(height: AppSpace.s2),
            ],
            AppButton(
              'Começar a noite',
              icon: 'play',
              tone: ButtonTone.primary,
              big: true,
              expand: true,
              onPressed: telescope.busy ? null : () => _start(context, ref),
            ),
            if (telescope.busy)
              const Padding(
                padding: EdgeInsets.only(top: 6),
                child: Text('O telescópio está ocupado: pare o trabalho atual primeiro.', style: AppText.small),
              ),
            const SizedBox(height: AppSpace.s1),
            AppButton('Adicionar alvo', icon: 'plus', expand: true, onPressed: () => context.go('/atlas')),
          ],
          const SizedBox(height: AppSpace.s3),
          const SectionLabel('Modos especiais'),
          Panel(
            onTap: () => context.go('/plan/special'),
            child: const Row(
              children: [
                AppIcon('planet', color: AppColors.muted),
                SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Lua, planetas e Sol', style: AppText.body),
                      Text('O que está no céu agora, e apontar para lá.', style: AppText.small),
                    ],
                  ),
                ),
                AppIcon('chevron', size: 18, color: AppColors.muted),
              ],
            ),
          ),
        ],
      ),
    );
  }

  static String _nightText(NightPlan p) {
    final (start, end) = (p.nightStart, p.nightEnd);
    if (start == null || end == null) return 'Sem noite escura nas próximas 24 horas neste local.';
    return 'Escuro das ${Fmt.clock(start)} às ${Fmt.clock(end)}. Os alvos rodam na ordem da lista.';
  }

  Future<void> _start(BuildContext context, WidgetRef ref) async {
    if (!await pathIsClear(context, ref)) return;
    await ref.read(commandsProvider).startNight();
  }
}

class _QueueRow extends ConsumerWidget {
  const _QueueRow({required this.number, required this.item, this.onUp, this.onDown});

  final int number;
  final PlanItem item;
  final VoidCallback? onUp;
  final VoidCallback? onDown;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final (start, end) = (item.start, item.end);
    final when = start != null && end != null ? '${Fmt.clock(start)} – ${Fmt.clock(end)}' : 'fora desta noite';
    final shots = item.isMosaic
        ? 'mosaico ${item.rows}×${item.cols}, ${item.frames} fotos por painel'
        : '${item.frames} fotos de ${Fmt.dec(item.exposureS, 0)} s';
    return Panel(
      onTap: () => context.go('/plan/item/${item.id}'),
      padding: const EdgeInsets.fromLTRB(AppSpace.s2, 10, 4, 10),
      child: Row(
        children: [
          SizedBox(
            width: 22,
            child: Text('$number', style: AppText.number.copyWith(color: AppColors.muted)),
          ),
          AppIcon(typeIcon(item.type), color: AppColors.muted),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.name.isEmpty || item.name == item.target ? item.target : '${item.target}  ${item.name}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: AppText.heading.copyWith(fontSize: 15),
                ),
                const SizedBox(height: 2),
                Text('$when · $shots', maxLines: 2, overflow: TextOverflow.ellipsis, style: AppText.small),
                if (!item.fits)
                  Text(
                    S.planStatus(item.status),
                    style: const TextStyle(color: AppColors.gold, fontSize: 13, fontWeight: FontWeight.w600),
                  ),
              ],
            ),
          ),
          Opacity(
            opacity: onUp == null ? 0.25 : 1,
            child: IconAction('arrow', label: 'Subir ${item.target} na fila', onPressed: onUp, size: 18),
          ),
          Opacity(
            opacity: onDown == null ? 0.25 : 1,
            child: RotatedBox(
              quarterTurns: 2,
              child: IconAction('arrow', label: 'Descer ${item.target} na fila', onPressed: onDown, size: 18),
            ),
          ),
        ],
      ),
    );
  }
}

// ------------------------------------------------- P3: a noite em andamento
class _Night extends ConsumerWidget {
  const _Night({required this.telescope, required this.onClose});

  final TelescopeState telescope;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final running = telescope.nightRunning;
    final commands = ref.read(commandsProvider);
    final night = telescope.night;
    final done = night.where((n) => n.status == 'done').length;
    final current = night.where((n) => n.status == 'running').firstOrNull;
    return ListView(
      padding: const EdgeInsets.fromLTRB(AppSpace.s2, AppSpace.s2, AppSpace.s2, 96),
      children: [
        Text(running ? 'Noite em andamento' : 'A noite terminou', style: AppText.title),
        const SizedBox(height: 4),
        Text(
          running
              ? '${S.activity(telescope.state)}${current == null ? '' : ' · ${current.target}'}'
              : '$done de ${night.length} alvos fotografados.',
          style: AppText.small,
        ),
        const SizedBox(height: AppSpace.s2),
        for (final item in night) ...[_NightRow(item: item), const SizedBox(height: 8)],
        const SizedBox(height: AppSpace.s1),
        if (running) ...[
          // parar a noite é o PARAR flutuante, o mesmo de todas as telas: aqui não se repete
          const Text('Para encerrar a noite, toque em PARAR.', style: AppText.small),
          const SizedBox(height: AppSpace.s1),
          AppButton(
            'Pular este alvo',
            expand: true,
            onPressed: current == null ? null : () => commands.act((api) => api.skipPlanItem()),
          ),
          const SizedBox(height: AppSpace.s1),
          AppButton('Ver a imagem ao vivo', icon: 'live', expand: true, onPressed: () => context.go('/observe')),
        ] else ...[
          AppButton('Ver na galeria', tone: ButtonTone.primary, expand: true, onPressed: () => context.go('/gallery')),
          const SizedBox(height: AppSpace.s1),
          AppButton('Fechar', expand: true, onPressed: onClose),
        ],
      ],
    );
  }
}

class _NightRow extends StatelessWidget {
  const _NightRow({required this.item});

  final NightItem item;

  @override
  Widget build(BuildContext context) {
    final (Widget mark, Color color) = switch (item.status) {
      'done' => (const AppIcon('check', size: 18, color: AppColors.ok), AppColors.ok),
      'running' => (const Busy(size: 14), AppColors.accent),
      'failed' => (const AppIcon('close', size: 18, color: AppColors.bad), AppColors.bad),
      'skipped' => (const AppIcon('chevron', size: 18, color: AppColors.gold), AppColors.gold),
      'stopped' => (const AppIcon('square', size: 16, color: AppColors.muted), AppColors.muted),
      _ => (const AppIcon('clock', size: 18, color: AppColors.dim), AppColors.muted),
    };
    return Panel(
      child: Row(
        children: [
          SizedBox.square(dimension: 22, child: Center(child: mark)),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(item.target, style: AppText.heading.copyWith(fontSize: 15)),
                const SizedBox(height: 2),
                Text(S.nightStatus(item.status, item.reason), style: AppText.small.copyWith(color: color)),
              ],
            ),
          ),
          if (item.accepted > 0) Text('${item.accepted} fotos', style: AppText.number),
        ],
      ),
    );
  }
}
