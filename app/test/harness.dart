import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:telescope_app/app/app.dart';
import 'package:telescope_app/app/link.dart';
import 'package:telescope_app/app/notices.dart';
import 'package:telescope_app/app/prefs.dart';
import 'package:telescope_app/core/errors.dart';
import 'package:telescope_app/core/widgets/kit.dart';
import 'package:telescope_app/data/alerts.dart';
import 'package:telescope_app/data/device_store.dart';
import 'package:telescope_app/data/discovery.dart';
import 'package:telescope_app/data/fake_telescope.dart';
import 'package:telescope_app/data/file_sharer.dart';
import 'package:telescope_app/data/http_telescope.dart';
import 'package:telescope_app/data/location.dart';
import 'package:telescope_app/data/telescope_wifi.dart';
import 'package:telescope_app/domain/pairing.dart';

/// Um instante fixo para os testes: 22h30 em São Paulo, em outubro.
final testNow = DateTime.utc(2026, 10, 10, 1, 30);

/// `SCREENSHOTS=1 flutter test --update-goldens` grava as telas em test/screens, para olhar.
final bool screenshots = Platform.environment['SCREENSHOTS'] == '1';

SavedDevice savedDevice() => SavedDevice(
  deviceId: 'tele-0b04',
  name: 'Telescópio',
  host: '192.168.3.221',
  port: 8443,
  fingerprint: Uint8List.fromList(List.generate(32, (i) => i)),
  token: 'token-de-teste',
);

class FakeLocation implements LocationSource {
  FakeLocation({this.problem});

  LocationProblem? problem;

  @override
  Future<GeoFix> current() async {
    if (problem != null) throw LocationFailure(problem!);
    return const GeoFix(lat: -22.9, lon: -43.2, elevM: 12, accuracyM: 15);
  }
}

class FakeWifi implements TelescopeWifi {
  FakeWifi([this.result = WifiJoin.joined]);

  WifiJoin result;
  final joined = <String>[];

  /// A senha com que o app pediu para entrar, da última vez.
  String? lastPsk;

  /// O que muda no mundo quando o celular entra no WiFi (o telescópio passa a responder lá).
  void Function()? onJoin;

  @override
  Future<WifiJoin> join(String ssid, String psk) async {
    joined.add(ssid);
    lastPsk = psk;
    if (result == WifiJoin.joined) onJoin?.call();
    return result;
  }

  @override
  Future<void> leave() async {}
}

/// No lugar da folha de compartilhar do Android: guarda o que o app mandou salvar ou enviar.
class FakeSharer implements FileSharer {
  final shared = <(String name, String mimeType, int bytes)>[];

  @override
  Future<bool> share(Uint8List bytes, {required String name, required String mimeType}) async {
    shared.add((name, mimeType, bytes.length));
    return true;
  }
}

/// Um cofre que demora a gravar, como o de verdade num celular ocupado.
class SlowStore extends MemoryDeviceStore {
  SlowStore(super.device, {this.delay = const Duration(seconds: 1)});

  final Duration delay;

  @override
  Future<void> save(SavedDevice device) async {
    await Future<void>.delayed(delay);
    await super.save(device);
  }
}

/// No lugar da busca na rede: os testes dizem quem está se anunciando.
class FakeDiscovery implements Discovery {
  final _changes = StreamController<List<FoundTelescope>>.broadcast();
  var _latest = const <FoundTelescope>[];

  /// Quantos estão escutando agora (a busca só deve rodar enquanto há quem escute).
  int get listeners => _listeners;
  var _listeners = 0;

  void announce(List<FoundTelescope> found) {
    _latest = found;
    _changes.add(found);
  }

  @override
  Stream<List<FoundTelescope>> watch() async* {
    _listeners++;
    try {
      yield _latest;
      yield* _changes.stream;
    } finally {
      _listeners--;
    }
  }
}

/// No lugar dos avisos do Android: guarda o que o app mandou mostrar.
class FakeAlerts implements Alerts {
  FakeAlerts({this.allowed = true});

