import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/strings.dart';
import '../data/alerts.dart';
import '../domain/models.dart';
import 'link.dart';
import 'prefs.dart';

/// O que vale avisar quando o estado do telescópio passa de [before] para [after].
///
/// Só o FIM de um trabalho que o app viu em andamento: ninguém quer o celular vibrando a cada
/// foto. O que a própria pessoa mandou parar não vira aviso.
AppNotice? noticeFor(TelescopeState? before, TelescopeState after) {
  final was = before?.job;
  final job = after.job;
  if (was == null || job == null || was.id != job.id || !was.isOpen || job.isOpen) return null;
  if (job.state == 'stopped') return null;
  final target = (job.target ?? '').isEmpty ? null : job.target;
  if (job.failed) {
    return AppNotice(
      switch (job.kind) {
        'focus' => 'O autofoco não achou o foco',
        'polar' => 'Não deu para medir o alinhamento polar',
        'plan' => 'A noite parou com erro',
        _ => target == null ? 'O telescópio parou com erro' : 'Não deu certo: $target',
      },
      S.jobError(job.error),
      bad: true,
    );
  }
  switch (job.kind) {
    case 'plan':
      final done = after.night.where((n) => n.status == 'done').length;
      final total = after.night.length;
      return AppNotice(
        'A noite terminou',
        total == 0
            ? 'O plano chegou ao fim.'
            : '$done de $total ${total == 1 ? 'alvo fotografado' : 'alvos fotografados'}.',
      );
    case 'planetary':
      final capture = after.capture;
      return AppNotice(
        'Captura pronta${target == null ? '' : ': $target'}',
        capture == null
            ? 'Os melhores quadros foram empilhados.'
            : '${capture.kept} de ${capture.total} quadros aproveitados.',
      );
    case 'polar':
      final polar = after.polar;
      if (polar == null || !polar.measured) return const AppNotice('Alinhamento polar medido', 'Abra o app para ver.');
      return AppNotice(
        polar.aligned ? 'A montagem está alinhada' : 'Alinhamento polar medido',
        polar.aligned
            ? 'O eixo erra o polo por ${S.arcmin(polar.totalArcmin)}: dá para fotografar.'
            : 'O eixo erra o polo por ${S.arcmin(polar.totalArcmin)}. Abra o app para ver o ajuste.',
      );
    case 'focus':
      return const AppNotice('Foco encontrado', 'O focalizador já está na posição mais nítida.');
    case 'goto':
      return AppNotice('Alvo centralizado', target ?? 'O telescópio está apontado.');
    default:
      final photos = after.stack.accepted;
      return AppNotice(
        target == null ? 'Sessão encerrada' : 'Sessão encerrada: $target',
        photos > 0
            ? '$photos ${photos == 1 ? 'foto empilhada' : 'fotos empilhadas'}.'
            : 'O telescópio terminou o trabalho.',
      );
  }
}

/// O texto do aviso fixo enquanto o telescópio trabalha com a tela apagada.
String ongoingText(TelescopeState t) {
  final job = t.job;
  final target = (job?.target ?? '').isNotEmpty ? job!.target! : t.stack.target;
  final activity = S.activity(t.state);
  final what = '${activity[0].toUpperCase()}${activity.substring(1)}';
  if (t.nightRunning && t.night.isNotEmpty) {
    final done = t.night.where((n) => const {'done', 'skipped', 'failed'}.contains(n.status)).length;
    final current = t.night.where((n) => n.status == 'running').firstOrNull;
    return 'Noite: $done de ${t.night.length}${current == null ? '' : ' · agora ${current.target}'}';
  }
  if (t.state == 'CAPTURING' && t.capture != null) {
    return 'Gravando ${S.body(t.capture!.body)} · ${t.capture!.frames} de ${t.capture!.total} quadros';
  }
  if (t.stacking) {
    return '$what${target.isEmpty ? '' : ' $target'} · ${t.stack.accepted} ${t.stack.accepted == 1 ? 'foto' : 'fotos'}';
  }
  return target.isEmpty ? what : '$what · $target';
}

/// O app está fora da vista: tela apagada, ou outro app na frente. Quem diz é o `TelescopeApp`.
final appHiddenProvider = StateProvider<bool>((ref) => false);

/// Sem sinal por este tempo, o app para de acompanhar: o telescópio pode ter ficado sem bateria,
/// e não faz sentido segurar o celular acordado (e procurando) a noite toda.
final noticeGiveUpProvider = Provider<Duration>((ref) => const Duration(minutes: 10));

final noticeWatcherProvider = Provider<NoticeWatcher>((ref) {
  final watcher = NoticeWatcher(ref);
  ref.onDispose(watcher.dispose);
  return watcher;
});

