import 'dart:async';
import 'dart:math';

import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/errors.dart';
import '../core/strings.dart';
import '../data/telescope_api.dart';
import '../domain/models.dart';
import 'link.dart';
import 'prefs.dart';
import 'queries.dart';

/// Um aviso curto para quem usa: comando aceito, ou por que não foi.
class Toast {
  const Toast(this.text, {this.bad = false});

  final String text;
  final bool bad;
}

final toastProvider = StateProvider<Toast?>((ref) => null);

final commandsProvider = Provider<Commands>(Commands.new);

/// Os comandos que movem ou capturam. Cada um leva um identificador sorteado aqui: se a rede
/// cair no meio, o reenvio usa o MESMO identificador e a Jetson não executa duas vezes.
class Commands {
  Commands(this._ref);

  final Ref _ref;
  static final _random = Random.secure();

  static String _newId() => 'a-${List.generate(10, (_) => _random.nextInt(16).toRadixString(16)).join()}';

  void _say(String text, {bool bad = false}) => _ref.read(toastProvider.notifier).state = Toast(text, bad: bad);

  Future<Job?> _send(Future<Job> Function(TelescopeApi api, String id) send) async {
    final api = _ref.read(linkProvider).api;
    if (api == null) return null;
    final id = _newId();
    try {
      Job job;
      try {
        job = await send(api, id);
      } on ApiFailure catch (failure) {
        if (failure.kind != FailureKind.unreachable) rethrow;
        job = await send(api, id); // uma segunda tentativa, com o mesmo identificador
      }
      if (_ref.read(prefsProvider).haptics) unawaited(HapticFeedback.lightImpact());
      if (job.ignored.isNotEmpty) {
        _say('Câmera simulada: ${job.ignored.map(S.ignoredParam).join(', ')} ainda não é aplicado.');
      }
      return job;
    } on ApiFailure catch (failure) {
      _say(S.failure(failure), bad: true);
      return null;
    }
  }

  /// A "noite rápida": apontar, centralizar e empilhar.
  Future<Job?> observe(String target) => _send((api, id) => api.observe(commandId: id, target: target));

  Future<Job?> goTo(String target) => _send((api, id) => api.goTo(commandId: id, target: target));

  Future<Job?> goToCoordinates(double raDeg, double decDeg) =>
      _send((api, id) => api.goTo(commandId: id, raDeg: raDeg, decDeg: decDeg));

  Future<Job?> stack({double? exposureS, int? gain}) =>
      _send((api, id) => api.stack(commandId: id, exposureS: exposureS, gain: gain));

  /// PARAR: nunca pede confirmação.
  Future<Job?> stop() => _send((api, id) => api.stop(commandId: id));

  /// A câmera ao vivo, sem empilhar: enquadrar e focar à mão.
  Future<Job?> preview() => _send((api, id) => api.startPreview(commandId: id));

  Future<Job?> autofocus() => _send((api, id) => api.autofocus(commandId: id));

  /// Um modo do telescópio pelo nome (`tracking`: rastrear um objeto que cruza o campo).
  Future<Job?> run(String mode) => _send((api, id) => api.run(commandId: id, mode: mode));

  /// A noite autônoma: o telescópio percorre o plano sozinho.
  Future<Job?> startNight() => _send((api, id) => api.startPlan(commandId: id));

  Future<Job?> goToBody(String body, {bool filterConfirmed = false}) =>
      _send((api, id) => api.goToBody(commandId: id, body: body, filterConfirmed: filterConfirmed));

  /// Lua e planetas: muitos quadros curtos, e só os mais nítidos empilhados.
  Future<Job?> planetary(String body, {int frames = 300, int keepPercent = 15, bool point = true}) => _send(
    (api, id) =>
        api.capturePlanetary(commandId: id, body: body, frames: frames, keepPercent: keepPercent, point: point),
  );

  /// Mede o erro do eixo polar da montagem.
  Future<Job?> measurePolar() => _send((api, id) => api.measurePolar(commandId: id));

  /// Uma ação que não vira trabalho (foco, câmera, montagem à mão). Devolve o resultado, ou
  /// nulo se não deu — e aí quem usa já foi avisado do porquê.
  Future<T?> act<T>(Future<T> Function(TelescopeApi api) action, {bool quiet = false}) async {
    final api = _ref.read(linkProvider).api;
    if (api == null) return null;
    try {
      return await action(api);
    } on ApiFailure catch (failure) {
      if (!quiet) _say(S.failure(failure), bad: true);
      return null;
    }
  }

  void say(String text) => _say(text);
}

final planEditorProvider = Provider<PlanEditor>(PlanEditor.new);

/// Mexe na fila da noite. A fila mora no telescópio: cada mudança manda a fila inteira, e os
/// horários voltam recalculados.
class PlanEditor {
  PlanEditor(this._ref);

  final Ref _ref;

  Future<bool> _save(List<PlanItem> Function(List<PlanItem> now) change) async {
    final commands = _ref.read(commandsProvider);
    final saved = await commands.act((api) async => api.savePlan(change((await api.plan()).items)));
    if (saved == null) return false;
    _ref.invalidate(planProvider);
    return true;
  }

  /// Põe um alvo no fim da fila (com a grade de um mosaico, se for o caso).
  Future<bool> add(String target, {int rows = 1, int cols = 1, double overlap = 0.15}) async {
    final ok = await _save((now) => [...now, PlanItem(target: target, rows: rows, cols: cols, overlap: overlap)]);
    if (ok) _ref.read(commandsProvider).say('$target entrou no plano da noite.');
    return ok;
  }

  Future<bool> remove(String id) => _save(
    (now) => [
      for (final item in now)
        if (item.id != id) item,
    ],
  );

  /// Sobe (`-1`) ou desce (`+1`) um item na fila.
  Future<bool> move(String id, int delta) => _save((now) {
    final from = now.indexWhere((item) => item.id == id);
    final to = from + delta;
    if (from < 0 || to < 0 || to >= now.length) return now;
    final next = List.of(now);
    next.insert(to, next.removeAt(from));
    return next;
  });

  Future<bool> update(PlanItem changed) =>
      _save((now) => [for (final item in now) item.id == changed.id ? changed : item]);
}
