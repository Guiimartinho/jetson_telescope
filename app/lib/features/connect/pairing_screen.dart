import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/link.dart';
import '../../app/prefs.dart';
import '../../core/errors.dart';
import '../../core/strings.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import '../../data/device_store.dart';
import '../../data/telescope_wifi.dart';
import '../../domain/pairing.dart';

/// C5 — Pareando (e C4, quando o código traz o WiFi do telescópio).
///
/// As etapas aparecem pelo nome, e a que falhar diz o que houve e o que fazer. A mais importante
/// é a primeira: se quem respondeu não apresentar o certificado do código, o app PARA — nada
/// é enviado a um possível impostor.
class PairingScreen extends ConsumerStatefulWidget {
  const PairingScreen({super.key, required this.code});

  final PairingCode code;

  @override
  ConsumerState<PairingScreen> createState() => _PairingScreenState();
}

enum _Stage { ask, wifi, pairing, failed }

class _PairingScreenState extends ConsumerState<PairingScreen> {
  late final _name = TextEditingController(
    text: ref.read(prefsProvider).clientName.isEmpty ? 'Meu celular' : ref.read(prefsProvider).clientName,
  );
  _Stage _stage = _Stage.ask;
  ApiFailure? _failure;
  WifiJoin? _wifi;

  PairingCode get _code => widget.code;
  String get _host => _code.host ?? 'telescopio.local';

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _pair() async {
    final name = _name.text.trim().isEmpty ? 'Meu celular' : _name.text.trim();
    setState(() {
      _failure = null;
      _wifi = null;
      _stage = _code.ssid == null ? _Stage.pairing : _Stage.wifi;
    });
    if (_code.ssid != null) {
      final joined = await ref.read(telescopeWifiProvider).join(_code.ssid!, _code.psk ?? '');
      if (!mounted) return;
      if (joined == WifiJoin.unavailable) {
        setState(() {
          _wifi = joined;
          _stage = _Stage.failed;
        });
        return;
      }
      setState(() => _stage = _Stage.pairing);
    }
    try {
      final paired = await ref.read(pairerProvider)(code: _code, host: _host, clientName: name);
      await ref.read(prefsProvider.notifier).setClientName(name);
      // pareou pelo WiFi do próprio telescópio: vale oferecer, uma vez, pô-lo no WiFi de casa
      // (antes de conectar: conectado, o app sai desta tela)
      if (_code.ssid != null) await ref.read(prefsProvider.notifier).setOfferHomeWifi(true);
      // conectado, o roteador leva para Observar
      await ref
          .read(linkProvider.notifier)
          .adopt(
            SavedDevice(
              deviceId: paired.deviceId,
              name: 'Telescópio',
              host: _host,
              port: _code.port,
              fingerprint: _code.fingerprint,
              token: paired.token,
              // pareou pelo WiFi do próprio telescópio: o app guarda como voltar a ele no campo
              wifiSsid: _code.ssid,
              wifiPsk: _code.ssid == null ? null : _code.psk,
              wifiHost: _code.ssid == null ? null : _host,
            ),
          );
    } on ApiFailure catch (failure) {
      if (!mounted) return;
      setState(() {
        _failure = failure;
        _stage = _Stage.failed;
      });
    }
  }

  /// Em qual etapa a falha aconteceu.
  int get _failedStep {
    if (_wifi != null) return 0;
    final first = _code.ssid == null ? 0 : 1;
    return switch (_failure?.kind) {
      FailureKind.unreachable || FailureKind.identityMismatch => first,
      _ => first + 1,
    };
  }

  String _stepState(int index) {
    if (_stage == _Stage.ask) return 'pending';
    final current = switch (_stage) {
      _Stage.wifi => 0,
      _Stage.pairing => _code.ssid == null ? 0 : 1,
      _ => _failedStep,
    };
    if (index < current) return 'done';
    if (index > current) return 'pending';
    return _stage == _Stage.failed ? 'failed' : 'running';
  }

