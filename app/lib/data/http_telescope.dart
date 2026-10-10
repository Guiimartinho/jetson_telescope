import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import '../core/errors.dart';
import '../domain/live_state.dart';
import '../domain/models.dart';
import '../domain/pairing.dart';
import 'mjpeg.dart';
import 'telescope_api.dart';

/// Um cliente HTTPS que só aceita UM certificado: o do aparelho pareado.
///
/// Não há autoridade certificadora nesta história. O contexto nasce SEM raízes confiáveis, então
/// todo certificado "falha" na conferência comum e cai no nosso teste: a impressão digital
/// (SHA-256) tem de ser a que veio no QR. Assim nem um certificado válido de verdade, emitido
/// para outro, passa. E só TLS 1.3.
///
/// As datas do certificado não importam (a confiança é a chave fixada): no campo a Jetson pode
/// ligar achando que é o ano 2000, e é por esta conexão que o celular acerta a hora dela.
class PinnedClient {
  PinnedClient(Uint8List fingerprint, {Duration connectTimeout = const Duration(seconds: 6)})
    : _fingerprint = fingerprint {
    final context = SecurityContext(withTrustedRoots: false)..minimumTlsProtocolVersion = TlsProtocolVersion.tls1_3;
    http = HttpClient(context: context)
      ..connectionTimeout = connectTimeout
      ..idleTimeout = const Duration(seconds: 20)
      ..badCertificateCallback = (certificate, host, port) {
        final ok = sameBytes(certificateFingerprint(certificate.der), _fingerprint);
        if (!ok) mismatch = true;
        return ok;
      };
  }

  final Uint8List _fingerprint;
  late final HttpClient http;

  /// Ficou verdadeiro: alguém respondeu com OUTRO certificado. Possível impostor.
  bool mismatch = false;

  void close() => http.close(force: true);
}

/// O que o pareamento devolve: o bastante para falar com o aparelho daqui em diante.
class Paired {
  const Paired({required this.token, required this.clientId, required this.role, required this.deviceId});

  final String token;
  final String clientId;
  final String role;
  final String deviceId;
}

/// O telescópio de verdade: REST + WebSocket sobre TLS 1.3 com o certificado fixado.
class HttpTelescope implements TelescopeApi {
  HttpTelescope({
    required this.host,
    required this.port,
    required Uint8List fingerprint,
    this.token,
    this.timeout = const Duration(seconds: 12),
  }) : _pinned = PinnedClient(fingerprint);

  final String host;
  final int port;

  /// Nulo só durante o pareamento (as rotas dele não pedem token).
  final String? token;
  final Duration timeout;
  final PinnedClient _pinned;

  // ------------------------------------------------------------------ transporte
  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri(scheme: 'https', host: host, port: port, path: '/api/v1$path', queryParameters: query);

  Future<HttpClientResponse> _open(
    String method,
    String path, {
    Map<String, String>? query,
    Object? body,
    Duration? patience,
  }) async {
    _pinned.mismatch = false; // cada chamada é julgada por si: um impostor de antes não condena esta
    try {
      final request = await _pinned.http.openUrl(method, _uri(path, query)).timeout(timeout);
      if (token != null) request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $token');
      if (body != null) {
        final bytes = utf8.encode(jsonEncode(body));
        request.headers.contentType = ContentType.json;
        request.contentLength = bytes.length;
        request.add(bytes);
      }
      // `patience`: a Jetson pode levar um tempo montando um arquivo grande antes de responder
      return await request.close().timeout(patience ?? timeout);
    } on ApiFailure {
      rethrow;
    } on Object catch (error) {
      throw _failure(error);
    }
  }

  ApiFailure _failure(Object error) {
    if (_pinned.mismatch) {
      return const ApiFailure(FailureKind.identityMismatch, message: 'certificado diferente do pareado');
    }
    return ApiFailure(FailureKind.unreachable, message: '$error');
  }

