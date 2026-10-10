import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import '../core/errors.dart';
import '../domain/ephemeris.dart';
import '../domain/models.dart';
import 'png.dart';
import 'telescope_api.dart';

/// O telescópio falso: obedece ao mesmo contrato da API, sem rede e sem aparelho.
///
/// É o **modo demonstração** do app (conhecer o produto sem telescópio) e o que os testes de
/// tela usam. O céu é de verdade — um punhado de alvos com as coordenadas reais, e a altitude
/// calculada para o local e a hora —, as imagens são desenhadas aqui mesmo, e os comandos
/// seguem o ciclo real: apontar, reconhecer o céu, empilhar, parar.
class FakeTelescope implements TelescopeApi {
  FakeTelescope({
    this.step = const Duration(milliseconds: 900),
    DateTime Function()? now,
    this.lat = -23.55,
    this.lon = -46.63,
    this.deviceId = 'tele-demo',
  }) : _now = now ?? DateTime.now;

  /// Como este telescópio se identifica (os testes dão o do aparelho pareado).
  final String deviceId;

  /// Quanto dura cada etapa simulada (apontar, reconhecer, uma foto).
  final Duration step;
  final DateTime Function() _now;
  double lat;
  double lon;

  /// Os testes ligam isto para ver o app lidar com um goto que não converge.
  bool gotoFails = false;

  /// Os testes põem uma falha aqui para ver o app lidar com ela: toda chamada passa a falhar
  /// assim (fora do ar, identidade trocada, celular revogado).
  ApiFailure? failure;

  set offline(bool value) =>
      failure = value ? const ApiFailure(FailureKind.unreachable, message: 'demonstração fora do ar') : null;

  /// Os testes usam isto para ver o app diante de uma montagem DE VERDADE, que o telescópio
  /// já lê mas ainda não comanda: aparece na tela, sem nada para mexer.
  void pretendRealMount() =>
      _emit(_with(mount: const MountState(source: 'indi', connected: true, raDeg: 83.82, decDeg: -5.39)));

  /// Derruba o canal em tempo real, como uma queda de sinal (ou com a falha indicada).
  void drop([ApiFailure cause = const ApiFailure(FailureKind.unreachable)]) {
    if (!_closed) _changes.addError(cause);
  }

  /// Os testes ligam isto para ver o app lidar com um autofoco que não acha estrela.
  bool focusFails = false;

  /// Idem para uma medida do eixo polar que não fecha.
  bool polarFails = false;

  /// Idem para uma atualização que falha no meio (a versão de antes tem de continuar valendo).
  bool updateFails = false;

  /// Trocar de rede e reiniciar derrubam a ligação, como no aparelho de verdade. Na
  /// demonstração fica desligado, para a conversa não ser interrompida.
  bool dropsLink = false;

  /// Os testes desligam para ver o app diante de um telescópio que ainda não troca de rede
  /// nem se atualiza pelo app — como o de verdade, hoje.
  bool networkEnabled = true;
  bool updatesEnabled = true;

  /// Os testes desligam para ver o app na mão de quem não é dono.
  bool owner = true;

  /// Os testes põem uma demora aqui para ver o app diante de uma rede lenta: é quanto `info` e
  /// `network` levam para responder (ou para falhar).
  Duration? latency;

  Future<void> _lag() async {
    if (latency case final Duration wait) await Future<void>.delayed(wait);
  }

  /// Onde o foco fica nítido — escondido de quem foca, como no simulador da Jetson.
  static const focusBest = 6300;
  static const _mountFeatures = ['jog', 'park', 'tracking', 'home', 'polar'];

  /// As redes ao alcance do telescópio de mentira: nome -> (senha, ou nulo se aberta; sinal).
  static const nearbyNetworks = <String, (String?, int)>{
    'Casa': ('senha-de-casa', 78),
    'Vizinho 5G': ('outra-senha', 41),
    'Visitantes': (null, 55),
  };
  static const hotspotSsid = 'Telescopio-demo';
  static const newerVersion = '1.1.0';
  static const _cameraLimits = {'exposure_s': (0.001, 600.0), 'gain': (0.0, 600.0), 'offset': (0.0, 255.0)};

  var _state = const TelescopeState(
    backend: 'CuPy/GPU (demonstração)',
    focusPos: focusBest,
    camera: CameraState(connected: true, model: 'demonstração'),
    mount: MountState(tracking: true, parked: false, features: _mountFeatures),
    focus: FocusState(position: focusBest, min: 0, max: 10000),
  );
  final _changes = StreamController<TelescopeState>.broadcast();
  final _frames = StreamController<Uint8List>.broadcast();
  final _jobs = <String, Job>{};
  final _images = <String, Uint8List>{};
  Timer? _timer;
  Timer? _jogTimer;
  var _jobCount = 0;
  var _synced = false;
  var _closed = false;
  var _skip = false;
  String _target = 'M8';
  String _name = 'Demonstração';

  // o eixo polar da montagem de mentira nasce desalinhado, como o do simulador da Jetson
  var _polarAlt = 38.0;
  var _polarAz = -52.0;

  // a rede: começa no WiFi próprio, sem nenhuma rede de casa guardada
  var _netMode = 'field';
  String? _netWifi;
  final _netKnown = <String, String?>{};
  var _hotspotPsk = 'ceu-estrelado';
  String? _netError;
  Timer? _netTimer;

  // a atualização
  var _software = '1.0.0';
  var _updateFound = false;
  var _updateState = 'idle';
  double? _updateProgress;
  String? _updateError;
  Timer? _updateTimer;

  /// O enquadramento manual: quanto a montagem foi levada para o lado, em passos.
  var _nudge = (0, 0);
  var _plan = <PlanItem>[];
  late var _clients = <PairedClient>[
    PairedClient(id: 'c-demo', name: 'Este celular', created: _now(), lastUsed: _now(), current: true),
  ];
  var _sessions = const [
    Session(id: 'demo-m8', target: 'M8 Lagoa', type: 'nebula', frames: 42, integrationS: 1260, source: 'demo'),
    Session(id: 'demo-m51', target: 'M51 Redemoinho', type: 'galaxy', frames: 96, integrationS: 2880, source: 'demo'),
    Session(id: 'demo-m42', target: 'M42 Órion', type: 'nebula', frames: 30, integrationS: 900, source: 'demo'),
  ];

  /// Comandos recebidos, na ordem (os testes conferem).
  final commands = <String>[];

  void _check() {
    if (failure case final ApiFailure f) throw f;
  }

  void _emit(TelescopeState next) {
    _state = next;
    if (!_closed) _changes.add(next);
  }

  TelescopeState _with({
    String? state,
    String? phase,
    Job? job,
    StackState? stack,
    Pointing? pointing,
    MountState? mount,
    CameraState? camera,
    FocusState? focus,
    List<NightItem>? night,
    QueueState? queue,
    CaptureState? Function()? capture,
    PolarState? Function()? polar,
  }) => TelescopeState(
    capture: capture == null ? _state.capture : capture(),
    polar: polar == null ? _state.polar : polar(),
    state: state ?? _state.state,
    phase: phase ?? _state.phase,
    backend: _state.backend,
    focusPos: (focus ?? _state.focus).position,
    job: job ?? _state.job,
    mount: mount ?? _state.mount,
    camera: camera ?? _state.camera,
    stack: stack ?? _state.stack,
    pointing: pointing ?? _state.pointing,
    queue: queue ?? _state.queue,
    system: const SystemState(tempC: 41.5, diskFreeGb: 200.1),
    focus: focus ?? _state.focus,
    night: night ?? _state.night,
  );

  /// O tamanho das estrelas para a posição atual do focalizador: mínimo no foco, crescendo
  /// para os dois lados (a curva em V que o autofoco percorre).
  double _fwhm([int? position]) =>
      ((2.9 + ((position ?? _state.focus.position) - focusBest).abs() / 350) * 10).roundToDouble() / 10;

  ApiFailure _conflict(String code) => ApiFailure(FailureKind.conflict, code: code, status: 409);

  // ------------------------------------------------------------------ aparelho
  @override
  Future<TelescopeInfo> info() async {
    await _lag();
    _check();
    return TelescopeInfo(
      id: deviceId,
      name: _name,
      software: 'demo',
      capabilities: const Capabilities(
        modes: ['stack', 'goto', 'night', 'preview', 'focus', 'plan', 'tracking'],
        gpu: 'CuPy/GPU (demonstração)',
      ),
      clockUtc: _now().toUtc(),
      clockSynced: _synced,
      site: Site(lat: lat, lon: lon, elevM: 760, source: _synced ? 'phone' : 'default'),
    );
  }