  @override
  Widget build(BuildContext context) {
    final steps = [
      if (_code.ssid != null) 'Entrar no WiFi do telescópio',
      'Conferir a identidade do telescópio',
      'Provar o código e receber a chave',
    ];
    final busy = _stage == _Stage.wifi || _stage == _Stage.pairing;
    return SubPage(
      title: 'Parear com o telescópio',
      onBack: () => context.go('/connect'),
      child: ListView(
        padding: const EdgeInsets.all(AppSpace.s2),
        children: [
          Panel(
            child: Row(
              children: [
                const AppIcon('mount', size: 28, color: AppColors.accent),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Telescópio ${_code.deviceId}', style: AppText.heading),
                      const SizedBox(height: 2),
                      Text('em $_host', style: AppText.small),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: AppSpace.s2),
          if (_stage == _Stage.ask) ...[
            const SectionLabel('Como este celular aparece no telescópio'),
            TextField(controller: _name, maxLength: 40, textCapitalization: TextCapitalization.sentences),
            if (_code.ssid != null) ...[
              const SizedBox(height: AppSpace.s1),
              Text(
                'Vou conectar este app ao WiFi "${_code.ssid}". O Android vai pedir sua permissão. '
                'O resto do celular continua na internet.',
                style: AppText.small,
              ),
            ],
            const SizedBox(height: AppSpace.s2),
            AppButton('Parear', icon: 'lock', tone: ButtonTone.primary, big: true, expand: true, onPressed: _pair),
          ] else ...[
            Panel(
              child: Column(
                children: [
                  for (var i = 0; i < steps.length; i++) _StepRow(number: i + 1, name: steps[i], state: _stepState(i)),
                ],
              ),
            ),
            const SizedBox(height: AppSpace.s2),
            if (busy) const Busy(),
            if (_stage == _Stage.failed) _failureNotice(),
          ],
        ],
      ),
    );
  }

  Widget _failureNotice() {
    final retry = AppButton('Tentar de novo', tone: ButtonTone.primary, onPressed: _pair);
    final rescan = AppButton('Ler o código de novo', onPressed: () => context.go('/connect/scan'));
    if (_wifi != null) {
      return Notice(
        title: 'Não entrei no WiFi do telescópio',
        text:
            'O aviso do Android foi fechado, ou a rede "${_code.ssid}" não apareceu. Veja se o telescópio '
            'está ligado e por perto; depois toque em "Tentar de novo" e escolha Conectar no aviso.',
        actions: [retry],
      );
    }
    final failure = _failure!;
    if (failure.kind == FailureKind.identityMismatch) {
      return Notice(
        title: 'A identidade não confere',
        text:
            'Quem respondeu em $_host não é o telescópio deste código. Pode ser outro aparelho no mesmo '
            'endereço, ou alguém se passando por ele. Nada foi enviado. Confira se leu o código do '
            'telescópio certo.',
        actions: [rescan],
      );
    }
    return Notice(
      title: 'Não pareou',
      text: S.failure(failure),
      actions: [
        retry,
        if (failure.kind == FailureKind.pairingRejected || failure.kind == FailureKind.pairingExpired) rescan,
      ],
    );
  }
}

class _StepRow extends StatelessWidget {
  const _StepRow({required this.number, required this.name, required this.state});

  final int number;
  final String name;
  final String state;

  @override
  Widget build(BuildContext context) {
    final (String? icon, Color color) = switch (state) {
      'done' => ('check', AppColors.ok),
      'failed' => ('close', AppColors.bad),
      'running' => (null, AppColors.accent),
      _ => (null, AppColors.dim),
    };
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 9),
      child: Row(
        children: [
          SizedBox.square(
            dimension: 22,
            child: icon != null
                ? AppIcon(icon, size: 20, color: color)
                : Center(
                    child: Text('$number', style: AppText.number.copyWith(color: color)),
                  ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              name,
              style: AppText.body.copyWith(color: state == 'pending' ? AppColors.muted : AppColors.text),
            ),
          ),
          Text(S.stepState(state == 'pending' ? '' : state), style: AppText.small.copyWith(color: color)),
        ],
      ),
    );
  }
}
