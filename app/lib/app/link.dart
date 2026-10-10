import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/errors.dart';
import '../data/device_store.dart';
import '../data/discovery.dart';
import '../data/fake_telescope.dart';
import '../data/http_telescope.dart';
import '../data/telescope_api.dart';
import '../domain/models.dart';
import '../domain/pairing.dart';
import 'prefs.dart';

/// Em que pé está a ligação do app com o telescópio.
enum LinkPhase {
  /// Abrindo o app: lendo o que está guardado.
  starting,

  /// Nenhum telescópio pareado: é preciso achar um (ou usar a demonstração).
  noDevice,

  /// Tentando falar com o telescópio pareado pela primeira vez nesta abertura.
  connecting,

  /// Há um telescópio pareado, mas ele não respondeu. O app continua tentando.
  offline,

  /// Conversando: o estado chega empurrado.
  online,

  /// Estava conversando e o sinal caiu. Nada é desfeito; o app tenta de novo sozinho.
  reconnecting,

  /// Quem respondeu apresentou OUTRO certificado: possível impostor, ou a Jetson foi regravada.
  identityChanged,

  /// O telescópio não aceita mais este celular (revogado, ou o pareamento foi zerado).
  revoked,
}

class Link {
  const Link({
    this.phase = LinkPhase.starting,
    this.device,
    this.demo = false,
    this.api,
    this.info,
    this.telescope,
    this.updatedAt,
    this.lostAt,
  });

  final LinkPhase phase;
  final SavedDevice? device;
  final bool demo;
  final TelescopeApi? api;
  final TelescopeInfo? info;

  /// O último estado recebido. Com o sinal caído ele fica congelado, e a tela diz desde quando.
  final TelescopeState? telescope;
  final DateTime? updatedAt;
  final DateTime? lostAt;

  bool get online => phase == LinkPhase.online;

  /// Dá para mostrar as telas do telescópio (mesmo reconectando: o que já se sabe continua lá).
  bool get usable => api != null && (phase == LinkPhase.online || phase == LinkPhase.reconnecting);
  String get name => info?.name ?? (demo ? 'Demonstração' : device?.name ?? 'Telescópio');

  Link copyWith({
    LinkPhase? phase,
    SavedDevice? device,
    TelescopeInfo? info,
    TelescopeState? telescope,
    DateTime? updatedAt,
    DateTime? lostAt,
    bool clearLost = false,
  }) => Link(
    phase: phase ?? this.phase,
    device: device ?? this.device,
    demo: demo,
    api: api,
    info: info ?? this.info,
    telescope: telescope ?? this.telescope,
    updatedAt: updatedAt ?? this.updatedAt,
    lostAt: clearLost ? null : (lostAt ?? this.lostAt),
  );
}

// ------------------------------------------------------------------ dependências
/// Onde o pareamento fica guardado (cofre do sistema). Os testes trocam por memória.
final deviceStoreProvider = Provider<DeviceStore>((ref) => SecureDeviceStore());

/// Como se fala com um telescópio pareado. Os testes trocam pelo falso.
final apiFactoryProvider = Provider<TelescopeApi Function(SavedDevice)>(
  (ref) =>
      (device) =>
          HttpTelescope(host: device.host, port: device.port, fingerprint: device.fingerprint, token: device.token),
);

/// O telescópio do modo demonstração.
final demoFactoryProvider = Provider<TelescopeApi Function()>((ref) => FakeTelescope.new);

typedef Pairer = Future<Paired> Function({required PairingCode code, required String host, required String clientName});

/// O pareamento (canal cifrado, prova do código). Os testes trocam.
final pairerProvider = Provider<Pairer>(
  (ref) =>
      ({required code, required host, required clientName}) =>
          HttpTelescope.pair(code: code, host: host, clientName: clientName),
);

final clockProvider = Provider<DateTime Function()>((ref) => DateTime.now);

final linkProvider = NotifierProvider<LinkController, Link>(LinkController.new);

/// O telescópio com quem as telas falam. Só é lido debaixo da navegação principal, onde a
/// ligação já existe.
final apiProvider = Provider<TelescopeApi>((ref) {
  final api = ref.watch(linkProvider.select((l) => l.api));
  if (api == null) throw StateError('sem telescópio conectado');
  return api;
});

/// O estado do telescópio (o último recebido).
final telescopeProvider = Provider<TelescopeState>(
  (ref) => ref.watch(linkProvider.select((l) => l.telescope)) ?? const TelescopeState(),
);

/// Onde um telescópio pode estar mesmo sem nunca ter sido visto lá: no WiFi que ele mesmo cria
/// (o endereço do ponto de acesso do NetworkManager) e, em casa, pelo apelido na rede.
/// Ver `app/docs/03-conexao.md` §2.
const fieldHost = '10.42.0.1';
const homeAlias = 'telescopio.local';

