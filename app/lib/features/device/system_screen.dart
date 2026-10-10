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

/// D7 — Sistema: versões, temperatura, disco, e desligar com segurança.
class SystemScreen extends ConsumerWidget {
  const SystemScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final system = ref.watch(systemProvider);
    final telescope = ref.watch(telescopeProvider);
    return SubPage(
      title: 'Sistema',
      onBack: () => context.go('/device'),
      child: system.when(
        loading: () => const Busy(),
        error: (error, _) => Padding(
          padding: const EdgeInsets.all(AppSpace.s2),
          child: Notice(
            title: 'O telescópio não respondeu',
            text: error is ApiFailure ? S.failure(error) : null,
            actions: [AppButton('Tentar de novo', onPressed: () => ref.invalidate(systemProvider))],
          ),
        ),
        data: (s) => ListView(
          padding: const EdgeInsets.all(AppSpace.s2),
          children: [
            Panel(
              padding: const EdgeInsets.symmetric(horizontal: AppSpace.s2, vertical: 8),
              child: Column(
                children: [
                  InfoLine(icon: 'mount', label: 'Aparelho', value: s.deviceId),
                  InfoLine(icon: 'info', label: 'Software', value: '${s.software} (API ${s.api})'),
                  InfoLine(
                    icon: 'chip',
                    label: 'Processamento',
                    value: telescope.backend.isEmpty ? '—' : telescope.backend,
                  ),
                  if (s.tempC != null) InfoLine(icon: 'thermo', label: 'Temperatura', value: '${Fmt.dec(s.tempC!)} °C'),
                  if (s.diskFreeGb != null)
                    InfoLine(icon: 'disk', label: 'Espaço livre', value: '${Fmt.dec(s.diskFreeGb!)} GB'),
                ],
              ),
            ),
            const SizedBox(height: AppSpace.s3),
            const SectionLabel('Energia'),
            if (!s.power)
              const Notice(
                bad: false,
                icon: 'info',
                title: 'Desligar pelo app ainda não está habilitado',
                text:
                    'Neste telescópio o desligamento pelo celular não foi ligado. Por enquanto, desligue-o '
                    'pela própria Jetson.',
              )
            else ...[
              AppButton('Reiniciar', icon: 'power', expand: true, onPressed: () => _power(context, ref, 'restart')),
              const SizedBox(height: AppSpace.s1),
              AppButton(
                'Desligar',
                icon: 'power',
                tone: ButtonTone.danger,
                expand: true,
                onPressed: () => _power(context, ref, 'shutdown'),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _power(BuildContext context, WidgetRef ref, String action) async {
    final busy = ref.read(telescopeProvider).busy;
    final verb = action == 'restart' ? 'Reiniciar' : 'Desligar';
    final yes = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: Text(busy ? 'Há uma sessão em andamento' : '$verb o telescópio?'),
        content: Text(
          busy ? 'A sessão será encerrada antes. $verb mesmo assim?' : 'O app perde a ligação até o telescópio voltar.',
        ),
        actions: [
          AppButton('Voltar', onPressed: () => Navigator.of(context).pop(false)),
          AppButton(verb, tone: ButtonTone.danger, onPressed: () => Navigator.of(context).pop(true)),
        ],
      ),
    );
    if (yes != true) return;
    try {
      if (busy) await ref.read(commandsProvider).stop();
      await ref.read(apiProvider).power(action);
      ref.read(toastProvider.notifier).state = Toast(action == 'restart' ? 'Reiniciando...' : 'Desligando...');
    } on ApiFailure catch (failure) {
      ref.read(toastProvider.notifier).state = Toast(S.failure(failure), bad: true);
    }
  }
}
