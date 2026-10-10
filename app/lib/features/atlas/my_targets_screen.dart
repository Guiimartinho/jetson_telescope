import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/prefs.dart';
import '../../app/queries.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import 'atlas_screen.dart';

/// A4 — Meus alvos: os que a pessoa marcou com a estrela. Ficam guardados no celular.
class MyTargetsScreen extends ConsumerWidget {
  const MyTargetsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final favorites = ref.watch(prefsProvider.select((p) => p.favorites)).toList()..sort();
    return SubPage(
      title: 'Meus alvos',
      onBack: () => context.go('/atlas'),
      child: favorites.isEmpty
          ? EmptyState(
              icon: 'star',
              title: 'Nenhum alvo guardado',
              text: 'No Atlas, toque na estrela de um alvo para guardá-lo aqui.',
              action: AppButton('Abrir o Atlas', onPressed: () => context.go('/atlas')),
            )
          : ListView.separated(
              padding: const EdgeInsets.all(AppSpace.s2),
              itemCount: favorites.length,
              separatorBuilder: (_, _) => const SizedBox(height: 8),
              itemBuilder: (context, index) {
                final id = favorites[index];
                return ref
                    .watch(targetDetailProvider(id))
                    .when(
                      loading: () => const Panel(child: SizedBox(height: 54, child: Busy())),
                      // some do catálogo (ou da demonstração): a pessoa ainda pode tirá-lo daqui
                      error: (_, _) => Panel(
                        child: Row(
                          children: [
                            Expanded(child: Text('$id: não está neste telescópio', style: AppText.small)),
                            IconAction(
                              'trash',
                              label: 'Tirar dos meus alvos',
                              onPressed: () => ref.read(prefsProvider.notifier).toggleFavorite(id),
                            ),
                          ],
                        ),
                      ),
                      data: (detail) => TargetRow(target: detail.target),
                    );
              },
            ),
    );
  }
}