/// Quem respondeu, e onde ([host] nulo: no endereço de sempre).
class _Reached {
  const _Reached(this.api, this.host, this.info);

  final TelescopeApi api;
  final String? host;
  final TelescopeInfo info;
}

// ------------------------------------------------------------------ controlador
/// Mantém a ligação viva sem ninguém pedir: conecta ao abrir, escuta o estado, e quando o
/// sinal cai tenta de novo com espera crescente. A Jetson segue trabalhando sozinha nesse
/// meio-tempo; ao voltar, o app recebe o retrato completo.
///
/// O telescópio muda de endereço (o roteador dá outro número; ele sai de casa e cria o próprio
/// WiFi). Por isso, quando ele não responde onde estava, o app o procura nos outros lugares
/// possíveis. O endereço nunca é a identidade: só vale quem apresentar o certificado pareado.
class LinkController extends Notifier<Link> {
  static const _backoff = [1, 2, 3, 5, 8];

  /// Quanto o endereço de sempre tem para responder antes de a procura começar em paralelo.
  static const _headStart = Duration(milliseconds: 1500);

  StreamSubscription<TelescopeState>? _subscription;
  StreamSubscription<List<FoundTelescope>>? _discovery;
  TelescopeApi? _api; // o mesmo de `state.api`; guardado para fechar ao descartar
  Timer? _retry;
  int _attempt = 0;
  bool _everOnline = false;

  /// A ligação que está sendo tentada agora (uma tentativa por vez, por telescópio).
  TelescopeApi? _connecting;

  /// Endereços em que a rede anunciou o telescópio pareado. Com teto: qualquer um na rede pode
  /// anunciar o que quiser, quantas vezes quiser, e cada candidato custa uma tentativa cifrada.
  var _found = <String>{};
  static const _maxAnnounced = 4;

  /// Um anúncio novo manda tentar logo — mas não a cada anúncio.
  static const _announceGap = Duration(seconds: 1);
  Timer? _announced;

  /// As gravações do pareamento, uma depois da outra. Guardar o endereço novo ou o WiFi pode
  /// estar no meio do caminho quando alguém manda esquecer o telescópio: em fila, o "esquecer"
  /// é sempre o último, e nada do aparelho esquecido volta a ser escrito depois dele.
  Future<void> _stored = Future<void>.value();

  Future<void> _store(Future<void> Function(DeviceStore store) write) {
    final store = ref.read(deviceStoreProvider);
    return _stored = _stored.then((_) => write(store)).catchError((Object _) {
      // O cofre do sistema pode falhar (backup restaurado, chave perdida). A ligação segue com
      // o que tem em mãos; só não fica guardado para a próxima abertura do app.
    });
  }

  DateTime get _now => ref.read(clockProvider)();

  @override
  Link build() {
    ref.onDispose(_release);
    return const Link();
  }

  /// Chamado uma vez, ao abrir o app.
  Future<void> start() async {
    final device = await ref.read(deviceStoreProvider).load();
    if (device == null) {
      state = const Link(phase: LinkPhase.noDevice);
      return;
    }
    _open(device, ref.read(apiFactoryProvider)(device));
  }

  /// Entra no modo demonstração: o app inteiro funcionando, sem aparelho.
  Future<void> startDemo() async {
    _release();
    _open(null, ref.read(demoFactoryProvider)(), demo: true);
  }

  /// Guarda um telescópio recém-pareado e conecta.
  Future<void> adopt(SavedDevice device) async {
    // primeiro larga o anterior: nada dele pode ser gravado depois do novo
    _release();
    final saved = _store((store) => store.save(device));
    _open(device, ref.read(apiFactoryProvider)(device));
    await saved;
  }

  /// Esquece o telescópio (parear de novo, ou sair da demonstração).
  Future<void> forget() async {
    final demo = state.demo;
    // primeiro solta a ligação: o que estiver a caminho deixa de valer antes de apagar
    _release();
    state = const Link(phase: LinkPhase.noDevice);
    if (!demo) await _store((store) => store.clear());
  }

  /// "Tentar agora", sem esperar o próximo ciclo.
  void retryNow() {
    if (state.api == null || identical(_connecting, state.api)) return;
    _retry?.cancel();
    unawaited(_connect());
  }

  void _open(SavedDevice? device, TelescopeApi api, {bool demo = false}) {
    _attempt = 0;
    _everOnline = false;
    _api = api;
    state = Link(phase: LinkPhase.connecting, device: device, demo: demo, api: api);
    unawaited(_connect());
  }

