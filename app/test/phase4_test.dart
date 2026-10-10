// O que faltava para o app ficar completo, sem tela: rede do telescópio, atualização,
// alinhamento polar, captura planetária e a regra dos avisos. O app entende o que a Jetson
// responde (arquivos gravados da API de verdade) e o telescópio falso se comporta como ela.
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:nsd/nsd.dart' as nsd;
import 'package:telescope_app/app/notices.dart';
import 'package:telescope_app/core/errors.dart';
import 'package:telescope_app/core/strings.dart';
import 'package:telescope_app/data/alerts.dart';
import 'package:telescope_app/data/discovery.dart';
import 'package:telescope_app/data/fake_telescope.dart';
import 'package:telescope_app/domain/live_state.dart';
import 'package:telescope_app/domain/models.dart';

import 'support.dart';

final _when = DateTime.utc(2026, 10, 10, 1, 30); // 22h30 em São Paulo
const _step = Duration(milliseconds: 5);

FakeTelescope _fake() => FakeTelescope(step: _step, now: () => _when);

Future<void> _wait(int steps) => Future<void>.delayed(_step * steps);

Matcher _fails(FailureKind kind, [String? code]) {
  var matcher = isA<ApiFailure>().having((f) => f.kind, 'kind', kind);
  if (code != null) matcher = matcher.having((f) => f.code, 'code', code);
  return throwsA(matcher);
}

/// Espera o telescópio falso chegar a um estado (ou falha dizendo onde ele ficou).
Future<TelescopeState> _until(FakeTelescope t, bool Function(TelescopeState) done) async {
  for (var i = 0; i < 400; i++) {
    final s = await t.state();
    if (done(s)) return s;
    await _wait(1);
  }
  fail('o telescópio falso não chegou lá: ficou em ${(await t.state()).state}');
}

TelescopeState _state({String state = 'IDLE', Job? job, StackState stack = const StackState()}) =>
    TelescopeState(state: state, job: job, stack: stack);

