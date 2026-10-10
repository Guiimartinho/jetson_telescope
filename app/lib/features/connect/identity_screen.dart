import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/link.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';

/// C9 — Identidade mudou. Quem respondeu no endereço do telescópio apresentou OUTRO
/// certificado. O app não manda nada (nem o token) e explica as duas causas possíveis.
class IdentityChangedScreen extends ConsumerWidget {
  const IdentityChangedScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final link = ref.watch(linkProvider);
    final controller = ref.read(linkProvider.notifier);
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(AppSpace.s2),
          children: [
            const SizedBox(height: AppSpace.s3),
            const Center(child: AppIcon('warning', size: 56, color: AppColors.bad)),
            const SizedBox(height: AppSpace.s2),
            const Text('Este não é o telescópio que você pareou', textAlign: TextAlign.center, style: AppText.title),
            const SizedBox(height: AppSpace.s2),
            Text(
              'Quem respondeu em ${link.device?.host ?? 'seu endereço'} não provou ser o "${link.name}". '
              'Por segurança, o app não enviou nada.',
              textAlign: TextAlign.center,
              style: AppText.body,
            ),
            const SizedBox(height: AppSpace.s3),
            const Panel(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SectionLabel('O que pode ter acontecido'),
                  Text(
                    'O telescópio foi reinstalado ou trocado: ele tem uma identidade nova, e é só parear de novo.',
                    style: AppText.body,
                  ),
                  SizedBox(height: AppSpace.s1),
                  Text(
                    'Ou outro aparelho na rede está respondendo no lugar dele. Se você não mexeu no '
                    'telescópio, desconfie desta rede.',
                    style: AppText.body,
                  ),
                ],
              ),
            ),
            const SizedBox(height: AppSpace.s3),
            AppButton(
              'Parear de novo',
              icon: 'qr',
              tone: ButtonTone.primary,
              big: true,
              expand: true,
              onPressed: controller.forget,
            ),
            const SizedBox(height: AppSpace.s1),
            AppButton('Tentar de novo', expand: true, onPressed: controller.retryNow),
          ],
        ),
      ),
    );
  }
}
