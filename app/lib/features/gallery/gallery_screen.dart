import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/queries.dart';
import '../../core/errors.dart';
import '../../core/format.dart';
import '../../core/strings.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import '../../domain/models.dart';

/// De onde vem a sessão, quando não é deste telescópio: dito na tela, não escondido.
String? sessionSourceNote(Session session) => switch (session.source) {
  'reference' => 'dado de referência',
  'demo' => 'demonstração',
  _ => null,
};

String sessionSummary(Session session) {
  final time = session.integrationS == null
      ? ''
      : ' · ${session.integrationApprox ? 'cerca de ' : ''}${Fmt.duration(session.integrationS!)}';
  return '${session.frames} fotos$time';
}

/// G1 — Galeria: o que já foi feito.
class GalleryScreen extends ConsumerWidget {
  const GalleryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sessions = ref.watch(sessionsProvider);
    return sessions.when(
      loading: () => const Busy(),
      error: (error, _) => Padding(
        padding: const EdgeInsets.all(AppSpace.s2),
        child: Notice(
          title: 'Não consegui abrir a galeria',
          text: error is ApiFailure ? S.failure(error) : null,
          actions: [AppButton('Tentar de novo', onPressed: () => ref.invalidate(sessionsProvider))],
        ),
      ),
      data: (items) => items.isEmpty
          ? EmptyState(
              icon: 'album',
              title: 'Nenhuma sessão ainda',
              text: 'Quando você empilhar um alvo, o resultado aparece aqui.',
              action: AppButton('Escolher um alvo', icon: 'atlas', onPressed: () => context.go('/atlas')),
            )
          : GridView.builder(
              padding: const EdgeInsets.fromLTRB(AppSpace.s2, AppSpace.s2, AppSpace.s2, 96),
              gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                maxCrossAxisExtent: 260,
                mainAxisSpacing: 12,
                crossAxisSpacing: 12,
                childAspectRatio: 0.82,
              ),
              itemCount: items.length,
              itemBuilder: (context, index) => _SessionCard(session: items[index]),
            ),
    );
  }
}

class _SessionCard extends ConsumerWidget {
  const _SessionCard({required this.session});

  final Session session;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final note = sessionSourceNote(session);
    return Panel(
      padding: const EdgeInsets.all(8),
      onTap: () => context.go('/gallery/${session.id}'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: SizedBox(
              width: double.infinity,
              child: LazyImage(load: ref.watch(sessionThumbProvider(session.id).future), placeholder: 'album'),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            session.target,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: AppText.heading.copyWith(fontSize: 14),
          ),
          const SizedBox(height: 2),
          Text(sessionSummary(session), maxLines: 1, overflow: TextOverflow.ellipsis, style: AppText.small),
          if (note != null) ...[
            const SizedBox(height: 2),
            Text(
              note,
              style: const TextStyle(color: AppColors.gold, fontSize: 11.5, fontWeight: FontWeight.w600),
            ),
          ],
        ],
      ),
    );
  }
}
