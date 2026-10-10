import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/link.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import '../../data/telescope_wifi.dart';

enum _Stage { ask, joining, searching, refused, unsupported, silent }

/// C4 — Entrar no WiFi do telescópio (modo campo).
///
/// Longe de casa o telescópio cria o próprio WiFi. O app pede ao Android para usar essa rede
/// SÓ dentro dele: o resto do celular continua na internet. Entrando, a ligação procura o
/// telescópio no endereço que ele tem nesse WiFi; achou, o app segue para Observar sozinho.
///
/// O nome e a senha vêm do QR (se o pareamento foi no campo) ou do próprio telescópio, que
/// os conta ao dono enquanto está em casa.
class TelescopeWifiScreen extends ConsumerStatefulWidget {
  const TelescopeWifiScreen({super.key});

  /// Quanto esperar o telescópio responder depois de entrar no WiFi dele.
  static const patience = Duration(seconds: 15);

  @override
  ConsumerState<TelescopeWifiScreen> createState() => _TelescopeWifiScreenState();
}

class _TelescopeWifiScreenState extends ConsumerState<TelescopeWifiScreen> {
  _Stage _stage = _Stage.ask;
  bool _showPassword = false;
  Timer? _giveUp;

  @override
  void dispose() {
    _giveUp?.cancel();
    super.dispose();
  }

  Future<void> _join() async {
    final device = ref.read(linkProvider).device;
    if (device == null || !device.knowsWifi) return;
    setState(() => _stage = _Stage.joining);
    final result = await ref.read(telescopeWifiProvider).join(device.wifiSsid!, device.wifiPsk ?? '');
    if (!mounted) return;
    switch (result) {
      case WifiJoin.joined:
        _search();
      case WifiJoin.unavailable:
        setState(() => _stage = _Stage.refused);
      case WifiJoin.unsupported:
        setState(() => _stage = _Stage.unsupported);
    }
  }

  /// Já no WiFi do telescópio: manda a ligação procurá-lo agora. Se ele responder, o app sai
  /// desta tela sozinho; se passar o prazo, a tela diz.
  void _search() {
    setState(() => _stage = _Stage.searching);
    ref.read(linkProvider.notifier).retryNow();
    _giveUp?.cancel();
    _giveUp = Timer(TelescopeWifiScreen.patience, () {
      if (mounted && !ref.read(linkProvider).online) setState(() => _stage = _Stage.silent);
    });
  }

  @override
  Widget build(BuildContext context) {
    final link = ref.watch(linkProvider);
    final device = link.device;
    final ssid = device?.wifiSsid ?? '';
    final retry = AppButton('Tentar de novo', tone: ButtonTone.primary, onPressed: _join);
    return SubPage(
      title: 'WiFi do telescópio',
      onBack: () => context.go(link.usable ? '/device/network' : '/connect'),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(AppSpace.s2, 0, AppSpace.s2, AppSpace.s3),
        children: [
          if (device == null || !device.knowsWifi) ...[
            Notice(
              bad: false,
              icon: 'info',
              title: 'O app ainda não conhece o WiFi deste telescópio',
              text:
                  'O nome e a senha vêm no QR dele. Abra a janela de pareamento no telescópio e leia o '
                  'código de novo.',
              actions: [
                AppButton(
                  'Ler o QR do telescópio',
                  icon: 'qr',
                  tone: ButtonTone.primary,
                  onPressed: () => context.go('/connect/scan'),
                ),
              ],
            ),
          ] else ...[
            Panel(
              child: Row(
                children: [
                  const AppIcon('wifi', size: 28, color: AppColors.accent),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(ssid, style: AppText.heading),
                        const SizedBox(height: 2),
                        Text('o WiFi de ${device.name}', style: AppText.small),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: AppSpace.s2),
            ...switch (_stage) {
              _Stage.ask => [
                Text(
                  'Vou conectar este app ao WiFi "$ssid". O Android vai pedir sua permissão. Esse WiFi '
                  'não tem internet: ele só liga o celular ao telescópio, e o resto do celular continua '
                  'na internet de sempre.',
                  style: AppText.body,
                ),
                const SizedBox(height: AppSpace.s2),
                AppButton(
                  'Entrar no WiFi do telescópio',
                  icon: 'wifi',
                  tone: ButtonTone.primary,
                  big: true,
                  expand: true,
                  onPressed: _join,
                ),
              ],
              _Stage.joining => [
                const _Waiting('Pedindo ao Android para entrar no WiFi. Escolha "Conectar" no aviso dele.'),
              ],
              _Stage.searching => [const _Waiting('Dentro do WiFi. Procurando o telescópio.')],
              _Stage.refused => [
                Notice(
                  title: 'Não entrei no WiFi do telescópio',
                  text:
                      'O aviso do Android foi fechado, ou a rede "$ssid" não está ao alcance. Veja se o '
                      'telescópio está ligado e por perto: ele leva cerca de um minuto para criar o WiFi '
                      'depois de ligado.',
                  actions: [retry],
                ),
              ],
              _Stage.unsupported => [
                Notice(
                  bad: false,
                  icon: 'info',
                  title: 'Este celular não entra no WiFi pelo app',
                  text:
                      'Abra as configurações de WiFi do celular e entre na rede "$ssid". Se o Android avisar '
                      'que ela não tem internet, mande manter a conexão. Depois volte aqui.',
                  actions: [AppButton('Já entrei: procurar', tone: ButtonTone.primary, onPressed: _search)],
                ),
                const SizedBox(height: AppSpace.s1),
                Panel(
                  padding: const EdgeInsets.symmetric(horizontal: AppSpace.s2, vertical: 6),
                  child: Row(
                    children: [
                      const Text('Senha', style: AppText.small),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          _showPassword ? (device.wifiPsk ?? '') : '•' * 10,
                          style: AppText.number.copyWith(fontSize: 15),
                        ),
                      ),
                      IconAction(
                        'eye',
                        label: _showPassword ? 'Esconder a senha' : 'Mostrar a senha',
                        color: _showPassword ? AppColors.accent : AppColors.muted,
                        onPressed: () => setState(() => _showPassword = !_showPassword),
                      ),
                    ],
                  ),
                ),
              ],
              _Stage.silent => [
                Notice(
                  title: 'O telescópio não respondeu',
                  text:
                      'O celular entrou no WiFi "$ssid", mas o telescópio não atendeu. Espere um instante '
                      'e tente de novo; se continuar, desligue e ligue o telescópio.',
                  actions: [
                    AppButton('Procurar de novo', tone: ButtonTone.primary, onPressed: _search),
                    retry,
                  ],
                ),
              ],
            },
          ],
        ],
      ),
    );
  }
}

class _Waiting extends StatelessWidget {
  const _Waiting(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Panel(
    child: Row(
      children: [
        const Busy(),
        const SizedBox(width: 14),
        Expanded(child: Text(text, style: AppText.body)),
      ],
    ),
  );
}
