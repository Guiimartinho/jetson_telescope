import 'dart:math' as math;

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
import '../device/camera_screen.dart';
import '../device/mount_screen.dart';

Widget _failed(WidgetRef ref, Object error, VoidCallback retry) => Padding(
  padding: const EdgeInsets.all(AppSpace.s2),
  child: Notice(
    title: 'O telescópio não respondeu',
    text: error is ApiFailure ? S.failure(error) : null,
    actions: [AppButton('Tentar de novo', onPressed: retry)],
  ),
);

// -------------------------------------------------------- P2: item do plano
/// P2 — um item da fila: quantas fotos, de quanto tempo, e a altitude mínima. O horário é o
/// telescópio que calcula; aqui se vê o efeito de cada ajuste ao salvar.
class PlanItemScreen extends ConsumerStatefulWidget {
  const PlanItemScreen({super.key, required this.id});

  final String id;

  @override
  ConsumerState<PlanItemScreen> createState() => _PlanItemScreenState();
}

class _PlanItemScreenState extends ConsumerState<PlanItemScreen> {
  PlanItem? _draft;
  bool _saving = false;

  @override
  Widget build(BuildContext context) {
    final plan = ref.watch(planProvider);
    return SubPage(
      title: 'Item do plano',
      onBack: () => context.go('/plan'),
      child: plan.when(
        loading: () => const Busy(),
        error: (error, _) => _failed(ref, error, () => ref.invalidate(planProvider)),
        data: (p) {
          final saved = p.items.where((i) => i.id == widget.id).firstOrNull;
          if (saved == null) {
            return EmptyState(
              icon: 'list',
              title: 'Este item saiu do plano',
              action: AppButton('Voltar ao plano', onPressed: () => context.go('/plan')),
            );
          }
          final item = _draft ?? saved;
          final changed = _draft != null;
          final seconds = (item.rows * item.cols * (120 + item.frames * item.exposureS)).round();
          void edit(PlanItem next) => setState(() => _draft = next);
          return ListView(
            padding: const EdgeInsets.fromLTRB(AppSpace.s2, 0, AppSpace.s2, 96),
            children: [
              Text(
                saved.name.isEmpty || saved.name == saved.target ? saved.target : '${saved.target}  ${saved.name}',
                style: AppText.title,
              ),
              const SizedBox(height: 4),
              Text(
                saved.start != null && saved.end != null
                    ? 'Nesta noite: das ${Fmt.clock(saved.start!)} às ${Fmt.clock(saved.end!)}'
                          '${saved.altStartDeg == null ? '' : ', a ${Fmt.degrees(saved.altStartDeg!)} de altitude'}.'
                    : 'Fora desta noite: ${S.planStatus(saved.status)}.',
                style: AppText.small.copyWith(color: saved.fits ? AppColors.muted : AppColors.gold),
              ),
              if (saved.fits == false && saved.start != null)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(
                    'Atenção: ${S.planStatus(saved.status)}.',
                    style: const TextStyle(color: AppColors.gold, fontSize: 13, fontWeight: FontWeight.w600),
                  ),
                ),
              const SizedBox(height: AppSpace.s2),
              Panel(
                child: Column(
                  children: [
                    StepRow(
                      label: 'Fotos',
                      hint: item.isMosaic ? 'por painel do mosaico' : 'quantas empilhar',
                      value: '${item.frames}',
                      onMinus: item.frames > 10 ? () => edit(item.copyWith(frames: item.frames - 10)) : null,
                      onPlus: item.frames < 5000 ? () => edit(item.copyWith(frames: item.frames + 10)) : null,
                    ),
                    StepRow(
                      label: 'Exposição',
                      hint: 'o tempo de cada foto',
                      value: exposureLabel(item.exposureS),
                      onMinus: item.exposureS > 1
                          ? () => edit(item.copyWith(exposureS: math.max(1, nextExposure(item.exposureS, -1))))
                          : null,
                      onPlus: item.exposureS < 600
                          ? () => edit(item.copyWith(exposureS: nextExposure(item.exposureS, 1)))
                          : null,
                    ),
                    StepRow(
                      label: 'Altitude mínima',
                      hint: 'só fotografa acima disto',
                      value: Fmt.degrees(item.minAltDeg),
                      onMinus: item.minAltDeg >= 5 ? () => edit(item.copyWith(minAltDeg: item.minAltDeg - 5)) : null,
                      onPlus: item.minAltDeg <= 75 ? () => edit(item.copyWith(minAltDeg: item.minAltDeg + 5)) : null,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: AppSpace.s1),
              Text(
                'Duração: ${Fmt.duration(seconds)}'
                '${item.isMosaic ? ' (${item.rows * item.cols} painéis)' : ''}, contando apontar e focar.',
                style: AppText.small,
              ),
              const SizedBox(height: AppSpace.s2),
              AppButton(
                item.isMosaic ? 'Mosaico ${item.rows}×${item.cols}: mudar a grade' : 'Transformar em mosaico',
                icon: 'grid',
                expand: true,
                onPressed: () => context.go('/plan/mosaic/${saved.target}?item=${saved.id}'),
              ),
              const SizedBox(height: AppSpace.s3),
              AppButton(
                'Salvar',
                tone: ButtonTone.primary,
                big: true,
                expand: true,
                onPressed: !changed || _saving
                    ? null
                    : () async {
                        setState(() => _saving = true);
                        final ok = await ref.read(planEditorProvider).update(item);
                        if (!context.mounted) return;
                        setState(() => _saving = false);
                        if (ok) context.go('/plan');
                      },
              ),
              const SizedBox(height: AppSpace.s1),
              AppButton(
                'Tirar do plano',
                icon: 'trash',
                expand: true,
                onPressed: () async {
                  final ok = await ref.read(planEditorProvider).remove(saved.id);
                  if (ok && context.mounted) context.go('/plan');
                },
              ),
            ],
          );
        },
      ),
    );
  }
}

// --------------------------------------------------------------- P4: mosaico
/// P4 — Mosaico: para um alvo maior que o campo, uma grade de quadros vizinhos. Escolhe-se
/// linhas, colunas e a sobreposição, e a grade vai para o plano.
class MosaicScreen extends ConsumerStatefulWidget {
  const MosaicScreen({super.key, required this.target, this.itemId});

  final String target;

  /// O item do plano que está sendo mudado; nulo quando o mosaico é um item novo.
  final String? itemId;

  @override
  ConsumerState<MosaicScreen> createState() => _MosaicScreenState();
}

class _MosaicScreenState extends ConsumerState<MosaicScreen> {
  static const _overlaps = [(0.10, '10%'), (0.15, '15%'), (0.25, '25%')];
  int _rows = 2;
  int _cols = 2;
  double _overlap = 0.15;
  bool _saving = false;

  Future<void> _send() async {
    setState(() => _saving = true);
    final editor = ref.read(planEditorProvider);
    final existing = widget.itemId == null
        ? null
        : ref.read(planProvider).valueOrNull?.items.where((i) => i.id == widget.itemId).firstOrNull;
    final ok = existing == null
        ? await editor.add(widget.target, rows: _rows, cols: _cols, overlap: _overlap)
        : await editor.update(existing.copyWith(rows: _rows, cols: _cols, overlap: _overlap));
    if (!mounted) return;
    setState(() => _saving = false);
    if (ok) context.go('/plan');
  }

  @override
  Widget build(BuildContext context) {
    final key = (widget.target, _rows, _cols, _overlap);
    final grid = ref.watch(mosaicProvider(key));
    final night = ref.watch(planProvider).valueOrNull;
    return SubPage(
      title: 'Mosaico de ${widget.target}',
      onBack: () =>
          context.go(widget.itemId == null ? '/atlas/target/${widget.target}' : '/plan/item/${widget.itemId}'),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(AppSpace.s2, 0, AppSpace.s2, 96),
        children: [
          grid.when(
            loading: () => const SizedBox(height: 220, child: Busy()),
            error: (error, _) => _failed(ref, error, () => ref.invalidate(mosaicProvider(key))),
            data: (g) {
              final panels = g.rows * g.cols;
              // cada painel: apontar e focar (2 min) mais 40 fotos de 30 s, o padrão do plano
              final seconds = panels * (120 + 40 * 30);
              final nightS = night?.nightStart != null && night?.nightEnd != null
                  ? night!.nightEnd!.difference(night.nightStart!).inSeconds
                  : null;
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Panel(
                    child: AspectRatio(
                      aspectRatio: (g.coversDeg[0] / math.max(g.coversDeg[1], 0.01)).clamp(0.6, 2.4),
                      child: Semantics(
                        label: 'Grade do mosaico: ${g.rows} por ${g.cols} painéis',
                        child: CustomPaint(painter: _GridPainter(g)),
                      ),
                    ),
                  ),
                  const SizedBox(height: AppSpace.s1),
                  Text(
                    '$panels ${panels == 1 ? 'painel' : 'painéis'} · cobre ${Fmt.dec(g.coversDeg[0])}° × '
                    '${Fmt.dec(g.coversDeg[1])}°'
                    "${g.objectArcmin == null ? '' : " · o alvo tem ${Fmt.dec(g.objectArcmin!, 0)}'"}",
                    style: AppText.small,
                  ),
                  if (g.coversObject == false)
                    const Padding(
                      padding: EdgeInsets.only(top: 4),
                      child: Text(
                        'O alvo ainda transborda a grade: aumente as linhas ou as colunas.',
                        style: TextStyle(color: AppColors.gold, fontSize: 13, fontWeight: FontWeight.w600),
                      ),
                    ),
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text('Com 40 fotos de 30 s por painel: ${Fmt.duration(seconds)}.', style: AppText.small),
                  ),
                  if (nightS != null && seconds > nightS)
                    const Padding(
                      padding: EdgeInsets.only(top: 4),
                      child: Text(
                        'É grade demais para uma noite só: diminua os painéis ou as fotos por painel.',
                        style: TextStyle(color: AppColors.gold, fontSize: 13, fontWeight: FontWeight.w600),
                      ),
                    ),
                ],
              );
            },
          ),
          const SizedBox(height: AppSpace.s2),
          Panel(
            child: Column(
              children: [
                StepRow(
                  label: 'Linhas',
                  value: '$_rows',
                  onMinus: _rows > 1 ? () => setState(() => _rows--) : null,
                  onPlus: _rows < 6 ? () => setState(() => _rows++) : null,
                ),
                StepRow(
                  label: 'Colunas',
                  value: '$_cols',
                  onMinus: _cols > 1 ? () => setState(() => _cols--) : null,
                  onPlus: _cols < 6 ? () => setState(() => _cols++) : null,
                ),
                const SizedBox(height: 6),
                Row(
                  children: [
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Sobreposição', style: AppText.body),
                          Text('o que os vizinhos têm em comum, para costurar', style: AppText.small),
                        ],
                      ),
                    ),
                    for (final (value, label) in _overlaps) ...[
                      const SizedBox(width: 6),
                      Choice(label, selected: _overlap == value, onTap: () => setState(() => _overlap = value)),
                    ],
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: AppSpace.s3),
          AppButton(
            widget.itemId == null ? 'Mandar para o plano' : 'Usar esta grade',
            icon: 'list',
            tone: ButtonTone.primary,
            big: true,
            expand: true,
            onPressed: _saving || !grid.hasValue ? null : _send,
          ),
        ],
      ),
    );
  }
}

