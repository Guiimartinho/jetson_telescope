import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/commands.dart';
import '../../app/queries.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import '../../domain/models.dart';
import 'gallery_screen.dart';

/// G2 — Uma sessão: a imagem grande, o que foi capturado, e a porta para o estúdio.
class SessionScreen extends ConsumerWidget {
  const SessionScreen({super.key, required this.id});

  final String id;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionsProvider).valueOrNull?.where((s) => s.id == id).firstOrNull;
    final image = ref.watch(sessionImageProvider(id));
    return SubPage(
      title: session?.target ?? 'Sessão',
      onBack: () => context.go('/gallery'),
      child: session == null
          ? (ref.watch(sessionsProvider).isLoading
                ? const Busy()
                : EmptyState(
                    icon: 'album',
                    title: 'Esta sessão não está mais no telescópio',
                    action: AppButton('Voltar à galeria', onPressed: () => context.go('/gallery')),
                  ))
          : ListView(
              padding: const EdgeInsets.all(AppSpace.s2),
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(AppSpace.radius),
                  child: AspectRatio(
                    aspectRatio: 4 / 3,
                    child: image.when(
                      loading: () => const ColoredBox(color: AppColors.surface2, child: Busy()),
                      error: (_, _) => const ColoredBox(
                        color: AppColors.surface2,
                        child: Center(child: Text('Não consegui carregar a imagem.', style: AppText.small)),
                      ),
                      data: (bytes) => bytes == null
                          ? const ColoredBox(
                              color: AppColors.surface2,
                              child: Center(child: Text('O arquivo não está no telescópio.', style: AppText.small)),
                            )
                          : InteractiveViewer(
                              maxScale: 6,
                              child: BytesImage(bytes, fit: BoxFit.contain, label: session.target),
                            ),
                    ),
                  ),
                ),
                const SizedBox(height: AppSpace.s2),
                _Facts(session: session),
                const SizedBox(height: AppSpace.s2),
                AppButton(
                  'Abrir no estúdio',
                  icon: 'sliders',
                  tone: ButtonTone.primary,
                  big: true,
                  expand: true,
                  onPressed: () => context.go('/gallery/$id/studio'),
                ),
                const SizedBox(height: AppSpace.s1),
                AppButton('Exportar', icon: 'share', expand: true, onPressed: () => context.go('/gallery/$id/export')),
                // as imagens de referência vêm com o telescópio: não são de apagar
                if (!session.isReference) ...[
                  const SizedBox(height: AppSpace.s1),
                  AppButton(
                    'Apagar',
                    icon: 'trash',
                    expand: true,
                    onPressed: () async {
                      // Q2 — apagar não tem volta
                      final yes = await confirm(
                        context,
                        title: 'Apagar ${session.target}?',
                        text: 'Não dá para desfazer.',
                        yes: 'Apagar',
                        no: 'Manter',
                        danger: true,
                      );
                      if (!yes) return;
                      final ok = await ref.read(commandsProvider).act((api) async {
                        await api.deleteSession(id);
                        return true;
                      });
                      if (ok != true) return;
                      ref.invalidate(sessionsProvider);
                      if (context.mounted) context.go('/gallery');
                    },
                  ),
                ],
                const SizedBox(height: 96),
              ],
            ),
    );
  }
}

class _Facts extends StatelessWidget {
  const _Facts({required this.session});

  final Session session;

  @override
  Widget build(BuildContext context) {
    final note = switch (session.source) {
      'reference' =>
        'Dado real de outro instrumento, processado pelo nosso pipeline. As sessões deste telescópio '
            'entram aqui quando a câmera estiver instalada.',
      'demo' => 'Imagem da demonstração, desenhada pelo próprio app.',
      _ => null,
    };
    return Panel(
      padding: const EdgeInsets.symmetric(horizontal: AppSpace.s2, vertical: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InfoLine(icon: 'layers', label: 'Capturado', value: sessionSummary(session)),
          if (session.camera.isNotEmpty) InfoLine(icon: 'camera', label: 'Câmera', value: session.camera),
          if (note != null) Padding(padding: const EdgeInsets.symmetric(vertical: 8), child: SourceNote(note)),
        ],
      ),
    );
  }
}