  Future<void> _connect() async {
    final api = state.api;
    if (api == null || identical(_connecting, api)) return;
    _connecting = api;
    var mine = api; // a ligação desta tentativa (muda se o telescópio for achado em outro endereço)
    try {
      final reached = await _reach(api, state.demo ? null : state.device);
      if (!identical(api, state.api)) {
        // trocaram de telescópio enquanto esperávamos
        if (!identical(reached.api, api)) reached.api.close();
        return;
      }
      if (reached.host != null) {
        // a tentativa continua sendo esta, agora pela ligação nova: sem isto, um "tentar agora"
        // no meio da gravação abriria uma segunda
        mine = reached.api;
        _connecting = mine;
        await _moveTo(reached);
        if (!identical(reached.api, state.api)) return;
      }
      _attempt = 0;
      _everOnline = true;
      state = state.copyWith(phase: LinkPhase.online, info: reached.info, clearLost: true);
      _stopSearch();
      _listen(reached.api);
      unawaited(_sendSite(reached.api, reached.info));
      unawaited(_learnWifi(reached.api));
    } on ApiFailure catch (failure) {
      if (identical(api, state.api)) _onFailure(failure);
    } finally {
      if (identical(_connecting, mine)) _connecting = null;
    }
  }

  /// Os outros lugares onde o telescópio pareado pode estar: onde a rede o anunciou, no WiFi
  /// próprio dele, e pelo apelido de casa.
  List<String> _elsewhere(SavedDevice device) => [
    for (final host in {..._found, device.wifiHost ?? fieldHost, homeAlias})
      if (host != device.host) host,
  ];

  /// Fala com o telescópio no endereço de sempre; se ele não responder logo, procura ao mesmo
  /// tempo nos outros. Vale o primeiro que responder COM a identidade certa. Quem responde
  /// num endereço candidato com outro certificado não é alarme: só não é ele.
  Future<_Reached> _reach(TelescopeApi api, SavedDevice? device) {
    final done = Completer<_Reached>();
    final probes = <TelescopeApi>[];
    ApiFailure? failure;
    var open = 1; // tentativas ainda sem resposta
    var searched = device == null; // sem aparelho guardado (demonstração) não há onde procurar

    void finish() {
      if (open > 0 || !searched || done.isCompleted) return;
      done.completeError(failure ?? const ApiFailure(FailureKind.unreachable));
    }

    void search() {
      if (searched || done.isCompleted) return;
      searched = true;
      final build = ref.read(apiFactoryProvider);
      for (final host in _elsewhere(device!)) {
        final probe = build(device.copyWith(host: host));
        probes.add(probe);
        open++;
        probe.info().then(
          (info) {
            open--;
            if (info.id == device.deviceId && !done.isCompleted) {
              done.complete(_Reached(probe, host, info));
            } else {
              finish();
            }
          },
          onError: (Object _) {
            open--;
            finish();
          },
        );
      }
      finish();
    }

    final headStart = Timer(_headStart, search);
    api.info().then(
      (info) {
        open--;
        if (!done.isCompleted) done.complete(_Reached(api, null, info));
      },
      onError: (Object error) {
        open--;
        failure = error is ApiFailure ? error : const ApiFailure(FailureKind.unreachable);
        search(); // não está onde estava: procura já
        finish();
      },
    );

    void discard(TelescopeApi? winner) {
      headStart.cancel();
      for (final probe in probes) {
        if (!identical(probe, winner) && !identical(probe, api)) probe.close();
      }
    }

    return done.future.then(
      (reached) {
        discard(reached.api);
        return reached;
      },
      onError: (Object error) {
        discard(null);
        throw error;
      },
    );
  }

  /// O telescópio respondeu em OUTRO endereço: passa a falar por lá e guarda, para a próxima
  /// vez começar por ele.
  Future<void> _moveTo(_Reached reached) async {
    final moved = state.device!.copyWith(host: reached.host);
    final old = _api;
    unawaited(_subscription?.cancel());
    _subscription = null;
    _api = reached.api;
    state = Link(
      phase: state.phase,
      device: moved,
      api: reached.api,
      info: state.info,
      telescope: state.telescope,
      updatedAt: state.updatedAt,
      lostAt: state.lostAt,
    );
    if (!identical(old, reached.api)) old?.close();
    await _store((store) => store.save(moved));
  }

  /// Enquanto o telescópio não responde, escuta os anúncios da rede: se ele aparecer em outro
  /// endereço, tenta por lá sem esperar o próximo ciclo.
  void _search() {
    if (_discovery != null || state.demo || state.device == null) return;
    _discovery = ref.read(discoveryProvider).watch().listen(
      (found) {
        final device = state.device;
        if (device == null) return;
        final hosts = {
          for (final f in found)
            if (f.deviceId == device.deviceId) f.host,
        }.take(_maxAnnounced).toSet();
        final fresh = hosts.difference(_found).isNotEmpty;
        _found = hosts;
        if (fresh && !state.online) {
          _announced ??= Timer(_announceGap, () {
            _announced = null;
            if (!state.online) retryNow();
          });
        }
      },
      onError: (Object _) {}, // sem a busca, o app segue pelos endereços que já conhece
    );
  }