  Future<Uint8List> _bytes(HttpClientResponse response, {Duration? patience}) async {
    final builder = BytesBuilder(copy: false);
    try {
      await response.forEach(builder.add).timeout(patience ?? timeout);
    } on Object catch (error) {
      throw _failure(error);
    }
    final bytes = builder.takeBytes();
    if (response.statusCode >= 400) throw _apiError(response.statusCode, bytes);
    return bytes;
  }

  static ApiFailure _apiError(int status, List<int> body) {
    try {
      final error = (jsonDecode(utf8.decode(body)) as Map)['error'] as Map;
      return ApiFailure.fromApi(status, '${error['code']}', '${error['message']}');
    } on Object {
      return ApiFailure.fromApi(status, '', 'HTTP $status');
    }
  }

  Future<Json> _json(String method, String path, {Map<String, String>? query, Object? body}) async {
    final bytes = await _bytes(await _open(method, path, query: query, body: body));
    final decoded = jsonDecode(utf8.decode(bytes));
    return decoded is Map ? decoded.cast<String, dynamic>() : <String, dynamic>{};
  }

  /// Imagem ou nada: "não tem" (404) não é erro para quem pede uma miniatura.
  Future<Uint8List?> _image(
    String method,
    String path, {
    Map<String, String>? query,
    Object? body,
    Duration? patience,
  }) async {
    try {
      return await _bytes(
        await _open(method, path, query: query, body: body, patience: patience),
        patience: patience,
      );
    } on ApiFailure catch (failure) {
      if (failure.kind == FailureKind.notFound) return null;
      rethrow;
    }
  }

  // ------------------------------------------------------------------ pareamento
  /// Pareia este celular: confere a identidade do aparelho (o certificado tem de ser o do QR),
  /// prova que tem o segredo sem enviá-lo e recebe o token. Ver `07-seguranca.md` §4.
  static Future<Paired> pair({
    required PairingCode code,
    required String host,
    required String clientName,
    Duration timeout = const Duration(seconds: 12),
  }) async {
    final api = HttpTelescope(host: host, port: code.port, fingerprint: code.fingerprint, timeout: timeout);
    try {
      final info = await api.info();
      if (info.id != code.deviceId) {
        throw const ApiFailure(FailureKind.identityMismatch, message: 'o aparelho não é o do código');
      }
      final started = await api._json('POST', '/pair/start', body: {'client_name': clientName});
      final nonce = b64uDecode('${started['nonce']}');
      final proof = pairingProof(code.secret, nonce, code.fingerprint, clientName);
      final done = await api._json('POST', '/pair/finish', body: {'client_name': clientName, 'proof': b64u(proof)});
      return Paired(
        token: '${done['token']}',
        clientId: '${done['client_id']}',
        role: '${done['role']}',
        deviceId: '${done['device_id']}',
      );
    } finally {
      api.close();
    }
  }

  // ------------------------------------------------------------------ aparelho
  @override
  Future<TelescopeInfo> info() async => TelescopeInfo.fromJson(await _json('GET', '/info'));

  @override
  Future<TelescopeState> state() async => TelescopeState.fromJson(await _json('GET', '/state'));

  @override
  Stream<TelescopeState> watch() async* {
    final WebSocket socket;
    try {
      socket = await WebSocket.connect(
        Uri(scheme: 'wss', host: host, port: port, path: '/api/v1/ws').toString(),
        headers: {HttpHeaders.authorizationHeader: 'Bearer $token'},
        customClient: _pinned.http,
      ).timeout(timeout);
    } on Object catch (error) {
      throw _failure(error);
    }
    socket.pingInterval = const Duration(seconds: 10); // nota a queda mesmo sem tráfego
    TelescopeState? current;
    try {
      await for (final raw in socket) {
        if (raw is! String) continue;
        final Object? message;
        try {
          message = jsonDecode(raw);
        } on FormatException {
          continue;
        }
        if (message is! Map) continue;
        current = applyLiveMessage(current, message.cast<String, dynamic>());
        yield current;
      }
    } finally {
      unawaited(socket.close());
    }
    // A Jetson fecha com 4401 quando o token deixa de valer (celular revogado).
    if (socket.closeCode == 4401) {
      throw const ApiFailure(FailureKind.unauthorized, code: 'unauthorized', status: 401);
    }
    throw const ApiFailure(FailureKind.unreachable, message: 'o canal em tempo real caiu');
  }