  /// A pessoa deixa o app mostrar avisos?
  bool allowed;
  final notices = <AppNotice>[];

  /// O aviso fixo de agora (título, texto); nulo quando não há.
  (String, String)? ongoingNow;
  final ongoingLog = <String>[];
  var asked = 0;

  @override
  Future<bool> enable() async {
    asked++;
    return allowed;
  }

  @override
  Future<void> ongoing(String title, String text) async {
    ongoingNow = (title, text);
    ongoingLog.add(text);
  }

  @override
  Future<void> endOngoing() async => ongoingNow = null;

  @override
  Future<void> notify(AppNotice notice) async => notices.add(notice);
}

/// Toca no botão do produto com este rótulo (e não num título de mesmo texto).
Future<void> pressButton(WidgetTester tester, String label) async {
  final button = find.widgetWithText(AppButton, label).first;
  await tester.ensureVisible(button);
  await tester.pump();
  await tester.tap(button);
  await tester.pump();
}

/// Vai para um destino da barra de baixo.
Future<void> openTab(WidgetTester tester, String label) async {
  await tester.tap(find.bySemanticsLabel(label).last);
  await tester.pump(const Duration(milliseconds: 350));
}

/// Toca num texto, rolando a lista até ele aparecer se for preciso.
Future<void> pressText(WidgetTester tester, String text) async {
  final target = find.text(text).first;
  await tester.ensureVisible(target);
  await tester.pump();
  await tester.tap(target);
  await tester.pump();
}

/// O app inteiro, com o telescópio falso no lugar da rede. Devolve o que os testes mexem.
class Harness {
  Harness({
    SavedDevice? device,
    Map<String, Object> prefs = const {},
    this.pairer,
    this.noticeGiveUp,
    FakeLocation? location,
    FakeWifi? wifi,
    MemoryDeviceStore? store,
  }) : store = store ?? MemoryDeviceStore(device),
       _prefs = prefs,
       location = location ?? FakeLocation(),
       wifi = wifi ?? FakeWifi();

  final MemoryDeviceStore store;
  final Map<String, Object> _prefs;
  final Pairer? pairer;

  /// Depois de quanto tempo sem sinal os avisos desistem (o app usa 10 minutos).
  final Duration? noticeGiveUp;
  final FakeLocation location;
  final FakeWifi wifi;
  final sharer = FakeSharer();
  final discovery = FakeDiscovery();
  final alerts = FakeAlerts();

  /// O telescópio "de verdade" (o pareado) e o da demonstração: os dois são falsos aqui.
  final telescope = FakeTelescope(
    step: const Duration(milliseconds: 400),
    now: () => testNow,
    deviceId: 'tele-0b04', // o mesmo do `savedDevice()`
  );
  final demo = FakeTelescope(step: const Duration(milliseconds: 400), now: () => testNow);

  /// Em que endereços o telescópio pareado atende. Sem nada aqui, em qualquer um (é o caso da
  /// maioria dos testes); com algo, só nesses — e nos outros ninguém responde.
  final hosts = <String>{};
  final nowhere = FakeTelescope()..offline = true;

  /// Endereços em que responde OUTRO aparelho, com outro certificado.
  final impostors = <String>{};
  final impostor = FakeTelescope()..failure = const ApiFailure(FailureKind.identityMismatch);

  /// Os endereços em que o app foi procurar, na ordem.
  final asked = <String>[];
  late ProviderContainer container;