  @override
  Future<TelescopeState> state() async {
    _check();
    return _state;
  }

  @override
  Stream<TelescopeState> watch() async* {
    _check();
    yield _state;
    yield* _changes.stream;
  }

  @override
  Future<SiteResult> setSite({
    required DateTime utc,
    required double lat,
    required double lon,
    double elevM = 0,
    double? accuracyM,
  }) async {
    _check();
    this.lat = lat;
    this.lon = lon;
    _synced = true;
    return const SiteResult(clockSet: true);
  }

  @override
  Future<SystemInfo> system() async {
    _check();
    return SystemInfo(
      tempC: 41.5,
      diskFreeGb: 200.1,
      software: _software,
      deviceId: deviceId,
      updatesEnabled: updatesEnabled,
    );
  }

  @override
  Future<void> power(String action) async =>
      throw const ApiFailure(FailureKind.notSupported, code: 'not_enabled', status: 501);

  @override
  Future<List<PairedClient>> clients() async {
    _check();
    return List.of(_clients);
  }

  @override
  Future<void> revoke(String clientId) async {
    _check();
    commands.add('revoke:$clientId');
    _clients = [
      for (final c in _clients)
        if (c.id != clientId) c,
    ];
  }

  @override
  Future<void> setRole(String clientId, String role) async {
    _check();
    final client = _clients.where((c) => c.id == clientId).firstOrNull;
    if (client == null) throw const ApiFailure(FailureKind.notFound, code: 'not_found', status: 404);
    final owners = _clients.where((c) => c.role == 'owner').length;
    if (client.role == 'owner' && role != 'owner' && owners <= 1) throw _conflict('last_owner');
    commands.add('role:$clientId:$role');
    _clients = [
      for (final c in _clients)
        c.id == clientId
            ? PairedClient(
                id: c.id,
                name: c.name,
                role: role,
                created: c.created,
                lastUsed: c.lastUsed,
                current: c.current,
              )
            : c,
    ];
  }

  @override
  Future<Invite> invite({String role = 'operator', int minutes = 5}) async {
    _check();
    commands.add('invite:$role');
    // um convidado de mentira, para a lista ter com quem mexer na demonstração
    _clients = [
      ..._clients,
      PairedClient(
        id: 'c-${_clients.length}',
        name: 'Celular convidado',
        role: role,
        created: _now(),
        lastUsed: _now(),
      ),
    ];
    return Invite(
      uri: 'tele://pair?v=1&id=tele-demo&fp=ZGVtb25zdHJhY2Fv&s=Y29udml0ZQ&port=8443&host=demo',
      role: role,
      expiresS: minutes * 60,
      qrSvg:
          '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 5 5">'
          '<path d="M0 0h2v2H0zM3 0h2v2H3zM0 3h2v2H0zM2 2h1v1H2zM4 4h1v1H4z"/></svg>',
    );
  }

  @override
  Future<String> rename(String name) async {
    _check();
    commands.add('rename:$name');
    return _name = name.trim();
  }

  // ------------------------------------------------------------------ rede
  ApiFailure get _forbidden => const ApiFailure(FailureKind.forbidden, code: 'forbidden', status: 403);
  ApiFailure get _notEnabled => const ApiFailure(FailureKind.notSupported, code: 'not_enabled', status: 501);
  ApiFailure get _invalid => const ApiFailure(FailureKind.invalid, code: 'invalid_argument', status: 400);
  ApiFailure get _missing => const ApiFailure(FailureKind.notFound, code: 'not_found', status: 404);

  /// Só o dono mexe na rede e na atualização; e só onde isso já existe.
  void _ownerOnly(bool enabled) {
    _check();
    if (!owner) throw _forbidden;
    if (!enabled) throw _notEnabled;
  }

  @override
  Future<NetworkInfo> network() async {
    await _lag();
    _check();
    if (!networkEnabled) return const NetworkInfo(hostname: 'demonstração', address: 'sem aparelho');
    return NetworkInfo(
      enabled: true,
      mode: _netMode,
      hostname: 'demonstração',
      address: 'sem aparelho',
      port: 8443,
      wifiSsid: _netWifi,
      wifiSignal: nearbyNetworks[_netWifi]?.$2 ?? 0,
      // a senha do WiFi próprio é só do dono
      hotspot: Hotspot(
        ssid: hotspotSsid,
        active: _netMode == 'field',
        psk: owner ? _hotspotPsk : null,
        address: '10.42.0.1',
      ),
      known: _netKnown.keys.toList()..sort(),
      lastError: _netError,
      switching: _netTimer != null,
    );
  }

  @override
  Future<List<WifiNetwork>> scanNetworks() async {
    _ownerOnly(networkEnabled);
    return [
      for (final e in nearbyNetworks.entries)
        WifiNetwork(ssid: e.key, signal: e.value.$2, secure: e.value.$1 != null, known: _netKnown.containsKey(e.key)),
    ]..sort((a, b) => b.signal.compareTo(a.signal));
  }

  /// A troca acontece DEPOIS da resposta (o celular precisa ouvir "aceito" antes de a rede
  /// cair). Se a rede nova não der certo, o telescópio fica onde estava e conta o motivo.
  NetworkChange _switchLater(String mode, {String? ssid, String? psk}) {
    _netError = null;
    _netTimer?.cancel();
    _netTimer = Timer(step * 3, () {
      _netTimer = null;
      if (mode == 'field') {
        _netMode = 'field';
        _netWifi = null;
      } else {
        final real = nearbyNetworks[ssid];
        if (real == null) {
          _netError = 'not_found';
        } else if (real.$1 != null && real.$1 != psk) {
          _netError = 'wrong_password';
        } else {
          _netMode = 'home';
          _netWifi = ssid;
          _netKnown[ssid!] = psk;
        }
      }
      if (dropsLink) drop();
    });
    return const NetworkChange(accepted: true, reconnectS: 8);
  }

  @override
  Future<NetworkChange> joinNetwork(String ssid, {String? psk}) async {
    _ownerOnly(networkEnabled);
    final real = nearbyNetworks[ssid];
    if (real == null) throw _missing;
    final password = (psk ?? '').isEmpty ? _netKnown[ssid] : psk; // rede guardada dispensa a senha
    if (real.$1 != null && (password ?? '').isEmpty) throw _invalid;
    commands.add('net:join:$ssid');
    return _switchLater('home', ssid: ssid, psk: password);
  }

  @override
  Future<NetworkChange> setNetworkMode(String mode) async {
    _ownerOnly(networkEnabled);
    if (mode != 'home' && mode != 'field') throw _invalid;
    if (mode == _netMode && _netTimer == null) return const NetworkChange(accepted: true);
    if (mode == 'field') {
      commands.add('net:mode:field');
      return _switchLater('field');
    }
    final reachable = _netKnown.keys.where(nearbyNetworks.containsKey).toList()
      ..sort((a, b) => nearbyNetworks[b]!.$2.compareTo(nearbyNetworks[a]!.$2));
    if (reachable.isEmpty) throw _conflict('no_known_network');
    commands.add('net:mode:home');
    return _switchLater('home', ssid: reachable.first, psk: _netKnown[reachable.first]);
  }

  @override
  Future<void> setHotspotPassword(String psk) async {
    _ownerOnly(networkEnabled);
    if (psk.length < 8 || psk.length > 63) throw _invalid;
    commands.add('net:hotspot');
    _hotspotPsk = psk;
  }

  @override
  Future<void> forgetNetwork(String ssid) async {
    _ownerOnly(networkEnabled);
    if (!_netKnown.containsKey(ssid)) throw _missing;
    if (ssid == _netWifi) throw _conflict('in_use');
    commands.add('net:forget:$ssid');
    _netKnown.remove(ssid);
  }

  // ------------------------------------------------------------------ atualização
  UpdateInfo _update() => !updatesEnabled
      ? UpdateInfo(current: _software)
      : UpdateInfo(
          enabled: true,
          current: _software,
          available: _updateFound ? newerVersion : null,
          notes: _updateFound ? const ['Autofoco mais rápido', 'Correções na noite autônoma'] : const [],
          state: _updateState,
          progress: _updateProgress,
          error: _updateError,
        );

  @override
  Future<UpdateInfo> update() async {
    _check();
    return _update();
  }

  @override
  Future<UpdateInfo> checkUpdate() async {
    _ownerOnly(updatesEnabled);
    if (_update().working) throw _conflict('busy');
    commands.add('update:check');
    _updateState = 'checking';
    _updateError = null;
    _updateTimer?.cancel();
    _updateTimer = Timer(step * 2, () {
      _updateFound = _software != newerVersion;
      _updateState = 'idle';
    });
    return _update();
  }

