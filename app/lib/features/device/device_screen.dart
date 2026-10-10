import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/link.dart';
import '../../core/format.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';

/// D1 — Aparelho: cada parte com o seu estado em uma linha. O que tem problema sobe para o topo.
class DeviceScreen extends ConsumerWidget {
  const DeviceScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final link = ref.watch(linkProvider);
    final telescope = ref.watch(telescopeProvider);
    final info = link.info;
    final mount = telescope.mount;
    final mountBroken = mount.isReal && !mount.connected;
    final synced = info?.clockSynced ?? false;

    final rows = <(bool, Widget)>[
      (
        mountBroken,
        _Row(
          icon: 'mount',
          title: 'Montagem',
          state: !mount.isReal ? 'simulada' : (mount.connected ? 'conectada' : 'desconectada'),
          color: !mount.isReal ? AppColors.gold : (mount.connected ? AppColors.ok : AppColors.bad),
          detail: mountBroken
              ? (mount.error ?? 'sem resposta')
              : (mount.raDeg != null && mount.decDeg != null
                    ? 'RA ${Fmt.ra(mount.raDeg!)}   DEC ${Fmt.dec2(mount.decDeg!)}'
                    : (mount.parked == true ? 'estacionada' : null)),
          onTap: () => context.go('/device/mount'),
        ),
      ),
      (
        false,
        _Row(
          icon: 'camera',
          title: 'Câmera',
          state: telescope.camera.isReal ? (telescope.camera.connected ? 'conectada' : 'desconectada') : 'simulada',
          color: telescope.camera.isReal ? AppColors.ok : AppColors.gold,
          detail: telescope.camera.isReal ? null : 'as imagens ao vivo vêm do simulador',
          onTap: () => context.go('/device/camera'),
        ),
      ),
      (
        false,
        _Row(
          icon: 'focus',
          title: 'Foco',
          state: info != null && info.capabilities.focuser != 'sim' ? 'conectado' : 'simulado',
          color: info != null && info.capabilities.focuser != 'sim' ? AppColors.ok : AppColors.gold,
          detail: telescope.focusPos > 0 ? 'posição ${telescope.focusPos}' : null,
          onTap: () => context.go('/device/focus'),
        ),
      ),
      (
        !synced && !link.demo,
        _Row(
          icon: 'pin',
          title: 'Local e hora',
          state: synced ? 'enviados' : 'faltam enviar',
          color: synced ? AppColors.ok : AppColors.gold,
          detail: info == null ? null : '${Fmt.dec(info.site.lat, 2)}°, ${Fmt.dec(info.site.lon, 2)}°',
          onTap: () => context.go('/device/site'),
        ),
      ),
      (
        false,
        _Row(
          icon: 'lock',
          title: 'Ligação',
          state: link.demo ? 'demonstração' : (link.online ? 'protegida' : 'sem sinal'),
          color: link.demo ? AppColors.gold : (link.online ? AppColors.ok : AppColors.bad),
          detail: link.demo ? 'sem aparelho' : '${link.device?.host ?? ''} · canal cifrado, só este telescópio',
          onTap: () => context.go('/device/network'),
        ),
      ),
      (
        false,
        _Row(
          icon: 'phone',
          title: 'Celulares pareados',
          state: '',
          color: AppColors.muted,
          detail: 'quem pode usar o telescópio, e convidar mais um',
          onTap: () => context.go('/device/phones'),
        ),
      ),
      (
        false,
        _Row(
          icon: 'chip',
          title: 'Sistema',
          state: telescope.system.tempC == null ? '' : '${Fmt.dec(telescope.system.tempC!, 0)} °C',
          color: AppColors.muted,
          detail: telescope.system.diskFreeGb == null ? null : '${Fmt.dec(telescope.system.diskFreeGb!, 0)} GB livres',
          onTap: () => context.go('/device/system'),
        ),
      ),
      (
        false,
        _Row(
          icon: 'sliders',
          title: 'Preferências do app',
          state: '',
          color: AppColors.muted,
          detail: 'modo vermelho, modo Pro, vibração',
          onTap: () => context.go('/device/prefs'),
        ),
      ),
      (
        false,
        _Row(
          icon: 'download',
          title: 'Atualizações',
          state: '',
          color: AppColors.muted,
          detail: 'as versões de cada parte, e atualizar o telescópio',
          onTap: () => context.go('/device/updates'),
        ),
      ),
      (
        false,
        _Row(
          icon: 'info',
          title: 'Ajuda e sobre',
          state: '',
          color: AppColors.muted,
          detail: 'uma noite passo a passo, as palavras, as licenças',
          onTap: () => context.go('/device/about'),
        ),
      ),
    ]..sort((a, b) => (b.$1 ? 1 : 0) - (a.$1 ? 1 : 0));

    return ListView(
      padding: const EdgeInsets.fromLTRB(AppSpace.s2, AppSpace.s2, AppSpace.s2, 96),
      children: [
        Row(
          children: [
            Expanded(child: Text(link.name, style: AppText.title)),
            if (!link.demo)
              IconAction('keyboard', label: 'Mudar o nome do telescópio', onPressed: () => context.go('/device/name')),
          ],
        ),
        if (info != null) Text('${info.id} · versão ${info.software}', style: AppText.small),
        const SizedBox(height: AppSpace.s2),
        for (final (_, row) in rows) ...[row, const SizedBox(height: 8)],
        const SizedBox(height: AppSpace.s2),
        AppButton(
          link.demo ? 'Sair da demonstração' : 'Esquecer este telescópio',
          expand: true,
          onPressed: () => link.demo ? ref.read(linkProvider.notifier).forget() : _confirmForget(context, ref),
        ),
      ],
    );
  }

  Future<void> _confirmForget(BuildContext context, WidgetRef ref) async {
    final yes = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text('Esquecer este telescópio?'),
        content: const Text('Para usá-lo de novo será preciso ler o código de pareamento outra vez.'),
        actions: [
          AppButton('Manter', onPressed: () => Navigator.of(context).pop(false)),
          AppButton('Esquecer', tone: ButtonTone.danger, onPressed: () => Navigator.of(context).pop(true)),
        ],
      ),
    );
    if (yes == true) await ref.read(linkProvider.notifier).forget();
  }
}

class _Row extends StatelessWidget {
  const _Row({
    required this.icon,
    required this.title,
    required this.state,
    required this.color,
    this.detail,
    this.onTap,
  });

  final String icon;
  final String title;
  final String state;
  final Color color;
  final String? detail;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => Panel(
    onTap: onTap,
    child: Row(
      children: [
        AppIcon(icon, color: AppColors.muted),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(child: Text(title, style: AppText.heading.copyWith(fontSize: 15))),
                  if (state.isNotEmpty) StatusText(state, color: color),
                ],
              ),
              if (detail != null) ...[
                const SizedBox(height: 3),
                Text(detail!, maxLines: 2, overflow: TextOverflow.ellipsis, style: AppText.small),
              ],
            ],
          ),
        ),
        if (onTap != null) ...[const SizedBox(width: 8), const AppIcon('chevron', size: 18, color: AppColors.muted)],
      ],
    ),
  );
}
