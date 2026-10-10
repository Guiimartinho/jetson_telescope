import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nsd/nsd.dart' as nsd;

/// Um telescópio que se anunciou na rede local.
class FoundTelescope {
  const FoundTelescope({required this.deviceId, required this.host, this.port = 8443, this.name = ''});

  /// O identificador que ele anuncia. NÃO é prova de nada: qualquer um na rede pode anunciar
  /// o que quiser. A confiança vem do certificado, conferido antes de qualquer conversa.
  final String deviceId;
  final String host;
  final int port;
  final String name;

  @override
  bool operator ==(Object other) =>
      other is FoundTelescope && other.deviceId == deviceId && other.host == host && other.port == port;

  @override
  int get hashCode => Object.hash(deviceId, host, port);

  @override
  String toString() => 'FoundTelescope($deviceId em $host:$port)';
}

/// A porta: quem está se anunciando como telescópio na rede em que o celular está.
///
/// A Jetson anuncia o serviço `_telescope._tcp` (avahi), com o identificador do aparelho. Isto
/// só poupa a pessoa de digitar um endereço — a lista é de CANDIDATOS. Ver
/// `app/docs/03-conexao.md` §2.
abstract interface class Discovery {
  /// A lista de agora e cada mudança dela. A busca roda enquanto alguém escuta.
  Stream<List<FoundTelescope>> watch();
}

/// A descoberta pelo serviço do sistema (NSD no Android, Bonjour no iOS).
class NsdDiscovery implements Discovery {
  NsdDiscovery() {
    _changes = StreamController<List<FoundTelescope>>.broadcast(onListen: _start, onCancel: _stop);
  }

  static const serviceType = '_telescope._tcp';

  late final StreamController<List<FoundTelescope>> _changes;
  nsd.Discovery? _discovery;
  var _latest = const <FoundTelescope>[];
  var _starting = false;

  @override
  Stream<List<FoundTelescope>> watch() async* {
    yield _latest;
    yield* _changes.stream;
  }

  Future<void> _start() async {
    if (_discovery != null || _starting) return;
    _starting = true;
    try {
      final discovery = await nsd.startDiscovery(serviceType, ipLookupType: nsd.IpLookupType.v4);
      if (!_changes.hasListener) {
        await nsd.stopDiscovery(discovery); // desistiram enquanto a busca subia
        return;
      }
      _discovery = discovery..addListener(_publish);
      _publish();
    } on Object {
      // sem o serviço (computador, emulador, permissão negada): a lista fica vazia e o resto
      // do app segue pelo endereço guardado e pelo QR
    } finally {
      _starting = false;
    }
  }

  Future<void> _stop() async {
    final discovery = _discovery;
    _discovery = null;
    _latest = const [];
    if (discovery == null) return;
    discovery.removeListener(_publish);
    try {
      await nsd.stopDiscovery(discovery);
    } on Object {
      // já tinha parado
    }
  }

  void _publish() {
    final discovery = _discovery;
    if (discovery == null) return;
    _latest = [for (final service in discovery.services) ?found(service)];
    if (!_changes.isClosed) _changes.add(_latest);
  }

  /// Um serviço anunciado vira candidato só se trouxer o identificador e um endereço IPv4 de
  /// rede local: é onde um telescópio pode estar. Um IPv6 de enlace (`fe80::…%wlan0`) nem
  /// serviria para conectar, e um endereço de fora não tem o que fazer num anúncio local.
  static FoundTelescope? found(nsd.Service service) {
    final id = _text(service.txt?['id']);
    final address = [
      ...?service.addresses,
      ?InternetAddress.tryParse(service.host ?? ''),
    ].where(isLocalIPv4).firstOrNull;
    if (id.isEmpty || address == null) return null;
    return FoundTelescope(deviceId: id, host: address.address, port: service.port ?? 8443, name: service.name ?? '');
  }

  /// 10.x, 172.16 a 172.31, 192.168.x e 169.254.x: as faixas de rede local.
  static bool isLocalIPv4(InternetAddress address) {
    if (address.type != InternetAddressType.IPv4) return false;
    final b = address.rawAddress;
    return b[0] == 10 ||
        (b[0] == 172 && b[1] >= 16 && b[1] <= 31) ||
        (b[0] == 192 && b[1] == 168) ||
        (b[0] == 169 && b[1] == 254);
  }

  static String _text(Uint8List? bytes) => bytes == null ? '' : utf8.decode(bytes, allowMalformed: true).trim();
}

final discoveryProvider = Provider<Discovery>((ref) => NsdDiscovery());

/// Os telescópios anunciados na rede agora (para a tela "Achar o telescópio").
final foundTelescopesProvider = StreamProvider.autoDispose<List<FoundTelescope>>(
  (ref) => ref.watch(discoveryProvider).watch(),
);