  @override
  Future<SiteResult> setSite({
    required DateTime utc,
    required double lat,
    required double lon,
    double elevM = 0,
    double? accuracyM,
  }) async => SiteResult.fromJson(
    await _json(
      'POST',
      '/site',
      body: {'utc': utc.toUtc().toIso8601String(), 'lat': lat, 'lon': lon, 'elev_m': elevM, 'accuracy_m': ?accuracyM},
    ),
  );

  @override
  Future<SystemInfo> system() async => SystemInfo.fromJson(await _json('GET', '/system'));

  @override
  Future<void> power(String action) async => _json('POST', '/system/$action');

  @override
  Future<List<PairedClient>> clients() async {
    final body = await _json('GET', '/clients');
    return [
      for (final c in (body['items'] as List? ?? const [])) PairedClient.fromJson((c as Map).cast<String, dynamic>()),
    ];
  }

  @override
  Future<void> revoke(String clientId) async => _json('DELETE', '/clients/${Uri.encodeComponent(clientId)}');

  // ------------------------------------------------------------------ céu
  @override
  Future<TargetPage> targets({
    String query = '',
    String type = '',
    bool visible = false,
    bool fits = false,
    int limit = 50,
    int offset = 0,
  }) async => TargetPage.fromJson(
    await _json(
      'GET',
      '/targets',
      query: {
        if (query.isNotEmpty) 'q': query,
        if (type.isNotEmpty) 'type': type,
        if (visible) 'visible': '1',
        if (fits) 'fits': '1',
        'limit': '$limit',
        'offset': '$offset',
      },
    ),
  );

  @override
  Future<TargetDetail> target(String id) async =>
      TargetDetail.fromJson(await _json('GET', '/targets/${Uri.encodeComponent(id)}'));

  @override
  Future<Uint8List?> targetThumb(String id) => _image('GET', '/targets/${Uri.encodeComponent(id)}/thumb');

  // ------------------------------------------------------------------ observar
  @override
  Future<Job> goTo({required String commandId, String? target, double? raDeg, double? decDeg}) async => Job.fromJson(
    await _json(
      'POST',
      '/observe/goto',
      body: {'id': commandId, 'target': ?target, 'ra_deg': ?raDeg, 'dec_deg': ?decDeg},
    ),
  );

  @override
  Future<Job> observe({required String commandId, required String target}) async =>
      Job.fromJson(await _json('POST', '/observe/target', body: {'id': commandId, 'target': target}));

  @override
  Future<Job> stack({required String commandId, double? exposureS, int? gain, int frames = 0}) async => Job.fromJson(
    await _json(
      'POST',
      '/observe/stack',
      body: {'id': commandId, 'exposure_s': ?exposureS, 'gain': ?gain, 'frames': frames},
    ),
  );

  @override
  Future<Job> run({required String commandId, required String mode, String? target}) async =>
      Job.fromJson(await _json('POST', '/observe/run', body: {'id': commandId, 'mode': mode, 'target': ?target}));

  @override
  Future<Job> stop({required String commandId}) async =>
      Job.fromJson(await _json('POST', '/observe/stop', body: {'id': commandId}));

  @override
  Stream<Uint8List> preview({int maxSide = 1280}) async* {
    final response = await _open('GET', '/preview.mjpg', query: {'max_side': '$maxSide'});
    if (response.statusCode >= 400) throw _apiError(response.statusCode, await _drain(response));
    try {
      yield* response.transform(const MjpegSplitter());
    } on ApiFailure {
      rethrow;
    } on Object catch (error) {
      throw _failure(error);
    }
  }

