// O app contra o software da Jetson DE VERDADE (rodando no PC, com os simuladores).
//
// Prova que os dois lados conversam: TLS 1.3 com o certificado fixado, pareamento pelo código
// do QR, token, canal em tempo real e imagem ao vivo. Não roda no `flutter test` comum: precisa
// do servidor no ar. Quem cuida de tudo (subir, abrir a janela de pareamento, rodar e derrubar):
//
//     py -3.11 scripts/run_app_integration.py
//
// Sem a variável TELE_PAIR_URI os testes são pulados.
import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:telescope_app/core/errors.dart';
import 'package:telescope_app/data/http_telescope.dart';
import 'package:telescope_app/domain/models.dart';
import 'package:telescope_app/domain/pairing.dart';

void main() {
  final uri = Platform.environment['TELE_PAIR_URI'];
  final skip = uri == null ? 'sem servidor: rode scripts/run_app_integration.py' : false;

  late PairingCode code;
  late String host;
  late Paired paired;
  late HttpTelescope api;

  ApiFailure failure(FailureKind kind) => ApiFailure(kind);
  Matcher failsWith(FailureKind kind) => throwsA(isA<ApiFailure>().having((f) => f.kind, 'kind', failure(kind).kind));

  setUpAll(() async {
    if (uri == null) return;
    code = PairingCode.parse(uri);
    host = code.host ?? '127.0.0.1';
  });

  tearDownAll(() {
    if (uri != null) api.close();
  });

  test('impostor: com outra impressão digital o app para antes de mandar qualquer coisa', () async {
    final wrong = Uint8List.fromList(code.fingerprint)..[0] ^= 0xFF;
    final fake = HttpTelescope(host: host, port: code.port, fingerprint: wrong);
    addTearDown(fake.close);
    await expectLater(fake.info(), failsWith(FailureKind.identityMismatch));
  }, skip: skip);

  test('sem token, só /info responde', () async {
    final anonymous = HttpTelescope(host: host, port: code.port, fingerprint: code.fingerprint);
    addTearDown(anonymous.close);
    expect((await anonymous.info()).id, code.deviceId);
    await expectLater(anonymous.state(), failsWith(FailureKind.unauthorized));
  }, skip: skip);

  test('código errado é recusado; o certo pareia', () async {
    final wrongSecret = PairingCode(
      deviceId: code.deviceId,
      fingerprint: code.fingerprint,
      secret: Uint8List(16),
      port: code.port,
    );
    await expectLater(
      HttpTelescope.pair(code: wrongSecret, host: host, clientName: 'Teste Dart'),
      failsWith(FailureKind.pairingRejected),
    );
    paired = await HttpTelescope.pair(code: code, host: host, clientName: 'Teste Dart');
    expect((paired.role, paired.deviceId), ('owner', code.deviceId));
    expect(paired.token.length, greaterThan(30));
    api = HttpTelescope(host: host, port: code.port, fingerprint: code.fingerprint, token: paired.token);
    // uma janela, um celular: depois de parear ela se fecha sozinha
    await expectLater(
      HttpTelescope.pair(code: code, host: host, clientName: 'Outro'),
      failsWith(FailureKind.pairingClosed),
    );
  }, skip: skip);

  test(
    'estado, hora e local, alvos, ficha, sessões e estúdio pelo canal cifrado',
    () async {
      final state = await api.state();
      expect(state.backend, isNotEmpty);
      final site = await api.setSite(utc: DateTime.now().toUtc(), lat: -23.55, lon: -46.63, elevM: 760);
      expect(site.clockSet, isTrue);
      expect((await api.info()).clockSynced, isTrue);

      final page = await api.targets(visible: true, fits: true, limit: 5);
      expect(page.items, hasLength(5));
      expect(page.items.every((t) => t.isHigh), isTrue);
      final detail = await api.target('M42');
      expect((detail.target.id, detail.night.isNotEmpty), ('M42', true));
      await expectLater(api.target('XYZ999'), failsWith(FailureKind.notFound));
      expect(await api.targetThumb('NGC 7'), isNull, reason: 'sem miniatura não é erro');

      final sessions = await api.sessions();
      final presets = await api.presets();
      expect(presets.controls, contains('stretch'));
      if (sessions.isNotEmpty) {
        final image = await api.render(sessions.first.id, {'preset': 'vivido', 'stretch': 12.0});
        expect(image!.sublist(0, 2), [0xFF, 0xD8]);
        await expectLater(api.render(sessions.first.id, {'stretch': 99.0}), failsWith(FailureKind.invalid));
      }
      expect((await api.system()).deviceId, code.deviceId);
      expect((await api.clients()).where((c) => c.current).single.name, 'Teste Dart');
    },
    skip: skip,
    timeout: const Timeout(Duration(minutes: 2)),
  );

  test(
    'goto acompanhado pelo canal em tempo real até terminar; imagem ao vivo chega',
    () async {
      final states = api.watch().asBroadcastStream();
      final first = await states.first.timeout(const Duration(seconds: 10));
      expect(first.state, isNotEmpty);
      final done = states.firstWhere((s) => s.job != null && !s.job!.isOpen).timeout(const Duration(seconds: 90));
      final job = await api.goTo(commandId: 'dart-1', target: 'M42');
      expect((job.kind, job.state), ('goto', 'accepted'));
      expect(
        (await api.goTo(commandId: 'dart-1', target: 'M42')).id,
        job.id,
        reason: 'reenvio não repete',
      );
      final end = await done;
      expect((end.job!.id, end.job!.state), (job.id, 'done'));
      expect(end.job!.steps.map((s) => s.name).take(2), ['slew', 'solve']);
      expect(end.pointing.unit, 'arcmin');

      final frame = await api.preview(maxSide: 640).first.timeout(const Duration(seconds: 20));
      expect(frame.sublist(0, 2), [0xFF, 0xD8], reason: 'JPEG');
      expect(frame.length, lessThan(400 * 1024), reason: 'reduzido para a tela do celular');
      expect((await api.frame(maxSide: 320))!.sublist(0, 2), [0xFF, 0xD8]);
    },
    skip: skip,
    timeout: const Timeout(Duration(minutes: 3)),
  );

  test(
    'fase 3: câmera ao vivo, foco e montagem à mão, autofoco, plano e noite, mosaico, planetas',
    () async {
      final states = api.watch().asBroadcastStream();
      await states.first.timeout(const Duration(seconds: 10));
      Future<T> soon<T>(Future<T> future, [int seconds = 20]) => future.timeout(Duration(seconds: seconds));

      // câmera ao vivo: é nela que se enquadra e se foca à mão
      final live = states.firstWhere((s) => s.previewing);
      expect((await api.startPreview(commandId: 'dart-p1')).kind, 'preview');
      final seen = await soon(live, 40);
      expect(seen.mount.features, contains('jog'), reason: 'no PC a montagem é a simulada');
      final before = (await api.state()).focus.position;
      final refocused = states.firstWhere((s) => s.focus.position == before + 100);
      expect(await api.moveFocus(delta: 100), before + 100);
      expect((await soon(refocused)).focusPos, before + 100);

      // movimento manual com prazo: sem renovar, a montagem para sozinha
      final moving = states.firstWhere((s) => s.mount.moving == 'E');
      await api.jog('E', rate: 3, holdMs: 400);
      await soon(moving);
      await soon(states.firstWhere((s) => s.mount.moving == null));

      final camera = await api.setCamera(exposureS: 60, gain: 200);
      expect((camera.state.exposureS, camera.state.gain, camera.state.applied), (60.0, 200, false));
      expect(camera.limits, contains('gain'));
      final idle = states.firstWhere((s) => !s.busy);
      await api.stop(commandId: 'dart-p2');
      await soon(idle, 30);

      // estacionada não anda
      final parked = states.firstWhere((s) => s.mount.parked == true);
      await api.mountAction('park');
      await soon(parked);
      await expectLater(api.jog('N'), failsWith(FailureKind.conflict));
      final free = states.firstWhere((s) => s.mount.parked == false);
      await api.mountAction('unpark');
      await soon(free);

      // autofoco: a curva chega pelo canal e o trabalho termina no foco
      final focused = states.firstWhere((s) => s.job?.kind == 'focus' && !(s.job?.isOpen ?? true));
      await api.autofocus(commandId: 'dart-f1');
      final sharp = await soon(focused, 150);
      expect(sharp.job!.state, 'done');
      expect(sharp.focus.best, isNotNull);
      expect(sharp.focus.curve.length, greaterThan(4));

      // plano: guardado na Jetson, com os horários calculados por ela
      final plan = await api.savePlan(const [
        PlanItem(target: 'ngc 253', frames: 3),
        PlanItem(target: 'NGC188', frames: 3),
      ]);
      expect([for (final i in plan.items) i.target], ['NGC253', 'NGC188']);
      expect(plan.items.last.status, 'never_up', reason: 'colado no polo norte: de São Paulo não nasce');
      expect((await api.plan()).items, hasLength(2));
      await expectLater(api.savePlan(const [PlanItem(target: 'alvo inventado')]), failsWith(FailureKind.invalid));
      final grid = await api.mosaic(target: 'M31', rows: 2, cols: 3);
      expect((grid.panels.length, grid.coversObject), (6, true));
      final bodies = await api.solar();
      expect([for (final b in bodies) b.id], containsAll(<String>['moon', 'saturn', 'sun']));

      // a noite autônoma: cada item termina com o que aconteceu com ele
      final dawn = states.firstWhere((s) => s.job?.kind == 'plan' && !(s.job?.isOpen ?? true));
      final night = await api.startPlan(commandId: 'dart-n1');
      expect((await api.startPlan(commandId: 'dart-n1')).id, night.id, reason: 'reenvio não começa outra noite');
      final end = await soon(dawn, 240);
      expect(end.night, hasLength(2));
      expect(end.night.first.status, anyOf('done', 'skipped', 'failed'));
      expect((end.night.last.status, end.night.last.reason), ('skipped', 'below_horizon'));
    },
    skip: skip,
    timeout: const Timeout(Duration(minutes: 8)),
  );

  test(
    'fase 3: convite de uso único com papel, nome, rede e exportar',
    () async {
      final invite = await api.invite(role: 'viewer', minutes: 1);
      final guestCode = PairingCode.parse(invite.uri);
      expect(guestCode.secret, isNot(code.secret), reason: 'o segredo do aparelho não viaja: o convite tem o seu');
      final guest = await HttpTelescope.pair(code: guestCode, host: host, clientName: 'Convidado Dart');
      expect(guest.role, 'viewer');
      await expectLater(
        HttpTelescope.pair(code: guestCode, host: host, clientName: 'De novo'),
        failsWith(FailureKind.pairingClosed),
        reason: 'um convite, um celular',
      );
      final guestApi = HttpTelescope(host: host, port: code.port, fingerprint: code.fingerprint, token: guest.token);
      addTearDown(guestApi.close);
      expect((await guestApi.state()).state, isNotEmpty, reason: 'visitante acompanha');
      await expectLater(guestApi.startPreview(commandId: 'dart-g1'), failsWith(FailureKind.forbidden));
      await expectLater(guestApi.clients(), failsWith(FailureKind.forbidden));
      await api.setRole(guest.clientId, 'operator');
      await expectLater(api.setRole(paired.clientId, 'viewer'), failsWith(FailureKind.conflict));
      await api.revoke(guest.clientId);
      await expectLater(guestApi.state(), failsWith(FailureKind.unauthorized));

      expect(await api.rename('  Telescópio   de teste '), 'Telescópio de teste');
      expect((await api.info()).name, 'Telescópio de teste');
      expect((await api.network()).hostname, isNotEmpty);

      final sessions = await api.sessions();
      if (sessions.isNotEmpty) {
        final id = sessions.first.id;
        final jpeg = await api.exportSession(id, maxSide: 800);
        expect(jpeg!.sublist(0, 2), [0xFF, 0xD8]);
        final tiff = await api.exportSession(id, format: 'tif', maxSide: 800);
        expect(tiff!.sublist(0, 2), anyOf(equals([0x49, 0x49]), equals([0x4D, 0x4D])), reason: 'TIFF');
        await expectLater(api.deleteSession(id), failsWith(FailureKind.conflict), reason: 'imagem de referência');
      }
    },
    skip: skip,
    timeout: const Timeout(Duration(minutes: 4)),
  );

  test(
    'o que faltava: rede (casa e campo), atualização, alinhamento polar e captura planetária',
    () async {
      final states = api.watch().asBroadcastStream();
      await states.first.timeout(const Duration(seconds: 10));
      Future<T> soon<T>(Future<T> future, [int seconds = 30]) => future.timeout(Duration(seconds: seconds));

      /// Pergunta até a troca de rede acabar (ela acontece DEPOIS da resposta).
      Future<NetworkInfo> switched() async {
        for (var i = 0; i < 40; i++) {
          final n = await api.network();
          if (!n.switching) return n;
          await Future<void>.delayed(const Duration(milliseconds: 500));
        }
        fail('a troca de rede não terminou');
      }

      // rede: no PC é o adapter de mentira, com o mesmo contrato do de verdade
      final field = await api.network();
      expect((field.enabled, field.mode, field.hotspot!.active), (true, 'field', true));
      expect(field.hotspot!.psk, isNotEmpty, reason: 'o dono recebe a senha do WiFi próprio');
      expect(field.hotspot!.address, isNotEmpty);
      final seen = await api.scanNetworks();
      expect([for (final n in seen) n.ssid], contains('Casa'));
      expect((await api.joinNetwork('Casa', psk: 'senha-errada')).accepted, isTrue);
      expect((await api.network()).switching, isTrue, reason: 'a resposta sai antes da troca');
      final refused = await switched();
      expect(
        (refused.mode, refused.lastError),
        ('field', 'wrong_password'),
        reason: 'ficou onde estava, e diz por quê',
      );
      await api.joinNetwork('Casa', psk: 'senha-de-casa');
      final home = await switched();
      expect((home.mode, home.wifiSsid, home.lastError), ('home', 'Casa', null));
      expect(home.known, ['Casa']);
      await expectLater(api.forgetNetwork('Casa'), failsWith(FailureKind.conflict), reason: 'está em uso');
      expect((await api.setNetworkMode('field')).reconnectS, greaterThan(0));
      expect((await switched()).mode, 'field');
      await api.forgetNetwork('Casa');
      await expectLater(api.setNetworkMode('home'), failsWith(FailureKind.conflict));
      await api.setHotspotPassword('senha-nova-do-campo');
      expect((await api.network()).hotspot!.psk, 'senha-nova-do-campo');

      // atualização: procurar, instalar, reiniciar
      final start = await api.update();
      expect((start.enabled, start.available), (true, null));
      await expectLater(api.installUpdate(), failsWith(FailureKind.conflict));
      expect((await api.checkUpdate()).state, 'checking');
      UpdateInfo update = start;
      for (var i = 0; i < 20 && (update.working || update.available == null); i++) {
        await Future<void>.delayed(const Duration(milliseconds: 500));
        update = await api.update();
      }
      final version = update.available!;
      expect(update.notes, isNotEmpty);
      expect((await api.installUpdate()).installing, isTrue);
      for (var i = 0; i < 40 && (update.working || update.current != version); i++) {
        await Future<void>.delayed(const Duration(milliseconds: 500));
        update = await api.update();
      }
      expect((update.current, update.available, update.state), (version, null, 'idle'));

      // alinhamento polar: três campos, o erro separado, e os parafusos da montagem simulada
      final measured = states.firstWhere((s) => s.job?.kind == 'polar' && !(s.job?.isOpen ?? true));
      final measuring = states.firstWhere((s) => s.measuringPolar && (s.polar?.step ?? 0) >= 1);
      expect((await api.measurePolar(commandId: 'dart-pa1')).kind, 'polar');
      await soon(measuring, 60);
      final first = (await soon(measured, 120)).polar!;
      expect((first.measured, first.aligned, first.stale), (true, false, false));
      expect(first.totalArcmin, greaterThan(30));
      final stale = states.firstWhere((s) => s.polar?.stale ?? false);
      await api.adjustPolar(altArcmin: -first.altArcmin, azArcmin: -first.azArcmin);
      await soon(stale);
      final again = states.firstWhere(
        (s) => s.job?.kind == 'polar' && !(s.job?.isOpen ?? true) && s.polar?.stale == false && s.job?.state == 'done',
      );
      await api.measurePolar(commandId: 'dart-pa2');
      final second = (await soon(again, 120)).polar!;
      expect(second.totalArcmin, lessThan(first.totalArcmin / 4), reason: 'girou o que a medida pediu');

      // captura planetária: aponta, grava, fica com os mais nítidos, empilha
      final captured = states.firstWhere((s) => s.capture?.done ?? false);
      final recording = states.firstWhere((s) => s.state == 'CAPTURING' && (s.capture?.frames ?? 0) > 0);
      final job = await api.capturePlanetary(commandId: 'dart-c1', body: 'saturn', frames: 60, keepPercent: 25);
      expect((job.kind, job.target), ('planetary', 'Saturno'));
      expect((await soon(recording, 120)).capture!.total, 60);
      final result = await soon(captured, 120);
      expect((result.capture!.kept, result.capture!.frames, result.job!.state), (15, 60, 'done'));
      expect((await api.frame(maxSide: 320))!.sublist(0, 2), [0xFF, 0xD8], reason: 'o resultado vai para a tela');
      await expectLater(api.capturePlanetary(commandId: 'dart-c2', body: 'sun'), failsWith(FailureKind.notFound));
    },
    skip: skip,
    timeout: const Timeout(Duration(minutes: 6)),
  );

  test('revogado: a chamada seguinte é recusada e o canal em tempo real cai', () async {
    final channel = api.watch();
    final dropped = Completer<Object>();
    final sub = channel.listen(
      (_) {},
      onError: (Object e) {
        if (!dropped.isCompleted) dropped.complete(e);
      },
    );
    await Future<void>.delayed(const Duration(milliseconds: 500));
    await api.revoke(paired.clientId);
    await expectLater(api.state(), failsWith(FailureKind.unauthorized));
    final error = await dropped.future.timeout(const Duration(seconds: 15));
    await sub.cancel();
    expect(error, isA<ApiFailure>().having((f) => f.kind, 'kind', FailureKind.unauthorized));
  }, skip: skip);
}
