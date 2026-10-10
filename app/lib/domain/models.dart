/// Os tipos que o app conhece — o espelho do contrato da API v1 (`app/docs/04-api.md`).
/// Imutáveis e sem lógica de rede: quem busca é a porta `TelescopeApi`.
library;

typedef Json = Map<String, dynamic>;

double? _d(Object? v) => v is num ? v.toDouble() : null;
int _i(Object? v) => v is num ? v.toInt() : 0;
String _s(Object? v) => v is String ? v : '';
Json _m(Object? v) => v is Map ? v.cast<String, dynamic>() : const <String, dynamic>{};
DateTime? _t(Object? v) => v is String ? DateTime.tryParse(v) : null;

/// O que este telescópio tem de verdade. `sim` = simulado: o app DIZ isso na tela.
class Capabilities {
  const Capabilities({
    this.mount = 'sim',
    this.goto = 'sim',
    this.camera = 'sim',
    this.focuser = 'sim',
    this.filterWheel = false,
    this.modes = const [],
    this.gpu = '',
  });

  factory Capabilities.fromJson(Json j) => Capabilities(
    mount: _s(j['mount']),
    goto: _s(j['goto']),
    camera: _s(j['camera']),
    focuser: _s(j['focuser']),
    filterWheel: j['filter_wheel'] == true,
    modes: [for (final m in (j['modes'] as List? ?? const [])) '$m'],
    gpu: _s(j['gpu']),
  );

  final String mount;
  final String goto;
  final String camera;
  final String focuser;
  final bool filterWheel;
  final List<String> modes;
  final String gpu;

  bool get mountIsReal => mount != 'sim';
  bool get gotoIsReal => goto != 'sim';
  bool get cameraIsReal => camera != 'sim';
  bool get usesGpu => gpu.contains('GPU');
}

class Site {
  const Site({this.lat = 0, this.lon = 0, this.elevM = 0, this.source = 'default'});

  factory Site.fromJson(Json j) =>
      Site(lat: _d(j['lat']) ?? 0, lon: _d(j['lon']) ?? 0, elevM: _d(j['elev_m']) ?? 0, source: _s(j['source']));

  final double lat;
  final double lon;
  final double elevM;

  /// `phone`: veio deste app; `default`: o aparelho ainda não sabe onde está.
  final String source;
}

class TelescopeInfo {
  const TelescopeInfo({
    required this.id,
    required this.name,
    this.api = 1,
    this.software = '',
    this.capabilities = const Capabilities(),
    this.clockUtc,
    this.clockSynced = false,
    this.site = const Site(),
    this.pairingOpen = false,
  });

  factory TelescopeInfo.fromJson(Json j) => TelescopeInfo(
    id: _s(j['id']),
    name: _s(j['name']),
    api: _i(j['api']),
    software: _s(j['software']),
    capabilities: Capabilities.fromJson(_m(j['capabilities'])),
    clockUtc: _t(_m(j['clock'])['utc']),
    clockSynced: _m(j['clock'])['synced'] == true,
    site: Site.fromJson(_m(j['site'])),
    pairingOpen: j['pairing_open'] == true,
  );

  final String id;
  final String name;
  final int api;
  final String software;
  final Capabilities capabilities;
  final DateTime? clockUtc;

  /// Falso enquanto ninguém mandou a hora e o local: é o que dispara o envio pelo celular.
  final bool clockSynced;
  final Site site;
  final bool pairingOpen;
}

class MountState {
  const MountState({
    this.source = 'sim',
    this.connected = false,
    this.raDeg,
    this.decDeg,
    this.tracking,
    this.parked,
    this.moving,
    this.features = const [],
    this.error,
  });

  factory MountState.fromJson(Json j) => MountState(
    source: _s(j['source']),
    connected: j['connected'] == true,
    raDeg: _d(j['ra_deg']),
    decDeg: _d(j['dec_deg']),
    tracking: j['tracking'] as bool?,
    parked: j['parked'] as bool?,
    moving: j['moving'] as String?,
    features: [for (final f in (j['features'] as List? ?? const [])) '$f'],
    error: j['error'] as String?,
  );

  final String source;
  final bool connected;
  final double? raDeg;
  final double? decDeg;
  final bool? tracking;
  final bool? parked;

  /// A direção do movimento manual em curso (`N`, `S`, `E`, `W`), ou nulo se parada.
  final String? moving;

  /// O que dá para fazer à mão NESTA montagem: `jog`, `park`, `tracking`, `home`. Vazio: só
  /// olhar (hoje é o caso da montagem real).
  final List<String> features;
  final String? error;

  bool get isReal => source != 'sim';
  bool can(String feature) => features.contains(feature);
}

class CameraState {
  const CameraState({
    this.source = 'sim',
    this.connected = false,
    this.model = '',
    this.exposureS = 30,
    this.gain = 120,
    this.offset = 10,
    this.tempC,
    this.applied = false,
  });

