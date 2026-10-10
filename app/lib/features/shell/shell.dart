import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/commands.dart';
import '../../app/link.dart';
import '../../app/prefs.dart';
import '../../core/format.dart';
import '../../core/strings.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';

/// A moldura de todas as telas do telescópio: faixa de estado (X1) em cima, navegação (X2)
/// embaixo e o PARAR flutuante (X3) enquanto houver algo rodando.
class Shell extends ConsumerWidget {
  const Shell({super.key, required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  static const observeIndex = 2;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final busy = ref.watch(telescopeProvider.select((t) => t.busy));
    final index = navigationShell.currentIndex;
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            const StatusStrip(),
            Expanded(
              child: Stack(
                children: [
                  // Um contêiner de semântica próprio para as páginas: sem ele, a barreira que
                  // cada página põe atrás de si escondia a faixa de estado do leitor de tela.
                  Positioned.fill(child: Semantics(container: true, child: navigationShell)),
                  // abaixo da barra das páginas de segundo nível: um aviso não pode ficar em cima
                  // do "voltar"
                  const Positioned(left: 12, right: 12, top: 60, child: ToastHost()),
                  // em Observar o PARAR já é o botão principal da tela
                  if (busy && index != observeIndex)
                    Positioned(
                      right: 16,
                      bottom: 16,
                      child: AppButton(
                        'PARAR',
                        icon: 'square',
                        tone: ButtonTone.danger,
                        big: true,
                        onPressed: () => ref.read(commandsProvider).stop(),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
      bottomNavigationBar: NavBar(
        index: index,
        onTap: (i) => navigationShell.goBranch(i, initialLocation: i == index),
      ),
    );
  }
}

/// X1 — nome do telescópio, conexão, o que ele está fazendo e o atalho do modo vermelho.
class StatusStrip extends ConsumerWidget {
  const StatusStrip({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final link = ref.watch(linkProvider);
    final red = ref.watch(prefsProvider.select((p) => p.redMode));
    final telescope = link.telescope;
    return Container(
      height: 52,
      padding: const EdgeInsets.only(left: 14),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppColors.line)),
      ),
      child: Row(
        children: [
          const BrandMark(size: 24),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  link.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700, height: 1.1),
                ),
                const SizedBox(height: 3),
                _Connection(link: link),
              ],
            ),
          ),
          if (telescope != null && link.online)
            Padding(
              padding: const EdgeInsets.only(right: 6),
              child: Text(
                S.activity(telescope.state),
                style: AppText.small.copyWith(color: telescope.busy ? AppColors.accent : AppColors.muted),
              ),
            ),
          IconAction(
            'eye',
            label: red ? 'Desligar o modo vermelho' : 'Ligar o modo vermelho',
            color: red ? AppColors.bad : AppColors.muted,
            onPressed: () => ref.read(prefsProvider.notifier).setRedMode(!red),
          ),
        ],
      ),
    );
  }
}

class _Connection extends StatefulWidget {
  const _Connection({required this.link});

  final Link link;

  @override
  State<_Connection> createState() => _ConnectionState();
}

class _ConnectionState extends State<_Connection> {
  Timer? _tick;

  @override
  void initState() {
    super.initState();
    _sync();
  }

  @override
  void didUpdateWidget(_Connection old) {
    super.didUpdateWidget(old);
    _sync();
  }

  /// Só conta os segundos enquanto está reconectando.
  void _sync() {
    final counting = widget.link.phase == LinkPhase.reconnecting;
    if (counting && _tick == null) {
      _tick = Timer.periodic(const Duration(seconds: 1), (_) => setState(() {}));
    } else if (!counting) {
      _tick?.cancel();
      _tick = null;
    }
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final link = widget.link;
    final (String text, Color color) = switch (link.phase) {
      LinkPhase.online => (
        link.demo ? 'demonstração, sem aparelho' : 'conectado',
        link.demo ? AppColors.gold : AppColors.ok,
      ),
      LinkPhase.reconnecting => (
        'reconectando ${link.lostAt == null ? '' : Fmt.ago(DateTime.now().difference(link.lostAt!))}'.trim(),
        AppColors.gold,
      ),
      _ => ('sem conexão', AppColors.bad),
    };
    return StatusText(text, color: color, style: const TextStyle(fontSize: 11.5, height: 1.1));
  }
}

