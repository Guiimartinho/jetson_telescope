import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:go_router/go_router.dart';

import '../../app/commands.dart';
import '../../app/link.dart';
import '../../app/queries.dart';
import '../../core/errors.dart';
import '../../core/format.dart';
import '../../core/strings.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import '../../domain/models.dart';

const _roles = ['owner', 'operator', 'viewer'];

/// D6 — Celulares pareados: quem pode falar com o telescópio, com que papel, e o convite para
/// mais um. Só o dono administra.
class PhonesScreen extends ConsumerWidget {
  const PhonesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final clients = ref.watch(clientsProvider);
    final now = ref.watch(clockProvider)();
    return SubPage(
      title: 'Celulares pareados',
      onBack: () => context.go('/device'),
      child: clients.when(
        loading: () => const Busy(),
        error: (error, _) => Padding(
          padding: const EdgeInsets.all(AppSpace.s2),
          child: error is ApiFailure && error.kind == FailureKind.forbidden
              ? const Notice(
                  bad: false,
                  icon: 'lock',
                  title: 'Só o dono vê os celulares pareados',
                  text: 'Este celular entrou por convite, com um papel menor. Peça ao dono do telescópio.',
                )
              : Notice(
                  title: 'O telescópio não respondeu',
                  text: error is ApiFailure ? S.failure(error) : null,
                  actions: [AppButton('Tentar de novo', onPressed: () => ref.invalidate(clientsProvider))],
                ),
        ),
        data: (list) => ListView(
          padding: const EdgeInsets.fromLTRB(AppSpace.s2, 0, AppSpace.s2, 96),
          children: [
            for (final client in list) ...[
              Panel(
                onTap: () => _manage(context, ref, client, list),
                child: Row(
                  children: [
                    AppIcon('phone', color: client.current ? AppColors.accent : AppColors.muted),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            client.current ? '${client.name} (este celular)' : client.name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: AppText.heading.copyWith(fontSize: 15),
                          ),
                          const SizedBox(height: 3),
                          Text(
                            '${S.role(client.role)}'
                            '${client.lastUsed == null ? '' : ' · usado ${Fmt.ago(now.difference(client.lastUsed!))}'}',
                            style: AppText.small,
                          ),
                        ],
                      ),
                    ),
                    const AppIcon('chevron', size: 18, color: AppColors.muted),
                  ],
                ),
              ),
              const SizedBox(height: 8),
            ],
            const SizedBox(height: AppSpace.s2),
            AppButton(
              'Convidar outro celular',
              icon: 'qr',
              tone: ButtonTone.primary,
              expand: true,
              onPressed: () => _invite(context, ref),
            ),
            const SizedBox(height: 8),
            const Text(
              'O convite é um código de uso único: vale para um celular só, por poucos minutos.',
              style: AppText.small,
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _manage(BuildContext context, WidgetRef ref, PairedClient client, List<PairedClient> all) async {
    final action = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: AppColors.surface,
      isScrollControlled: true, // a folha cresce até caber tudo; em tela pequena, rola
      builder: (context) => SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpace.s2),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(client.name, style: AppText.heading),
              const SizedBox(height: AppSpace.s2),
              const SectionLabel('Papel'),
              for (final role in _roles) ...[
                Panel(
                  onTap: role == client.role ? null : () => Navigator.of(context).pop(role),
                  color: role == client.role ? AppColors.elev : null,
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(S.role(role), style: AppText.body),
                            Text(S.roleHint(role), style: AppText.small),
                          ],
                        ),
                      ),
                      if (role == client.role) const AppIcon('check', size: 18, color: AppColors.accent),
                    ],
                  ),
                ),
                const SizedBox(height: 6),
              ],
              const SizedBox(height: AppSpace.s1),
              AppButton(
                client.current ? 'Revogar este celular' : 'Revogar',
                icon: 'trash',
                tone: ButtonTone.danger,
                expand: true,
                onPressed: () => Navigator.of(context).pop('revoke'),
              ),
            ],
          ),
        ),
      ),
    );
    if (action == null || !context.mounted) return;
    final commands = ref.read(commandsProvider);
    if (action == 'revoke') {
      final sure = await confirm(
        context,
        title: client.current ? 'Revogar ESTE celular?' : 'Revogar ${client.name}?',
        text: client.current
            ? 'Você perde o acesso agora mesmo. Para voltar, será preciso parear de novo no telescópio.'
            : 'Ele deixa de falar com o telescópio na hora.',
        yes: 'Revogar',
        danger: true,
      );
      if (!sure || !context.mounted) return;
      // revogar o próprio celular tranca a porta por fora: pergunta duas vezes
      if (client.current &&
          !await confirm(
            context,
            title: 'Tem certeza?',
            text: 'Não dá para desfazer daqui.',
            yes: 'Sim, revogar',
            danger: true,
          )) {
        return;
      }
      await commands.act((api) => api.revoke(client.id));
    } else {
      await commands.act((api) => api.setRole(client.id, action));
    }
    ref.invalidate(clientsProvider);
  }

  Future<void> _invite(BuildContext context, WidgetRef ref) async {
    final role = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: AppColors.surface,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpace.s2),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text('O que o convidado vai poder fazer?', style: AppText.heading),
              const SizedBox(height: AppSpace.s2),
              for (final role in _roles.reversed) ...[
                Panel(
                  onTap: () => Navigator.of(context).pop(role),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(S.role(role), style: AppText.body),
                      Text(S.roleHint(role), style: AppText.small),
                    ],
                  ),
                ),
                const SizedBox(height: 6),
              ],
            ],
          ),
        ),
      ),
    );
    if (role == null || !context.mounted) return;
    final invite = await ref.read(commandsProvider).act((api) => api.invite(role: role));
    if (invite == null || !context.mounted) return;
    await showDialog<void>(
      context: context,
      builder: (context) => _InviteDialog(invite: invite, demo: ref.read(linkProvider).demo),
    );
    ref.invalidate(clientsProvider);
  }
}

class _InviteDialog extends StatelessWidget {
  const _InviteDialog({required this.invite, required this.demo});

  final Invite invite;
  final bool demo;

  @override
  Widget build(BuildContext context) => AlertDialog(
    backgroundColor: AppColors.surface,
    title: Text('Convite de ${S.role(invite.role).toLowerCase()}'),
    content: SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (invite.qrSvg case final String svg)
            // fundo claro com margem: é o que a câmera do outro celular precisa para ler
            Container(
              color: Colors.white,
              padding: const EdgeInsets.all(10),
              child: SvgPicture.string(svg, width: 220, height: 220, semanticsLabel: 'Código do convite'),
            )
          else
            const Text('Este telescópio não desenha o código: copie o texto abaixo.', style: AppText.small),
          const SizedBox(height: AppSpace.s2),
          Text(
            demo
                ? 'Demonstração: este código não pareia com nada.'
                : 'No outro celular: abra o app, toque em "Ler o QR do telescópio" e aponte para cá. '
                      'Vale por ${Fmt.duration(invite.expiresS)}, para um celular só.',
            style: AppText.small,
          ),
          const SizedBox(height: AppSpace.s1),
          SelectableText(invite.uri, style: AppText.small.copyWith(fontSize: 11)),
        ],
      ),
    ),
    actions: [AppButton('Fechar', onPressed: () => Navigator.of(context).pop())],
  );
}