/// Os painéis (com a sobreposição à vista) e, por cima, o tamanho do alvo.
class _GridPainter extends CustomPainter {
  _GridPainter(this.grid);

  final MosaicGrid grid;

  @override
  void paint(Canvas canvas, Size size) {
    final (wide, tall) = (math.max(grid.coversDeg[0], 0.01), math.max(grid.coversDeg[1], 0.01));
    final scale = math.min(size.width / wide, size.height / tall);
    final origin = Offset((size.width - wide * scale) / 2, (size.height - tall * scale) / 2);
    final (fieldW, fieldH) = (grid.fieldDeg[0] * scale, grid.fieldDeg[1] * scale);
    final stepW = grid.cols > 1 ? (wide * scale - fieldW) / (grid.cols - 1) : 0.0;
    final stepH = grid.rows > 1 ? (tall * scale - fieldH) / (grid.rows - 1) : 0.0;
    final fill = Paint()..color = AppColors.accent.withValues(alpha: 0.10);
    final edge = Paint()
      ..color = AppColors.accent.withValues(alpha: 0.85)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2;
    for (var r = 0; r < grid.rows; r++) {
      for (var c = 0; c < grid.cols; c++) {
        final rect = Rect.fromLTWH(origin.dx + c * stepW, origin.dy + r * stepH, fieldW, fieldH);
        canvas.drawRect(rect, fill); // onde dois painéis se cobrem, fica mais claro
        canvas.drawRect(rect, edge);
      }
    }
    if (grid.objectArcmin case final double arcmin) {
      final diameter = arcmin / 60 * scale;
      canvas.drawOval(
        Rect.fromCenter(center: size.center(Offset.zero), width: diameter, height: diameter * 0.6),
        Paint()
          ..color = AppColors.gold.withValues(alpha: 0.9)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.6,
      );
    }
  }