  factory CameraState.fromJson(Json j) => CameraState(
    source: _s(j['source']),
    connected: j['connected'] == true,
    model: _s(j['model']),
    exposureS: _d(j['exposure_s']) ?? 30,
    gain: j['gain'] is num ? _i(j['gain']) : 120,
    offset: j['offset'] is num ? _i(j['offset']) : 10,
    tempC: _d(j['temp_c']),
    applied: j['applied'] == true,
  );

  final String source;
  final bool connected;
  final String model;
  final double exposureS;
  final int gain;
  final int offset;
  final double? tempC;

  /// Falso com a câmera simulada: os ajustes ficam guardados, mas não mudam a imagem.
  final bool applied;

  bool get isReal => source != 'sim';
}

/// A câmera com os limites de cada ajuste (`GET /camera`).
class CameraInfo {
  const CameraInfo({required this.state, this.limits = const {}});

  factory CameraInfo.fromJson(Json j) => CameraInfo(
    state: CameraState.fromJson(j),
    limits: {
      for (final e in _m(j['limits']).entries)
        if (e.value case [final num lo, final num hi]) e.key: (lo.toDouble(), hi.toDouble()),
    },
  );

  final CameraState state;

  /// Nome do ajuste (`exposure_s`, `gain`, `offset`) -> (mínimo, máximo).
  final Map<String, (double, double)> limits;
}

class FocusPoint {
  const FocusPoint(this.position, this.fwhmPx);

  final int position;

  /// Tamanho das estrelas nesta posição; nulo quando não havia estrela para medir.
  final double? fwhmPx;
}

/// O focalizador: onde está, até onde vai, e a curva do último autofoco.
class FocusState {
  const FocusState({this.source = 'sim', this.position = 0, this.min, this.max, this.curve = const [], this.best});

  factory FocusState.fromJson(Json j) => FocusState(
    source: _s(j['source']),
    position: _i(j['position']),
    min: j['min'] is num ? _i(j['min']) : null,
    max: j['max'] is num ? _i(j['max']) : null,
    curve: [for (final p in (j['curve'] as List? ?? const [])) FocusPoint(_i(_m(p)['pos']), _d(_m(p)['fwhm_px']))],
    best: j['best'] is num ? _i(j['best']) : null,
  );

  final String source;
  final int position;
  final int? min;
  final int? max;
  final List<FocusPoint> curve;

  /// Onde o autofoco achou o foco; nulo se ainda não rodou ou não achou.
  final int? best;

  bool get atLimit => (min != null && position <= min!) || (max != null && position >= max!);
}

/// Um item da noite autônoma em andamento: o que aconteceu com cada alvo do plano.
class NightItem {
  const NightItem({
    required this.id,
    required this.target,
    this.status = 'pending',
    this.accepted = 0,
    this.snr = 0,
    this.reason = '',
  });

  factory NightItem.fromJson(Json j) => NightItem(
    id: _s(j['id']),
    target: _s(j['target']),
    status: _s(j['status']),
    accepted: _i(j['accepted']),
    snr: _d(j['snr']) ?? 0,
    reason: _s(j['reason']),
  );

  final String id;
  final String target;

  /// `pending`, `running`, `done`, `skipped`, `failed`, `stopped`.
  final String status;
  final int accepted;
  final double snr;

  /// Por que foi pulado ou falhou: `user`, `below_horizon`, `not_found`.
  final String reason;
}

/// A captura planetária em curso: muitos quadros curtos, dos quais só os mais nítidos ficam.
class CaptureState {
  const CaptureState({
    this.body = '',
    this.frames = 0,
    this.total = 0,
    this.kept = 0,
    this.keep = 0,
    this.done = false,
  });

  factory CaptureState.fromJson(Json j) => CaptureState(
    body: _s(j['body']),
    frames: _i(j['frames']),
    total: _i(j['total']),
    kept: _i(j['kept']),
    keep: _d(j['keep']) ?? 0,
    done: j['done'] == true,
  );

  final String body;

  /// Quadros já recebidos, de [total].
  final int frames;
  final int total;

  /// Quantos estão sendo aproveitados (os mais nítidos até agora).
  final int kept;

  /// A fração que fica (0,15 = os 15% melhores).
  final double keep;

  /// O resultado já foi empilhado.
  final bool done;

  double get progress => total <= 0 ? 0 : (frames / total).clamp(0.0, 1.0);
}

/// A última medida do alinhamento polar: quanto o eixo da montagem erra o polo celeste.
class PolarState {
  const PolarState({
    this.step = 0,
    this.points = 3,
    this.measured = false,
    this.altArcmin = 0,
    this.azArcmin = 0,
    this.totalArcmin = 0,
    this.aligned = false,
    this.stale = false,
    this.latDeg,
  });

  factory PolarState.fromJson(Json j) => PolarState(
    step: _i(j['step']),
    points: j['points'] is num ? _i(j['points']) : 3,
    measured: j['measured'] == true,
    altArcmin: _d(j['alt_arcmin']) ?? 0,
    azArcmin: _d(j['az_arcmin']) ?? 0,
    totalArcmin: _d(j['total_arcmin']) ?? 0,
    aligned: j['aligned'] == true,
    stale: j['stale'] == true,
    latDeg: _d(j['lat']),
  );