/// Liga o telescópio aos avisos do celular (preferência "Avisar com a tela apagada").
///
/// Enquanto houver um trabalho rodando, mantém o aviso fixo — é ele que deixa o app ouvir o
/// telescópio com a tela apagada. Quando o trabalho termina ou falha, ou o sinal cai no meio,
/// e ninguém está olhando, sai um aviso comum.
class NoticeWatcher {
  NoticeWatcher(this._ref) {
    _alerts; // resolve agora
    _link = _ref.listen<Link>(linkProvider, _onLink, fireImmediately: true);
    _pref = _ref.listen<bool>(
      prefsProvider.select((p) => p.notify),
      (_, on) => on ? _onLink(null, _ref.read(linkProvider)) : _end(),
    );
  }

  /// O aviso fixo muda a cada mudança de atividade; fora isso, no máximo neste ritmo (uma
  /// captura planetária publica dezenas de vezes por segundo).
  static const _pace = Duration(seconds: 3);

  /// O aviso fixo só sai um instante depois de o trabalho acabar. O Android derruba o app se o
  /// serviço for parado antes de terminar de subir (um trabalho que acaba na hora), e entre dois
  /// trabalhos seguidos não vale a pena tirar e pôr.
  static const _linger = Duration(seconds: 2);

  final Ref _ref;
  // guardado já: ao descartar não se pode mais ler outros provedores
  late final Alerts _alerts = _ref.read(alertsProvider);
  late final Duration _giveUpAfter = _ref.read(noticeGiveUpProvider);
  late final ProviderSubscription<Link> _link;
  late final ProviderSubscription<bool> _pref;
  String? _shown;
  String? _activity;
  DateTime? _shownAt;
  Timer? _ending;
  Timer? _givingUp;

  /// Desistiu de acompanhar nesta queda de sinal: só volta quando a ligação voltar.
  bool _gaveUp = false;

  bool get _hidden => _ref.read(appHiddenProvider);

  void _onLink(Link? before, Link after) {
    if (!_ref.read(prefsProvider).notify) return;
    final telescope = after.telescope;
    final lost = after.phase == LinkPhase.reconnecting;
    // O que vale acompanhar com a tela apagada é um trabalho em curso. A câmera ao vivo não
    // entra: ela não termina sozinha, e não há o que contar.
    final working = after.usable && telescope != null && telescope.busy && !telescope.previewing;
    if (!lost) {
      _givingUp?.cancel();
      _givingUp = null;
      _gaveUp = false;
    }
    if (!working || _gaveUp) {
      _end();
    } else {
      _ending?.cancel(); // voltou a trabalhar antes de o aviso fixo sair: ele fica
      _ending = null;
      if (lost) _givingUp ??= Timer(_giveUpAfter, _giveUp);
      final text = lost ? 'Sem sinal: tentando reconectar. O telescópio continua.' : ongoingText(telescope);
      final activity = '${after.phase.name}/${telescope.state}/${telescope.job?.id}';
      final now = _ref.read(clockProvider)();
      final due = _shownAt == null || now.difference(_shownAt!) >= _pace;
      if (text != _shown && (activity != _activity || due)) {
        _shown = text;
        _activity = activity;
        _shownAt = now;
        unawaited(_alerts.ongoing(after.name, text));
      }
    }
    if (before == null || !_hidden) return; // com o app na frente, a própria tela conta
    if (before.phase == LinkPhase.online && lost && working) {
      unawaited(
        _alerts.notify(
          const AppNotice(
            'Sem sinal do telescópio',
            'Ele continua trabalhando sozinho. O app está tentando reconectar.',
            bad: true,
            slot: AppNotice.signalSlot,
          ),
        ),
      );
    }
    if (telescope == null) return;
    final notice = noticeFor(before.telescope, telescope);
    if (notice != null) unawaited(_alerts.notify(notice));
  }

  /// Sem sinal há tempo demais: solta o celular e diz por quê.
  void _giveUp() {
    _givingUp = null;
    _gaveUp = true;
    _end();
    if (!_hidden) return;
    final minutes = _giveUpAfter.inMinutes;
    unawaited(
      _alerts.notify(
        AppNotice(
          'O app parou de acompanhar o telescópio',
          'Sem sinal há ${minutes < 1 ? 'algum tempo' : (minutes == 1 ? '1 minuto' : '$minutes minutos')}. '
              'Ele pode continuar trabalhando; abra o app para tentar de novo.',
          bad: true,
          slot: AppNotice.signalSlot,
        ),
      ),
    );
  }

  void _end() {
    if (_shown == null || _ending != null) return;
    _ending = Timer(_linger, () {
      _ending = null;
      _shown = _activity = null;
      _shownAt = null;
      unawaited(_alerts.endOngoing());
    });
  }

  void dispose() {
    _link.close();
    _pref.close();
    _ending?.cancel();
    _givingUp?.cancel();
    if (_shown != null) unawaited(_alerts.endOngoing());
  }
}
