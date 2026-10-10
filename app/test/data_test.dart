// A camada de dados sem rede: o fluxo de imagem ao vivo e o telescópio falso.
import 'dart:async';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter_test/flutter_test.dart';
import 'package:telescope_app/core/errors.dart';
import 'package:telescope_app/data/fake_telescope.dart';
import 'package:telescope_app/data/mjpeg.dart';
import 'package:telescope_app/data/png.dart';
import 'package:telescope_app/domain/models.dart';

import 'support.dart';

List<int> _jpeg(int filler, int size) => [0xFF, 0xD8, ...List.filled(size, filler), 0xFF, 0xD9];

List<int> _part(List<int> jpeg) => [
  ...'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ${jpeg.length}\r\n\r\n'.codeUnits,
  ...jpeg,
  ...'\r\n'.codeUnits,
];

const _fast = Duration(milliseconds: 4);

Future<TelescopeState> _until(FakeTelescope api, bool Function(TelescopeState) test) =>
    api.watch().firstWhere(test).timeout(const Duration(seconds: 5));

void main() {
  group('imagem ao vivo (MJPEG)', () {
    test('remonta os quadros qualquer que seja o tamanho dos pedaços da rede', () async {
      final a = _jpeg(1, 300), b = _jpeg(2, 5), c = _jpeg(3, 1200);
      final all = [..._part(a), ..._part(b), ..._part(c)];
      for (final chunk in [1, 7, 64, all.length]) {
        final pieces = [for (var i = 0; i < all.length; i += chunk) all.sublist(i, (i + chunk).clamp(0, all.length))];
        final frames = await Stream.fromIterable(pieces).transform(const MjpegSplitter()).toList();
        expect(frames, [a, b, c], reason: 'pedaços de $chunk bytes');
      }
    });

    test('fluxo corrompido não cresce sem limite: o quadro gigante é descartado', () async {
      final junk = [0xFF, 0xD8, ...List.filled(5000, 9)]; // começa e nunca termina
      final good = _jpeg(4, 10);
      final frames = await Stream.fromIterable([
        junk,
        good,
      ]).transform(const MjpegSplitter(maxFrameBytes: 1000)).toList();
      expect(frames, [good]);
    });

    test('o fim do fluxo no meio de um quadro não inventa um quadro', () async {
      final frames = await Stream.fromIterable([_jpeg(1, 50).sublist(0, 30)]).transform(const MjpegSplitter()).toList();
      expect(frames, isEmpty);
    });
  });

  group('telescópio falso (modo demonstração)', () {
    late FakeTelescope api;
    setUp(() => api = FakeTelescope(step: _fast, now: () => DateTime.utc(2026, 10, 10, 1, 30)));
    tearDown(() => api.close());

    test('apontar segue as etapas de verdade e termina', () async {
      final seen = <String>[];
      final sub = api.watch().listen((s) => seen.add('${s.state}/${s.job?.state}'));
      final job = await api.goTo(commandId: 'c-1', target: 'M8');
      expect((job.kind, job.state, job.target), ('goto', 'accepted', 'M8'));
      final end = await _until(api, (s) => s.job?.state == 'done');
      await sub.cancel();
      expect(end.state, 'STOPPED');
      expect(end.job!.steps.map((s) => s.name), ['slew', 'solve', 'slew', 'solve']);
      expect(end.pointing.unit, 'arcmin');
      expect(end.pointing.error, lessThan(1));
      expect(seen, containsAllInOrder(['SLEWING/running', 'SOLVING/running', 'STOPPED/done']));
    });

    test('reenviar o mesmo comando não executa de novo', () async {
      final a = await api.goTo(commandId: 'c-7', target: 'M8');
      final b = await api.goTo(commandId: 'c-7', target: 'M8');
      expect(b.id, a.id);
      expect(api.commands, ['goto:M8']);
    });

    test('goto que não converge termina como falha, com o motivo', () async {
      api.gotoFails = true;
      await api.goTo(commandId: 'c-1', target: 'M8');
      final end = await _until(api, (s) => s.job?.failed ?? false);
      expect(end.job!.error, 'not_converged');
      expect(end.job!.steps.last.state, 'failed');
    });

    test('empilhar soma fotos até o app parar', () async {
      final job = await api.stack(commandId: 's-1', exposureS: 30);
      expect(job.ignored, ['exposure_s'], reason: 'como a Jetson: avisa o que não é aplicado');
      final running = await _until(api, (s) => s.stack.accepted >= 5);
      expect((running.stacking, running.busy), (true, true));
      expect(running.stack.snr, greaterThan(0));
      final stopping = _until(api, (s) => s.job?.state == 'stopped');
      await api.stop(commandId: 's-2');
      final end = await stopping;
      expect((end.state, end.busy), ('STOPPED', false));
      expect(api.commands, ['stack', 'stop']);
    });

    test('alvos: o mais alto primeiro, com busca e filtros', () async {
      final all = await api.targets();
      expect(all.total, greaterThan(10));
      expect(all.items.first.altDeg, greaterThanOrEqualTo(all.items.last.altDeg));
      final high = await api.targets(visible: true);
      expect(high.items, isNotEmpty);
      expect(high.items.every((t) => t.isHigh), isTrue);
      expect((await api.targets(query: 'orion')).items.single.id, 'M42');
      expect((await api.targets(type: 'cluster')).items.every((t) => t.type == 'cluster'), isTrue);
      expect((await api.targets(fits: true)).items.every((t) => t.fits == true), isTrue);
      final page = await api.targets(limit: 3, offset: 3);
      expect(page.items.first.id, all.items[3].id);
    });

    test('a ficha traz a noite que vem', () async {
      final d = await api.target('m 42'); // em outubro Órion sobe de madrugada
      expect(d.target.id, 'M42');
      expect(d.night.length, inInclusiveRange(10, 60));
      expect(d.bestFrom, isNotNull);
      expect(d.bestTo!.isAfter(d.bestFrom!), isTrue);
      expect(d.fills, closeTo(1.04, 0.01), reason: 'maior que o campo');
      final m8 = await api.target('M8'); // a Lagoa já está se pondo a essa hora
      expect((m8.bestFrom, m8.fills), (null, 0.52));
      expect(() => api.target('XYZ'), throwsA(isA<ApiFailure>().having((f) => f.kind, 'kind', FailureKind.notFound)));
    });

    test('a altitude confere com a conta da Jetson', () {
      // A ficha do M42 gravada da API real (São Paulo, 2026-10-10 01:30 UTC) traz a altitude
      // que a Jetson calculou: a conta em Dart tem de dar o mesmo.
      final real = fixtureMap('target_detail');
      final when = DateTime.utc(2026, 10, 10, 1, 30);
      final ours = altitudeDeg(real['ra_deg'] as double, real['dec_deg'] as double, -23.55, -46.63, when);
      expect(ours, closeTo(real['alt_deg'] as double, 0.1));
      expect(sunAltitudeDeg(-23.55, -46.63, DateTime.utc(2026, 10, 9, 15)), greaterThan(60));
      expect(sunAltitudeDeg(-23.55, -46.63, DateTime.utc(2026, 10, 9, 3)), lessThan(-30));
    });

    test('fora do ar, toda chamada falha como "sem resposta"', () async {
      api.offline = true;
      final unreachable = throwsA(isA<ApiFailure>().having((f) => f.kind, 'kind', FailureKind.unreachable));
      expect(api.info, unreachable);
      expect(api.state, unreachable);
      expect(() => api.targets(), unreachable);
    });

    test('hora e local do celular passam a valer', () async {
      expect((await api.info()).clockSynced, isFalse);
      await api.setSite(utc: DateTime.utc(2026, 10, 10), lat: -22.9, lon: -43.2);
      final info = await api.info();
      expect((info.clockSynced, info.site.lat, info.site.source), (true, -22.9, 'phone'));
    });
  });

  group('imagens do modo demonstração', () {
    TestWidgetsFlutterBinding.ensureInitialized();

    test('o PNG gerado é uma imagem de verdade', () async {
      final rgb = Uint8List(4 * 2 * 3)..fillRange(0, 24, 200);
      final codec = await ui.instantiateImageCodec(encodePng(4, 2, rgb));
      final frame = await codec.getNextFrame();
      expect((frame.image.width, frame.image.height), (4, 2));
    });

    test('miniatura, quadro ao vivo e render saem decodificáveis e estáveis', () async {
      final api = FakeTelescope(step: _fast);
      addTearDown(api.close);
      for (final bytes in [
        (await api.targetThumb('M8'))!,
        (await api.frame())!,
        (await api.sessionImage('demo-m8'))!,
        (await api.render('demo-m8', {'preset': 'vivido', 'stretch': 13.0}))!,
      ]) {
        final codec = await ui.instantiateImageCodec(bytes);
        expect((await codec.getNextFrame()).image.width, greaterThan(0));
      }
      expect(await api.targetThumb('M8'), same(await api.targetThumb('M8')), reason: 'o mesmo alvo, a mesma imagem');
      expect(await api.render('demo-m8', {'stretch': 5.0}), isNot(await api.render('demo-m8', {'stretch': 25.0})));
    });
  });
}