  @override
  bool shouldRepaint(_GridPainter old) => old.grid != grid;
}

// ------------------------------------------------------- P5: modos especiais
/// P5 — Lua, planetas e Sol: o que está no céu agora, e apontar para lá. O Sol só depois de
/// confirmar o filtro.
class SpecialScreen extends ConsumerWidget {
  const SpecialScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bodies = ref.watch(solarProvider);
    final telescope = ref.watch(telescopeProvider);
    final info = ref.watch(linkProvider.select((l) => l.info));
    return SubPage(
      title: 'Lua, planetas e Sol',
      onBack: () => context.go('/plan'),
      child: bodies.when(
        loading: () => const Busy(),
        error: (error, _) => _failed(ref, error, () => ref.invalidate(solarProvider)),
        data: (list) => ListView(
          padding: const EdgeInsets.fromLTRB(AppSpace.s2, 0, AppSpace.s2, 96),
          children: [
            if (info != null && !info.capabilities.gotoIsReal) ...[
              const Align(alignment: Alignment.centerLeft, child: SourceNote('apontamento simulado')),
              const SizedBox(height: AppSpace.s2),
            ],
            // o que está no céu agora vem primeiro: é o que dá para apontar e fotografar
            for (final body in [...list.where((b) => b.isUp), ...list.where((b) => !b.isUp)]) ...[
              _BodyRow(body: body, enabled: !telescope.busy),
              const SizedBox(height: 8),
            ],
            const SizedBox(height: AppSpace.s1),
            const Text(
              '"Fotografar" grava um vídeo curto, com centenas de quadros rápidos, e empilha só os mais '
              'nítidos: é assim que se vence a turbulência do ar em Lua e planetas.',
              style: AppText.small,
            ),
            if (info != null && !info.capabilities.cameraIsReal)
              const Padding(
                padding: EdgeInsets.only(top: 6),
                child: Text('Com a câmera simulada, o planeta também é simulado.', style: AppText.small),
              ),
            // só aparece em telescópio que sabe rastrear (o `/info` dele diz)
            if (info != null && info.capabilities.modes.contains('tracking')) ...[
              const SizedBox(height: AppSpace.s3),
              const SectionLabel('Satélite'),
              Panel(
                child: Row(
                  children: [
                    const AppIcon('satellite', color: AppColors.muted),
                    const SizedBox(width: 14),
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Rastrear o que cruza o campo', style: AppText.body),
                          Text(
                            'O telescópio acha o objeto em cada foto e move a montagem para mantê-lo no centro.',
                            style: AppText.small,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    AppButton(
                      'Rastrear',
                      onPressed: telescope.busy
                          ? null
                          : () async {
                              if (!await pathIsClear(context, ref) || !context.mounted) return;
                              final job = await ref.read(commandsProvider).run('tracking');
                              if (job != null && context.mounted) context.go('/observe');
                            },
                    ),
                  ],
                ),
              ),
              if (!info.capabilities.cameraIsReal)
                const Padding(
                  padding: EdgeInsets.only(top: 6),
                  child: Text('Com a câmera simulada, o objeto também é simulado.', style: AppText.small),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class _BodyRow extends ConsumerWidget {
  const _BodyRow({required this.body, required this.enabled});

  final SolarBody body;
  final bool enabled;

  static String _phase(double fraction) {
    if (fraction < 0.04) return 'nova';
    if (fraction > 0.96) return 'cheia';
    return '${(fraction * 100).round()}% iluminada';
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final up = body.isUp;
    final where = up ? '${Fmt.degrees(body.altDeg)} acima do horizonte' : 'abaixo do horizonte';
    final extra = body.phase == null ? '' : ' · ${_phase(body.phase!)}';
    return Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              AppIcon(
                body.isSun ? 'sun' : (body.kind == 'moon' ? 'moon' : 'planet'),
                color: up ? AppColors.text : AppColors.dim,
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(body.name, style: AppText.heading.copyWith(fontSize: 15)),
                    const SizedBox(height: 2),
                    Text('$where$extra', style: AppText.small.copyWith(color: up ? AppColors.muted : AppColors.dim)),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpace.s1),
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              AppButton('Apontar', onPressed: up && enabled ? () => _point(context, ref) : null),
              // o Sol fica de fora da captura planetária: pede filtro e outro cuidado
              if (!body.isSun) ...[
                const SizedBox(width: 8),
                AppButton(
                  'Fotografar',
                  icon: 'camera',
                  tone: ButtonTone.primary,
                  onPressed: up && enabled ? () => _capture(context, ref) : null,
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  /// As opções da gravação e, confirmadas, a captura — que segue na tela Observar.
  Future<void> _capture(BuildContext context, WidgetRef ref) async {
    final options = await showModalBottomSheet<CaptureOptions>(
      context: context,
      backgroundColor: AppColors.surface,
      isScrollControlled: true,
      builder: (_) => CaptureSheet(body: body),
    );
    if (options == null || !context.mounted) return;
    if (options.point && (!await pathIsClear(context, ref) || !context.mounted)) return;
    final job = await ref
        .read(commandsProvider)
        .planetary(body.id, frames: options.frames, keepPercent: options.keepPercent, point: options.point);
    if (job != null && context.mounted) context.go('/observe');
  }

  Future<void> _point(BuildContext context, WidgetRef ref) async {
    var confirmed = false;
    if (body.isSun) {
      // Q5 — o Sol sem filtro destrói o sensor
      confirmed = await confirm(
        context,
        title: 'O filtro solar está na frente?',
        text: 'Apontar para o Sol sem filtro destrói o sensor — e o olho de quem espiar pelo tubo.',
        yes: 'Sim, está',
        danger: true,
      );
      if (!confirmed || !context.mounted) return;
    }
    if (!await pathIsClear(context, ref) || !context.mounted) return;
    final job = await ref.read(commandsProvider).goToBody(body.id, filterConfirmed: confirmed);
    if (job != null && context.mounted) context.go('/observe');
  }
}

/// O que a pessoa escolheu para a gravação.
class CaptureOptions {
  const CaptureOptions({this.frames = 300, this.keepPercent = 15, this.point = true});

  final int frames;
  final int keepPercent;
  final bool point;
}

/// As opções da captura planetária: quantos quadros gravar, quantos aproveitar, e se é para
/// apontar antes. Devolve [CaptureOptions] ao gravar; nada ao fechar.
class CaptureSheet extends StatefulWidget {
  const CaptureSheet({super.key, required this.body});

  final SolarBody body;

  @override
  State<CaptureSheet> createState() => _CaptureSheetState();
}

class _CaptureSheetState extends State<CaptureSheet> {
  static const _frames = [300, 600, 1200, 2400];
  static const _keeps = [5, 10, 15, 25, 50];
  int _total = 300;
  int _keep = 15;
  bool _point = true;

  @override
  Widget build(BuildContext context) {
    final kept = (_total * _keep / 100).round();
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpace.s2),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Fotografar ${widget.body.name}', style: AppText.heading),
            const SizedBox(height: AppSpace.s2),
            const Text('Quadros a gravar', style: AppText.body),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final n in _frames) Choice('$n', selected: _total == n, onTap: () => setState(() => _total = n)),
              ],
            ),
            const SizedBox(height: AppSpace.s2),
            const Text('Quanto aproveitar', style: AppText.body),
            const Text(
              'Menos quadros: imagem mais nítida, com mais ruído. Mais quadros: o contrário.',
              style: AppText.small,
            ),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final k in _keeps) Choice('$k%', selected: _keep == k, onTap: () => setState(() => _keep = k)),
              ],
            ),
            const SizedBox(height: AppSpace.s2),
            SwitchPanel(
              icon: 'reticle',
              title: 'Apontar antes',
              text: 'Desligue se o alvo já está no quadro: a montagem não se move.',
              value: _point,
              onChanged: (on) => setState(() => _point = on),
            ),
            const SizedBox(height: AppSpace.s2),
            Text('Ficam os $kept quadros mais nítidos de $_total.', style: AppText.small),
            const SizedBox(height: AppSpace.s1),
            AppButton(
              'Gravar',
              icon: 'camera',
              tone: ButtonTone.primary,
              big: true,
              expand: true,
              onPressed: () =>
                  Navigator.of(context).pop(CaptureOptions(frames: _total, keepPercent: _keep, point: _point)),
            ),
          ],
        ),
      ),
    );
  }
}
