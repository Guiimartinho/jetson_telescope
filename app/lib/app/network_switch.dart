import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/errors.dart';
import '../data/telescope_api.dart';
import '../data/telescope_wifi.dart';
import '../domain/models.dart';
import 'link.dart';

/// O que aconteceu depois de pedir ao telescópio para trocar de rede.
sealed class SwitchOutcome {
  const SwitchOutcome();
}

/// Trocou (ou já estava lá). [info] é a rede dele agora.
class Switched extends SwitchOutcome {
  const Switched(this.info);

  final NetworkInfo info;
}

/// O telescópio nem começou: recusou o pedido.
class SwitchRefused extends SwitchOutcome {
  const SwitchRefused(this.failure);

  final ApiFailure failure;
}

/// Tentou e não deu ([code]: `wrong_password`, `not_found`): ele continuou onde estava.
class SwitchFailed extends SwitchOutcome {
  const SwitchFailed(this.code, this.info);

  final String code;
  final NetworkInfo info;
}

/// Passou o prazo e o app não reencontrou o telescópio.
class SwitchLost extends SwitchOutcome {
  const SwitchLost();
}

final networkSwitcherProvider = Provider<NetworkSwitcher>(NetworkSwitcher.new);

/// Pede a troca de rede e espera o telescópio reaparecer.
///
/// Trocar de rede derruba a conexão: o telescópio responde "aceito", troca, e some por alguns
/// segundos. A ligação ([LinkController]) o reencontra sozinha no endereço novo; aqui só se
/// pergunta, de segundo em segundo, se a troca já acabou e como terminou. Se a rede nova não
/// deu certo, o telescópio volta para onde estava e conta o motivo.
class NetworkSwitcher {
  NetworkSwitcher(this._ref);

  final Ref _ref;
  static const _poll = Duration(seconds: 1);

  /// Quanto esperar cada resposta. Sumido, o telescópio não pode segurar a pergunta por muito
  /// mais que o intervalo entre elas.
  static const _ask = Duration(seconds: 4);

  /// [toField]: o telescópio vai passar a atender pelo WiFi que ele mesmo cria. O celular
  /// precisa entrar nesse WiFi para reencontrá-lo — o app pede isso ao Android.
  Future<SwitchOutcome> run(
    Future<NetworkChange> Function(TelescopeApi api) request, {
    bool toField = false,
    Duration patience = const Duration(seconds: 40),
  }) async {
    final api = _ref.read(linkProvider).api;
    if (api == null) return const SwitchRefused(ApiFailure(FailureKind.unreachable));
    final NetworkChange change;
    try {
      change = await request(api);
    } on ApiFailure catch (failure) {
      return SwitchRefused(failure);
    }
    if (change.reconnectS == 0) {
      // aceito sem nada a trocar (já estava lá): o resultado é a rede de agora, e um erro
      // antigo que ainda esteja registrado não é deste pedido
      try {
        return Switched(await api.network());
      } on ApiFailure {
        return const SwitchLost();
      }
    }
    // Os prazos correm pelo RELÓGIO, não pelo número de perguntas: com o telescópio sumido
    // cada pergunta demora, e contar voltas esticaria a espera por minutos.
    var expired = false;
    var mayLookElsewhere = false; // passou o prazo que o telescópio deu para trocar?
    final deadline = Timer(patience + Duration(seconds: change.reconnectS), () => expired = true);
    final grace = Timer(Duration(seconds: change.reconnectS), () => mayLookElsewhere = true);
    var joined = !toField;
    try {
      while (!expired) {
        await Future<void>.delayed(_poll);
        final link = _ref.read(linkProvider);
        final now = link.api; // a ligação pode ter mudado de endereço no meio do caminho
        if (now == null) return const SwitchLost();
        try {
          final info = await now.network().timeout(_ask);
          if (info.switching) continue;
          if (info.lastError != null) return SwitchFailed(info.lastError!, info);
          return Switched(info);
        } on ApiFailure {
          // no meio da troca o telescópio some: é o esperado
        } on TimeoutException {
          // idem: perguntou e ficou sem resposta
        }
        if (!joined && mayLookElsewhere) {
          joined = true;
          await _joinTelescopeWifi(link);
        }
      }
      return const SwitchLost();
    } finally {
      deadline.cancel();
      grace.cancel();
    }
  }

  /// O telescópio foi para o WiFi próprio e o celular ficou na rede de casa: entra no WiFi
  /// dele (só dentro deste app) e manda a ligação procurar de novo.
  Future<void> _joinTelescopeWifi(Link link) async {
    final device = link.device;
    if (device == null || !device.knowsWifi) return;
    final result = await _ref.read(telescopeWifiProvider).join(device.wifiSsid!, device.wifiPsk ?? '');
    if (result == WifiJoin.joined) _ref.read(linkProvider.notifier).retryNow();
  }
}
