import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/link.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import '../../data/discovery.dart';

/// C2 — Achar o telescópio. É onde o app chega sem telescópio pareado, ou quando o pareado
/// não respondeu. Nas outras vezes esta tela nem aparece: o app conecta e vai para Observar.
///
/// A lista "Na rede agora" mostra quem está se anunciando como telescópio. É só para poupar a
/// procura: anúncio não é identidade, e ninguém conversa com o app sem o certificado do QR.
class FindScreen extends ConsumerWidget {
  const FindScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final link = ref.watch(linkProvider);
    final controller = ref.read(linkProvider.notifier);
    final found = ref.watch(foundTelescopesProvider).valueOrNull ?? const <FoundTelescope>[];
    final paired = link.device;
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(AppSpace.s2),
          children: [
            const SizedBox(height: AppSpace.s2),
            const Row(
              children: [
                BrandMark(size: 36),
                SizedBox(width: 12),
                Text('Achar o telescópio', style: AppText.title),
              ],
            ),
            const SizedBox(height: AppSpace.s3),
            if (link.phase == LinkPhase.revoked) ...[
              Notice(
                title: 'Este celular não está mais pareado',
                text:
                    'O telescópio deixou de aceitar este celular. Abra a janela de pareamento nele e leia o código de novo.',
                actions: [AppButton('Esquecer este telescópio', onPressed: controller.forget)],
              ),
              const SizedBox(height: AppSpace.s2),
            ],
            if (link.phase == LinkPhase.offline && link.device != null) ...[
              Panel(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const AppIcon('mount', color: AppColors.muted),
                        const SizedBox(width: 10),
                        Expanded(child: Text(link.device!.name, style: AppText.heading)),
                        const AppIcon('lock', size: 16, color: AppColors.muted),
                      ],
                    ),
                    const SizedBox(height: 8),
                    const StatusText('sem resposta: tentando de novo', color: AppColors.gold),
                    const SizedBox(height: 6),
                    Text('Último endereço: ${link.device!.host}', style: AppText.small),
                    const SizedBox(height: AppSpace.s2),
                    Wrap(
                      spacing: AppSpace.s1,
                      runSpacing: AppSpace.s1,
                      children: [
                        AppButton('Tentar agora', tone: ButtonTone.primary, onPressed: controller.retryNow),
                        if (link.device!.knowsWifi)
                          AppButton(
                            'Entrar no WiFi do telescópio',
                            icon: 'wifi',
                            onPressed: () => context.go('/connect/wifi'),
                          ),
                        AppButton('Parear outro', onPressed: controller.forget),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: AppSpace.s2),
              Text(
                link.device!.knowsWifi
                    ? 'Em casa: veja se o telescópio está ligado e se o celular está no mesmo WiFi que ele. '
                          'Fora de casa: ele cria o próprio WiFi, e o app entra nele por aqui.'
                    : 'Não achou? Veja se o telescópio está ligado e se o celular está no mesmo WiFi que ele.',
                style: AppText.small,
              ),
              const SizedBox(height: AppSpace.s3),
            ],
            if (link.phase != LinkPhase.offline) ...[
              const Text(
                'Ligue o telescópio e leia o código de pareamento dele. O código prova ao app que é '
                'mesmo o seu telescópio, e ao telescópio que é você.',
                style: AppText.body,
              ),
              const SizedBox(height: AppSpace.s2),
              AppButton(
                'Ler o QR do telescópio',
                icon: 'qr',
                tone: ButtonTone.primary,
                big: true,
                expand: true,
                onPressed: () => context.go('/connect/scan'),
              ),
              const SizedBox(height: AppSpace.s1),
              AppButton(
                'Digitar o código',
                icon: 'keyboard',
                expand: true,
                onPressed: () => context.go('/connect/code'),
              ),
              const SizedBox(height: AppSpace.s3),
            ],
            const SectionLabel('Na rede agora'),
            if (found.isEmpty)
              const Padding(
                padding: EdgeInsets.only(bottom: AppSpace.s3),
                child: Text(
                  'Nenhum telescópio se anunciou nesta rede. O celular está no mesmo WiFi que ele?',
                  style: AppText.small,
                ),
              )
            else ...[
              for (final telescope in found) ...[
                _Found(
                  telescope: telescope,
                  paired: paired != null && paired.deviceId == telescope.deviceId,
                  // o pareado é reencontrado sozinho; os outros pedem o código deles
                  onTap: paired != null && paired.deviceId == telescope.deviceId
                      ? controller.retryNow
                      : () => context.go('/connect/scan'),
                ),
                const SizedBox(height: 8),
              ],
              const SizedBox(height: AppSpace.s2),
            ],
            const SectionLabel('Sem telescópio por perto'),
            Panel(
              onTap: controller.startDemo,
              child: const Row(
                children: [
                  AppIcon('play', color: AppColors.gold),
                  SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Demonstração', style: AppText.heading),
                        SizedBox(height: 2),
                        Text('O app inteiro funcionando, sem aparelho.', style: AppText.small),
                      ],
                    ),
                  ),
                  AppIcon('chevron', size: 18, color: AppColors.muted),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Um telescópio que se anunciou na rede: o pareado (que o app reencontra sozinho) ou outro,
/// que só entra com o código de pareamento dele.
class _Found extends StatelessWidget {
  const _Found({required this.telescope, required this.paired, required this.onTap});

  final FoundTelescope telescope;
  final bool paired;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Panel(
    onTap: onTap,
    child: Row(
      children: [
        AppIcon('mount', color: paired ? AppColors.accent : AppColors.muted),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                telescope.name.isEmpty ? 'Telescópio ${telescope.deviceId}' : telescope.name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: AppText.heading.copyWith(fontSize: 15),
              ),
              const SizedBox(height: 2),
              Text(
                // "anunciado", não "achado": só o certificado diz se é mesmo o seu
                paired
                    ? 'anunciado em ${telescope.host}: conferindo a identidade'
                    : 'em ${telescope.host} · para usar, leia o código dele',
                style: AppText.small,
              ),
            ],
          ),
        ),
        if (paired) const AppIcon('lock', size: 16, color: AppColors.muted),
        const SizedBox(width: 6),
        const AppIcon('chevron', size: 18, color: AppColors.muted),
      ],
    ),
  );
}