  /// Em qual dos [points] campos a medida está.
  final int step;
  final int points;

  /// Falso enquanto mede (ou se não deu para medir): os números ainda não valem.
  final bool measured;

  /// Positivo: o eixo está ALTO demais. Em minutos de arco.
  final double altArcmin;

  /// Positivo: o eixo está a LESTE do polo. Em minutos de arco.
  final double azArcmin;
  final double totalArcmin;

  /// O erro já é pequeno o bastante para fotografar minutos sem arrasto.
  final bool aligned;

  /// Mexeram nos parafusos depois desta medida: é preciso medir de novo.
  final bool stale;
  final double? latDeg;
}

class StackState {
  const StackState({
    this.target = '',
    this.accepted = 0,
    this.rejected = 0,
    this.snr = 0,
    this.fwhmPx = 0,
    this.integrationS,
  });

  factory StackState.fromJson(Json j) => StackState(
    target: _s(j['target']),
    accepted: _i(j['accepted']),
    rejected: _i(j['rejected']),
    snr: _d(j['snr']) ?? 0,
    fwhmPx: _d(j['fwhm_px']) ?? 0,
    integrationS: j['integration_s'] is num ? _i(j['integration_s']) : null,
  );

  final String target;
  final int accepted;
  final int rejected;
  final double snr;
  final double fwhmPx;

  /// Nulo com a câmera simulada: não há exposição de verdade para somar.
  final int? integrationS;
}

class Pointing {
  const Pointing({this.error = 0, this.unit = 'px'});

  factory Pointing.fromJson(Json j) => Pointing(error: _d(j['error']) ?? 0, unit: _s(j['unit']));

  final double error;
  final String unit;
}

class QueueState {
  const QueueState({this.done = 0, this.total = 0});

  factory QueueState.fromJson(Json j) => QueueState(done: _i(j['done']), total: _i(j['total']));

  final int done;
  final int total;
}

class SystemState {
  const SystemState({this.tempC, this.diskFreeGb});

  factory SystemState.fromJson(Json j) => SystemState(tempC: _d(j['temp_c']), diskFreeGb: _d(j['disk_free_gb']));

  final double? tempC;
  final double? diskFreeGb;
}

class JobStep {
  const JobStep(this.name, this.state);

  factory JobStep.fromJson(Json j) => JobStep(_s(j['name']), _s(j['state']));

  /// `slew`, `solve`, `focus`, `stack`, `schedule`, `track`.
  final String name;

  /// `running`, `done`, `failed`, `stopped`.
  final String state;
}

/// Um comando longo em andamento (apontar, empilhar...). Vem na resposta do comando e, depois,
/// no estado e nas mensagens `progress` do canal.
class Job {
  const Job({
    required this.id,
    required this.kind,
    required this.state,
    this.target,
    this.steps = const [],
    this.error,
    this.ignored = const [],
  });

  factory Job.fromJson(Json j) => Job(
    id: _s(j['job']),
    kind: _s(j['kind']),
    state: _s(j['state']),
    target: j['target'] as String?,
    steps: [for (final s in (j['steps'] as List? ?? const [])) JobStep.fromJson(_m(s))],
    error: j['error'] as String?,
    ignored: [for (final s in (j['ignored'] as List? ?? const [])) '$s'],
  );

  final String id;
  final String kind;

  /// `accepted` → `running` → `done` | `failed` | `stopped`.
  final String state;
  final String? target;
  final List<JobStep> steps;
  final String? error;

  /// Parâmetros que o aparelho ainda não aplica (câmera simulada): o app avisa.
  final List<String> ignored;

  bool get isOpen => state == 'accepted' || state == 'running';
  bool get failed => state == 'failed';
}

/// O retrato do telescópio: o que `GET /state` devolve e o canal em tempo real atualiza.
class TelescopeState {
  const TelescopeState({
    this.state = 'IDLE',
    this.phase = '',
    this.backend = '',
    this.filter = '',
    this.focusPos = 0,
    this.job,
    this.mount = const MountState(),
    this.camera = const CameraState(),
    this.stack = const StackState(),
    this.pointing = const Pointing(),
    this.queue = const QueueState(),
    this.system = const SystemState(),
    this.focus = const FocusState(),
    this.night = const [],
    this.capture,
    this.polar,
  });