/// X2 — os cinco destinos, na ordem em que a noite acontece. Observar no centro, maior.
class NavBar extends StatelessWidget {
  const NavBar({super.key, required this.index, required this.onTap});

  final int index;
  final ValueChanged<int> onTap;

  static const _items = [
    ('atlas', 'Atlas'),
    ('list', 'Planejar'),
    ('reticle', 'Observar'),
    ('album', 'Galeria'),
    ('mount', 'Aparelho'),
  ];

  @override
  Widget build(BuildContext context) => Container(
    decoration: const BoxDecoration(
      color: AppColors.surface,
      border: Border(top: BorderSide(color: AppColors.line)),
    ),
    child: SafeArea(
      top: false,
      child: SizedBox(
        height: 64,
        child: Row(
          children: [
            for (var i = 0; i < _items.length; i++)
              Expanded(
                child: _NavItem(
                  icon: _items[i].$1,
                  label: _items[i].$2,
                  selected: i == index,
                  main: i == Shell.observeIndex,
                  onTap: () => onTap(i),
                ),
              ),
          ],
        ),
      ),
    ),
  );
}

class _NavItem extends StatelessWidget {
  const _NavItem({
    required this.icon,
    required this.label,
    required this.selected,
    required this.main,
    required this.onTap,
  });

  final String icon;
  final String label;
  final bool selected;
  final bool main;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = selected ? AppColors.accent : AppColors.muted;
    return Semantics(
      container: true,
      button: true,
      selected: selected,
      label: label,
      onTap: onTap,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: main ? 46 : 32,
              height: main ? 34 : 26,
              decoration: main
                  ? BoxDecoration(
                      color: selected ? const Color(0x2233DDC4) : AppColors.elev,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: selected ? AppColors.accent : AppColors.line),
                    )
                  : null,
              child: Center(
                child: AppIcon(icon, size: main ? 24 : 22, color: color),
              ),
            ),
            const SizedBox(height: 3),
            Text(
              main ? label.toUpperCase() : label,
              maxLines: 1,
              style: TextStyle(color: color, fontSize: 10.5, fontWeight: main ? FontWeight.w700 : FontWeight.w600),
            ),
          ],
        ),
      ),
    );
  }
}

/// Mostra o aviso atual por alguns segundos, por cima da tela, sem tomar o toque do resto.
class ToastHost extends ConsumerStatefulWidget {
  const ToastHost({super.key});

  @override
  ConsumerState<ToastHost> createState() => _ToastHostState();
}

class _ToastHostState extends ConsumerState<ToastHost> {
  Timer? _hide;

  @override
  void dispose() {
    _hide?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(toastProvider, (_, next) {
      _hide?.cancel();
      if (next != null) {
        _hide = Timer(const Duration(seconds: 4), () => ref.read(toastProvider.notifier).state = null);
      }
    });
    final toast = ref.watch(toastProvider);
    if (toast == null) return const SizedBox.shrink();
    final color = toast.bad ? AppColors.bad : AppColors.accent;
    return Semantics(
      liveRegion: true,
      child: GestureDetector(
        onTap: () => ref.read(toastProvider.notifier).state = null,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            color: const Color(0xF2060A12),
            borderRadius: BorderRadius.circular(AppSpace.radiusSmall),
            border: Border.all(color: color),
          ),
          child: Row(
            children: [
              AppIcon(toast.bad ? 'warning' : 'check', size: 18, color: color),
              const SizedBox(width: 10),
              Expanded(child: Text(toast.text, style: AppText.body.copyWith(fontSize: 14))),
            ],
          ),
        ),
      ),
    );
  }
}
