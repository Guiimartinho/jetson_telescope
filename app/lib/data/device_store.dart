import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../domain/pairing.dart';

/// O telescópio pareado com este celular.
class SavedDevice {
  const SavedDevice({
    required this.deviceId,
    required this.name,
    required this.host,
    required this.port,
    required this.fingerprint,
    required this.token,
    this.wifiSsid,
    this.wifiPsk,
    this.wifiHost,
  });

  final String deviceId;
  final String name;

  /// O último endereço em que ele respondeu (muda com a rede; a identidade é a impressão digital).
  final String host;
  final int port;
  final Uint8List fingerprint;
  final String token;

  /// O WiFi que o próprio telescópio cria (modo campo), quando o app o conhece: veio no QR, ou
  /// o telescópio contou ao dono. É com ele que o app o reencontra longe de casa. A senha é
  /// segredo: vai para o cofre, com o token.
  final String? wifiSsid;
  final String? wifiPsk;

  /// Onde o telescópio atende nesse WiFi.
  final String? wifiHost;

  bool get knowsWifi => (wifiSsid ?? '').isNotEmpty;

  SavedDevice copyWith({String? name, String? host, String? wifiSsid, String? wifiPsk, String? wifiHost}) =>
      SavedDevice(
        deviceId: deviceId,
        name: name ?? this.name,
        host: host ?? this.host,
        port: port,
        fingerprint: fingerprint,
        token: token,
        wifiSsid: wifiSsid ?? this.wifiSsid,
        wifiPsk: wifiPsk ?? this.wifiPsk,
        wifiHost: wifiHost ?? this.wifiHost,
      );
}

/// Onde o pareamento fica guardado. O token é segredo: vai para o cofre do sistema (Keystore
/// no Android, Chaveiro no iOS); o resto, para as preferências.
abstract interface class DeviceStore {
  Future<SavedDevice?> load();
  Future<void> save(SavedDevice device);
  Future<void> clear();
}

class SecureDeviceStore implements DeviceStore {
  SecureDeviceStore({FlutterSecureStorage? secure}) : _secure = secure ?? const FlutterSecureStorage();

  static const _key = 'device';
  static const _tokenKey = 'telescope.token';
  static const _wifiKey = 'telescope.wifi_psk';
  final FlutterSecureStorage _secure;

  @override
  Future<SavedDevice?> load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key);
    if (raw == null) return null;
    try {
      final j = (jsonDecode(raw) as Map).cast<String, dynamic>();
      final token = await _secure.read(key: _tokenKey);
      if (token == null || token.isEmpty) return null;
      return SavedDevice(
        deviceId: j['id'] as String,
        name: j['name'] as String,
        host: j['host'] as String,
        port: j['port'] as int,
        fingerprint: b64uDecode(j['fp'] as String),
        token: token,
        wifiSsid: j['wifi'] as String?,
        wifiPsk: j['wifi'] == null ? null : await _secure.read(key: _wifiKey),
        wifiHost: j['wifi_host'] as String?,
      );
    } on Object {
      return null; // registro estragado: melhor parear de novo do que falhar ao abrir
    }
  }

  @override
  Future<void> save(SavedDevice device) async {
    final prefs = await SharedPreferences.getInstance();
    await _secure.write(key: _tokenKey, value: device.token);
    if (device.wifiPsk == null) {
      await _secure.delete(key: _wifiKey);
    } else {
      await _secure.write(key: _wifiKey, value: device.wifiPsk);
    }
    await prefs.setString(
      _key,
      jsonEncode({
        'id': device.deviceId,
        'name': device.name,
        'host': device.host,
        'port': device.port,
        'fp': b64u(device.fingerprint),
        'wifi': ?device.wifiSsid,
        'wifi_host': ?device.wifiHost,
      }),
    );
  }

  @override
  Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_key);
    await _secure.delete(key: _tokenKey);
    await _secure.delete(key: _wifiKey);
  }
}

/// Em memória: para os testes e para o modo demonstração.
class MemoryDeviceStore implements DeviceStore {
  MemoryDeviceStore([this.device]);

  SavedDevice? device;

  @override
  Future<SavedDevice?> load() async => device;

  @override
  Future<void> save(SavedDevice device) async => this.device = device;

  @override
  Future<void> clear() async => device = null;
}