  /// Baixa, instala e reinicia. Se falhar no meio, a versão de antes continua valendo.
  @override
  Future<UpdateInfo> installUpdate() async {
    _ownerOnly(updatesEnabled);
    if (_update().working || _state.busy) throw _conflict('busy');
    if (!_updateFound) throw _conflict('nothing_to_install');
    commands.add('update:install');
    _updateState = 'downloading';
    _updateProgress = 0;
    _updateError = null;
    _updateTimer?.cancel();
    _updateTimer = Timer.periodic(step, (timer) {
      if (_updateState == 'restarting') {
        timer.cancel();
        _software = newerVersion;
        _updateFound = false;
        _updateState = 'idle';
        if (dropsLink) drop();
        return;
      }
      final progress = ((_updateProgress ?? 0) * 10 + 2).round() / 10; // de 0,2 em 0,2, sem resto
      if (updateFails && progress >= 0.6) {
        timer.cancel();
        updateFails = false;
        _updateState = 'failed';
        _updateProgress = null;
        _updateError = 'install_failed';
      } else if (progress >= 1) {
        _updateState = 'restarting';
        _updateProgress = null;
      } else {
        _updateState = progress >= 0.4 ? 'installing' : 'downloading';
        _updateProgress = progress;
      }
    });
    return _update();
  }

  // ------------------------------------------------------------------ céu
  @override
  Future<TargetPage> targets({
    String query = '',
    String type = '',
    bool visible = false,
    bool fits = false,
    int limit = 50,
    int offset = 0,
  }) async {
    _check();
    final when = _now().toUtc();
    final needle = _fold(query);
    final rows = <Target>[
      for (final t in _catalog.map((t) => _withAltitude(t, when)))
        if ((!visible || t.isHigh) &&
            (type.isEmpty || t.type == type) &&
            (!fits || t.fits == true) &&
            (needle.isEmpty || _fold('${t.id}${t.catalog}${t.name}').contains(needle)))
          t,
    ]..sort((a, b) => b.altDeg.compareTo(a.altDeg));
    return TargetPage(total: rows.length, items: rows.skip(offset).take(limit).toList());
  }

  Target _withAltitude(Target t, DateTime when) => Target(
    id: t.id,
    name: t.name,
    catalog: t.catalog,
    type: t.type,
    raDeg: t.raDeg,
    decDeg: t.decDeg,
    mag: t.mag,
    sizeArcmin: t.sizeArcmin,
    altDeg: (altitudeDeg(t.raDeg, t.decDeg, lat, lon, when) * 10).roundToDouble() / 10,
    fits: t.sizeArcmin == null ? null : t.sizeArcmin! >= 2.6 && t.sizeArcmin! <= 77.8,
    hasThumb: true,
  );

  @override
  Future<TargetDetail> target(String id) async {
    _check();
    final base = _catalog.where((t) => t.id.toLowerCase() == id.toLowerCase().replaceAll(' ', '')).firstOrNull;
    if (base == null) throw const ApiFailure(FailureKind.notFound, code: 'not_found', status: 404);
    final start = _now().toUtc();
    final curve = <AltitudePoint>[];
    final best = <DateTime>[];
    for (var i = 0; i < 72; i++) {
      final t = start.add(Duration(minutes: 20 * i));
      if (sunAltitudeDeg(lat, lon, t) > -12) {
        if (curve.isNotEmpty) break;
        continue;
      }
      final alt = altitudeDeg(base.raDeg, base.decDeg, lat, lon, t);
      curve.add(AltitudePoint(t, (alt * 10).roundToDouble() / 10));
      if (alt >= 25) best.add(t);
    }
    return TargetDetail(
      target: _withAltitude(base, start),
      night: curve,
      bestFrom: best.isEmpty ? null : best.first,
      bestTo: best.isEmpty ? null : best.last,
      fovDeg: const [2.57, 1.44],
      fills: base.sizeArcmin == null ? null : (base.sizeArcmin! / 86.4 * 100).roundToDouble() / 100,
    );
  }

  @override
  Future<Uint8List?> targetThumb(String id) async {
    _check();
    return _image('thumb:$id', 96, 96, quality: 1);
  }

  // ------------------------------------------------------------------ observar
  Job _open(String commandId, String kind, {String? target, List<String> ignored = const []}) {
    final job = Job(id: 'j-demo-${++_jobCount}', kind: kind, state: 'accepted', target: target, ignored: ignored);
    _jobs[commandId] = job;
    // a captura planetária é de um modo só: outro trabalho começa sem ela
    if (kind != 'planetary') _state = _state.copyWith(capture: () => null);
    return job;
  }

  @override
  Future<Job> goTo({required String commandId, String? target, double? raDeg, double? decDeg}) async {
    _check();
    if (_jobs[commandId] case final Job known) return known;
    final name = target ?? '${raDeg?.toStringAsFixed(2)}, ${decDeg?.toStringAsFixed(2)}';
    if (target != null) _requireTarget(target);
    commands.add('goto:$name');
    return _point(_open(commandId, 'goto', target: name), thenStack: false);
  }

  @override
  Future<Job> observe({required String commandId, required String target}) async {
    _check();
    if (_jobs[commandId] case final Job known) return known;
    _requireTarget(target);
    commands.add('observe:$target');
    return _point(_open(commandId, 'observe', target: target), thenStack: true);
  }

  void _requireTarget(String target) {
    if (!_catalog.any((t) => t.id.toLowerCase() == target.toLowerCase())) {
      throw const ApiFailure(FailureKind.notFound, code: 'not_found', status: 404);
    }
    _target = _catalog.firstWhere((t) => t.id.toLowerCase() == target.toLowerCase()).id;
  }

  /// Aponta e centraliza (duas voltas de apontar + reconhecer o céu, como o laço de verdade).
  /// Com [thenStack], segue empilhando no mesmo trabalho — a "noite rápida"; com [then], segue
  /// para o que vier (a captura planetária).
  Job _point(Job job, {required bool thenStack, void Function(List<JobStep> pointed)? then}) {
    _emit(_with(state: 'IDLE', job: job, stack: const StackState()));
    const phases = [('SLEWING', 'slew'), ('SOLVING', 'solve'), ('SLEWING', 'slew'), ('SOLVING', 'solve')];
    var index = 0;
    _timer?.cancel();
    _timer = Timer.periodic(step, (timer) {
      if (index < phases.length) {
        final steps = [for (var i = 0; i <= index; i++) JobStep(phases[i].$2, i == index ? 'running' : 'done')];
        _emit(
          _with(
            state: phases[index].$1,
            job: Job(id: job.id, kind: job.kind, state: 'running', target: job.target, steps: steps),
            pointing: Pointing(error: 16.0 / (1 << (index * 2)), unit: 'arcmin'),
          ),
        );
        _publishFrame(0);
        index++;
        return;
      }
      timer.cancel();
      final failed = gotoFails;
      final pointed = [
        for (var i = 0; i < phases.length; i++)
          JobStep(phases[i].$2, failed && i == phases.length - 1 ? 'failed' : 'done'),
      ];
      if (thenStack && !failed) {
        _stackLoop(job, pointed);
        return;
      }
      if (then != null && !failed) {
        then(pointed);
        return;
      }
      _emit(
        _with(
          state: 'STOPPED',
          job: Job(
            id: job.id,
            kind: job.kind,
            state: failed ? 'failed' : 'done',
            target: job.target,
            error: failed ? 'not_converged' : null,
            steps: pointed,
          ),
          pointing: Pointing(error: failed ? 12.0 : 0.36, unit: 'arcmin'),
        ),
      );
    });
    return job;
  }

  @override
  Future<Job> stack({required String commandId, double? exposureS, int? gain, int frames = 0}) async {
    _check();
    if (_jobs[commandId] case final Job known) return known;
    commands.add('stack');
    final job = _open(
      commandId,
      'stack',
      ignored: [if (exposureS != null) 'exposure_s', if (gain != null) 'gain', if (frames > 0) 'frames'],
    );
    _stackLoop(job, const []);
    return job;
  }

  /// Uma foto por [step]; uma em cada sete é rejeitada (nuvem, vento), como numa noite real.
  void _stackLoop(Job job, List<JobStep> before) {
    var accepted = 0;
    var rejected = 0;
    final steps = [...before, const JobStep('stack', 'running')];
    Job running() => Job(id: job.id, kind: job.kind, state: 'running', target: job.target, steps: steps);
    _emit(
      _with(
        state: 'STACKING',
        job: running(),
        pointing: const Pointing(error: 0.36, unit: 'arcmin'),
      ),
    );
    _timer?.cancel();
    _timer = Timer.periodic(step, (_) {
      (accepted + rejected) % 7 == 6 ? rejected++ : accepted++;
      _emit(
        _with(
          state: 'STACKING',
          job: running(),
          stack: StackState(
            target: _target,
            accepted: accepted,
            rejected: rejected,
            snr: (math.sqrt(accepted) * 28).roundToDouble() / 10,
            fwhmPx: _fwhm(),
          ),
        ),
      );
      _publishFrame(accepted);
    });
  }