  factory TelescopeState.fromJson(Json j) => TelescopeState(
    state: _s(j['state']).isEmpty ? 'IDLE' : _s(j['state']),
    phase: _s(j['phase']),
    backend: _s(j['backend']),
    filter: _s(j['filter']),
    focusPos: _i(j['focus_pos']),
    job: j['job'] is Map ? Job.fromJson(_m(j['job'])) : null,
    mount: MountState.fromJson(_m(j['mount'])),
    camera: CameraState.fromJson(_m(j['camera'])),
    stack: StackState.fromJson(_m(j['stack'])),
    pointing: Pointing.fromJson(_m(j['pointing'])),
    queue: QueueState.fromJson(_m(j['queue'])),
    system: SystemState.fromJson(_m(j['system'])),
    // um aparelho mais antigo não manda `focus`: a posição vem do campo de sempre
    focus: j['focus'] is Map ? FocusState.fromJson(_m(j['focus'])) : FocusState(position: _i(j['focus_pos'])),
    night: [for (final n in (j['night'] as List? ?? const [])) NightItem.fromJson(_m(n))],
    capture: j['capture'] is Map ? CaptureState.fromJson(_m(j['capture'])) : null,
    polar: j['polar'] is Map ? PolarState.fromJson(_m(j['polar'])) : null,
  );

  /// `IDLE`, `SLEWING`, `SOLVING`, `FOCUSING`, `STACKING`, `SCHEDULING`, `TRACKING`,
  /// `PREVIEW` (câmera ao vivo, sem empilhar), `CAPTURING` (vídeo planetário), `ERROR`,
  /// `STOPPED`.
  final String state;
  final String phase;
  final String backend;
  final String filter;
  final int focusPos;
  final Job? job;
  final MountState mount;
  final CameraState camera;
  final StackState stack;
  final Pointing pointing;
  final QueueState queue;
  final SystemState system;
  final FocusState focus;

  /// O andamento da noite autônoma: um registro por item do plano.
  final List<NightItem> night;

  /// A captura planetária em curso (ou a última, enquanto outro modo não começa).
  final CaptureState? capture;

  /// A última medida do alinhamento polar; nulo se nunca mediu.
  final PolarState? polar;

  /// Há algo se movendo ou capturando: é o que faz o PARAR aparecer em qualquer tela.
  bool get busy => (job?.isOpen ?? false) || !const {'IDLE', 'STOPPED', 'ERROR'}.contains(state);
  bool get stacking => state == 'STACKING';
  bool get previewing => state == 'PREVIEW';
  bool get usesGpu => backend.contains('GPU');

  /// Este trabalho é uma captura planetária (gravando, empilhando ou já terminada).
  bool get planetary => job?.kind == 'planetary';

  /// O alinhamento polar está medindo agora.
  bool get measuringPolar => job?.kind == 'polar' && (job?.isOpen ?? false);

  /// Uma noite autônoma está rodando.
  bool get nightRunning => job?.kind == 'plan' && (job?.isOpen ?? false);

  /// Dá para mexer na montagem à mão agora: nada rodando, ou só a câmera ao vivo.
  bool get mountFree => const {'IDLE', 'STOPPED', 'ERROR', 'PREVIEW'}.contains(state);

  TelescopeState copyWith({
    Job? job,
    MountState? mount,
    CameraState? camera,
    StackState? stack,
    Pointing? pointing,
    QueueState? queue,
    SystemState? system,
    FocusState? focus,
    List<NightItem>? night,
    // estes dois podem VOLTAR a nulo (a captura acabou): por isso vêm como função
    CaptureState? Function()? capture,
    PolarState? Function()? polar,
  }) => TelescopeState(
    state: state,
    phase: phase,
    backend: backend,
    filter: filter,
    focusPos: focus?.position ?? focusPos,
    job: job ?? this.job,
    mount: mount ?? this.mount,
    camera: camera ?? this.camera,
    stack: stack ?? this.stack,
    pointing: pointing ?? this.pointing,
    queue: queue ?? this.queue,
    system: system ?? this.system,
    focus: focus ?? this.focus,
    night: night ?? this.night,
    capture: capture == null ? this.capture : capture(),
    polar: polar == null ? this.polar : polar(),
  );
}

/// Um alvo do catálogo, com a altitude de agora.
class Target {
  const Target({
    required this.id,
    required this.name,
    this.catalog = '',
    this.type = 'other',
    this.raDeg = 0,
    this.decDeg = 0,
    this.mag,
    this.sizeArcmin,
    this.altDeg = 0,
    this.fits,
    this.hasThumb = false,
  });

  factory Target.fromJson(Json j) => Target(
    id: _s(j['id']),
    name: _s(j['name']),
    catalog: _s(j['catalog']),
    type: _s(j['type']),
    raDeg: _d(j['ra_deg']) ?? 0,
    decDeg: _d(j['dec_deg']) ?? 0,
    mag: _d(j['mag']),
    sizeArcmin: _d(j['size_arcmin']),
    altDeg: _d(j['alt_deg']) ?? 0,
    fits: j['fits'] as bool?,
    hasThumb: j['has_thumb'] == true,
  );

  final String id;
  final String name;
  final String catalog;

  /// `nebula`, `galaxy`, `cluster` ou `other`.
  final String type;
  final double raDeg;
  final double decDeg;
  final double? mag;

  /// Eixo maior aparente, em minutos de arco.
  final double? sizeArcmin;
  final double altDeg;

