import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Um aviso para quem não está olhando a tela.
class AppNotice {
  const AppNotice(this.title, this.text, {this.bad = false, this.slot});

  /// O lugar dos avisos sobre o sinal: um só, que o seguinte substitui. WiFi oscilando não pode
  /// empilhar uma fileira de "sem sinal".
  static const signalSlot = 2;

  final String title;
  final String text;

  /// Algo deu errado: o aviso pede atenção.
  final bool bad;

  /// Avisos com o mesmo lugar se substituem; sem lugar, cada um fica.
  final int? slot;

  @override
  bool operator ==(Object other) =>
      other is AppNotice && other.title == title && other.text == text && other.bad == bad && other.slot == slot;

  @override
  int get hashCode => Object.hash(title, text, bad, slot);

  @override
  String toString() => 'AppNotice($title | $text${bad ? ' | ruim' : ''})';
}

/// A porta dos avisos com a tela apagada.
///
/// Uma noite autônoma dura horas e ninguém fica olhando o celular. Para o app continuar
/// ouvindo o telescópio com a tela apagada, o Android exige um SERVIÇO EM PRIMEIRO PLANO, com
/// um aviso fixo dizendo o que está acontecendo ([ongoing]). Quando o trabalho termina (ou
/// falha), sai um aviso comum ([notify]).
abstract interface class Alerts {
  /// Pede a permissão de mostrar avisos (Android 13 em diante). Falso: a pessoa negou, ou
  /// este aparelho não avisa.
  Future<bool> enable();

  /// Liga (ou atualiza) o aviso fixo e mantém o app acordado para o telescópio.
  Future<void> ongoing(String title, String text);
  Future<void> endOngoing();
  Future<void> notify(AppNotice notice);
}

/// Pelo sistema de avisos do Android (`flutter_local_notifications`).
///
/// ESTADO: escrito conforme a documentação do pacote e do Android; ainda NÃO validado num
/// celular. O serviço e as permissões estão em `android/app/src/main/AndroidManifest.xml`.
class PlatformAlerts implements Alerts {
  final _plugin = FlutterLocalNotificationsPlugin();
  Future<bool>? _ready;
  var _next = 100;

  static const _ongoingId = 1;
  static const _ongoingChannel = AndroidNotificationDetails(
    'telescope.ongoing',
    'Acompanhando o telescópio',
    channelDescription: 'O aviso fixo enquanto o telescópio trabalha com a tela apagada.',
    importance: Importance.low,
    priority: Priority.low,
    ongoing: true,
    autoCancel: false,
    onlyAlertOnce: true,
    showWhen: false,
    playSound: false,
    enableVibration: false,
    category: AndroidNotificationCategory.progress,
  );
  static const _eventChannel = AndroidNotificationDetails(
    'telescope.events',
    'Avisos do telescópio',
    channelDescription: 'Quando um trabalho termina ou falha.',
    importance: Importance.high,
    priority: Priority.high,
  );

  AndroidFlutterLocalNotificationsPlugin? get _android =>
      _plugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();

  Future<bool> _init() => _ready ??= () async {
    if (!Platform.isAndroid) return false;
    try {
      // o ícone é o símbolo do produto, exportado do ui_kit (res/drawable/ic_stat_telescope.xml)
      const settings = InitializationSettings(android: AndroidInitializationSettings('ic_stat_telescope'));
      return await _plugin.initialize(settings: settings) ?? false;
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    }
  }();

  Future<T?> _guard<T>(Future<T?> Function() action) async {
    if (!await _init()) return null;
    try {
      return await action();
    } on MissingPluginException {
      return null;
    } on PlatformException {
      // sem permissão, ou o Android não deixou subir o serviço com o app em segundo plano:
      // o app continua funcionando, só não avisa
      return null;
    }
  }

  @override
  Future<bool> enable() async => await _guard(() async => _android?.requestNotificationsPermission()) ?? false;

  @override
  Future<void> ongoing(String title, String text) => _guard(
    () async => _android?.startForegroundService(
      id: _ongoingId,
      title: title,
      body: text,
      notificationDetails: _ongoingChannel,
      // Não "grudento": se o Android matar o app, o serviço NÃO é recriado sozinho. Recriado
      // sem o app ele não teria quem escutasse o telescópio — e o pacote quebra nesse caso.
      startType: AndroidServiceStartType.startNotSticky,
      foregroundServiceTypes: {AndroidServiceForegroundType.foregroundServiceTypeConnectedDevice},
    ),
  );

  @override
  Future<void> endOngoing() => _guard(() async => _android?.stopForegroundService());

  @override
  Future<void> notify(AppNotice notice) => _guard(
    () => _plugin.show(
      id: notice.slot ?? _next++,
      title: notice.title,
      body: notice.text,
      notificationDetails: const NotificationDetails(android: _eventChannel),
    ),
  );
}

final alertsProvider = Provider<Alerts>((ref) => PlatformAlerts());
