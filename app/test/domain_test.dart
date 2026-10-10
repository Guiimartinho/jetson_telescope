// O domínio do app contra respostas REAIS da API da Jetson (test/fixtures).
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:telescope_app/core/errors.dart';
import 'package:telescope_app/core/format.dart';
import 'package:telescope_app/domain/live_state.dart';
import 'package:telescope_app/domain/models.dart';
import 'package:telescope_app/domain/pairing.dart';

import 'support.dart';

void main() {
  group('pareamento', () {
    final v = fixtureMap('pairing_vector');

    test('a prova é a mesma conta da Jetson, byte a byte', () {
      final proof = pairingProof(
        b64uDecode(v['secret'] as String),
        b64uDecode(v['nonce'] as String),
        b64uDecode(v['fingerprint'] as String),
        v['client_name'] as String, // tem acento e travessão: UTF-8 dos dois lados
      );
      expect(b64u(proof), v['proof']);
    });

    test('o QR traz tudo para confiar no aparelho antes de falar com ele', () {
      final code = PairingCode.parse(v['uri'] as String);
      expect(code.deviceId, 'tele-6465');
      expect(code.fingerprint, b64uDecode(v['fingerprint'] as String));
      expect(code.secret, b64uDecode(v['secret'] as String));
      expect((code.host, code.port), ('192.168.3.221', 8443));
      expect((code.ssid, code.psk), ('Telescopio-6465', 'senha-do-wifi'));
    });

    test('o WiFi do telescópio é opcional (em casa o QR não o traz)', () {
      final code = PairingCode.parse('tele://pair?v=1&id=tele-1&fp=${v['fingerprint']}&s=${v['secret']}');
      expect((code.host, code.ssid, code.psk, code.port), (null, null, null, 8443));
    });

    test('código que não é nosso é recusado com um motivo que se pode mostrar', () {
      for (final bad in [
        'https://exemplo.com',
        'tele://pair?v=2&id=x&fp=${v['fingerprint']}&s=${v['secret']}',
        'tele://pair?v=1&id=x&fp=curto&s=${v['secret']}',
        'tele://pair?v=1&id=x&fp=${v['fingerprint']}',
        'tele://pair?v=1&fp=${v['fingerprint']}&s=${v['secret']}',
        '',
      ]) {
        expect(
          () => PairingCode.parse(bad),
          throwsA(isA<FormatException>().having((e) => e.message, 'motivo', isNotEmpty)),
          reason: bad,
        );
      }
    });

    test('impressões digitais só são iguais se todos os bytes forem', () {
      final a = Uint8List.fromList(List.generate(32, (i) => i));
      expect(sameBytes(a, Uint8List.fromList(a)), isTrue);
      expect(sameBytes(a, Uint8List.fromList(a)..[31] = 0), isFalse);
      expect(sameBytes(a, a.sublist(0, 31)), isFalse);
    });
  });

  group('contrato da API', () {
    test('/info diz o que é real e o que é simulado', () {
      final info = TelescopeInfo.fromJson(fixtureMap('info'));
      expect(info.id, startsWith('tele-'));
      expect((info.api, info.clockSynced, info.pairingOpen), (1, false, false));
      expect(info.capabilities.mountIsReal, isTrue, reason: 'a montagem está ligada de verdade');
      expect(info.capabilities.gotoIsReal, isFalse, reason: 'mas o apontamento ainda é simulado');
      expect(info.capabilities.cameraIsReal, isFalse);
      expect(info.capabilities.usesGpu, isTrue);
      expect(info.capabilities.modes, contains('night'));
      expect(info.site.source, 'default');
    });

    test('estado parado', () {
      final s = TelescopeState.fromJson(fixtureMap('state_idle'));
      expect((s.state, s.busy, s.job), ('IDLE', false, null));
      expect((s.mount.isReal, s.mount.connected, s.mount.raDeg), (true, true, 83.82));
      expect(s.mount.tracking, isNull, reason: 'a API ainda não informa o rastreio');
      expect((s.system.tempC, s.system.diskFreeGb), (41.5, 200.1));
    });

    test('estado empilhando: trabalho em curso e números da sessão', () {
      final s = TelescopeState.fromJson(fixtureMap('state_stacking'));
      expect((s.state, s.busy, s.stacking), ('STACKING', true, true));
      expect((s.job!.kind, s.job!.state, s.job!.isOpen), ('stack', 'running', true));
      expect(s.job!.steps.single.name, 'stack');
      expect((s.stack.accepted, s.stack.rejected, s.stack.snr, s.stack.fwhmPx), (12, 2, 9.7, 2.9));
      expect(s.stack.integrationS, isNull, reason: 'câmera simulada: sem tempo de exposição');
    });

    test('a resposta de um comando avisa o que ainda não é aplicado', () {
      final job = Job.fromJson(fixtureMap('job_stack'));
      expect((job.kind, job.state), ('stack', 'accepted'));
      expect(job.ignored, ['exposure_s']);
    });

    test('alvos e ficha', () {
      final page = TargetPage.fromJson(fixtureMap('targets'));
      expect(page.total, greaterThan(page.items.length));
      expect(page.items, hasLength(4));
      expect(page.items.every((t) => t.isHigh && t.fits == true), isTrue);
      expect(page.items.first.altDeg, greaterThanOrEqualTo(page.items.last.altDeg));

      final d = TargetDetail.fromJson(fixtureMap('target_detail'));
      expect((d.target.id, d.target.type, d.target.catalog), ('M42', 'nebula', 'NGC1976'));
      expect(d.night.length, inInclusiveRange(10, 60));
      expect(d.night.first.utc.isUtc, isTrue);
      expect(d.fovDeg, [2.57, 1.44]);
      expect(d.fills, greaterThan(1), reason: 'Órion é maior que o nosso campo');
      expect(d.target.fits, isFalse);
    });

    test('sessões, presets do estúdio, sistema e hora/local', () {
      final sessions = [for (final s in fixtureMap('sessions')['items'] as List) Session.fromJson((s as Map).cast())];
      expect((sessions.single.id, sessions.single.frames, sessions.single.integrationS), ('lagoon_trifid', 15, 2700));
      expect(sessions.single.isReference, isTrue);

      final presets = RenderPresets.fromJson(fixtureMap('presets'));
      expect(presets.presets.keys, containsAll(['natural', 'vivido', 'nebulosa', 'suave']));
      final stretch = presets.controls['stretch']!;
      expect((stretch.min, stretch.max, stretch.step, stretch.initial), (1.0, 30.0, 0.5, 10.0));
      expect(presets.presets['vivido']!['stretch'], 13.0);
      expect(presets.toggles, {'remove_grad': false});

      final system = SystemInfo.fromJson(fixtureMap('system'));
      expect((system.api, system.power, system.tempC), (1, false, 41.5));

      final site = SiteResult.fromJson(fixtureMap('site'));
      expect((site.clockSet, site.mountUpdated), (true, true));
    });

    test('erro da API vira uma falha classificada', () {
      final e = fixtureMap('error_unauthorized')['error'] as Map;
      final failure = ApiFailure.fromApi(401, '${e['code']}', '${e['message']}');
      expect(failure.kind, FailureKind.unauthorized);
      expect(ApiFailure.fromApi(403, 'pairing_closed', '').kind, FailureKind.pairingClosed);
      expect(ApiFailure.fromApi(501, 'not_enabled', '').kind, FailureKind.notSupported);
      expect(ApiFailure.fromApi(500, 'algo_novo', '').kind, FailureKind.unknown);
    });
  });

  group('canal em tempo real', () {
    test('as mensagens parciais montam o mesmo retrato que a Jetson tem', () {
      TelescopeState? state;
      final seen = <String>[];
      for (final m in fixture('ws_messages') as List) {
        final message = (m as Map).cast<String, dynamic>();
        state = applyLiveMessage(state, message);
        seen.add(message['type'] as String);
      }
      expect(seen, ['state', 'state', 'stack', 'progress']);
      expect((state!.state, state.stack.accepted, state.stack.snr), ('STACKING', 13, 10.1));
      expect((state.job!.state, state.job!.steps.single.state), ('stopped', 'stopped'));
      expect(state.mount.connected, isTrue, reason: 'o que não veio na mensagem continua como estava');
    });

    test('mensagem desconhecida não derruba nem altera o estado', () {
      final before = TelescopeState.fromJson(fixtureMap('state_stacking'));
      final after = applyLiveMessage(before, {
        'seq': 9,
        'type': 'novidade',
        'data': {'x': 1},
      });
      expect(after, same(before));
      expect(applyLiveMessage(before, {'type': 'stack', 'data': 'lixo'}), same(before));
      expect(
        applyLiveMessage(null, {
          'type': 'stack',
          'data': {'accepted': 3},
        }).stack.accepted,
        3,
      );
    });
  });

  group('formatação em português', () {
    test('números, tempos e coordenadas', () {
      expect(Fmt.dec(52.14), '52,1');
      expect(Fmt.degrees(51.6), '52°');
      expect(
        [Fmt.duration(45), Fmt.duration(1260), Fmt.duration(7500), Fmt.duration(7200)],
        ['45 s', '21 min', '2 h 05 min', '2 h'],
      );
      expect(Fmt.ra(270.92), '18h 03m');
      expect(Fmt.dec2(-24.38), "-24° 22'");
      expect(
        [
          Fmt.ago(const Duration(seconds: 1)),
          Fmt.ago(const Duration(seconds: 12)),
          Fmt.ago(const Duration(minutes: 3)),
        ],
        ['agora', 'há 12 s', 'há 3 min'],
      );
      expect(Fmt.bytes(1312380), '1,3 MB');
    });
  });
}
