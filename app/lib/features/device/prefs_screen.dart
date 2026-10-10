import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/commands.dart';
import '../../app/prefs.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import '../../data/alerts.dart';

/// D9 — Preferências do app. Ficam no celular; nada disto muda o telescópio.
class PrefsScreen extends ConsumerWidget {
  const PrefsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final prefs = ref.watch(prefsProvider);
    final controller = ref.read(prefsProvider.notifier);
    return SubPage(
      title: 'Preferências do app',
      onBack: () => context.go('/device'),
      child: ListView(
        padding: const EdgeInsets.all(AppSpace.s2),
        children: [
          _Toggle(
            icon: 'eye',
            title: 'Modo vermelho',
            text: 'O app inteiro em vermelho escuro, para não estragar a visão noturna.',
            value: prefs.redMode,
            onChanged: controller.setRedMode,
          ),
          const SizedBox(height: 8),
          _Toggle(
            icon: 'chart',
            title: 'Modo Pro',
            text: 'Mostra o histograma, SNR e FWHM enquanto empilha.',
            value: prefs.proMode,
            onChanged: controller.setProMode,
          ),
          const SizedBox(height: 8),
          _Toggle(
            icon: 'phone',
            title: 'Vibrar ao aceitar um comando',
            text: 'Um toque curto confirma que o telescópio recebeu, sem precisar olhar.',
            value: prefs.haptics,
            onChanged: controller.setHaptics,
          ),
          const SizedBox(height: 8),
          _Toggle(
            icon: 'clock',
            title: 'Avisar com a tela apagada',
            text:
                'Enquanto o telescópio trabalha, o app fica acompanhando e avisa quando termina, quando '
                'falha ou se o sinal cair. O Android mostra um aviso fixo nesse tempo.',
            value: prefs.notify,
            onChanged: (on) async {
              if (!on) return controller.setNotify(false);
              // o Android (13 em diante) só mostra avisos com a permissão de quem usa
              final allowed = await ref.read(alertsProvider).enable();
              if (!context.mounted) return;
              if (allowed) return controller.setNotify(true);
              ref.read(toastProvider.notifier).state = const Toast(
                'O Android não deixou este app mostrar avisos. Libere "Notificações" nas configurações do celular.',
                bad: true,
              );
            },
          ),
          if (prefs.clientName.isNotEmpty) ...[
            const SizedBox(height: AppSpace.s3),
            Text('Este celular aparece no telescópio como "${prefs.clientName}".', style: AppText.small),
          ],
        ],
      ),
    );
  }
}

class _Toggle extends StatelessWidget {
  const _Toggle({
    required this.icon,
    required this.title,
    required this.text,
    required this.value,
    required this.onChanged,
  });

  final String icon;
  final String title;
  final String text;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) => MergeSemantics(
    child: Panel(
      onTap: () => onChanged(!value),
      child: Row(
        children: [
          AppIcon(icon, color: value ? AppColors.accent : AppColors.muted),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: AppText.heading.copyWith(fontSize: 15)),
                const SizedBox(height: 3),
                Text(text, style: AppText.small),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Switch(
            value: value,
            onChanged: onChanged,
            activeThumbColor: AppColors.onAccent,
            activeTrackColor: AppColors.accent,
            inactiveThumbColor: AppColors.muted,
            inactiveTrackColor: AppColors.elev,
          ),
        ],
      ),
    ),
  );
}