  static Future<List<int>> _drain(HttpClientResponse response) async {
    final builder = BytesBuilder(copy: false);
    await response.forEach(builder.add);
    return builder.takeBytes();
  }

  @override
  Future<Uint8List?> frame({int maxSide = 1280}) => _image('GET', '/frame.jpg', query: {'max_side': '$maxSide'});

  @override
  Future<List<double>> histogram() async {
    final body = await _json('GET', '/histogram');
    return [for (final v in (body['bins'] as List? ?? const [])) (v as num).toDouble()];
  }

  @override
  Future<Job> startPreview({required String commandId}) async =>
      Job.fromJson(await _json('POST', '/observe/preview', body: {'id': commandId}));

  @override
  Future<Job> autofocus({required String commandId}) async =>
      Job.fromJson(await _json('POST', '/observe/focus', body: {'id': commandId}));

  // ------------------------------------------------------------------ à mão
  @override
  Future<void> jog(String direction, {int rate = 2, int holdMs = 800}) async =>
      _json('POST', '/mount/slew', body: {'dir': direction, 'rate': rate, 'hold_ms': holdMs});

  @override
  Future<void> haltMount() async => _json('POST', '/mount/stop');

  @override
  Future<void> mountAction(String action) async => _json('POST', '/mount/${Uri.encodeComponent(action)}');

  @override
  Future<void> setTracking({required bool on}) async => _json('POST', '/mount/tracking', body: {'on': on});

  @override
  Future<int> moveFocus({int? delta, int? position}) async {
    final body = await _json('POST', '/focuser', body: {'delta': ?delta, 'position': ?position});
    return (body['position'] as num?)?.toInt() ?? 0;
  }

  @override
  Future<CameraInfo> camera() async => CameraInfo.fromJson(await _json('GET', '/camera'));

  @override
  Future<CameraInfo> setCamera({double? exposureS, int? gain, int? offset}) async => CameraInfo.fromJson(
    await _json('POST', '/camera', body: {'exposure_s': ?exposureS, 'gain': ?gain, 'offset': ?offset}),
  );

  // ------------------------------------------------------------------ sistema solar
  @override
  Future<List<SolarBody>> solar() async {
    final body = await _json('GET', '/solar');
    return [
      for (final b in (body['items'] as List? ?? const [])) SolarBody.fromJson((b as Map).cast<String, dynamic>()),
    ];
  }

  @override
  Future<Job> goToBody({required String commandId, required String body, bool filterConfirmed = false}) async =>
      Job.fromJson(
        await _json(
          'POST',
          '/observe/body',
          body: {'id': commandId, 'body': body, 'filter_confirmed': filterConfirmed},
        ),
      );

  // ------------------------------------------------------------------ plano
  @override
  Future<NightPlan> plan() async => NightPlan.fromJson(await _json('GET', '/plan'));

  @override
  Future<NightPlan> savePlan(List<PlanItem> items) async => NightPlan.fromJson(
    await _json(
      'PUT',
      '/plan',
      body: {
        'items': [for (final item in items) item.toJson()],
      },
    ),
  );

  @override
  Future<Job> startPlan({required String commandId}) async =>
      Job.fromJson(await _json('POST', '/plan/start', body: {'id': commandId}));

  @override
  Future<void> skipPlanItem() async => _json('POST', '/plan/skip');

  @override
  Future<MosaicGrid> mosaic({required String target, int rows = 2, int cols = 2, double overlap = 0.15}) async =>
      MosaicGrid.fromJson(
        await _json('POST', '/mosaic', body: {'target': target, 'rows': rows, 'cols': cols, 'overlap': overlap}),
      );

  // ------------------------------------------------------------------ celulares e aparelho
  @override
  Future<void> setRole(String clientId, String role) async =>
      _json('PATCH', '/clients/${Uri.encodeComponent(clientId)}', body: {'role': role});

  @override
  Future<Invite> invite({String role = 'operator', int minutes = 5}) async =>
      Invite.fromJson(await _json('POST', '/clients/invite', body: {'role': role, 'minutes': minutes}));