void main() {
  group('o que a Jetson responde', () {
    test('rede no campo: o WiFi próprio, com a senha e o endereço para o dono', () {
      final n = NetworkInfo.fromJson(fixtureMap('network_field'));
      expect((n.enabled, n.mode, n.inField, n.wifiSsid, n.switching), (true, 'field', true, null, false));
      expect((n.hotspot!.ssid, n.hotspot!.active, n.hotspot!.psk), ('Telescopio-6465', true, 'ceu-estrelado'));
      expect(n.hotspot!.address, '10.42.0.1', reason: 'é onde o app o procura longe de casa');
      expect(n.known, isEmpty);
      expect(n.lastError, isNull);
    });

    test('rede em casa: a rede em uso, o sinal e o que ficou guardado', () {
      final n = NetworkInfo.fromJson(fixtureMap('network_home'));
      expect((n.atHome, n.wifiSsid, n.wifiSignal), (true, 'Casa', 78));
      expect(n.known, ['Casa']);
      expect(n.hotspot!.active, isFalse);
      final change = NetworkChange.fromJson(fixtureMap('network_join'));
      expect((change.accepted, change.reconnectS), (true, 8), reason: 'a troca acontece depois da resposta');
    });

    test('rede ainda não habilitada (o aparelho de verdade, hoje)', () {
      final n = NetworkInfo.fromJson(fixtureMap('network'));
      expect((n.enabled, n.hotspot, n.wifiSsid), (false, null, null));
      expect(n.known, isEmpty);
    });

    test('as redes que o telescópio enxerga, da mais forte para a mais fraca', () {
      final items = [
        for (final i in fixtureMap('network_scan')['items'] as List) WifiNetwork.fromJson((i as Map).cast()),
      ];
      expect([for (final w in items) w.ssid], ['Casa', 'Visitantes', 'Vizinho 5G']);
      expect((items[0].secure, items[0].known, items[1].secure), (true, false, false));
      expect([for (final w in items) S.signal(w.signal)], ['sinal forte', 'sinal médio', 'sinal médio']);
    });

    test('atualização: versão nova achada, e o andamento da instalação', () {
      final found = UpdateInfo.fromJson(fixtureMap('update_available'));
      expect((found.enabled, found.current, found.available, found.working), (true, '0.1.0', '0.2.0', false));
      expect(found.notes, hasLength(2));
      final running = UpdateInfo.fromJson(fixtureMap('update_installing'));
      expect((running.state, running.progress, running.installing, running.failed), ('installing', 0.5, true, false));
      // um aparelho que ainda não se atualiza pelo app
      final off = UpdateInfo.fromJson({'enabled': false, 'current': '0.1.0', 'available': null, 'state': 'idle'});
      expect((off.enabled, off.available), (false, null));
      expect(off.notes, isEmpty);
    });

    test('captura planetária e alinhamento polar viajam no estado', () {
      final s = TelescopeState.fromJson(fixtureMap('state_capture'));
      expect((s.state, s.busy, s.planetary), ('CAPTURING', true, true));
      final c = s.capture!;
      expect((c.body, c.frames, c.total, c.kept, c.keep, c.done), ('saturn', 120, 300, 45, 0.15, false));
      expect(c.progress, closeTo(0.4, 1e-9));
      expect([for (final step in s.job!.steps) step.name], ['capture']);
      final p = s.polar!;
      expect((p.measured, p.aligned, p.stale, p.step, p.points), (true, false, false, 3, 3));
      expect((p.altArcmin, p.azArcmin, p.totalArcmin, p.latDeg), (38.2, -51.6, 64.2, -23.55));
      final job = Job.fromJson(fixtureMap('job_planetary'));
      expect((job.kind, job.target, job.isOpen), ('planetary', 'Saturno', true));
    });

    test('estado sem captura nem medida: os dois ficam vazios', () {
      final s = TelescopeState.fromJson(fixtureMap('state_idle'));
      expect((s.capture, s.polar, s.planetary, s.measuringPolar), (null, null, false, false));
    });

    test('mensagens do canal: a captura chega sozinha e também ACABA', () {
      var s = TelescopeState.fromJson(fixtureMap('state_idle'));
      s = applyLiveMessage(s, {
        'type': 'capture',
        'data': {'body': 'moon', 'frames': 5, 'total': 60, 'kept': 5, 'keep': 0.25, 'done': false},
      });
      expect((s.capture!.body, s.capture!.frames), ('moon', 5));
      s = applyLiveMessage(s, {
        'type': 'polar',
        'data': {'step': 2, 'points': 3, 'measured': false},
      });
      expect((s.polar!.step, s.polar!.measured, s.capture!.frames), (2, false, 5), reason: 'um não apaga o outro');
      s = applyLiveMessage(s, {'type': 'capture', 'data': null});
      expect(s.capture, isNull, reason: 'o fim da captura também é notícia');
      expect(s.polar, isNotNull);
      expect(applyLiveMessage(s, {'type': 'stack', 'data': null}).polar, isNotNull, reason: 'mensagem torta não apaga');
    });

    test('os erros novos viram falhas que a tela sabe dizer', () {
      for (final code in ['no_known_network', 'in_use', 'nothing_to_install']) {
        final failure = ApiFailure.fromApi(409, code, '');
        expect(failure.kind, FailureKind.conflict);
        expect(S.failure(failure), isNot('Agora não dá para fazer isso.'), reason: code);
      }
      expect(S.jobError('polar_failed'), contains('medir'));
      expect(S.networkError('wrong_password'), contains('senha'));
    });
  });

  group('ângulos pequenos, do jeito que se fala', () {
    test('minutos de arco, e graus quando passa de sessenta', () {
      expect(S.arcmin(0.34), "0,3'");
      expect(S.arcmin(-3.44), "3,4'", reason: 'o lado é dito em palavras, não no sinal');
      expect(S.arcmin(38.2), "38'");
      expect(S.arcmin(64.2), "1° 04'");
      expect(S.arcmin(119.6), "2° 00'", reason: 'arredonda antes de separar: nunca "1° 60\'"');
      expect(S.arcmin(9.96), "10'");
    });
  });

  group('telescópio falso: rede', () {
    late FakeTelescope t;
    setUp(() => t = _fake());
    tearDown(() => t.close());

    test('entrar no WiFi de casa acontece DEPOIS da resposta, e a rede fica guardada', () async {
      expect((await t.network()).mode, 'field');
      final change = await t.joinNetwork('Casa', psk: 'senha-de-casa');
      expect((change.accepted, change.reconnectS > 0), (true, true));
      final during = await t.network();
      expect((during.mode, during.switching), ('field', true), reason: 'ainda não trocou');
      await _wait(6);
      final after = await t.network();
      expect((after.mode, after.wifiSsid, after.wifiSignal, after.switching), ('home', 'Casa', 78, false));
      expect((after.hotspot!.active, after.lastError), (false, null));
      expect(after.known, ['Casa']);
      expect((await t.scanNetworks()).first.known, isTrue);
    });

    test('senha errada: o telescópio fica onde estava e conta por quê', () async {
      await t.joinNetwork('Casa', psk: 'senha-errada');
      await _wait(6);
      final n = await t.network();
      expect((n.mode, n.wifiSsid, n.lastError), ('field', null, 'wrong_password'));
      expect(n.known, isEmpty);
      await expectLater(t.joinNetwork('Não existe', psk: '12345678'), _fails(FailureKind.notFound));
      await expectLater(t.joinNetwork('Casa'), _fails(FailureKind.invalid), reason: 'rede com senha pede a senha');
      await t.joinNetwork('Visitantes'); // aberta: entra sem senha
      await _wait(6);
      expect((await t.network()).wifiSsid, 'Visitantes');
    });

    test('ir e voltar entre casa e campo usa a rede guardada; esquecer tem regra', () async {
      await expectLater(t.setNetworkMode('home'), _fails(FailureKind.conflict, 'no_known_network'));
      await t.joinNetwork('Casa', psk: 'senha-de-casa');
      await _wait(6);
      expect((await t.setNetworkMode('home')).reconnectS, 0, reason: 'já está em casa: nada a trocar');
      await expectLater(t.forgetNetwork('Casa'), _fails(FailureKind.conflict, 'in_use'));
      await t.setNetworkMode('field');
      await _wait(6);
      expect(((await t.network()).mode, (await t.network()).wifiSsid), ('field', null));
      await t.joinNetwork('Casa'); // guardada: dispensa a senha
      await _wait(6);
      expect((await t.network()).wifiSsid, 'Casa');
      await t.setNetworkMode('field');
      await _wait(6);
      await t.forgetNetwork('Casa');
      expect((await t.network()).known, isEmpty);
      await expectLater(t.forgetNetwork('Casa'), _fails(FailureKind.notFound));
      await expectLater(t.setNetworkMode('praia'), _fails(FailureKind.invalid));
    });

    test('a senha do WiFi próprio: só para o dono, e com a regra de todo WiFi', () async {
      expect((await t.network()).hotspot!.psk, 'ceu-estrelado');
      await expectLater(t.setHotspotPassword('curta'), _fails(FailureKind.invalid));
      await t.setHotspotPassword('outra-senha-boa');
      expect((await t.network()).hotspot!.psk, 'outra-senha-boa');
      t.owner = false;
      final seen = await t.network();
      expect((seen.enabled, seen.hotspot!.psk), (true, null), reason: 'operador vê a rede, não a senha');
      await expectLater(t.scanNetworks(), _fails(FailureKind.forbidden));
      await expectLater(t.setNetworkMode('field'), _fails(FailureKind.forbidden));
    });

    test('telescópio que ainda não troca de rede: mostra, e recusa mexer', () async {
      t.networkEnabled = false;
      expect(((await t.network()).enabled, (await t.network()).hotspot), (false, null));
      await expectLater(t.scanNetworks(), _fails(FailureKind.notSupported));
      await expectLater(t.joinNetwork('Casa', psk: 'senha-de-casa'), _fails(FailureKind.notSupported));
    });
  });

  group('telescópio falso: atualização', () {
    late FakeTelescope t;
    setUp(() => t = _fake());
    tearDown(() => t.close());

    Future<UpdateInfo> settled() async {
      for (var i = 0; i < 200; i++) {
        final u = await t.update();
        if (!u.working) return u;
        await _wait(1);
      }
      fail('a atualização não terminou');
    }

    test('procura, acha, instala, reinicia: a versão muda', () async {
      final start = await t.update();
      expect((start.enabled, start.current, start.available, start.state), (true, '1.0.0', null, 'idle'));
      await expectLater(t.installUpdate(), _fails(FailureKind.conflict, 'nothing_to_install'));
      expect((await t.checkUpdate()).state, 'checking');
      await expectLater(t.checkUpdate(), _fails(FailureKind.conflict, 'busy'), reason: 'uma de cada vez');
      final found = await settled();
      expect((found.available, found.notes.length), (FakeTelescope.newerVersion, 2));
      final seen = <String>[];
      expect((await t.installUpdate()).state, 'downloading');
      for (var i = 0; i < 2000; i++) {
        final u = await t.update();
        if (seen.isEmpty || seen.last != u.state) seen.add(u.state);
        if (!u.working) break;
        await Future<void>.delayed(const Duration(milliseconds: 1));
      }
      expect(seen, ['downloading', 'installing', 'restarting', 'idle']);
      final done = await t.update();
      expect((done.current, done.available, done.error), (FakeTelescope.newerVersion, null, null));
      expect((await t.system()).software, FakeTelescope.newerVersion);
      await t.checkUpdate();
      expect((await settled()).available, isNull, reason: 'já está na última');
    });

    test('instalação que falha: a versão de antes continua, e dá para tentar de novo', () async {
      await t.checkUpdate();
      await settled();
      t.updateFails = true;
      await t.installUpdate();
      final failed = await settled();
      expect((failed.state, failed.error, failed.current), ('failed', 'install_failed', '1.0.0'));
      expect((failed.failed, failed.available), (true, FakeTelescope.newerVersion));
      await t.installUpdate();
      expect((await settled()).current, FakeTelescope.newerVersion);
    });

    test('não atualiza no meio de um trabalho, nem na mão de quem não é dono', () async {
      await t.checkUpdate();
      await settled();
      await t.stack(commandId: 'a');
      await expectLater(t.installUpdate(), _fails(FailureKind.conflict, 'busy'));
      await t.stop(commandId: 'b');
      t.owner = false;
      await expectLater(t.installUpdate(), _fails(FailureKind.forbidden));
      expect((await t.update()).available, isNotNull, reason: 'ver, pode');
      t
        ..owner = true
        ..updatesEnabled = false;
      expect(((await t.update()).enabled, (await t.system()).updatesEnabled), (false, false));
      await expectLater(t.checkUpdate(), _fails(FailureKind.notSupported));
    });
  });

  group('telescópio falso: alinhamento polar', () {
    late FakeTelescope t;
    setUp(() => t = _fake());
    tearDown(() => t.close());

    test('mede em três campos e separa o erro em altitude e azimute', () async {
      final seen = <int>[];
      final watching = t.watch().listen((s) {
        final step = s.polar?.step;
        if (step != null && (seen.isEmpty || seen.last != step)) seen.add(step);
      });
      final job = await t.measurePolar(commandId: 'p1');
      expect((await t.measurePolar(commandId: 'p1')).id, job.id, reason: 'reenviar não mede de novo');
      final s = await _until(t, (s) => s.job?.id == job.id && !s.job!.isOpen);
      await watching.cancel();
      expect(seen, [0, 1, 2, 3], reason: 'o andamento avança campo a campo');
      final p = s.polar!;
      expect((s.job!.state, p.measured, p.aligned, p.stale), ('done', true, false, false));
      expect((s.state, s.busy), ('STOPPED', false), reason: 'mediu: a montagem fica parada, como depois de um goto');
      expect((p.altArcmin, p.azArcmin, p.latDeg), (38.0, -52.0, -23.55));
      expect(p.totalArcmin, closeTo(64.4, 0.05));
      expect({for (final step in s.job!.steps) step.name}, {'slew', 'solve'});
    });

    test('girar os parafusos invalida a medida; a próxima sai melhor', () async {
      await t.measurePolar(commandId: 'p1');
      final first = (await _until(t, (s) => s.polar?.measured ?? false)).polar!;
      await t.adjustPolar(altArcmin: -first.altArcmin, azArcmin: -first.azArcmin);
      expect((await t.state()).polar!.stale, isTrue, reason: 'mexeu nos parafusos: a medida não vale mais');
      await t.measurePolar(commandId: 'p2');
      final second = (await _until(t, (s) => s.job?.state == 'done' && s.polar?.stale == false)).polar!;
      expect(second.totalArcmin, lessThan(first.totalArcmin / 4));
      expect(second.totalArcmin, greaterThan(0), reason: 'a mão nunca gira exatamente o pedido');
      await expectLater(t.adjustPolar(altArcmin: 9999, azArcmin: 0), _fails(FailureKind.invalid));
    });

    test('a medida que não fecha vira falha; com a montagem real, nem começa', () async {
      t.polarFails = true;
      final job = await t.measurePolar(commandId: 'p1');
      final s = await _until(t, (s) => s.job?.id == job.id && !s.job!.isOpen);
      expect((s.job!.state, s.job!.error, s.polar!.measured), ('failed', 'polar_failed', false));
      t.pretendRealMount();
      await expectLater(t.measurePolar(commandId: 'p2'), _fails(FailureKind.notSupported));
      await expectLater(t.adjustPolar(altArcmin: 1, azArcmin: 1), _fails(FailureKind.notSupported));
    });

    test('com um trabalho em curso, a medida espera', () async {
      await t.stack(commandId: 'a');
      await expectLater(t.measurePolar(commandId: 'p1'), _fails(FailureKind.conflict, 'busy'));
    });
  });

  group('telescópio falso: captura planetária', () {
    late FakeTelescope t;
    setUp(() => t = _fake());
    tearDown(() => t.close());

    test('aponta, grava, fica com os mais nítidos e empilha', () async {
      final states = <String>[];
      final watching = t.watch().listen((s) {
        if (states.isEmpty || states.last != s.state) states.add(s.state);
      });
      final job = await t.capturePlanetary(commandId: 'c1', body: 'saturn', frames: 300, keepPercent: 15);
      expect((job.kind, job.target), ('planetary', 'Saturno'));
      final s = await _until(t, (s) => s.capture?.done ?? false);
      await watching.cancel();
      expect(states.indexOf('SOLVING'), lessThan(states.indexOf('CAPTURING')), reason: 'aponta antes de gravar');
      expect(states.indexOf('CAPTURING'), lessThan(states.lastIndexOf('STACKING')));
      final c = s.capture!;
      expect((c.body, c.frames, c.total, c.kept, c.keep), ('saturn', 300, 300, 45, 0.15));
      expect((s.job!.state, s.stack.accepted, s.stack.rejected), ('done', 45, 255));
      expect([for (final step in s.job!.steps) step.name].sublist(s.job!.steps.length - 2), ['capture', 'stack']);
      expect(t.commands, ['planetary:saturn:300:15']);
    });

    test('sem apontar grava de onde está; o Sol e os exageros ficam de fora', () async {
      await t.capturePlanetary(commandId: 'c1', body: 'moon', frames: 60, keepPercent: 25, point: false);
      final first = await t.state();
      expect((first.state, first.capture!.total), ('CAPTURING', 60), reason: 'começou sem mover a montagem');
      final done = await _until(t, (s) => s.capture?.done ?? false);
      expect(done.capture!.kept, 15);
      expect(t.commands.single, 'planetary:moon:60:25:here');
      await expectLater(t.capturePlanetary(commandId: 'c2', body: 'sun'), _fails(FailureKind.notFound));
      await expectLater(t.capturePlanetary(commandId: 'c3', body: 'moon', frames: 5), _fails(FailureKind.invalid));
      await expectLater(
        t.capturePlanetary(commandId: 'c4', body: 'moon', keepPercent: 90),
        _fails(FailureKind.invalid),
      );
    });

    test('a imagem ao vivo é o planeta, e outro trabalho começa sem a captura', () async {
      await t.capturePlanetary(commandId: 'c1', body: 'jupiter', frames: 60, point: false);
      final raw = await t.frame();
      await _until(t, (s) => s.capture?.done ?? false);
      final stacked = await t.frame();
      expect(raw!.sublist(0, 4), [0x89, 0x50, 0x4E, 0x47], reason: 'um PNG de verdade');
      expect(stacked, isNot(equals(raw)), reason: 'o resultado empilhado não é um quadro cru');
      await t.stack(commandId: 's1');
      expect((await t.state()).capture, isNull);
    });
  });

  group('avisos com a tela apagada: o que vale avisar', () {
    Job job(String kind, String state, {String? target, String? error}) =>
        Job(id: 'j-1', kind: kind, state: state, target: target, error: error);

    test('só o fim de um trabalho que o app viu em andamento', () {
      final running = _state(
        state: 'STACKING',
        job: job('observe', 'running', target: 'M42'),
      );
      expect(noticeFor(null, running), isNull, reason: 'o app acabou de chegar');
      expect(noticeFor(running, running), isNull, reason: 'nada mudou');
      final other = _state(
        job: const Job(id: 'j-2', kind: 'goto', state: 'done'),
      );
      expect(noticeFor(running, other), isNull, reason: 'outro trabalho: não foi este que terminou');
      final stopped = _state(
        state: 'STOPPED',
        job: job('observe', 'stopped', target: 'M42'),
      );
      expect(noticeFor(running, stopped), isNull, reason: 'quem mandou parar não precisa de aviso');
    });

    test('cada desfecho com as palavras dele', () {
      final pointing = _state(
        state: 'SLEWING',
        job: job('goto', 'running', target: 'M42'),
      );
      expect(
        noticeFor(pointing, _state(job: job('goto', 'done', target: 'M42'))),
        const AppNotice('Alvo centralizado', 'M42'),
      );
      expect(
        noticeFor(
          pointing,
          _state(
            job: job('goto', 'failed', target: 'M42', error: 'not_converged'),
          ),
        ),
        AppNotice('Não deu certo: M42', S.jobError('not_converged'), bad: true),
      );
      final focusing = _state(state: 'FOCUSING', job: job('focus', 'running'));
      expect(noticeFor(focusing, _state(job: job('focus', 'done')))!.title, 'Foco encontrado');
      final lost = noticeFor(focusing, _state(job: job('focus', 'failed', error: 'focus_failed')))!;
      expect((lost.title, lost.bad), ('O autofoco não achou o foco', true));
      final stacking = _state(state: 'STACKING', job: job('stack', 'running'));
      final ended = _state(job: job('stack', 'done'), stack: const StackState(accepted: 40));
      expect(noticeFor(stacking, ended), const AppNotice('Sessão encerrada', '40 fotos empilhadas.'));
    });

    test('a noite, a captura planetária e o alinhamento polar', () {
      final night = TelescopeState.fromJson(fixtureMap('state_night'));
      final over = TelescopeState(
        job: Job(id: night.job!.id, kind: 'plan', state: 'done'),
        night: [
          for (final n in night.night)
            NightItem(id: n.id, target: n.target, status: n.target == 'NGC188' ? 'skipped' : 'done'),
        ],
      );
      expect(noticeFor(night, over), const AppNotice('A noite terminou', '2 de 3 alvos fotografados.'));

      final capturing = TelescopeState.fromJson(fixtureMap('state_capture'));
      final captured = TelescopeState(
        job: Job(id: capturing.job!.id, kind: 'planetary', state: 'done', target: 'Saturno'),
        capture: const CaptureState(body: 'saturn', frames: 300, total: 300, kept: 45, keep: 0.15, done: true),
      );
      expect(
        noticeFor(capturing, captured),
        const AppNotice('Captura pronta: Saturno', '45 de 300 quadros aproveitados.'),
      );

      final measuring = _state(state: 'SOLVING', job: job('polar', 'running'));
      final measured = TelescopeState(
        job: job('polar', 'done'),
        polar: const PolarState(step: 3, measured: true, altArcmin: 38, azArcmin: -52, totalArcmin: 64.4),
      );
      final notice = noticeFor(measuring, measured)!;
      expect((notice.title, notice.text.contains("1° 04'"), notice.bad), ('Alinhamento polar medido', true, false));
      final aligned = TelescopeState(
        job: job('polar', 'done'),
        polar: const PolarState(step: 3, measured: true, totalArcmin: 1.2, aligned: true),
      );
      expect(noticeFor(measuring, aligned)!.title, 'A montagem está alinhada');
      expect(noticeFor(measuring, _state(job: job('polar', 'failed', error: 'polar_failed')))!.bad, isTrue);
    });

    test('o aviso fixo diz o que o telescópio está fazendo', () {
      expect(ongoingText(TelescopeState.fromJson(fixtureMap('state_night'))), 'Noite: 1 de 3 · agora M42');
      expect(
        ongoingText(TelescopeState.fromJson(fixtureMap('state_capture'))),
        'Gravando Saturno · 120 de 300 quadros',
      );
      expect(
        ongoingText(
          _state(
            state: 'STACKING',
            job: job('observe', 'running', target: 'M42'),
            stack: const StackState(target: 'M42', accepted: 1),
          ),
        ),
        'Empilhando M42 · 1 foto',
      );
      expect(
        ongoingText(
          _state(
            state: 'SLEWING',
            job: job('goto', 'running', target: 'M8'),
          ),
        ),
        'Apontando · M8',
      );
      expect(ongoingText(_state(state: 'FOCUSING', job: job('focus', 'running'))), 'Focando');
    });
  });

  group('achar o telescópio na rede', () {
    Uint8List text(String value) => Uint8List.fromList(value.codeUnits);

    test('um anúncio só vira candidato com identificador e endereço', () {
      final ok = NsdDiscovery.found(
        nsd.Service(name: 'Telescópio tele-0b04', host: '192.168.3.50', port: 8443, txt: {'id': text('tele-0b04')}),
      );
      expect(ok, const FoundTelescope(deviceId: 'tele-0b04', host: '192.168.3.50'));
      expect((ok!.name, ok.port), ('Telescópio tele-0b04', 8443));
      expect(NsdDiscovery.found(const nsd.Service(name: 'sem id', host: '192.168.3.51', port: 8443)), isNull);
      expect(NsdDiscovery.found(nsd.Service(name: 'sem endereço', txt: {'id': text('tele-1')})), isNull);
      expect(NsdDiscovery.found(nsd.Service(host: '10.0.0.9', txt: {'id': text('  ')})), isNull);
    });

    test('só endereço IPv4 de rede local vira candidato', () {
      nsd.Service at(String host, [List<InternetAddress>? addresses]) =>
          nsd.Service(host: host, addresses: addresses, txt: {'id': text('tele-0b04')});
      for (final local in ['10.42.0.1', '172.16.5.9', '172.31.255.1', '192.168.3.50', '169.254.7.7']) {
        expect(NsdDiscovery.found(at(local))?.host, local);
      }
      for (final foreign in ['8.8.8.8', '172.32.0.1', '192.169.1.1', 'fe80::1%wlan0', 'tele-0b04.local', '']) {
        expect(NsdDiscovery.found(at(foreign)), isNull, reason: foreign);
      }
      // o Android pode entregar primeiro um IPv6 de enlace: vale o IPv4 que vier junto
      final mixed = at('tele-0b04.local', [InternetAddress('fe80::1'), InternetAddress('192.168.3.50')]);
      expect(NsdDiscovery.found(mixed)?.host, '192.168.3.50');
      expect(NsdDiscovery.found(at('tele-0b04.local', [InternetAddress('fe80::1')])), isNull);
    });
  });
}
