import 'dart:typed_data';

import '../domain/models.dart';

/// A porta: tudo que o app enxerga do telescópio.
///
/// É o equivalente, no app, das portas `Mount`/`Focuser` da Jetson. As telas não sabem se do
/// outro lado há o aparelho de verdade ([HttpTelescope], canal cifrado), o software da Jetson
/// rodando no PC com simuladores, ou o falso do modo demonstração ([FakeTelescope]). Toda
/// falha vira [ApiFailure], já classificada.
abstract interface class TelescopeApi {
  // ---- aparelho ----
  Future<TelescopeInfo> info();
  Future<TelescopeState> state();

  /// O estado ao vivo, empurrado pela Jetson. Emite o retrato inteiro a cada mudança (as
  /// mensagens parciais já vêm aplicadas). Termina com erro quando o canal cai: quem escuta
  /// decide reconectar.
  Stream<TelescopeState> watch();

  /// Hora e local, que só o celular sabe (no campo a Jetson não tem internet nem GPS).
  Future<SiteResult> setSite({
    required DateTime utc,
    required double lat,
    required double lon,
    double elevM = 0,
    double? accuracyM,
  });

  Future<SystemInfo> system();

  /// `shutdown` ou `restart`.
  Future<void> power(String action);
  Future<List<PairedClient>> clients();
  Future<void> revoke(String clientId);

  // ---- céu ----
  Future<TargetPage> targets({
    String query = '',
    String type = '',
    bool visible = false,
    bool fits = false,
    int limit = 50,
    int offset = 0,
  });
  Future<TargetDetail> target(String id);
  Future<Uint8List?> targetThumb(String id);

  // ---- observar ----
  /// [commandId] identifica o comando: reenviar o mesmo (depois de uma queda de sinal) devolve
  /// o mesmo trabalho, sem mover a montagem duas vezes.
  Future<Job> goTo({required String commandId, String? target, double? raDeg, double? decDeg});

  /// A "noite rápida": aponta, centraliza e, se deu certo, empilha até alguém parar. É um
  /// comando só para a sequência seguir na Jetson mesmo que o celular perca o sinal.
  Future<Job> observe({required String commandId, required String target});
  Future<Job> stack({required String commandId, double? exposureS, int? gain, int frames = 0});
  Future<Job> run({required String commandId, required String mode, String? target});
  Future<Job> stop({required String commandId});

  /// A imagem ao vivo, quadro a quadro (JPEG), já no tamanho pedido.
  Stream<Uint8List> preview({int maxSide = 1280});
  Future<Uint8List?> frame({int maxSide = 1280});
  Future<List<double>> histogram();

  /// Liga a câmera ao vivo SEM empilhar: para enquadrar e focar à mão.
  Future<Job> startPreview({required String commandId});

  /// Autofoco: varre o focalizador e vai ao foco. A curva chega no estado (`focus.curve`).
  Future<Job> autofocus({required String commandId});

  // ---- montagem, foco e câmera, à mão ----
  /// Move a montagem na direção `N`, `S`, `E` ou `W` por no máximo [holdMs]. É para ser
  /// renovado enquanto o dedo está no botão: sem renovar, a montagem para sozinha.
  Future<void> jog(String direction, {int rate = 2, int holdMs = 800});
  Future<void> haltMount();

  /// `park`, `unpark` ou `home`.
  Future<void> mountAction(String action);
  Future<void> setTracking({required bool on});

  /// Move o focalizador [delta] passos, ou vai para [position]. Devolve onde ele deve parar.
  Future<int> moveFocus({int? delta, int? position});
  Future<CameraInfo> camera();
  Future<CameraInfo> setCamera({double? exposureS, int? gain, int? offset});

  // ---- Lua, planetas e Sol ----
  Future<List<SolarBody>> solar();

  /// Aponta para um corpo do sistema solar. O Sol exige [filterConfirmed].
  Future<Job> goToBody({required String commandId, required String body, bool filterConfirmed = false});

  // ---- plano da noite ----
  Future<NightPlan> plan();

  /// Troca a fila inteira (é assim que se reordena) e devolve os horários recalculados.
  Future<NightPlan> savePlan(List<PlanItem> items);
  Future<Job> startPlan({required String commandId});

  /// Pula o alvo em curso; a noite segue no próximo.
  Future<void> skipPlanItem();
  Future<MosaicGrid> mosaic({required String target, int rows = 2, int cols = 2, double overlap = 0.15});

  // ---- celulares e aparelho ----
  Future<void> setRole(String clientId, String role);

  /// Convite para outro celular: um código de uso único, já desenhado como QR.
  Future<Invite> invite({String role = 'operator', int minutes = 5});

  /// Dá um nome ao telescópio; devolve o nome que ficou.
  Future<String> rename(String name);

  // ---- captura planetária e alinhamento polar ----
  /// Lua e planetas: grava [frames] quadros curtos e empilha só os [keepPercent]% mais
  /// nítidos. Com [point], aponta e centraliza antes. O andamento chega em `capture`.
  Future<Job> capturePlanetary({
    required String commandId,
    required String body,
    int frames = 300,
    int keepPercent = 15,
    bool point = true,
  });

  /// Mede o erro do eixo polar em três pontos. O resultado chega em `polar`.
  Future<Job> measurePolar({required String commandId});

  /// Os parafusos da montagem SIMULADA (na real, quem gira é a pessoa). A medida anterior
  /// deixa de valer.
  Future<void> adjustPolar({required double altArcmin, required double azArcmin});

  // ---- rede do telescópio ----
  Future<NetworkInfo> network();

  /// As redes que o TELESCÓPIO enxerga.
  Future<List<WifiNetwork>> scanNetworks();

  /// Manda o telescópio entrar numa rede de casa. Sem [psk] quando ela é aberta ou já está
  /// guardada. A troca acontece depois da resposta.
  Future<NetworkChange> joinNetwork(String ssid, {String? psk});

  /// `home` (a rede de casa guardada) ou `field` (o WiFi próprio).
  Future<NetworkChange> setNetworkMode(String mode);
  Future<void> setHotspotPassword(String psk);
  Future<void> forgetNetwork(String ssid);

  // ---- atualização do software do telescópio ----
  Future<UpdateInfo> update();
  Future<UpdateInfo> checkUpdate();
  Future<UpdateInfo> installUpdate();

  // ---- galeria e estúdio ----
  Future<List<Session>> sessions();
  Future<Uint8List?> sessionImage(String id, {bool thumb = false});

  /// Prévia com os controles do estúdio (`preset`, `stretch`, `saturation`..., `full`).
  Future<Uint8List?> render(String sessionId, Map<String, Object> controls);
  Future<RenderPresets> presets();

  /// O resultado para levar: `jpg` (tratado), `tif` (16 bits, linear) ou `fits`.
  /// [maxSide] reduz a imagem; 0 é o tamanho cheio.
  Future<Uint8List?> exportSession(String id, {String format = 'jpg', int maxSide = 0});
  Future<void> deleteSession(String id);

  /// Libera conexões e temporizadores. Depois disso o objeto não serve mais.
  void close();
}