  @override
  Future<Job> run({required String commandId, required String mode, String? target}) => switch (mode) {
    'goto' => goTo(commandId: commandId, target: target),
    'tracking' => _track(commandId),
    _ => stack(commandId: commandId),
  };

  /// Rastreio: um objeto cruza o campo e a montagem o acompanha; o erro vai caindo até o
  /// objeto ficar no centro. Roda até alguém parar.
  Future<Job> _track(String commandId) async {
    _check();
    if (_jobs[commandId] case final Job known) return known;
    commands.add('tracking');
    final job = _open(commandId, 'tracking');
    var tick = 0;
    Job running() => Job(id: job.id, kind: 'tracking', state: 'running', steps: const [JobStep('track', 'running')]);
    _target = 'objeto';
    _timer?.cancel();
    _emit(_with(state: 'TRACKING', job: running(), stack: const StackState(), pointing: const Pointing(error: 80)));
    _timer = Timer.periodic(step, (_) {
      tick++;
      _emit(
        _with(
          state: 'TRACKING',
          job: running(),
          pointing: Pointing(error: (80 / (1 + tick * tick) * 10).roundToDouble() / 10 + 2, unit: 'px'),
        ),
      );
      _publishFrame(tick);
    });
    return job;
  }

  @override
  Future<Job> stop({required String commandId}) async {
    _check();
    if (_jobs[commandId] case final Job known) return known;
    commands.add('stop');
    _timer?.cancel();
    _jogTimer?.cancel();
    final current = _state.job;
    _emit(
      _with(
        state: 'STOPPED',
        mount: _mount(moving: null),
        job: current == null || !current.isOpen
            ? current
            : Job(
                id: current.id,
                kind: current.kind,
                state: 'stopped',
                target: current.target,
                steps: [for (final s in current.steps) JobStep(s.name, s.state == 'running' ? 'stopped' : s.state)],
              ),
        night: [
          for (final n in _state.night)
            n.status == 'running'
                ? NightItem(id: n.id, target: n.target, status: 'stopped', accepted: n.accepted, snr: n.snr)
                : n,
        ],
      ),
    );
    return _jobs[commandId] = Job(id: 'j-demo-${++_jobCount}', kind: 'stop', state: 'done');
  }

  /// A chave da imagem ao vivo: o alvo, quantas fotos já entraram, para onde a montagem foi
  /// levada à mão e o quanto o foco está fora — cada um muda o que se vê.
  Uint8List _liveImage(int accepted) {
    if (_state.capture case final CaptureState capture when _state.planetary) {
      return _planet(capture.body, sharp: capture.done, tick: accepted);
    }
    final blur = ((_state.focus.position - focusBest).abs() / 500).round();
    return _image(
      'live:$_target${_nudge == (0, 0) ? '' : '@${_nudge.$1},${_nudge.$2}'}:$accepted:$blur',
      480,
      360,
      quality: accepted,
      blur: blur,
    );
  }

  void _publishFrame(int accepted) {
    if (!_closed && _frames.hasListener) _frames.add(_liveImage(accepted));
  }

  @override
  Stream<Uint8List> preview({int maxSide = 1280}) async* {
    _check();
    yield _liveImage(_state.stack.accepted);
    yield* _frames.stream;
  }

  @override
  Future<Uint8List?> frame({int maxSide = 1280}) async {
    _check();
    return _liveImage(_state.stack.accepted);
  }

  @override
  Future<Job> startPreview({required String commandId}) async {
    _check();
    if (_jobs[commandId] case final Job known) return known;
    commands.add('preview');
    final job = _open(commandId, 'preview');
    Job running() => Job(id: job.id, kind: 'preview', state: 'running', steps: const [JobStep('preview', 'running')]);
    _timer?.cancel();
    _emit(
      _with(
        state: 'PREVIEW',
        job: running(),
        stack: StackState(target: _target, fwhmPx: _fwhm()),
      ),
    );
    _publishFrame(0);
    _timer = Timer.periodic(step, (_) {
      _emit(
        _with(
          state: 'PREVIEW',
          job: running(),
          stack: StackState(target: _target, fwhmPx: _fwhm()),
        ),
      );
      _publishFrame(0);
    });
    return job;
  }

  @override
  Future<Job> autofocus({required String commandId}) async {
    _check();
    if (_jobs[commandId] case final Job known) return known;
    commands.add('focus');
    final job = _open(commandId, 'focus');
    final start = _state.focus.position;
    final positions = [for (var i = 0; i < 9; i++) (start - 2000 + i * 500).clamp(0, 10000)];
    var curve = <FocusPoint>[];
    var index = 0;
    Job running() => Job(id: job.id, kind: 'focus', state: 'running', steps: const [JobStep('focus', 'running')]);
    FocusState focusAt(int position, {int? best}) =>
        FocusState(position: position, min: 0, max: 10000, curve: curve, best: best);
    _timer?.cancel();
    _emit(_with(state: 'FOCUSING', job: running(), focus: focusAt(start)));
    _timer = Timer.periodic(step, (timer) {
      if (index < positions.length) {
        final position = positions[index++];
        curve = [...curve, FocusPoint(position, focusFails ? null : _fwhm(position))];
        _emit(
          _with(
            state: 'FOCUSING',
            job: running(),
            focus: focusAt(position),
            stack: StackState(target: _target, fwhmPx: focusFails ? 0 : _fwhm(position)),
          ),
        );
        _publishFrame(0);
        return;
      }
      timer.cancel();
      final found = !focusFails;
      _emit(
        _with(
          state: 'IDLE',
          focus: focusAt(found ? focusBest : start, best: found ? focusBest : null),
          stack: StackState(target: _target, fwhmPx: found ? _fwhm(focusBest) : 0),
          job: Job(
            id: job.id,
            kind: 'focus',
            state: found ? 'done' : 'failed',
            error: found ? null : 'focus_failed',
            steps: [JobStep('focus', found ? 'done' : 'failed')],
          ),
        ),
      );
      _publishFrame(0);
    });
    return job;
  }

  // ------------------------------------------------------------------ à mão
  MountState _mount({bool? parked, bool? tracking, required String? moving}) => MountState(
    source: _state.mount.source,
    tracking: tracking ?? _state.mount.tracking,
    parked: parked ?? _state.mount.parked,
    moving: moving,
    features: _state.mount.features,
  );

  void _requireFreeMount() {
    if (!_state.mountFree) throw _conflict('busy');
  }

  @override
  Future<void> jog(String direction, {int rate = 2, int holdMs = 800}) async {
    _check();
    _requireFreeMount();
    if (_state.mount.parked == true) throw _conflict('parked');
    commands.add('jog:$direction:$rate');
    final (dx, dy) = switch (direction) {
      'N' => (0, -1),
      'S' => (0, 1),
      'E' => (1, 0),
      _ => (-1, 0),
    };
    _nudge = (_nudge.$1 + dx * rate, _nudge.$2 + dy * rate);
    _emit(_with(mount: _mount(moving: direction)));
    _publishFrame(_state.stack.accepted);
    // o prazo: sem renovação, para sozinha
    _jogTimer?.cancel();
    _jogTimer = Timer(Duration(milliseconds: holdMs), () => _emit(_with(mount: _mount(moving: null))));
  }

  @override
  Future<void> haltMount() async {
    _check();
    commands.add('halt');
    _jogTimer?.cancel();
    _emit(_with(mount: _mount(moving: null)));
  }

  @override
  Future<void> mountAction(String action) async {
    _check();
    if (action != 'unpark') _requireFreeMount();
    commands.add(action);
    _jogTimer?.cancel();
    switch (action) {
      case 'park':
        _emit(_with(mount: _mount(parked: true, tracking: false, moving: null)));
      case 'unpark':
        _emit(_with(mount: _mount(parked: false, tracking: true, moving: null)));
      case 'home':
        _nudge = (0, 0);
        _emit(_with(mount: _mount(parked: false, moving: null)));
        _publishFrame(_state.stack.accepted);
      default:
        throw const ApiFailure(FailureKind.notFound, code: 'not_found', status: 404);
    }
  }

  @override
  Future<void> setTracking({required bool on}) async {
    _check();
    if (_state.mount.parked == true) throw _conflict('parked');
    commands.add('tracking:${on ? 'on' : 'off'}');
    _emit(
      _with(
        mount: _mount(tracking: on, moving: _state.mount.moving),
      ),
    );
  }