  /// Cabe no nosso campo? Nulo quando o catálogo não traz o tamanho.
  final bool? fits;
  final bool hasThumb;

  /// Alto o bastante para valer a pena agora (acima de 25 graus).
  bool get isHigh => altDeg >= 25;
  bool get isUp => altDeg > 0;
}

class TargetPage {
  const TargetPage({this.total = 0, this.items = const []});

  factory TargetPage.fromJson(Json j) => TargetPage(
    total: _i(j['total']),
    items: [for (final t in (j['items'] as List? ?? const [])) Target.fromJson(_m(t))],
  );

  final int total;
  final List<Target> items;
}

class AltitudePoint {
  const AltitudePoint(this.utc, this.altDeg);

  final DateTime utc;
  final double altDeg;
}

/// A ficha de um alvo: os dados dele mais a noite que vem.
class TargetDetail {
  const TargetDetail({
    required this.target,
    this.night = const [],
    this.bestFrom,
    this.bestTo,
    this.fovDeg = const [0, 0],
    this.fills,
  });

  factory TargetDetail.fromJson(Json j) {
    final night = _m(j['night']);
    final framing = _m(j['framing']);
    return TargetDetail(
      target: Target.fromJson(j),
      night: [
        for (final p in (night['altitude'] as List? ?? const []))
          if (_t(_m(p)['utc']) case final DateTime utc) AltitudePoint(utc, _d(_m(p)['alt_deg']) ?? 0),
      ],
      bestFrom: _t(night['best_from']),
      bestTo: _t(night['best_to']),
      fovDeg: [
        for (final v in (framing['fov_deg'] as List? ?? const [0, 0])) _d(v) ?? 0,
      ],
      fills: _d(framing['fills']),
    );
  }

  final Target target;
  final List<AltitudePoint> night;
  final DateTime? bestFrom;
  final DateTime? bestTo;

  /// O nosso campo: largura e altura em graus.
  final List<double> fovDeg;

  /// Quanto do lado menor do campo o alvo ocupa (1,0 = o campo inteiro).
  final double? fills;
}

/// Uma sessão guardada na Jetson.
class Session {
  const Session({
    required this.id,
    required this.target,
    this.type = 'other',
    this.frames = 0,
    this.integrationS,
    this.integrationApprox = false,
    this.camera = '',
    this.source = 'reference',
    this.hasFits = false,
  });

  factory Session.fromJson(Json j) => Session(
    id: _s(j['id']),
    target: _s(j['target']),
    type: _s(j['type']),
    frames: _i(j['frames']),
    integrationS: j['integration_s'] is num ? _i(j['integration_s']) : null,
    integrationApprox: j['integration_approx'] == true,
    camera: _s(j['camera']),
    source: _s(j['source']),
    hasFits: j['has_fits'] == true,
  );

  final String id;
  final String target;
  final String type;
  final int frames;
  final int? integrationS;
  final bool integrationApprox;
  final String camera;

  /// `reference`: dado real de outro instrumento, processado pelo nosso pipeline.
  /// `telescope`: capturado por este telescópio.
  final String source;
  final bool hasFits;

  bool get isReference => source == 'reference';
}

class RenderControl {
  const RenderControl({required this.min, required this.max, required this.step, required this.initial});

  factory RenderControl.fromJson(Json j) => RenderControl(
    min: _d(j['min']) ?? 0,
    max: _d(j['max']) ?? 1,
    step: _d(j['step']) ?? 0.05,
    initial: _d(j['default']) ?? 0,
  );

  final double min;
  final double max;
  final double step;
  final double initial;
}

/// Presets de um toque e os limites de cada controle do estúdio.
class RenderPresets {
  const RenderPresets({this.presets = const {}, this.controls = const {}, this.toggles = const {}});

  factory RenderPresets.fromJson(Json j) => RenderPresets(
    presets: {for (final e in _m(j['presets']).entries) e.key: _m(e.value).cast<String, Object>()},
    controls: {for (final e in _m(j['controls']).entries) e.key: RenderControl.fromJson(_m(e.value))},
    toggles: {for (final e in _m(j['toggles']).entries) e.key: _m(e.value)['default'] == true},
  );

  final Map<String, Map<String, Object>> presets;
  final Map<String, RenderControl> controls;
  final Map<String, bool> toggles;
}

class SystemInfo {
  const SystemInfo({
    this.tempC,
    this.diskFreeGb,
    this.software = '',
    this.api = 1,
    this.deviceId = '',
    this.power = false,
    this.uptimeS,
    this.firmware,
    this.updatesEnabled = false,
  });

  factory SystemInfo.fromJson(Json j) => SystemInfo(
    tempC: _d(j['temp_c']),
    diskFreeGb: _d(j['disk_free_gb']),
    software: _s(j['software']),
    api: _i(j['api']),
    deviceId: _s(j['device_id']),
    power: j['power'] == true,
    uptimeS: j['uptime_s'] is num ? _i(j['uptime_s']) : null,
    firmware: j['firmware'] as String?,
    updatesEnabled: _m(j['update'])['enabled'] == true,
  );

