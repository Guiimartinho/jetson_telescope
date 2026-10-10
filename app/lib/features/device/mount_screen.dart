import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/commands.dart';
import '../../app/link.dart';
import '../../core/format.dart';
import '../../core/strings.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import '../../domain/models.dart';

/// Já se perguntou, nesta abertura do app, se o caminho da montagem está livre?
final pathClearedProvider = StateProvider<bool>((ref) => false);

/// D2 — Montagem: como ela está e, onde isso existe, mexer nela à mão. O movimento é de
/// segurar: o app renova o comando enquanto o dedo está no botão, e a montagem para sozinha
/// se as renovações pararem (soltou, ou o sinal caiu).
class MountScreen extends ConsumerWidget {
  const MountScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final telescope = ref.watch(telescopeProvider);
    final mount = telescope.mount;
    final commands = ref.read(commandsProvider);
    final parked = mount.parked == true;
    final free = telescope.mountFree;

    return SubPage(
      title: 'Montagem',
      onBack: () => context.go('/device'),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(AppSpace.s2, 0, AppSpace.s2, 96),
        children: [
          Panel(
            padding: const EdgeInsets.symmetric(horizontal: AppSpace.s2, vertical: 8),
            child: Column(
              children: [
                InfoLine(
                  icon: 'mount',
                  label: 'Ligação',
                  value: !mount.isReal ? 'simulada' : (mount.connected ? 'conectada' : 'desconectada'),
                  color: !mount.isReal ? AppColors.gold : (mount.connected ? AppColors.ok : AppColors.bad),
                ),
                if (mount.raDeg != null && mount.decDeg != null) ...[
                  InfoLine(icon: 'reticle', label: 'Ascensão reta', value: Fmt.ra(mount.raDeg!)),
                  InfoLine(icon: 'reticle', label: 'Declinação', value: Fmt.dec2(mount.decDeg!)),
                ],
                if (mount.tracking != null)
                  InfoLine(
                    icon: 'star',
                    label: 'Rastreio',
                    value: mount.tracking! ? 'acompanhando o céu' : 'parado',
                    color: mount.tracking! ? AppColors.ok : AppColors.muted,
                  ),
                if (mount.parked != null)
                  InfoLine(icon: 'lock', label: 'Repouso', value: parked ? 'estacionada' : 'solta'),
              ],
            ),
          ),
          if (mount.isReal && !mount.connected) ...[
            const SizedBox(height: AppSpace.s2),
            Notice(
              title: 'A montagem não está respondendo',
              text: mount.error ?? 'Confira o cabo USB entre o telescópio e a montagem, e a energia dela.',
            ),
          ],
          const SizedBox(height: AppSpace.s3),
          if (mount.features.isEmpty)
            const Notice(
              bad: false,
              icon: 'info',
              title: 'Mover à mão pelo app ainda não existe nesta montagem',
              text:
                  'O app já lê a montagem de verdade, mas ainda não a comanda: o movimento só é liberado '
                  'depois de validado na bancada, com a mecânica montada.',
            )
          else ...[
            if (!free) ...[
              const Notice(
                bad: false,
                icon: 'info',
                title: 'O telescópio está trabalhando',
                text: 'Pare o trabalho em andamento para mexer na montagem à mão.',
              ),
              const SizedBox(height: AppSpace.s2),
            ],
            if (mount.can('jog')) ...[
              const SectionLabel('Mover'),
              _JogPad(enabled: free && !parked),
              const SizedBox(height: AppSpace.s3),
            ],
            if (mount.can('tracking'))
              SwitchPanel(
                icon: 'star',
                title: 'Rastreio',
                text: 'Acompanha a rotação do céu. Sem ele, as estrelas escorregam pelo campo.',
                value: mount.tracking == true,
                onChanged: parked ? null : (on) => commands.act((api) => api.setTracking(on: on)),
              ),
            const SizedBox(height: AppSpace.s1),
            Row(
              children: [
                if (mount.can('park'))
                  Expanded(
                    child: AppButton(
                      parked ? 'Tirar do repouso' : 'Estacionar',
                      icon: 'lock',
                      expand: true,
                      onPressed: parked
                          ? () => commands.act((api) => api.mountAction('unpark'))
                          : (free ? () => _moving(context, ref, 'park') : null),
                    ),
                  ),
                if (mount.can('park') && mount.can('home')) const SizedBox(width: 8),
                if (mount.can('home'))
                  Expanded(
                    child: AppButton(
                      'Ir para casa',
                      icon: 'target',
                      expand: true,
                      onPressed: free && !parked ? () => _moving(context, ref, 'home') : null,
                    ),
                  ),
              ],
            ),
          ],
          const SizedBox(height: AppSpace.s3),
          const SectionLabel('Antes de fotos longas'),
          Panel(
            onTap: () => context.go('/device/mount/polar'),
            child: Row(
              children: [
                const AppIcon('target', color: AppColors.muted),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Alinhamento polar', style: AppText.heading.copyWith(fontSize: 15)),
                      const SizedBox(height: 3),
                      Text(switch (telescope.polar) {
                        final PolarState p when p.measured =>
                          p.aligned
                              ? 'alinhada: o eixo erra o polo por ${S.arcmin(p.totalArcmin)}'
                              : 'o eixo erra o polo por ${S.arcmin(p.totalArcmin)}',
                        _ => 'medir quanto o eixo da montagem erra o polo, e o que ajustar',
                      }, style: AppText.small),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                const AppIcon('chevron', size: 18, color: AppColors.muted),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// Estacionar e ir para casa movem a montagem sozinhos: antes do primeiro, a pergunta.
  Future<void> _moving(BuildContext context, WidgetRef ref, String action) async {
    if (!await pathIsClear(context, ref)) return;
    await ref.read(commandsProvider).act((api) => api.mountAction(action));
  }
}

/// Q1 — antes do primeiro movimento: "o caminho está livre?". Uma vez por abertura do app.
Future<bool> pathIsClear(BuildContext context, WidgetRef ref) async {
  if (ref.read(pathClearedProvider)) return true;
  final yes = await confirm(
    context,
    title: 'A montagem vai se mover',
    text: 'O caminho está livre? Cabos, tripé e pessoas longe do tubo.',
    yes: 'Mover',
  );
  if (yes) ref.read(pathClearedProvider.notifier).state = true;
  return yes;
}

/// O direcional: quatro botões de segurar e três velocidades.
class _JogPad extends ConsumerStatefulWidget {
  const _JogPad({required this.enabled});

  final bool enabled;

  @override
  ConsumerState<_JogPad> createState() => _JogPadState();
}

class _JogPadState extends ConsumerState<_JogPad> {
  static const _rates = [(1, 'Fina'), (2, 'Média'), (3, 'Rápida')];
  int _rate = 2;

  Widget _button(String direction, String label, int quarterTurns) {
    final cleared = ref.watch(pathClearedProvider);
    final commands = ref.read(commandsProvider);
    if (!cleared) {
      // o primeiro toque só pergunta; o movimento vem no toque seguinte, já de segurar
      return _Ask(label: label, quarterTurns: quarterTurns, enabled: widget.enabled);
    }
    return HoldButton(
      label: label,
      enabled: widget.enabled,
      // o prazo cobre duas renovações: uma perdida não dá tranco, duas param a montagem
      onHold: () => commands.act((api) => api.jog(direction, rate: _rate, holdMs: 800), quiet: true),
      onRelease: () => commands.act((api) => api.haltMount(), quiet: true),
      child: RotatedBox(quarterTurns: quarterTurns, child: const AppIcon('arrow', size: 26)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final moving = ref.watch(telescopeProvider.select((t) => t.mount.moving));
    return Column(
      children: [
        _button('N', 'Mover para o norte', 0),
        const SizedBox(height: 8),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            _button('W', 'Mover para o oeste', 3),
            SizedBox(
              width: 80,
              child: Center(
                child: Text(
                  moving == null ? 'parada' : 'movendo',
                  style: AppText.small.copyWith(color: moving == null ? AppColors.muted : AppColors.accent),
                ),
              ),
            ),
            _button('E', 'Mover para o leste', 1),
          ],
        ),
        const SizedBox(height: 8),
        _button('S', 'Mover para o sul', 2),
        const SizedBox(height: AppSpace.s2),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            for (final (rate, name) in _rates) ...[
              Choice(name, selected: _rate == rate, onTap: () => setState(() => _rate = rate)),
              if (rate != 3) const SizedBox(width: 8),
            ],
          ],
        ),
        const SizedBox(height: 6),
        const Text('Segure para mover; solte para parar.', style: AppText.small),
      ],
    );
  }
}

class _Ask extends ConsumerWidget {
  const _Ask({required this.label, required this.quarterTurns, required this.enabled});

  final String label;
  final int quarterTurns;
  final bool enabled;

  @override
  Widget build(BuildContext context, WidgetRef ref) => Opacity(
    opacity: enabled ? 1 : 0.35,
    child: Semantics(
      container: true,
      button: true,
      enabled: enabled,
      label: label,
      onTap: enabled ? () => pathIsClear(context, ref) : null,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: enabled ? () => pathIsClear(context, ref) : null,
        child: Container(
          width: 64,
          height: 64,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: AppColors.elev,
            borderRadius: BorderRadius.circular(AppSpace.radius),
            border: Border.all(color: AppColors.line),
          ),
          child: RotatedBox(quarterTurns: quarterTurns, child: const AppIcon('arrow', size: 26)),
        ),
      ),
    ),
  );
}