  Future<void> pump(WidgetTester tester, {Size size = const Size(412, 870)}) async {
    // ler arquivo é assíncrono de verdade: dentro do relógio falso dos testes nunca terminaria
    await tester.runAsync(_loadFonts);
    tester.view.physicalSize = size * 2;
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);
    SharedPreferences.setMockInitialValues(_prefs);
    final preferences = await SharedPreferences.getInstance();
    container = ProviderContainer(
      overrides: [
        sharedPreferencesProvider.overrideWithValue(preferences),
        deviceStoreProvider.overrideWithValue(store),
        apiFactoryProvider.overrideWithValue((device) {
          asked.add(device.host);
          if (impostors.contains(device.host)) return impostor;
          return hosts.isEmpty || hosts.contains(device.host) ? telescope : nowhere;
        }),
        discoveryProvider.overrideWithValue(discovery),
        alertsProvider.overrideWithValue(alerts),
        if (noticeGiveUp != null) noticeGiveUpProvider.overrideWithValue(noticeGiveUp!),
        demoFactoryProvider.overrideWithValue(() => demo),
        clockProvider.overrideWithValue(() => testNow),
        locationProvider.overrideWithValue(location),
        telescopeWifiProvider.overrideWithValue(wifi),
        fileSharerProvider.overrideWithValue(sharer),
        if (pairer != null) pairerProvider.overrideWithValue(pairer!),
      ],
    );
    await tester.pumpWidget(UncontrolledProviderScope(container: container, child: const TelescopeApp()));
    await settle(tester);
    // a transição da abertura para a primeira tela: até ela acabar, a tela está deslocada
    await tester.pump(const Duration(milliseconds: 400));
    await settle(tester);
  }

  /// Deixa as buscas e as imagens terminarem (decodificar imagem é assíncrono de verdade).
  Future<void> settle(WidgetTester tester, [int rounds = 3]) async {
    for (var i = 0; i < rounds; i++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 40)));
      await tester.pump(const Duration(milliseconds: 20));
    }
  }

  /// Depois de um toque que troca de página: um quadro para a página nova nascer, e o tempo
  /// da transição (durante ela as duas páginas estão sobrepostas e deslocadas).
  Future<void> route(WidgetTester tester) async {
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await settle(tester);
  }

  /// O sinal cai: o telescópio para de responder e o canal em tempo real se desfaz. A queda só
  /// chega ao app depois de uma volta do relógio DE VERDADE (cancelar a escuta termina fora do
  /// tempo simulado dos testes): por isso o `settle`.
  Future<void> loseSignal(WidgetTester tester) async {
    telescope
      ..offline = true
      ..drop();
    await settle(tester);
  }

  /// Desmonta o app: fecha a ligação e cancela os temporizadores do telescópio falso.
  Future<void> close(WidgetTester tester) async {
    await tester.pumpWidget(const SizedBox());
    container.dispose();
    telescope.close();
    demo.close();
    nowhere.close();
    impostor.close();
    await tester.pump(const Duration(seconds: 1));
  }

  Future<void> shot(WidgetTester tester, String name) async {
    if (!screenshots) return;
    await settle(tester);
    autoUpdateGoldenFiles = true;
    await expectLater(find.byType(TelescopeApp), matchesGoldenFile('screens/$name.png'));
  }
}

/// O pareamento de mentira dos testes: aceita qualquer código, ou falha como mandarem.
Pairer fakePairer({Object? failure}) =>
    ({required PairingCode code, required String host, required String clientName}) async {
      if (failure != null) throw failure;
      return Paired(token: 'token-novo', clientId: 'c-1', role: 'owner', deviceId: code.deviceId);
    };

bool _fontsLoaded = false;

/// Nos testes o Flutter desenha texto com quadradinhos; para as capturas mostrarem o app como
/// ele é, carrega o Roboto que vem com o próprio SDK.
Future<void> _loadFonts() async {
  if (_fontsLoaded) return;
  _fontsLoaded = true;
  final root = Platform.environment['FLUTTER_ROOT'];
  if (root == null) return;
  final loader = FontLoader('Roboto');
  for (final name in ['roboto-regular', 'roboto-medium', 'roboto-bold']) {
    final file = File('$root/bin/cache/artifacts/material_fonts/$name.ttf');
    if (file.existsSync()) loader.addFont(file.readAsBytes().then((b) => ByteData.view(Uint8List.fromList(b).buffer)));
  }
  await loader.load();
}