  @override
  Future<int> moveFocus({int? delta, int? position}) async {
    _check();
    if (_state.state == 'FOCUSING') throw _conflict('busy');
    final wanted = (position ?? _state.focus.position + (delta ?? 0)).clamp(0, 10000);
    commands.add('focus:$wanted');
    _emit(
      _with(
        focus: FocusState(position: wanted, min: 0, max: 10000, curve: _state.focus.curve, best: _state.focus.best),
        stack: StackState(
          target: _state.stack.target,
          accepted: _state.stack.accepted,
          rejected: _state.stack.rejected,
          snr: _state.stack.snr,
          fwhmPx: _state.previewing || _state.stacking ? _fwhm(wanted) : _state.stack.fwhmPx,
        ),
      ),
    );
    _publishFrame(_state.stack.accepted);
    return wanted;
  }

  @override
  Future<CameraInfo> camera() async {
    _check();
    return CameraInfo(state: _state.camera, limits: _cameraLimits);
  }

  @override
  Future<CameraInfo> setCamera({double? exposureS, int? gain, int? offset}) async {
    _check();
    final now = _state.camera;
    commands.add('camera');
    _emit(
      _with(
        camera: CameraState(
          connected: true,
          model: now.model,
          exposureS: exposureS ?? now.exposureS,
          gain: gain ?? now.gain,
          offset: offset ?? now.offset,
        ),
      ),
    );
    return camera();
  }

  // ------------------------------------------------------------------ sistema solar
  @override
  Future<List<SolarBody>> solar() async {
    _check();
    return solarSystem(lat, lon, _now().toUtc());
  }

  @override
  Future<Job> goToBody({required String commandId, required String body, bool filterConfirmed = false}) async {
    _check();
    if (_jobs[commandId] case final Job known) return known;
    final found = solarBodies.where((b) => b.$1 == body).firstOrNull;
    if (found == null) throw const ApiFailure(FailureKind.notFound, code: 'not_found', status: 404);
    if (body == 'sun' && !filterConfirmed) {
      throw const ApiFailure(FailureKind.invalid, code: 'solar_filter_required', status: 400);
    }
    commands.add('body:$body');
    _target = found.$2;
    return _point(_open(commandId, 'goto', target: found.$2), thenStack: false);
  }

  // ------------------------------------------------------------------ captura planetária
  @override
  Future<Job> capturePlanetary({
    required String commandId,
    required String body,
    int frames = 300,
    int keepPercent = 15,
    bool point = true,
  }) async {
    _check();
    if (_jobs[commandId] case final Job known) return known;
    final found = solarBodies.where((b) => b.$1 == body && b.$3 != 'sun').firstOrNull;
    if (found == null) throw _missing; // o Sol não entra neste modo
    if (frames < 50 || frames > 3000 || keepPercent < 5 || keepPercent > 50) throw _invalid;
    commands.add('planetary:$body:$frames:$keepPercent${point ? '' : ':here'}');
    _target = found.$2;
    final job = _open(commandId, 'planetary', target: found.$2);
    if (point) {
      return _point(job, thenStack: false, then: (pointed) => _captureLoop(job, pointed, body, frames, keepPercent));
    }
    _captureLoop(job, const [], body, frames, keepPercent);
    return job;
  }

  /// Grava os quadros (uma leva a cada [step]), ficando só com os mais nítidos; no fim, um
  /// passo empilhando os que ficaram.
  void _captureLoop(Job job, List<JobStep> before, String body, int total, int keepPercent) {
    final want = math.max(1, (total * keepPercent / 100).round());
    var frames = 0;
    Job at(String state, List<JobStep> steps) =>
        Job(id: job.id, kind: 'planetary', state: state, target: job.target, steps: [...before, ...steps]);
    CaptureState capture({bool done = false}) => CaptureState(
      body: body,
      frames: frames,
      total: total,
      kept: math.min(frames, want),
      keep: keepPercent / 100,
      done: done,
    );
    _timer?.cancel();
    _emit(
      _with(
        state: 'CAPTURING',
        job: at('running', const [JobStep('capture', 'running')]),
        stack: const StackState(),
        capture: capture,
      ),
    );
    _publishFrame(0);
    _timer = Timer.periodic(step, (timer) {
      if (frames < total) {
        frames = math.min(total, frames + (total / 6).ceil());
        _emit(_with(state: 'CAPTURING', job: at('running', const [JobStep('capture', 'running')]), capture: capture));
        _publishFrame(frames);
        return;
      }
      if (_state.state == 'CAPTURING') {
        _emit(
          _with(
            state: 'STACKING',
            job: at('running', const [JobStep('capture', 'done'), JobStep('stack', 'running')]),
            capture: capture,
          ),
        );
        return;
      }
      timer.cancel();
      _emit(
        _with(
          state: 'IDLE',
          job: at('done', const [JobStep('capture', 'done'), JobStep('stack', 'done')]),
          stack: StackState(target: _target, accepted: want, rejected: total - want),
          capture: () => capture(done: true),
        ),
      );
      _publishFrame(total);
    });
  }

  // ------------------------------------------------------------------ alinhamento polar
  /// Alinhamento polar por três pontos: gira a ascensão reta, reconhece o céu em cada parada
  /// e mede quanto o eixo da montagem erra o polo.
  @override
  Future<Job> measurePolar({required String commandId}) async {
    _check();
    if (_jobs[commandId] case final Job known) return known;
    if (_state.mount.isReal) throw const ApiFailure(FailureKind.notSupported, code: 'not_supported', status: 501);
    _requireFreeMount();
    commands.add('polar');
    final job = _open(commandId, 'polar');
    var tick = 0;
    _timer?.cancel();
    _emit(_with(state: 'IDLE', job: job, stack: const StackState(), polar: () => const PolarState()));
    _timer = Timer.periodic(step, (timer) {
      if (tick < 6) {
        final solving = tick.isOdd;
        _emit(
          _with(
            state: solving ? 'SOLVING' : 'SLEWING',
            job: Job(
              id: job.id,
              kind: 'polar',
              state: 'running',
              steps: [
                for (var i = 0; i <= tick; i++) JobStep(i.isOdd ? 'solve' : 'slew', i == tick ? 'running' : 'done'),
              ],
            ),
            polar: () => PolarState(step: (tick + 1) ~/ 2),
          ),
        );
        _publishFrame(0);
        tick++;
        return;
      }
      timer.cancel();
      const steps = ['slew', 'solve', 'slew', 'solve', 'slew', 'solve'];
      if (polarFails) {
        _emit(
          _with(
            state: 'STOPPED',
            job: Job(
              id: job.id,
              kind: 'polar',
              state: 'failed',
              error: 'polar_failed',
              steps: [for (final (i, name) in steps.indexed) JobStep(name, i == steps.length - 1 ? 'failed' : 'done')],
            ),
            polar: () => const PolarState(step: 3),
          ),
        );
        return;
      }
      double tenth(double v) => (v * 10).roundToDouble() / 10;
      final total = math.sqrt(_polarAlt * _polarAlt + _polarAz * _polarAz);
      _emit(
        _with(
          state: 'STOPPED', // mediu: a montagem fica parada, como depois de um goto
          job: Job(id: job.id, kind: 'polar', state: 'done', steps: [for (final name in steps) JobStep(name, 'done')]),
          polar: () => PolarState(
            step: 3,
            measured: true,
            altArcmin: tenth(_polarAlt),
            azArcmin: tenth(_polarAz),
            totalArcmin: tenth(total),
            aligned: total <= 2.0,
            latDeg: lat,
          ),
        ),
      );
    });
    return job;
  }

  @override
  Future<void> adjustPolar({required double altArcmin, required double azArcmin}) async {
    _check();
    if (_state.mount.isReal) throw const ApiFailure(FailureKind.notSupported, code: 'not_supported', status: 501);
    _requireFreeMount();
    if (altArcmin.abs() > 600 || azArcmin.abs() > 600) throw _invalid;
    commands.add('polar:adjust:${altArcmin.toStringAsFixed(1)}:${azArcmin.toStringAsFixed(1)}');
    // a mão nunca gira exatamente o que pretendia: sobra um resto, como no simulador da Jetson
    _polarAlt += altArcmin * 0.95;
    _polarAz += azArcmin * 0.95;
    final last = _state.polar;
    if (last == null || !last.measured) return;
    _emit(
      _with(
        polar: () => PolarState(
          step: last.step,
          points: last.points,
          measured: true,
          altArcmin: last.altArcmin,
          azArcmin: last.azArcmin,
          totalArcmin: last.totalArcmin,
          aligned: last.aligned,
          stale: true, // mexeu nos parafusos: a medida não vale mais
          latDeg: last.latDeg,
        ),
      ),
    );
  }