  final double? tempC;
  final double? diskFreeGb;
  final String software;
  final int api;
  final String deviceId;

  /// O aparelho aceita desligar e reiniciar pelo app?
  final bool power;

  /// Há quanto tempo o software do telescópio está no ar.
  final int? uptimeS;

  /// Versão do firmware da montagem; nulo enquanto o telescópio não a lê.
  final String? firmware;

  /// Atualizar pelo app já existe neste aparelho?
  final bool updatesEnabled;
}

class PairedClient {
  const PairedClient({
    required this.id,
    required this.name,
    this.role = 'owner',
    this.created,
    this.lastUsed,
    this.current = false,
  });

  factory PairedClient.fromJson(Json j) => PairedClient(
    id: _s(j['id']),
    name: _s(j['name']),
    role: _s(j['role']),
    created: _epoch(j['created']),
    lastUsed: _epoch(j['last_used']),
    current: j['current'] == true,
  );

  static DateTime? _epoch(Object? v) =>
      v is num ? DateTime.fromMillisecondsSinceEpoch((v * 1000).round(), isUtc: true) : null;

  final String id;
  final String name;
  final String role;
  final DateTime? created;
  final DateTime? lastUsed;

  /// É este celular.
  final bool current;
}

class SiteResult {
  const SiteResult({this.clockSet = false, this.clockOffsetS = 0, this.mountUpdated = false});

  factory SiteResult.fromJson(Json j) => SiteResult(
    clockSet: j['clock_set'] == true,
    clockOffsetS: _d(j['clock_offset_s']) ?? 0,
    mountUpdated: j['mount_updated'] == true,
  );

  final bool clockSet;
  final double clockOffsetS;

  /// A placa da montagem recebeu a hora e o local agora.
  final bool mountUpdated;
}

/// Um alvo na fila da noite, com o horário que o telescópio calculou para ele.
class PlanItem {
  const PlanItem({
    this.id = '',
    required this.target,
    this.name = '',
    this.type = 'other',
    this.frames = 40,
    this.exposureS = 30,
    this.minAltDeg = 25,
    this.rows = 1,
    this.cols = 1,
    this.overlap = 0.15,
    this.start,
    this.end,
    this.durationS = 0,
    this.altStartDeg,
    this.altEndDeg,
    this.status = 'ok',
  });

  factory PlanItem.fromJson(Json j) {
    final grid = j['mosaic'] as List? ?? const [1, 1];
    return PlanItem(
      id: _s(j['id']),
      target: _s(j['target']),
      name: _s(j['name']),
      type: _s(j['type']),
      frames: _i(j['frames']),
      exposureS: _d(j['exposure_s']) ?? 30,
      minAltDeg: _d(j['min_alt_deg']) ?? 25,
      rows: grid.isNotEmpty ? _i(grid[0]) : 1,
      cols: grid.length > 1 ? _i(grid[1]) : 1,
      overlap: _d(j['overlap']) ?? 0.15,
      start: _t(j['start']),
      end: _t(j['end']),
      durationS: _i(j['duration_s']),
      altStartDeg: _d(j['alt_start_deg']),
      altEndDeg: _d(j['alt_end_deg']),
      status: _s(j['status']),
    );
  }

  final String id;
  final String target;
  final String name;
  final String type;

  /// Número de fotos (por painel, num mosaico) e a exposição de cada uma.
  final int frames;
  final double exposureS;

  /// Só fotografa com o alvo acima disto.
  final double minAltDeg;

  /// Mosaico: linhas e colunas de painéis (1 x 1 = um quadro só).
  final int rows;
  final int cols;
  final double overlap;

  /// Quando começa e termina nesta noite; nulos se não cabe.
  final DateTime? start;
  final DateTime? end;
  final int durationS;
  final double? altStartDeg;
  final double? altEndDeg;

  /// `ok`, `never_up`, `after_dawn`, `sets_early`, `unknown`.
  final String status;

  bool get isMosaic => rows * cols > 1;
  bool get fits => status == 'ok';

  /// O que vai para o telescópio ao guardar o plano (o horário é ele quem calcula).
  Json toJson() => {
    if (id.isNotEmpty) 'id': id,
    'target': target,
    'frames': frames,
    'exposure_s': exposureS,
    'min_alt_deg': minAltDeg,
    'mosaic': [rows, cols],
    'overlap': overlap,
  };

  PlanItem copyWith({int? frames, double? exposureS, double? minAltDeg, int? rows, int? cols, double? overlap}) =>
      PlanItem(
        id: id,
        target: target,
        name: name,
        type: type,
        frames: frames ?? this.frames,
        exposureS: exposureS ?? this.exposureS,
        minAltDeg: minAltDeg ?? this.minAltDeg,
        rows: rows ?? this.rows,
        cols: cols ?? this.cols,
        overlap: overlap ?? this.overlap,
        start: start,
        end: end,
        durationS: durationS,
        altStartDeg: altStartDeg,
        altEndDeg: altEndDeg,
        status: status,
      );
}

