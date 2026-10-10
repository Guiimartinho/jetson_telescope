import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/link.dart';
import '../../core/strings.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';

/// C1 — Abertura. Nada para tocar: o app procura o telescópio pareado e segue sozinho para
/// Observar; se ele não responder, vai para "Achar o telescópio".
class SplashScreen extends ConsumerWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final link = ref.watch(linkProvider);
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const BrandMark(size: 84),
            const SizedBox(height: AppSpace.s3),
            Text(S.appName.toUpperCase(), style: AppText.label.copyWith(fontSize: 13, letterSpacing: 4)),
            const SizedBox(height: AppSpace.s3),
            const Busy(),
            const SizedBox(height: AppSpace.s2),
            Text(link.device == null ? 'Abrindo...' : 'Conectando a ${link.name}...', style: AppText.small),
          ],
        ),
      ),
    );
  }
}