  // ------------------------------------------------------------------ plano da noite
  /// Quando cada item cabe nesta noite — a mesma conta da Jetson (`src/api/plan.py`).
  NightPlan _schedule() {
    final now = _now().toUtc();
    const tick = Duration(minutes: 5);
    DateTime? start;
    DateTime? end;
    for (var i = 0; i <= 24 * 12; i++) {
      final t = now.add(tick * i);
      final dark = sunAltitudeDeg(lat, lon, t) <= -12;
      if (start == null && dark) {
        start = t;
      } else if (start != null && !dark) {
        end = t;
        break;
      }
    }
    if (start != null) end ??= now.add(const Duration(hours: 24));
    var cursor = start;
    var used = 0;
    final rows = <PlanItem>[];
    for (final item in _plan) {
      final target = _catalog.firstWhere((t) => t.id == item.target);
      double alt(DateTime t) => altitudeDeg(target.raDeg, target.decDeg, lat, lon, t);
      final seconds = (item.rows * item.cols * (120 + item.frames * item.exposureS)).round();
      DateTime? begin;
      if (cursor != null && end != null) {
        var t = cursor;
        while (t.isBefore(end) && alt(t) < item.minAltDeg) {
          t = t.add(tick);
        }
        if (t.isBefore(end)) begin = t;
      }
      PlanItem row({DateTime? from, DateTime? to, String status = 'never_up'}) => PlanItem(
        id: item.id,
        target: item.target,
        name: target.name,
        type: target.type,
        frames: item.frames,
        exposureS: item.exposureS,
        minAltDeg: item.minAltDeg,
        rows: item.rows,
        cols: item.cols,
        overlap: item.overlap,
        start: from,
        end: to,
        durationS: seconds,
        altStartDeg: from == null ? null : (alt(from) * 10).roundToDouble() / 10,
        altEndDeg: to == null ? null : (alt(to) * 10).roundToDouble() / 10,
        status: status,
      );
      if (begin == null || end == null) {
        rows.add(row());
        continue;
      }
      final finish = begin.add(Duration(seconds: seconds));
      final late = finish.isAfter(end);
      rows.add(
        row(
          from: begin,
          to: finish,
          status: late ? 'after_dawn' : (alt(finish) < item.minAltDeg ? 'sets_early' : 'ok'),
        ),
      );
      used += (late ? end : finish).difference(begin).inSeconds;
      cursor = late ? end : finish;
    }
    final nightS = start == null || end == null ? 0 : end.difference(start).inSeconds;
    return NightPlan(
      items: rows,
      nightStart: start,
      nightEnd: end,
      totalS: rows.fold(0, (sum, r) => sum + r.durationS),
      freeS: math.max(0, nightS - used),
      running: _state.nightRunning,
    );
  }

  @override
  Future<NightPlan> plan() async {
    _check();
    return _schedule();
  }

  @override
  Future<NightPlan> savePlan(List<PlanItem> items) async {
    _check();
    if (_state.nightRunning) throw _conflict('busy');
    final next = <PlanItem>[];
    for (final item in items) {
      final target = _catalog
          .where((t) => t.id.toLowerCase() == item.target.toLowerCase().replaceAll(' ', ''))
          .firstOrNull;
      if (target == null || item.frames < 1 || item.rows < 1 || item.rows > 6 || item.cols < 1 || item.cols > 6) {
        throw const ApiFailure(FailureKind.invalid, code: 'invalid_argument', status: 400);
      }
      var id = item.id;
      if (id.isEmpty || next.any((n) => n.id == id)) {
        var k = 1;
        while (next.any((n) => n.id == 'p-$k') || items.any((i) => i.id == 'p-$k')) {
          k++;
        }
        id = 'p-$k';
      }
      next.add(
        PlanItem(
          id: id,
          target: target.id,
          frames: item.frames,
          exposureS: item.exposureS,
          minAltDeg: item.minAltDeg,
          rows: item.rows,
          cols: item.cols,
          overlap: item.overlap,
        ),
      );
    }
    commands.add('plan:${next.map((i) => i.target).join(',')}');
    _plan = next;
    return _schedule();
  }

  @override
  Future<Job> startPlan({required String commandId}) async {
    _check();
    if (_jobs[commandId] case final Job known) return known;
    if (_plan.isEmpty) throw const ApiFailure(FailureKind.invalid, code: 'invalid_argument', status: 400);
    commands.add('night');
    final job = _open(commandId, 'plan');
    final planned = _schedule().items;
    var night = [for (final p in planned) NightItem(id: p.id, target: p.target)];
    var index = 0;
    var tick = 0;
    var done = 0;
    _skip = false;
    Job running(String name) => Job(id: job.id, kind: 'plan', state: 'running', steps: [JobStep(name, 'running')]);
    void mark(int i, String status, {String reason = '', int accepted = 0}) {
      night = [
        for (var k = 0; k < night.length; k++)
          k == i
              ? NightItem(
                  id: night[k].id,
                  target: night[k].target,
                  status: status,
                  reason: reason,
                  accepted: accepted,
                  snr: (math.sqrt(accepted) * 28).roundToDouble() / 10,
                )
              : night[k],
      ];
    }

    _timer?.cancel();
    _emit(
      _with(
        state: 'SCHEDULING',
        job: running('schedule'),
        night: night,
        queue: QueueState(total: night.length),
        stack: const StackState(),
      ),
    );
    const phases = [('SLEWING', 'slew'), ('SOLVING', 'solve'), ('FOCUSING', 'focus')];
    _timer = Timer.periodic(step, (timer) {
      while (index < planned.length && planned[index].status == 'never_up') {
        mark(index++, 'skipped', reason: 'below_horizon'); // não sobe nesta noite: nem tenta
        done++;
      }
      if (index >= planned.length) {
        timer.cancel();
        _emit(
          _with(
            state: 'IDLE',
            night: night,
            queue: QueueState(done: done, total: night.length),
            job: Job(id: job.id, kind: 'plan', state: 'done', steps: const [JobStep('schedule', 'done')]),
          ),
        );
        return;
      }
      if (_skip) {
        _skip = false;
        mark(index++, 'skipped', reason: 'user');
        done++;
        tick = 0;
        _emit(
          _with(
            state: 'SCHEDULING',
            job: running('schedule'),
            night: night,
            queue: QueueState(done: done, total: night.length),
          ),
        );
        return;
      }
      _target = planned[index].target;
      if (tick < phases.length) {
        mark(index, 'running');
        _emit(
          _with(
            state: phases[tick].$1,
            job: running(phases[tick].$2),
            night: night,
            queue: QueueState(done: done, total: night.length),
            stack: StackState(target: _target),
          ),
        );
        _publishFrame(0);
        tick++;
        return;
      }
      final accepted = tick - phases.length + 1;
      mark(index, 'running', accepted: accepted);
      _emit(
        _with(
          state: 'STACKING',
          job: running('stack'),
          night: night,
          queue: QueueState(done: done, total: night.length),
          stack: StackState(target: _target, accepted: accepted, snr: night[index].snr, fwhmPx: _fwhm()),
        ),
      );
      _publishFrame(accepted);
      tick++;
      // a demonstração encurta a noite: poucas fotos por alvo
      if (accepted >= math.min(planned[index].frames, 3)) {
        mark(index++, 'done', accepted: accepted);
        done++;
        tick = 0;
      }
    });
    return job;
  }

  @override
  Future<void> skipPlanItem() async {
    _check();
    if (!_state.nightRunning) throw _conflict('not_running');
    commands.add('skip');
    _skip = true;
  }

  @override
  Future<MosaicGrid> mosaic({required String target, int rows = 2, int cols = 2, double overlap = 0.15}) async {
    _check();
    final found = _catalog.where((t) => t.id.toLowerCase() == target.toLowerCase().replaceAll(' ', '')).firstOrNull;
    if (found == null) throw const ApiFailure(FailureKind.notFound, code: 'not_found', status: 404);
    const fov = (2.57, 1.44);
    final (stepW, stepH) = (fov.$1 * (1 - overlap), fov.$2 * (1 - overlap));
    final cosDec = math.max(math.cos(found.decDeg * math.pi / 180), 1e-3);
    final covers = [fov.$1 + (cols - 1) * stepW, fov.$2 + (rows - 1) * stepH];
    return MosaicGrid(
      target: found.id,
      name: found.name,
      rows: rows,
      cols: cols,
      overlap: overlap,
      fieldDeg: [fov.$1, fov.$2],
      coversDeg: [for (final v in covers) (v * 1000).roundToDouble() / 1000],
      objectArcmin: found.sizeArcmin,
      coversObject: found.sizeArcmin == null ? null : found.sizeArcmin! * 1.1 <= math.max(covers[0], covers[1]) * 60,
      panels: [
        for (var r = 0; r < rows; r++)
          for (var c = 0; c < cols; c++)
            MosaicPanel(
              name: 'R${r}C$c',
              row: r,
              col: c,
              raDeg: (found.raDeg + ((cols - 1) / 2 - c) * stepW / cosDec) % 360,
              decDeg: (found.decDeg + ((rows - 1) / 2 - r) * stepH).clamp(-90.0, 90.0),
            ),
      ],
    );
  }