  @override
  Future<String> rename(String name) async => '${(await _json('PUT', '/device', body: {'name': name}))['name']}';

  // ------------------------------------------------------------------ planetária e polar
  @override
  Future<Job> capturePlanetary({
    required String commandId,
    required String body,
    int frames = 300,
    int keepPercent = 15,
    bool point = true,
  }) async => Job.fromJson(
    await _json(
      'POST',
      '/observe/planetary',
      body: {'id': commandId, 'body': body, 'frames': frames, 'keep_percent': keepPercent, 'point': point},
    ),
  );

  @override
  Future<Job> measurePolar({required String commandId}) async =>
      Job.fromJson(await _json('POST', '/observe/polar', body: {'id': commandId}));

  @override
  Future<void> adjustPolar({required double altArcmin, required double azArcmin}) async =>
      _json('POST', '/mount/polar/adjust', body: {'alt_arcmin': altArcmin, 'az_arcmin': azArcmin});

  // ------------------------------------------------------------------ rede
  @override
  Future<NetworkInfo> network() async => NetworkInfo.fromJson(await _json('GET', '/network'));

  @override
  Future<List<WifiNetwork>> scanNetworks() async {
    final body = await _json('GET', '/network/scan');
    return [
      for (final n in (body['items'] as List? ?? const [])) WifiNetwork.fromJson((n as Map).cast<String, dynamic>()),
    ];
  }

  @override
  Future<NetworkChange> joinNetwork(String ssid, {String? psk}) async =>
      NetworkChange.fromJson(await _json('POST', '/network/join', body: {'ssid': ssid, 'psk': ?psk}));

  @override
  Future<NetworkChange> setNetworkMode(String mode) async =>
      NetworkChange.fromJson(await _json('POST', '/network/mode', body: {'mode': mode}));

  @override
  Future<void> setHotspotPassword(String psk) async => _json('POST', '/network/hotspot', body: {'psk': psk});

  @override
  Future<void> forgetNetwork(String ssid) async => _json('DELETE', '/network/known/${Uri.encodeComponent(ssid)}');

  // ------------------------------------------------------------------ atualização
  @override
  Future<UpdateInfo> update() async => UpdateInfo.fromJson(await _json('GET', '/system/update'));

  @override
  Future<UpdateInfo> checkUpdate() async => UpdateInfo.fromJson(await _json('POST', '/system/update/check'));

  @override
  Future<UpdateInfo> installUpdate() async => UpdateInfo.fromJson(await _json('POST', '/system/update/install'));

  // ------------------------------------------------------------------ galeria
  @override
  Future<Uint8List?> exportSession(String id, {String format = 'jpg', int maxSide = 0}) => _image(
    'GET',
    '/sessions/${Uri.encodeComponent(id)}/export',
    query: {'format': format, if (maxSide > 0) 'max_side': '$maxSide'},
    // um TIFF ou FITS cheio é grande: o prazo curto das outras chamadas não serve aqui
    patience: const Duration(minutes: 3),
  );

  @override
  Future<void> deleteSession(String id) async => _json('DELETE', '/sessions/${Uri.encodeComponent(id)}');

  @override
  Future<List<Session>> sessions() async {
    final body = await _json('GET', '/sessions');
    return [for (final s in (body['items'] as List? ?? const [])) Session.fromJson((s as Map).cast<String, dynamic>())];
  }

  @override
  Future<Uint8List?> sessionImage(String id, {bool thumb = false}) =>
      _image('GET', '/sessions/${Uri.encodeComponent(id)}/image', query: {if (thumb) 'thumb': '1'});

  @override
  Future<Uint8List?> render(String sessionId, Map<String, Object> controls) =>
      _image('POST', '/sessions/${Uri.encodeComponent(sessionId)}/render', body: controls);

  @override
  Future<RenderPresets> presets() async => RenderPresets.fromJson(await _json('GET', '/render/presets'));

  @override
  void close() => _pinned.close();
}
