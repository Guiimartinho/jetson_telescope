import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// As escolhas de quem usa, guardadas no celular (não vão para a Jetson).
class Prefs {
  const Prefs({
    this.redMode = false,
    this.proMode = false,
    this.haptics = true,
    this.notify = false,
    this.offerHomeWifi = false,
    this.favorites = const {},
    this.siteLat,
    this.siteLon,
    this.siteElevM = 0,
    this.clientName = '',
  });

  /// Modo vermelho: o app inteiro em vermelho escuro, para preservar a visão noturna.
  final bool redMode;

  /// Modo Pro: mostra histograma, SNR, FWHM e os termos do ofício.
  final bool proMode;

  /// Vibração curta quando um comando é aceito.
  final bool haptics;

  /// Avisar com a tela apagada: o fim de um trabalho, uma falha, a queda do sinal.
  final bool notify;

  /// Acabou de parear pelo WiFi do próprio telescópio: vale oferecer, uma vez, pô-lo no WiFi
  /// de casa.
  final bool offerHomeWifi;
  final Set<String> favorites;

  /// O último local enviado ao telescópio: reenviado sozinho a cada conexão.
  final double? siteLat;
  final double? siteLon;
  final double siteElevM;

  /// Como este celular se apresenta ao telescópio.
  final String clientName;

  bool get hasSite => siteLat != null && siteLon != null;
}

/// O armazenamento das preferências; em `main` é trocado pela instância já carregada.
final sharedPreferencesProvider = Provider<SharedPreferences>(
  (ref) => throw UnimplementedError('carregue SharedPreferences antes de runApp'),
);

final prefsProvider = NotifierProvider<PrefsController, Prefs>(PrefsController.new);

class PrefsController extends Notifier<Prefs> {
  SharedPreferences get _store => ref.read(sharedPreferencesProvider);

  @override
  Prefs build() {
    final s = ref.watch(sharedPreferencesProvider);
    return Prefs(
      redMode: s.getBool('red') ?? false,
      proMode: s.getBool('pro') ?? false,
      haptics: s.getBool('haptics') ?? true,
      notify: s.getBool('notify') ?? false,
      offerHomeWifi: s.getBool('offer.home_wifi') ?? false,
      favorites: (s.getStringList('favorites') ?? const []).toSet(),
      siteLat: s.getDouble('site.lat'),
      siteLon: s.getDouble('site.lon'),
      siteElevM: s.getDouble('site.elev') ?? 0,
      clientName: s.getString('client') ?? '',
    );
  }

  Prefs _copy({
    bool? redMode,
    bool? proMode,
    bool? haptics,
    bool? notify,
    bool? offerHomeWifi,
    Set<String>? favorites,
    double? siteLat,
    double? siteLon,
    double? siteElevM,
    String? clientName,
  }) => Prefs(
    redMode: redMode ?? state.redMode,
    proMode: proMode ?? state.proMode,
    haptics: haptics ?? state.haptics,
    notify: notify ?? state.notify,
    offerHomeWifi: offerHomeWifi ?? state.offerHomeWifi,
    favorites: favorites ?? state.favorites,
    siteLat: siteLat ?? state.siteLat,
    siteLon: siteLon ?? state.siteLon,
    siteElevM: siteElevM ?? state.siteElevM,
    clientName: clientName ?? state.clientName,
  );

  Future<void> setRedMode(bool on) async {
    state = _copy(redMode: on);
    await _store.setBool('red', on);
  }

  Future<void> setProMode(bool on) async {
    state = _copy(proMode: on);
    await _store.setBool('pro', on);
  }

  Future<void> setHaptics(bool on) async {
    state = _copy(haptics: on);
    await _store.setBool('haptics', on);
  }

  Future<void> setNotify(bool on) async {
    state = _copy(notify: on);
    await _store.setBool('notify', on);
  }

  Future<void> setOfferHomeWifi(bool on) async {
    state = _copy(offerHomeWifi: on);
    await _store.setBool('offer.home_wifi', on);
  }

  Future<void> toggleFavorite(String targetId) async {
    final next = {...state.favorites};
    next.contains(targetId) ? next.remove(targetId) : next.add(targetId);
    state = _copy(favorites: next);
    await _store.setStringList('favorites', next.toList()..sort());
  }

  Future<void> setSite(double lat, double lon, double elevM) async {
    state = _copy(siteLat: lat, siteLon: lon, siteElevM: elevM);
    await _store.setDouble('site.lat', lat);
    await _store.setDouble('site.lon', lon);
    await _store.setDouble('site.elev', elevM);
  }

  Future<void> setClientName(String name) async {
    state = _copy(clientName: name);
    await _store.setString('client', name);
  }
}