  void _stopSearch() {
    _announced?.cancel();
    _announced = null;
    unawaited(_discovery?.cancel());
    _discovery = null;
  }

  /// O dono fica sabendo o nome, a senha e o endereço do WiFi que o telescópio cria. O app os
  /// guarda (a senha, no cofre do sistema) para reencontrá-lo no campo, onde não há roteador
  /// nem o QR à mão.
  Future<void> _learnWifi(TelescopeApi api) async {
    if (state.demo || state.device == null) return;
    try {
      final hotspot = (await api.network()).hotspot;
      final psk = hotspot?.psk;
      final device = state.device;
      if (hotspot == null || psk == null || hotspot.ssid.isEmpty || device == null) return;
      if (!identical(api, state.api)) return;
      final address = hotspot.address.isEmpty ? device.wifiHost : hotspot.address;
      if (device.wifiSsid == hotspot.ssid && device.wifiPsk == psk && device.wifiHost == address) return;
      final learned = device.copyWith(wifiSsid: hotspot.ssid, wifiPsk: psk, wifiHost: address);
      await _store((store) => store.save(learned));
      if (identical(api, state.api)) state = state.copyWith(device: learned);
    } on ApiFailure {
      // um operador não recebe a senha; um telescópio mais antigo não tem a rota
    }
  }

  /// Relê o WiFi do telescópio (depois de mudar a senha dele, por exemplo).
  Future<void> refreshWifi() async {
    final api = state.api;
    if (api != null) await _learnWifi(api);
  }

  void _listen(TelescopeApi api) {
    unawaited(_subscription?.cancel());
    _subscription = api.watch().listen(
      (telescope) {
        if (!identical(api, state.api)) return;
        state = state.copyWith(phase: LinkPhase.online, telescope: telescope, updatedAt: _now, clearLost: true);
      },
      onError: (Object error) {
        if (identical(api, state.api)) {
          _onFailure(error is ApiFailure ? error : const ApiFailure(FailureKind.unreachable));
        }
      },
      onDone: () {
        if (identical(api, state.api)) _onFailure(const ApiFailure(FailureKind.unreachable));
      },
      cancelOnError: true,
    );
  }

  void _onFailure(ApiFailure failure) {
    unawaited(_subscription?.cancel());
    _subscription = null;
    switch (failure.kind) {
      case FailureKind.identityMismatch:
        state = state.copyWith(phase: LinkPhase.identityChanged);
      case FailureKind.unauthorized:
        state = state.copyWith(phase: LinkPhase.revoked);
      default:
        state = state.copyWith(
          phase: _everOnline ? LinkPhase.reconnecting : LinkPhase.offline,
          lostAt: state.lostAt ?? _now,
        );
        _search();
        final wait = _backoff[_attempt.clamp(0, _backoff.length - 1)];
        _attempt++;
        _retry?.cancel();
        _retry = Timer(Duration(seconds: wait), _connect);
    }
  }

  /// A cada conexão o celular manda a hora (sempre) e o último local conhecido: no campo a
  /// Jetson não tem internet nem GPS, e a montagem acorda achando que é o ano 2000.
  Future<void> _sendSite(TelescopeApi api, TelescopeInfo info) async {
    final prefs = ref.read(prefsProvider);
    if (!prefs.hasSite) return;
    try {
      await api.setSite(utc: _now.toUtc(), lat: prefs.siteLat!, lon: prefs.siteLon!, elevM: prefs.siteElevM);
    } on ApiFailure {
      // não é motivo para derrubar a ligação: a tela de local e hora mostra que falta enviar
    }
  }

  /// Manda o local escolhido na tela "Local e hora" e o guarda para as próximas conexões.
  Future<SiteResult> sendSite({required double lat, required double lon, double elevM = 0, double? accuracyM}) async {
    final api = state.api;
    if (api == null) throw const ApiFailure(FailureKind.unreachable);
    final result = await api.setSite(utc: _now.toUtc(), lat: lat, lon: lon, elevM: elevM, accuracyM: accuracyM);
    await ref.read(prefsProvider.notifier).setSite(lat, lon, elevM);
    final info = await api.info();
    if (identical(api, state.api)) state = state.copyWith(info: info);
    return result;
  }

  /// Relê o cartão do aparelho (depois de dar outro nome a ele, por exemplo).
  Future<void> refreshInfo() async {
    final api = state.api;
    if (api == null) return;
    final info = await api.info();
    if (identical(api, state.api)) state = state.copyWith(info: info);
  }

  void _release() {
    _retry?.cancel();
    _stopSearch();
    _found = {};
    unawaited(_subscription?.cancel());
    _subscription = null;
    _api?.close();
    _api = null;
  }
}