/// A fila da noite, com a noite que vem (do escuro ao amanhecer) e quanto dela sobra.
class NightPlan {
  const NightPlan({
    this.items = const [],
    this.nightStart,
    this.nightEnd,
    this.totalS = 0,
    this.freeS = 0,
    this.running = false,
  });

  factory NightPlan.fromJson(Json j) => NightPlan(
    items: [for (final i in (j['items'] as List? ?? const [])) PlanItem.fromJson(_m(i))],
    nightStart: _t(_m(j['night'])['start']),
    nightEnd: _t(_m(j['night'])['end']),
    totalS: _i(j['total_s']),
    freeS: _i(j['free_s']),
    running: j['running'] == true,
  );

  final List<PlanItem> items;
  final DateTime? nightStart;
  final DateTime? nightEnd;
  final int totalS;
  final int freeS;
  final bool running;
}

class MosaicPanel {
  const MosaicPanel({required this.name, this.row = 0, this.col = 0, this.raDeg = 0, this.decDeg = 0});

  factory MosaicPanel.fromJson(Json j) => MosaicPanel(
    name: _s(j['name']),
    row: _i(j['row']),
    col: _i(j['col']),
    raDeg: _d(j['ra_deg']) ?? 0,
    decDeg: _d(j['dec_deg']) ?? 0,
  );

  final String name;
  final int row;
  final int col;
  final double raDeg;
  final double decDeg;
}

/// A grade de um mosaico sobre um alvo: quantos painéis, quanto do céu cobrem.
class MosaicGrid {
  const MosaicGrid({
    required this.target,
    this.name = '',
    this.rows = 1,
    this.cols = 1,
    this.overlap = 0.15,
    this.fieldDeg = const [0, 0],
    this.coversDeg = const [0, 0],
    this.objectArcmin,
    this.coversObject,
    this.panels = const [],
  });

  factory MosaicGrid.fromJson(Json j) => MosaicGrid(
    target: _s(j['target']),
    name: _s(j['name']),
    rows: _i(j['rows']),
    cols: _i(j['cols']),
    overlap: _d(j['overlap']) ?? 0.15,
    fieldDeg: [
      for (final v in (j['field_deg'] as List? ?? const [0, 0])) _d(v) ?? 0,
    ],
    coversDeg: [
      for (final v in (j['covers_deg'] as List? ?? const [0, 0])) _d(v) ?? 0,
    ],
    objectArcmin: _d(j['object_arcmin']),
    coversObject: j['covers_object'] as bool?,
    panels: [for (final p in (j['panels'] as List? ?? const [])) MosaicPanel.fromJson(_m(p))],
  );

  final String target;
  final String name;
  final int rows;
  final int cols;
  final double overlap;

  /// Um quadro: largura e altura, em graus.
  final List<double> fieldDeg;

  /// A grade inteira: largura e altura, em graus.
  final List<double> coversDeg;
  final double? objectArcmin;

  /// O eixo maior do alvo cabe no lado maior da grade? Nulo sem o tamanho no catálogo.
  final bool? coversObject;
  final List<MosaicPanel> panels;
}

/// Lua, planeta ou o Sol, com a altitude de agora.
class SolarBody {
  const SolarBody({
    required this.id,
    required this.name,
    this.kind = 'planet',
    this.raDeg = 0,
    this.decDeg = 0,
    this.altDeg = 0,
    this.phase,
  });

  factory SolarBody.fromJson(Json j) => SolarBody(
    id: _s(j['id']),
    name: _s(j['name']),
    kind: _s(j['kind']),
    raDeg: _d(j['ra_deg']) ?? 0,
    decDeg: _d(j['dec_deg']) ?? 0,
    altDeg: _d(j['alt_deg']) ?? 0,
    phase: _d(j['phase']),
  );

  final String id;
  final String name;

  /// `moon`, `planet` ou `sun`.
  final String kind;
  final double raDeg;
  final double decDeg;
  final double altDeg;

  /// Fração iluminada (só a Lua): 0 = nova, 1 = cheia.
  final double? phase;

  bool get isUp => altDeg > 0;
  bool get isSun => kind == 'sun';
}

/// O convite de um dono para outro celular: o código (uso único) e o QR já desenhado.
class Invite {
  const Invite({required this.uri, this.role = 'operator', this.expiresS = 300, this.qrSvg});

  factory Invite.fromJson(Json j) =>
      Invite(uri: _s(j['uri']), role: _s(j['role']), expiresS: _i(j['expires_s']), qrSvg: j['qr_svg'] as String?);

  final String uri;
  final String role;
  final int expiresS;
  final String? qrSvg;
}

/// O WiFi que o próprio telescópio cria (modo campo).
class Hotspot {
  const Hotspot({this.ssid = '', this.active = false, this.psk, this.address = ''});