  @override
  Future<List<double>> histogram() async => [
    for (var i = 0; i < 40; i++) (math.exp(-math.pow((i - 7) / 4.5, 2)) * 1000).roundToDouble() / 1000,
  ];

  // ------------------------------------------------------------------ galeria
  @override
  Future<List<Session>> sessions() async {
    _check();
    return List.of(_sessions);
  }

  @override
  Future<Uint8List?> exportSession(String id, {String format = 'jpg', int maxSide = 0}) async {
    _check();
    if (!_sessions.any((s) => s.id == id)) return null;
    commands.add('export:$id:$format');
    return _image('full:$id', 480, 360, quality: 40);
  }

  @override
  Future<void> deleteSession(String id) async {
    _check();
    final session = _sessions.where((s) => s.id == id).firstOrNull;
    if (session == null) throw const ApiFailure(FailureKind.notFound, code: 'not_found', status: 404);
    if (session.isReference) throw _conflict('protected');
    commands.add('delete:$id');
    _sessions = [
      for (final s in _sessions)
        if (s.id != id) s,
    ];
  }

  @override
  Future<Uint8List?> sessionImage(String id, {bool thumb = false}) async {
    _check();
    return thumb ? _image('thumb:$id', 96, 96, quality: 40) : _image('full:$id', 480, 360, quality: 40);
  }

  @override
  Future<Uint8List?> render(String sessionId, Map<String, Object> controls) async {
    _check();
    final stretch = (controls['stretch'] as num?)?.toDouble() ?? 10;
    final saturation = (controls['saturation'] as num?)?.toDouble() ?? 1.8;
    return _image(
      'render:$sessionId:$stretch:$saturation:${controls['preset']}',
      480,
      360,
      quality: 40,
      gain: stretch / 10,
      saturation: saturation / 1.8,
    );
  }

  @override
  Future<RenderPresets> presets() async => const RenderPresets(
    presets: {
      'natural': {'stretch': 10.0, 'saturation': 1.8, 'denoise': 0.35},
      'vivido': {'stretch': 13.0, 'saturation': 2.3, 'denoise': 0.45},
      'nebulosa': {'stretch': 15.0, 'saturation': 2.7, 'denoise': 0.5},
      'suave': {'stretch': 8.0, 'saturation': 1.5, 'denoise': 0.6},
    },
    controls: {
      'stretch': RenderControl(min: 1, max: 30, step: 0.5, initial: 10),
      'saturation': RenderControl(min: 0, max: 3, step: 0.05, initial: 1.8),
      'denoise': RenderControl(min: 0, max: 1, step: 0.05, initial: 0.35),
      'black': RenderControl(min: 0, max: 0.3, step: 0.005, initial: 0.02),
      'white': RenderControl(min: 98, max: 100, step: 0.05, initial: 99.8),
      'scnr': RenderControl(min: 0, max: 1, step: 0.05, initial: 0.5),
      'deconv': RenderControl(min: 0, max: 20, step: 1, initial: 0),
      'star_reduce': RenderControl(min: 0, max: 1, step: 0.05, initial: 0),
      'sharpen': RenderControl(min: 0, max: 1, step: 0.02, initial: 0.1),
    },
    toggles: {'remove_grad': true},
  );

  @override
  void close() {
    _closed = true;
    _timer?.cancel();
    _jogTimer?.cancel();
    _netTimer?.cancel();
    _updateTimer?.cancel();
    unawaited(_changes.close());
    unawaited(_frames.close());
  }

  // ------------------------------------------------------------------ imagens
  /// Um campo de estrelas com uma nebulosa, desenhado a partir do nome: o mesmo alvo dá sempre
  /// a mesma imagem. [quality] é o número de fotos empilhadas: quanto mais, menos ruído.
  Uint8List _image(String key, int w, int h, {int quality = 0, double gain = 1, double saturation = 1, int blur = 0}) {
    // mexer na montagem e no foco gera imagens novas sem parar: guarda só as últimas
    if (_images.length > 48 && !_images.containsKey(key)) _images.remove(_images.keys.first);
    return _images.putIfAbsent(key, () {
      final subject = key.split(':')[1];
      final seed = subject.codeUnits.fold<int>(7, (a, c) => (a * 31 + c) & 0x7FFFFFFF);
      final shape = math.Random(seed);
      final noise = math.Random(seed ^ quality);
      final hue = [
        [1.0, 0.35, 0.45],
        [0.45, 0.6, 1.0],
        [1.0, 0.75, 0.4],
        [0.5, 1.0, 0.85],
      ][seed % 4];
      final cx = w * (0.4 + shape.nextDouble() * 0.2);
      final cy = h * (0.4 + shape.nextDouble() * 0.2);
      final radius = math.min(w, h) * (0.22 + shape.nextDouble() * 0.12);
      final stars = [
        for (var i = 0; i < w * h ~/ 900; i++) (shape.nextInt(w), shape.nextInt(h), 90 + shape.nextInt(165)),
      ];
      final sigma = 46.0 / math.sqrt(1 + quality);
      final rgb = Uint8List(w * h * 3);
      for (var y = 0; y < h; y++) {
        for (var x = 0; x < w; x++) {
          final d = math.sqrt(math.pow(x - cx, 2) + math.pow((y - cy) * 1.25, 2)) / radius;
          final cloud = 150 * math.exp(-d * d * 1.6) * gain;
          final grain = (noise.nextDouble() - 0.5) * 2 * sigma;
          final o = (y * w + x) * 3;
          for (var c = 0; c < 3; c++) {
            final tint = 1 + (hue[c] - 1) * saturation;
            rgb[o + c] = (10 + cloud * tint + grain).clamp(0, 255).toInt();
          }
        }
      }
      // fora de foco a estrela vira um disco maior e mais fraco
      for (final (x, y, level) in stars) {
        final dim = (level / (1 + blur * blur * 0.6)).round();
        for (var dy = -blur; dy <= blur; dy++) {
          for (var dx = -blur; dx <= blur; dx++) {
            final (px, py) = (x + dx, y + dy);
            if (px < 0 || py < 0 || px >= w || py >= h || dx * dx + dy * dy > blur * blur) continue;
            final o = (py * w + px) * 3;
            for (var c = 0; c < 3; c++) {
              rgb[o + c] = math.max(rgb[o + c], dim);
            }
          }
        }
      }
      return encodePng(w, h, rgb);
    });
  }
}

/// A cor de cada corpo e, para os gigantes, as faixas: (vermelho, verde, azul, contraste das
/// faixas). É o bastante para a demonstração não mostrar uma nebulosa no lugar de Saturno.
const _bodyLook = <String, (double, double, double, double)>{
  'moon': (0.86, 0.86, 0.84, 0),
  'mercury': (0.72, 0.68, 0.64, 0),
  'venus': (0.98, 0.95, 0.82, 0),
  'mars': (0.95, 0.52, 0.32, 0.12),
  'jupiter': (0.93, 0.80, 0.62, 0.30),
  'saturn': (0.95, 0.86, 0.60, 0.16),
  'uranus': (0.62, 0.88, 0.90, 0),
  'neptune': (0.42, 0.56, 0.96, 0.06),
};

