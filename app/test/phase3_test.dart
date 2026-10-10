// Fase 3, sem tela: o app entende o que a Jetson responde (arquivos gravados da API de
// verdade) e o telescópio falso se comporta como o de verdade.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:telescope_app/core/errors.dart';
import 'package:telescope_app/core/version.dart';
import 'package:telescope_app/data/fake_telescope.dart';
import 'package:telescope_app/domain/ephemeris.dart';
import 'package:telescope_app/domain/live_state.dart';
import 'package:telescope_app/domain/models.dart';

import 'support.dart';

final _when = DateTime.utc(2026, 10, 10, 1, 30); // 22h30 em São Paulo

FakeTelescope _fake({Duration step = const Duration(milliseconds: 5)}) => FakeTelescope(step: step, now: () => _when);

Matcher _conflict(String code) =>
    throwsA(isA<ApiFailure>().having((f) => f.kind, 'kind', FailureKind.conflict).having((f) => f.code, 'code', code));

void main() {
  group('o que a Jetson responde', () {
    test('estado com a noite em andamento, o foco e a montagem simulada', () {
      final s = TelescopeState.fromJson(fixtureMap('state_night'));
      expect(s.nightRunning, isTrue);
      expect([for (final n in s.night) n.status], ['done', 'running', 'pending']);
      expect((s.night[1].target, s.night[1].accepted), ('M42', 7));
      expect((s.focus.position, s.focus.best, s.focus.min, s.focus.max), (6290, 6290, 0, 10000));
      expect(s.focus.curve.map((p) => p.fwhmPx), [8.4, 5.1, 2.5, 5.3, null], reason: 'ponto sem estrela fica nulo');
      expect(s.mount.features, ['jog', 'park', 'tracking', 'home', 'polar']);
      expect((s.mount.can('jog'), s.mount.parked, s.mount.tracking, s.mount.moving), (true, false, true, null));
      expect((s.camera.exposureS, s.camera.gain, s.camera.applied), (30.0, 120, false));
    });

    test('a montagem real aparece, mas sem nada para mexer', () {
      final s = TelescopeState.fromJson(fixtureMap('state_idle'));
      expect((s.mount.isReal, s.mount.connected), (true, true));
      expect(s.mount.features, isEmpty);
      expect(s.mount.can('jog'), isFalse);
    });

    test('aparelho antigo, sem `focus`: a posição vem do campo de sempre', () {
      final old = Map<String, dynamic>.of(fixtureMap('state_idle'))..remove('focus');
      expect(TelescopeState.fromJson(old).focus.position, 6300);
    });

    test('foco, câmera, rede, convite e celulares', () {
      final focus = FocusState.fromJson(fixtureMap('focuser'));
      expect((focus.position, focus.curve.length, focus.atLimit), (6290, 5, false));
      final camera = CameraInfo.fromJson(fixtureMap('camera'));
      expect((camera.state.exposureS, camera.state.gain, camera.limits['gain']), (60.0, 200, (0.0, 600.0)));
      final network = NetworkInfo.fromJson(fixtureMap('network'));
      expect((network.enabled, network.mode, network.hostname), (false, 'unknown', 'telescopio'));
      final invite = Invite.fromJson(fixtureMap('invite'));
      expect((invite.role, invite.expiresS), ('operator', 300));
      expect(invite.uri, startsWith('tele://pair?v=1&id='));
      expect(invite.qrSvg, startsWith('<svg'));
      final system = SystemInfo.fromJson(fixtureMap('system'));
      expect((system.uptimeS, system.firmware, system.updatesEnabled), (0, null, false));
    });

    test('plano da noite: horários, e por que um item não cabe', () {
      final plan = NightPlan.fromJson(fixtureMap('plan'));
      expect(plan.running, isFalse);
      expect((plan.nightStart, plan.nightEnd), (DateTime.utc(2026, 10, 10, 1, 30), DateTime.utc(2026, 10, 10, 7, 50)));
      final [sculptor, orion, polar] = plan.items;
      expect((sculptor.target, sculptor.fits, sculptor.start), ('NGC253', true, DateTime.utc(2026, 10, 10, 1, 30)));
      expect((orion.isMosaic, orion.rows, orion.cols, orion.durationS), (true, 1, 2, 1440));
      expect((polar.status, polar.start, polar.fits), ('never_up', null, false));
      // o que volta para a Jetson ao guardar: só o que é do dono, não os horários
      expect(orion.toJson(), {
        'id': 'p-2',
        'target': 'M42',
        'frames': 20,
        'exposure_s': 30.0,
        'min_alt_deg': 25.0,
        'mosaic': [1, 2],
        'overlap': 0.15,
      });
    });

    test('mosaico: a grade e o quanto cobre', () {
      final grid = MosaicGrid.fromJson(fixtureMap('mosaic'));
      expect((grid.target, grid.rows, grid.cols, grid.panels.length), ('M31', 2, 2, 4));
      expect(grid.coversDeg, [4.748, 2.671]);
      expect(grid.coversObject, isTrue);
      expect(grid.panels.first.decDeg, greaterThan(grid.panels.last.decDeg), reason: 'a linha 0 é a do norte');
    });

    test('mensagens do canal: foco e noite chegam sozinhos', () {
      var s = TelescopeState.fromJson(fixtureMap('state_idle'));
      s = applyLiveMessage(s, {
        'type': 'focus',
        'data': {'position': 6400, 'min': 0, 'max': 10000, 'curve': <Object>[], 'best': null},
      });
      expect((s.focus.position, s.focusPos), (6400, 6400), reason: 'os dois campos andam juntos');
      s = applyLiveMessage(s, {
        'type': 'night',
        'data': [
          {'id': 'p-1', 'target': 'M8', 'status': 'running', 'accepted': 2},
        ],
      });
      expect((s.night.single.target, s.night.single.status), ('M8', 'running'));
      expect(
        applyLiveMessage(s, {'type': 'night', 'data': 'torto'}).night,
        hasLength(1),
        reason: 'mensagem torta não apaga',
      );
    });
  });

  group('Lua, planetas e Sol', () {
    test('a conta do app dá o mesmo que a da Jetson', () {
      final jetson = [for (final b in fixtureMap('solar')['items'] as List) SolarBody.fromJson((b as Map).cast())];
      final mine = solarSystem(-23.55, -46.63, _when);
      expect([for (final b in mine) b.id], [for (final b in jetson) b.id]);
      for (final (i, body) in mine.indexed) {
        final other = jetson[i];
        expect(body.raDeg, closeTo(other.raDeg, 0.01), reason: body.id);
        expect(body.decDeg, closeTo(other.decDeg, 0.01), reason: body.id);
        expect(body.altDeg, closeTo(other.altDeg, 0.15), reason: body.id);
        expect(body.phase, other.phase, reason: body.id);
      }
      final saturn = mine.firstWhere((b) => b.id == 'saturn');
      expect((saturn.name, saturn.isUp, saturn.isSun), ('Saturno', true, false));
      expect(mine.last.isSun && !mine.last.isUp, isTrue, reason: 'de noite o Sol está embaixo');
    });
  });

  group('telescópio falso', () {
    test('movimento manual tem prazo: sem renovar, para sozinho', () async {
      final t = _fake();
      addTearDown(t.close);
      await t.jog('E', rate: 3, holdMs: 30);
      expect((await t.state()).mount.moving, 'E');
      await Future<void>.delayed(const Duration(milliseconds: 80));
      expect((await t.state()).mount.moving, isNull);
      await t.jog('N', holdMs: 500);
      await t.haltMount();
      expect((await t.state()).mount.moving, isNull);
      expect(t.commands, ['jog:E:3', 'jog:N:2', 'halt']);
    });

    test('estacionada não anda; trabalhando, não se mexe à mão', () async {
      final t = _fake(step: const Duration(seconds: 5));
      addTearDown(t.close);
      await t.mountAction('park');
      expect(((await t.state()).mount.parked, (await t.state()).mount.tracking), (true, false));
      await expectLater(t.jog('N'), _conflict('parked'));
      await expectLater(t.setTracking(on: true), _conflict('parked'));
      await t.mountAction('unpark');
      await t.stack(commandId: 'c-1');
      await expectLater(t.jog('N'), _conflict('busy'));
      await expectLater(t.mountAction('park'), _conflict('busy'));
      await t.stop(commandId: 'c-2');
      await t.jog('N', holdMs: 20);
    });

    test('foco: passos, fim de curso, e a nitidez acompanha', () async {
      final t = _fake(step: const Duration(seconds: 5));
      addTearDown(t.close);
      await t.startPreview(commandId: 'c-1');
      final sharp = (await t.state()).stack.fwhmPx;
      expect(await t.moveFocus(delta: 1400), FakeTelescope.focusBest + 1400);
      expect((await t.state()).stack.fwhmPx, greaterThan(sharp + 3), reason: 'longe do foco a estrela incha');
      expect(await t.moveFocus(position: 999999), 10000);
      expect((await t.state()).focus.atLimit, isTrue);
    });

    test('autofoco percorre a curva e para no foco; sem estrelas, falha', () async {
      final t = _fake();
      addTearDown(t.close);
      await t.moveFocus(delta: -900);
      await t.autofocus(commandId: 'c-1');
      final done = await t.watch().firstWhere((s) => s.job?.kind == 'focus' && !(s.job?.isOpen ?? true));
      expect((done.job!.state, done.focus.best, done.focus.position), ('done', 6300, 6300));
      expect(done.focus.curve, hasLength(9));
      t.focusFails = true;
      await t.autofocus(commandId: 'c-2');
      final failed = await t.watch().firstWhere((s) => s.job?.id != done.job!.id && !(s.job?.isOpen ?? true));
      expect((failed.job!.failed, failed.job!.error, failed.focus.best), (true, 'focus_failed', null));
    });

    test('plano: guarda, agenda como a Jetson e recusa o que não existe', () async {
      final t = _fake();
      addTearDown(t.close);
      expect((await t.plan()).items, isEmpty);
      final plan = await t.savePlan(const [
        PlanItem(target: 'ngc253'),
        PlanItem(target: 'M42', frames: 20, rows: 1, cols: 2),
        PlanItem(target: 'M13'),
      ]);
      expect([for (final i in plan.items) i.id], ['p-1', 'p-2', 'p-3']);
      final [sculptor, orion, hercules] = plan.items;
      expect((sculptor.target, sculptor.status, sculptor.start), ('NGC253', 'ok', _when));
      expect((orion.status, orion.durationS), ('ok', 1440));
      expect(orion.start!.isAfter(sculptor.end!), isTrue, reason: 'Órion só sobe mais tarde');
      expect(hercules.status, 'never_up', reason: 'Hércules já se pôs em São Paulo a essa hora');
      await expectLater(
        t.savePlan(const [PlanItem(target: 'alvo inventado')]),
        throwsA(isA<ApiFailure>().having((f) => f.kind, 'kind', FailureKind.invalid)),
      );
      expect((await t.plan()).items, hasLength(3), reason: 'a fila recusada não apaga a guardada');
    });

    test('noite: na ordem, pulando o que não sobe; pular e parar funcionam', () async {
      final t = _fake();
      addTearDown(t.close);
      await expectLater(t.startPlan(commandId: 'c-0'), throwsA(isA<ApiFailure>()));
      await expectLater(t.skipPlanItem(), _conflict('not_running'));
      await t.savePlan(const [PlanItem(target: 'NGC253'), PlanItem(target: 'M13'), PlanItem(target: 'M42')]);
      final job = await t.startPlan(commandId: 'c-1');
      expect((await t.startPlan(commandId: 'c-1')).id, job.id, reason: 'o mesmo comando não começa duas noites');
      await expectLater(t.savePlan(const []), _conflict('busy'));
      final end = await t.watch().firstWhere((s) => s.job?.id == job.id && s.job?.state == 'done');
      expect(
        [for (final n in end.night) (n.status, n.reason)],
        [('done', ''), ('skipped', 'below_horizon'), ('done', '')],
      );
      expect((end.queue.done, end.queue.total, end.state), (3, 3, 'IDLE'));

      // de novo, agora pulando o primeiro e parando no segundo
      final slow = _fake(step: const Duration(milliseconds: 20));
      addTearDown(slow.close);
      await slow.savePlan(const [PlanItem(target: 'NGC253'), PlanItem(target: 'M42')]);
      await slow.startPlan(commandId: 'c-2');
      await slow.watch().firstWhere((s) => s.night.isNotEmpty && s.night[0].status == 'running');
      await slow.skipPlanItem();
      await slow.watch().firstWhere((s) => s.night.length == 2 && s.night[1].status == 'running');
      await slow.stop(commandId: 'c-3');
      final stopped = await slow.state();
      expect([for (final n in stopped.night) (n.status, n.reason)], [('skipped', 'user'), ('stopped', '')]);
      expect(stopped.nightRunning, isFalse);
    });

    test('mosaico: a grade cresce com as linhas e colunas', () async {
      final t = _fake();
      addTearDown(t.close);
      final one = await t.mosaic(target: 'M31', rows: 1, cols: 1);
      final six = await t.mosaic(target: 'm31', rows: 2, cols: 3, overlap: 0.2);
      expect((one.coversObject, six.coversObject, six.panels.length), (false, true, 6));
      expect(six.coversDeg[0], closeTo(2.57 + 2 * 2.57 * 0.8, 0.01));
      expect(six.panels.first.raDeg, greaterThan(six.panels[2].raDeg), reason: 'a coluna 0 é a do leste');
    });

    test('Sol: só com o filtro confirmado', () async {
      final t = _fake(step: const Duration(seconds: 5));
      addTearDown(t.close);
      await expectLater(
        t.goToBody(commandId: 'c-1', body: 'sun'),
        throwsA(isA<ApiFailure>().having((f) => f.code, 'code', 'solar_filter_required')),
      );
      final job = await t.goToBody(commandId: 'c-2', body: 'sun', filterConfirmed: true);
      expect((job.kind, job.target), ('goto', 'Sol'));
      expect(t.commands, ['body:sun']);
    });

    test('celulares: convite, papel, e o último dono fica', () async {
      final t = _fake();
      addTearDown(t.close);
      await expectLater(t.setRole('c-demo', 'viewer'), _conflict('last_owner'));
      final invite = await t.invite(role: 'viewer', minutes: 2);
      expect((invite.role, invite.expiresS), ('viewer', 120));
      final guest = (await t.clients()).last;
      expect((guest.role, guest.current), ('viewer', false));
      await t.setRole(guest.id, 'owner');
      await t.setRole('c-demo', 'operator');
      expect([for (final c in await t.clients()) c.role], ['operator', 'owner']);
      await t.revoke(guest.id);
      expect(await t.clients(), hasLength(1));
    });

    test('exportar entrega o arquivo; apagar tira da galeria', () async {
      final t = _fake();
      addTearDown(t.close);
      expect(await t.exportSession('demo-m8', format: 'tif'), isNotNull);
      expect(await t.exportSession('nada'), isNull);
      await t.deleteSession('demo-m8');
      expect([for (final s in await t.sessions()) s.id], ['demo-m51', 'demo-m42']);
    });
  });

  test('a versão que o app mostra é a do pubspec', () {
    final version = RegExp(
      r'^version:\s*([0-9.]+)',
      multiLine: true,
    ).firstMatch(File('pubspec.yaml').readAsStringSync());
    expect(appVersion, version!.group(1));
  });
}