  factory Hotspot.fromJson(Json j) =>
      Hotspot(ssid: _s(j['ssid']), active: j['active'] == true, psk: j['psk'] as String?, address: _s(j['address']));

  final String ssid;

  /// É por ele que o telescópio está atendendo agora.
  final bool active;

  /// A senha: só vem para o dono.
  final String? psk;

  /// Onde o telescópio atende nesse WiFi: o app guarda, para achá-lo no campo.
  final String address;
}

/// Uma rede WiFi que o TELESCÓPIO enxerga (não o celular).
class WifiNetwork {
  const WifiNetwork({required this.ssid, this.signal = 0, this.secure = true, this.known = false});

  factory WifiNetwork.fromJson(Json j) => WifiNetwork(
    ssid: _s(j['ssid']),
    signal: _i(j['signal']),
    secure: j['secure'] != false,
    known: j['known'] == true,
  );

  final String ssid;

  /// Força do sinal, de 0 a 100.
  final int signal;

  /// Pede senha.
  final bool secure;

  /// O telescópio já tem a senha guardada.
  final bool known;
}

/// A resposta a um pedido de troca de rede: aceito, e quanto esperar para procurar de novo.
class NetworkChange {
  const NetworkChange({this.accepted = false, this.reconnectS = 0});

  factory NetworkChange.fromJson(Json j) =>
      NetworkChange(accepted: j['accepted'] == true, reconnectS: _i(j['reconnect_s']));

  final bool accepted;

  /// A troca acontece DEPOIS da resposta; zero quando não há o que trocar.
  final int reconnectS;
}

/// Como o aparelho está na rede.
class NetworkInfo {
  const NetworkInfo({
    this.enabled = false,
    this.mode = 'unknown',
    this.hostname = '',
    this.address = '',
    this.port = 0,
    this.wifiSsid,
    this.wifiSignal = 0,
    this.hotspot,
    this.known = const [],
    this.lastError,
    this.switching = false,
  });

  factory NetworkInfo.fromJson(Json j) => NetworkInfo(
    enabled: j['enabled'] == true,
    mode: _s(j['mode']),
    hostname: _s(j['hostname']),
    address: _s(j['address']),
    port: _i(j['port']),
    wifiSsid: j['wifi'] is Map ? _s(_m(j['wifi'])['ssid']) : null,
    wifiSignal: _i(_m(j['wifi'])['signal']),
    hotspot: j['hotspot'] is Map ? Hotspot.fromJson(_m(j['hotspot'])) : null,
    known: [for (final s in (j['known'] as List? ?? const [])) '$s'],
    lastError: j['last_error'] as String?,
    switching: j['switching'] == true,
  );

  /// Trocar de rede pelo app já foi habilitado neste aparelho?
  final bool enabled;

  /// `home` (roteador de casa), `field` (WiFi próprio) ou `unknown`.
  final String mode;
  final String hostname;
  final String address;
  final int port;

  /// A rede de casa em que o telescópio está, e a força do sinal (0 a 100).
  final String? wifiSsid;
  final int wifiSignal;
  final Hotspot? hotspot;

  /// As redes de casa que o telescópio guarda.
  final List<String> known;

  /// Por que a última troca não deu certo: `wrong_password`, `not_found`. O telescópio ficou
  /// onde estava.
  final String? lastError;

  /// Uma troca foi pedida e ainda não aconteceu.
  final bool switching;

  bool get atHome => mode == 'home';
  bool get inField => mode == 'field';
}

/// A atualização do software do telescópio.
class UpdateInfo {
  const UpdateInfo({
    this.enabled = false,
    this.current = '',
    this.available,
    this.notes = const [],
    this.state = 'idle',
    this.progress,
    this.error,
  });

  factory UpdateInfo.fromJson(Json j) => UpdateInfo(
    enabled: j['enabled'] == true,
    current: _s(j['current']),
    available: j['available'] is Map ? _s(_m(j['available'])['version']) : null,
    notes: [for (final n in (_m(j['available'])['notes'] as List? ?? const [])) '$n'],
    state: _s(j['state']).isEmpty ? 'idle' : _s(j['state']),
    progress: _d(j['progress']),
    error: j['error'] as String?,
  );

  /// Atualizar pelo app existe neste aparelho?
  final bool enabled;
  final String current;

  /// A versão nova encontrada, com o que muda nela; nulo se não há (ou ainda não procurou).
  final String? available;
  final List<String> notes;

  /// `idle`, `checking`, `downloading`, `installing`, `restarting`, `failed`.
  final String state;

  /// De 0 a 1, enquanto baixa e instala.
  final double? progress;

  /// Por que a instalação falhou. A versão de antes continua valendo.
  final String? error;

  /// Há uma procura ou instalação em andamento.
  bool get working => const {'checking', 'downloading', 'installing', 'restarting'}.contains(state);
  bool get installing => const {'downloading', 'installing', 'restarting'}.contains(state);
  bool get failed => state == 'failed';
}
