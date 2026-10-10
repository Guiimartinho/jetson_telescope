import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// O resultado de pedir para entrar no WiFi do telescópio.
enum WifiJoin {
  /// Dentro: o tráfego deste app passa pelo WiFi do telescópio.
  joined,

  /// Não entrou: a pessoa fechou o aviso do sistema, ou a rede não apareceu (fora de alcance,
  /// telescópio desligado). O Android não diz qual dos dois.
  unavailable,

  /// Este aparelho não faz isso pelo app (iPhone, Android antigo, computador).
  unsupported,
}

/// Modo campo: entrar no WiFi do próprio telescópio **só dentro deste app**.
///
/// Esse WiFi não tem internet. Entrando nele pelas configurações do celular, o Android tende
/// a voltar para o 4G e o app perde o telescópio. Pela API de ponto de acesso local (Android 10
/// em diante) o sistema liga a rede só para este app; o resto do celular segue na internet.
/// Ver `app/docs/03-conexao.md`.
abstract interface class TelescopeWifi {
  Future<WifiJoin> join(String ssid, String psk);
  Future<void> leave();
}

class PlatformTelescopeWifi implements TelescopeWifi {
  const PlatformTelescopeWifi();

  static const _channel = MethodChannel('telescope/wifi');

  @override
  Future<WifiJoin> join(String ssid, String psk) async {
    try {
      final result = await _channel.invokeMethod<String>('join', {'ssid': ssid, 'psk': psk});
      return WifiJoin.values.asNameMap()[result] ?? WifiJoin.unavailable;
    } on MissingPluginException {
      return WifiJoin.unsupported;
    } on PlatformException {
      return WifiJoin.unavailable;
    }
  }

  @override
  Future<void> leave() async {
    try {
      await _channel.invokeMethod<void>('leave');
    } on MissingPluginException {
      // nada a desfazer onde não há o que fazer
    } on PlatformException {
      // idem
    }
  }
}

final telescopeWifiProvider = Provider<TelescopeWifi>((ref) => const PlatformTelescopeWifi());