extension on FakeTelescope {
  /// Um planeta (ou a Lua) no meio do quadro. Com [sharp], o resultado empilhado; sem ele, um
  /// quadro cru do vídeo: tremido, mole e com ruído, como a atmosfera entrega.
  Uint8List _planet(String body, {required bool sharp, int tick = 0}) {
    final key = 'planet:$body:${sharp ? 'final' : tick % 4}';
    if (_images.length > 48 && !_images.containsKey(key)) _images.remove(_images.keys.first);
    return _images.putIfAbsent(key, () {
      const size = 240;
      final (red, green, blue, bands) = _bodyLook[body] ?? _bodyLook['jupiter']!;
      final seed = body.codeUnits.fold<int>(11, (a, c) => (a * 31 + c) & 0x7FFFFFFF);
      final noise = math.Random(seed ^ (sharp ? 0 : tick % 4 + 1));
      final marks = math.Random(seed);
      // crateras (Lua, Mercúrio) ou manchas: as mesmas em todo quadro
      final spots = [
        for (var i = 0; i < (bands == 0 ? 14 : 3); i++)
          (marks.nextDouble() * 1.4 - 0.7, marks.nextDouble() * 1.4 - 0.7, 0.05 + marks.nextDouble() * 0.10),
      ];
      // Saturno menor, para os anéis caberem no quadro
      final radius = switch (body) {
        'moon' => 100.0,
        'saturn' => 50.0,
        _ => 78.0,
      };
      final (shakeX, shakeY) = sharp ? (0.0, 0.0) : (noise.nextDouble() * 10 - 5, noise.nextDouble() * 10 - 5);
      final soft = sharp ? 1.0 : 0.45; // a atmosfera borra o detalhe do quadro cru
      final grain = sharp ? 3.0 : 26.0;
      final rgb = Uint8List(size * size * 3);
      for (var y = 0; y < size; y++) {
        for (var x = 0; x < size; x++) {
          final dx = (x - size / 2 - shakeX) / radius;
          final dy = (y - size / 2 - shakeY) / radius;
          final d2 = dx * dx + dy * dy;
          var level = 0.0;
          if (d2 < 1) {
            level = 60 + 170 * math.sqrt(1 - d2); // a borda do disco é mais escura
            level *= 1 + bands * soft * math.sin(dy * 16 + math.sin(dx * 3) * 0.6);
            for (final (sx, sy, sr) in spots) {
              final s2 = (dx - sx) * (dx - sx) + (dy - sy) * (dy - sy);
              if (s2 < sr * sr) level *= 1 - 0.28 * soft;
            }
          } else if (body == 'saturn') {
            // os anéis: uma elipse achatada em volta do disco
            final ring = math.sqrt(dx * dx + dy * dy * 9);
            if (ring > 1.35 && ring < 2.2 && (ring < 1.72 || ring > 1.8 || !sharp)) level = 150;
          }
          final o = (y * size + x) * 3;
          final g = (noise.nextDouble() - 0.5) * 2 * grain;
          rgb[o] = (level * red + g + 6).clamp(0, 255).toInt();
          rgb[o + 1] = (level * green + g + 6).clamp(0, 255).toInt();
          rgb[o + 2] = (level * blue + g + 8).clamp(0, 255).toInt();
        }
      }
      return encodePng(size, size, rgb);
    });
  }
}

/// Texto para comparar na busca: minúsculo, sem espaços e sem acentos ("orion" acha "Órion").
String _fold(String text) {
  const from = 'áàâãäéèêëíìîïóòôõöúùûüç';
  const to = 'aaaaaeeeeiiiiooooouuuuc';
  final out = StringBuffer();
  for (final char in text.toLowerCase().replaceAll(' ', '').split('')) {
    final i = from.indexOf(char);
    out.write(i < 0 ? char : to[i]);
  }
  return out.toString();
}

// --------------------------------------------------------------------- o céu
double _rad(double degrees) => degrees * math.pi / 180;
double _deg(double radians) => radians * 180 / math.pi;
double _daysSinceJ2000(DateTime utc) => utc.millisecondsSinceEpoch / 86400000.0 + 2440587.5 - 2451545.0;

/// Altitude (graus) de um ponto do céu para um observador, por trigonometria esférica — a mesma
/// conta que a Jetson faz para filtrar o catálogo (`core/catalog.altitudes_deg`).
double altitudeDeg(double raDeg, double decDeg, double lat, double lon, DateTime utc) {
  final gmst = (280.46061837 + 360.98564736629 * _daysSinceJ2000(utc)) % 360;
  final hourAngle = _rad(gmst + lon - raDeg);
  final sinAlt =
      math.sin(_rad(lat)) * math.sin(_rad(decDeg)) + math.cos(_rad(lat)) * math.cos(_rad(decDeg)) * math.cos(hourAngle);
  return _deg(math.asin(sinAlt.clamp(-1.0, 1.0)));
}

/// Altitude do Sol (graus): abaixo de -12 o céu já serve para céu profundo.
double sunAltitudeDeg(double lat, double lon, DateTime utc) {
  final d = _daysSinceJ2000(utc);
  final g = _rad((357.528 + 0.9856003 * d) % 360);
  final lambda = _rad((280.460 + 0.9856474 * d) % 360 + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g));
  final eps = _rad(23.439 - 0.0000004 * d);
  final ra = _deg(math.atan2(math.cos(eps) * math.sin(lambda), math.cos(lambda))) % 360;
  final dec = _deg(math.asin(math.sin(eps) * math.sin(lambda)));
  return altitudeDeg(ra, dec, lat, lon, utc);
}

/// Alvos conhecidos, com as coordenadas reais (J2000).
const _catalog = <Target>[
  Target(
    id: 'M8',
    name: 'Nebulosa da Lagoa',
    catalog: 'NGC6523',
    type: 'nebula',
    raDeg: 270.92,
    decDeg: -24.38,
    mag: 5.8,
    sizeArcmin: 45,
  ),
  Target(
    id: 'M20',
    name: 'Nebulosa Trífida',
    catalog: 'NGC6514',
    type: 'nebula',
    raDeg: 270.67,
    decDeg: -22.97,
    mag: 6.3,
    sizeArcmin: 28,
  ),
  Target(
    id: 'M42',
    name: 'Grande Nebulosa de Órion',
    catalog: 'NGC1976',
    type: 'nebula',
    raDeg: 83.82,
    decDeg: -5.39,
    mag: 4.0,
    sizeArcmin: 90,
  ),
  Target(
    id: 'M31',
    name: 'Galáxia de Andrômeda',
    catalog: 'NGC224',
    type: 'galaxy',
    raDeg: 10.68,
    decDeg: 41.27,
    mag: 3.4,
    sizeArcmin: 178,
  ),
  Target(
    id: 'M51',
    name: 'Galáxia do Redemoinho',
    catalog: 'NGC5194',
    type: 'galaxy',
    raDeg: 202.47,
    decDeg: 47.20,
    mag: 8.4,
    sizeArcmin: 13.7,
  ),
  Target(
    id: 'M104',
    name: 'Galáxia do Sombreiro',
    catalog: 'NGC4594',
    type: 'galaxy',
    raDeg: 189.99,
    decDeg: -11.62,
    mag: 8.0,
    sizeArcmin: 8.7,
  ),
  Target(
    id: 'NGC253',
    name: 'Galáxia do Escultor',
    catalog: 'NGC253',
    type: 'galaxy',
    raDeg: 11.89,
    decDeg: -25.29,
    mag: 7.2,
    sizeArcmin: 27.5,
  ),
  Target(
    id: 'NGC5128',
    name: 'Centaurus A',
    catalog: 'NGC5128',
    type: 'galaxy',
    raDeg: 201.37,
    decDeg: -43.02,
    mag: 6.8,
    sizeArcmin: 25.7,
  ),
  Target(
    id: 'M13',
    name: 'Aglomerado de Hércules',
    catalog: 'NGC6205',
    type: 'cluster',
    raDeg: 250.42,
    decDeg: 36.46,
    mag: 5.8,
    sizeArcmin: 20,
  ),
  Target(
    id: 'NGC5139',
    name: 'Ômega Centauri',
    catalog: 'NGC5139',
    type: 'cluster',
    raDeg: 201.70,
    decDeg: -47.48,
    mag: 3.9,
    sizeArcmin: 36.3,
  ),
  Target(
    id: 'M7',
    name: 'Aglomerado de Ptolomeu',
    catalog: 'NGC6475',
    type: 'cluster',
    raDeg: 268.46,
    decDeg: -34.79,
    mag: 3.3,
    sizeArcmin: 80,
  ),
  Target(
    id: 'NGC3372',
    name: 'Nebulosa de Carina',
    catalog: 'NGC3372',
    type: 'nebula',
    raDeg: 161.26,
    decDeg: -59.87,
    mag: 3.0,
    sizeArcmin: 120,
  ),
  Target(
    id: 'M27',
    name: 'Nebulosa do Haltere',
    catalog: 'NGC6853',
    type: 'nebula',
    raDeg: 299.90,
    decDeg: 22.72,
    mag: 7.5,
    sizeArcmin: 8,
  ),
  Target(
    id: 'M16',
    name: 'Nebulosa da Águia',
    catalog: 'NGC6611',
    type: 'nebula',
    raDeg: 274.70,
    decDeg: -13.81,
    mag: 6.0,
    sizeArcmin: 35,
  ),
];
