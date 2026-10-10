// O app inteiro, tela por tela, contra o telescópio falso (o mesmo do modo demonstração).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:telescope_app/app/link.dart';
import 'package:telescope_app/app/prefs.dart';
import 'package:telescope_app/app/router.dart';
import 'package:telescope_app/core/errors.dart';
import 'package:telescope_app/core/widgets/kit.dart';
import 'package:telescope_app/data/location.dart';
import 'package:telescope_app/features/atlas/coords_screen.dart';
import 'package:telescope_app/features/observe/live_preview.dart';

import 'harness.dart';
import 'support.dart';

Future<void> tapText(WidgetTester tester, String text) async {
  await tester.tap(find.text(text).first);
  await tester.pump();
}

/// Toca no botão com este rótulo (e não num título de mesmo texto).
Future<void> tapButton(WidgetTester tester, String label) async {
  await tester.tap(find.widgetWithText(AppButton, label).first);
  await tester.pump();
}

Future<void> goTab(WidgetTester tester, String label) async {
  await tester.tap(find.bySemanticsLabel(label).last);
  await tester.pump(const Duration(milliseconds: 350));
}

void main() {
  // um toque que não acerta o alvo tem de falhar o teste, não passar em silêncio
  WidgetController.hitTestWarningShouldBeFatal = true;

  group('para onde a ligação manda', () {
    test('sem telescópio vai achar um; com telescópio vai observar', () {
      expect(redirectFor(LinkPhase.starting, '/observe'), '/');
      expect(redirectFor(LinkPhase.connecting, '/'), isNull);
      expect(redirectFor(LinkPhase.noDevice, '/'), '/connect');
      expect(redirectFor(LinkPhase.noDevice, '/connect/scan'), isNull);
      expect(redirectFor(LinkPhase.offline, '/atlas'), '/connect');
      expect(redirectFor(LinkPhase.online, '/'), '/observe');
      expect(redirectFor(LinkPhase.online, '/connect/pairing'), '/observe');
      expect(redirectFor(LinkPhase.online, '/atlas/target/M8'), isNull);
      expect(redirectFor(LinkPhase.reconnecting, '/gallery'), isNull, reason: 'o sinal caiu: nada é desfeito');
      expect(redirectFor(LinkPhase.identityChanged, '/observe'), '/connect/identity');
      expect(redirectFor(LinkPhase.revoked, '/observe'), '/connect');
    });
  });

  group('coordenadas digitadas', () {
    test('aceita as formas em que as pessoas escrevem', () {
      expect(parseSexagesimal('18 03 36'), closeTo(18.06, 1e-9));
      expect(parseSexagesimal('18h03m36s'), closeTo(18.06, 1e-9));
      expect(parseSexagesimal('18:03:36'), closeTo(18.06, 1e-9));
      expect(parseSexagesimal('18,06'), closeTo(18.06, 1e-9));
      expect(parseSexagesimal('-24 23 00'), closeTo(-24.3833, 1e-4));
      expect(parseSexagesimal('-0 30'), closeTo(-0.5, 1e-9), reason: 'o sinal vale mesmo com zero graus');
      for (final bad in ['', 'abc', '18 70 00', '1 2 3 4']) {
        expect(parseSexagesimal(bad), isNull, reason: bad);
      }
    });
  });

  testWidgets('primeira vez: sem telescópio, o app oferece o QR e a demonstração', (tester) async {
    final h = Harness();
    await h.pump(tester);
    expect(find.text('Achar o telescópio'), findsOneWidget);
    expect(find.text('Ler o QR do telescópio'), findsOneWidget);
    expect(find.text('Digitar o código'), findsOneWidget);
    await h.shot(tester, 'c2_achar');

    await tapText(tester, 'Demonstração');
    await h.route(tester);
    expect(find.text('Pronto para observar'), findsOneWidget);
    expect(find.text('demonstração, sem aparelho'), findsOneWidget);
    expect(find.text('simulada'), findsNWidgets(2), reason: 'montagem e câmera simuladas, ditas na tela');
    expect(find.text('Observar este alvo'), findsOneWidget);
    await h.shot(tester, 'o1_inicio');
    await h.close(tester);
  });

  testWidgets('noite rápida: um toque aponta, centraliza e empilha; PARAR encerra', (tester) async {
    final h = Harness(device: savedDevice(), prefs: {'site.lat': -23.55, 'site.lon': -46.63});
    await h.pump(tester);
    expect(find.text('conectado'), findsOneWidget);
    await tapText(tester, 'Observar este alvo');
    expect(h.telescope.commands.single, startsWith('observe:'));

    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('Apontar'), findsOneWidget);
    expect(find.text('agora...'), findsOneWidget);
    expect(find.text('PARAR'), findsOneWidget);
    expect(find.byType(LivePreview), findsOneWidget);
    expect(find.text('câmera simulada'), findsOneWidget);
    await h.shot(tester, 'o2_indo_para_o_alvo');

    await tester.pump(const Duration(seconds: 6)); // as etapas passam e o empilhamento começa
    await tester.pump();
    expect(find.textContaining('fotos'), findsOneWidget);
    expect(find.text('nitidez boa'), findsOneWidget);
    await h.shot(tester, 'o4_empilhando');

    await tapText(tester, 'PARAR');
    await tester.pump(const Duration(milliseconds: 100));
    expect(h.telescope.commands.last, 'stop');
    expect(find.textContaining('Sessão encerrada'), findsOneWidget);
    expect(find.text('Ver na galeria'), findsOneWidget);
    await h.shot(tester, 'o7_fim');

    await tapText(tester, 'Fechar');
    expect(find.text('Pronto para observar'), findsOneWidget);
    await h.close(tester);
  });

  testWidgets('goto que não converge: o erro aparece com as saídas', (tester) async {
    final h = Harness(device: savedDevice())..telescope.gotoFails = true;
    await h.pump(tester);
    await tapText(tester, 'Observar este alvo');
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
    expect(find.text('Não deu certo'), findsOneWidget);
    expect(find.textContaining('Não consegui centralizar'), findsOneWidget);
    expect(find.text('Tentar de novo'), findsOneWidget);
    expect(find.text('Escolher outro alvo'), findsOneWidget);
    await h.shot(tester, 'o2_falha');
    await h.close(tester);
  });

  testWidgets('em outro destino o PARAR flutua enquanto houver trabalho', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await goTab(tester, 'Atlas');
    await h.settle(tester);
    expect(find.text('Hoje'), findsOneWidget, reason: 'estamos no Atlas');
    expect(find.text('PARAR'), findsNothing);
    await h.telescope.stack(commandId: 't-1');
    await tester.pump(const Duration(milliseconds: 500));
    await h.settle(tester);
    expect(find.byType(LivePreview), findsNothing, reason: 'continuamos no Atlas');
    expect(find.text('PARAR'), findsOneWidget);
    await tapText(tester, 'PARAR');
    await h.settle(tester);
    expect(h.telescope.commands, ['stack', 'stop']);
    expect(find.text('PARAR'), findsNothing);
    await h.close(tester);
  });

  testWidgets('Atlas: hoje, busca, ficha com a noite e favoritos', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await goTab(tester, 'Atlas');
    await h.settle(tester);
    expect(find.textContaining('alto'), findsWidgets, reason: '"Hoje" vem ligado: só o que está alto');
    expect(find.textContaining('abaixo do horizonte'), findsNothing);
    await h.shot(tester, 'a1_atlas');

    await tester.enterText(find.byType(TextField), 'orion');
    await tester.pump(const Duration(milliseconds: 400)); // a busca espera a pessoa parar de digitar
    await h.settle(tester);
    expect(find.textContaining('Órion'), findsOneWidget);

    await tester.tap(find.bySemanticsLabel('Guardar nos meus alvos').first);
    await tester.pump();
    expect(h.container.read(prefsProvider).favorites, {'M42'});

    await tester.tap(find.textContaining('Órion'));
    await h.route(tester);
    await h.settle(tester);
    expect(find.text('ALTITUDE NESTA NOITE'), findsOneWidget);
    expect(find.textContaining('Melhor:'), findsOneWidget);
    expect(find.text('cabe só ao longo do lado maior'), findsOneWidget, reason: "90' num campo de 154' x 86'");
    expect(find.textContaining('mosaico'), findsOneWidget);
    await h.shot(tester, 'a2_ficha');
    await tester.scrollUntilVisible(find.text('Observar agora'), 300, scrollable: find.byType(Scrollable).last);
    expect(find.text('Observar agora'), findsOneWidget);
    expect(find.text('Só apontar'), findsOneWidget);
    await h.close(tester);
  });

  testWidgets('Galeria, sessão e estúdio: o preset pede uma prévia nova', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await goTab(tester, 'Galeria');
    await h.settle(tester);
    expect(find.text('M8 Lagoa'), findsOneWidget);
    expect(find.text('demonstração'), findsWidgets);
    await h.shot(tester, 'g1_galeria');

    await tapText(tester, 'M8 Lagoa');
    await h.route(tester);
    await h.settle(tester);
    expect(find.text('Abrir no estúdio'), findsOneWidget);
    await tapText(tester, 'Abrir no estúdio');
    await h.route(tester);
    await h.settle(tester);
    expect(find.text('Vívido'), findsOneWidget);
    expect(find.text('Brilho'), findsOneWidget);
    expect(find.text('10,0'), findsOneWidget, reason: 'o brilho do preset natural');
    await tapText(tester, 'Vívido');
    await h.settle(tester);
    expect(find.text('13,0'), findsOneWidget, reason: 'os controles acompanham o preset');
    await h.shot(tester, 'g3_estudio');
    await h.close(tester);
  });

  testWidgets('Aparelho, sistema e preferências; o modo vermelho cobre o app inteiro', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await goTab(tester, 'Aparelho');
    expect(find.text('Montagem'), findsOneWidget);
    expect(find.text('faltam enviar'), findsOneWidget, reason: 'hora e local ainda não foram enviados');
    await h.shot(tester, 'd1_aparelho');

    await tapText(tester, 'Sistema');
    await h.route(tester);
    await h.settle(tester);
    expect(find.textContaining('Desligar pelo app ainda não está habilitado'), findsOneWidget);

    await tester.tap(find.bySemanticsLabel('Ligar o modo vermelho'));
    await tester.pump();
    expect(h.container.read(prefsProvider).redMode, isTrue);
    expect(find.byType(ColorFiltered), findsWidgets);
    await h.shot(tester, 'x4_modo_vermelho');
    await h.close(tester);
  });

  testWidgets('hora e local: o GPS do celular vai para o telescópio e fica guardado', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    expect(find.text('O telescópio ainda não sabe a hora e o local'), findsOneWidget);
    await tapText(tester, 'Enviar agora');
    await h.route(tester);
    await tapText(tester, 'Usar o local deste celular');
    await h.settle(tester);
    expect(find.textContaining('Enviado.'), findsOneWidget);
    expect((h.telescope.lat, h.telescope.lon), (-22.9, -43.2));
    expect(h.container.read(prefsProvider).siteLat, -22.9, reason: 'reenviado sozinho nas próximas conexões');
    await h.shot(tester, 'c7_local_e_hora');
    await h.close(tester);
  });

  testWidgets('sem permissão de localização dá para digitar as coordenadas', (tester) async {
    final h = Harness(
      device: savedDevice(),
      location: FakeLocation(problem: LocationProblem.denied),
    );
    await h.pump(tester);
    await tapText(tester, 'Enviar agora');
    await h.route(tester);
    await tapText(tester, 'Usar o local deste celular');
    await h.settle(tester);
    expect(find.textContaining('Sem permissão de localização'), findsOneWidget);
    await tester.enterText(find.byType(TextField).first, '-23,55');
    await tester.enterText(find.byType(TextField).last, '-46,63');
    await tapText(tester, 'Enviar');
    await h.settle(tester);
    expect((h.telescope.lat, h.telescope.lon), (-23.55, -46.63));
    await h.close(tester);
  });

  testWidgets('o sinal cai: nada é desfeito, a faixa avisa, e a ligação volta sozinha', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    h.telescope
      ..offline = true
      ..drop();
    await h.settle(tester);
    expect(find.textContaining('reconectando'), findsOneWidget);
    expect(find.text('Pronto para observar'), findsOneWidget, reason: 'a tela continua onde estava');
    await h.shot(tester, 'x1_reconectando');

    h.telescope.offline = false;
    await tester.pump(const Duration(seconds: 2)); // a primeira nova tentativa
    await h.settle(tester);
    expect(find.text('conectado'), findsOneWidget);
    await h.close(tester);
  });

  testWidgets('telescópio pareado que não responde ao abrir: o app diz e continua tentando', (tester) async {
    final h = Harness(device: savedDevice())..telescope.offline = true;
    await h.pump(tester);
    expect(find.text('Achar o telescópio'), findsOneWidget);
    expect(find.textContaining('sem resposta'), findsOneWidget);
    expect(find.text('Tentar agora'), findsOneWidget);
    h.telescope.offline = false;
    await tapText(tester, 'Tentar agora');
    await h.settle(tester);
    expect(find.text('Pronto para observar'), findsOneWidget);
    await h.close(tester);
  });

  testWidgets('impostor: outro certificado no endereço do telescópio para tudo', (tester) async {
    final h = Harness(device: savedDevice())..telescope.failure = const ApiFailure(FailureKind.identityMismatch);
    await h.pump(tester);
    expect(find.text('Este não é o telescópio que você pareou'), findsOneWidget);
    expect(find.text('Parear de novo'), findsOneWidget);
    await h.shot(tester, 'c9_identidade_mudou');
    await tapText(tester, 'Parear de novo');
    await h.settle(tester);
    expect(find.text('Achar o telescópio'), findsOneWidget);
    expect(h.store.device, isNull, reason: 'o pareamento antigo foi esquecido');
    await h.close(tester);
  });

  testWidgets('celular revogado no meio do uso: o app volta a pedir o pareamento', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    h.telescope.drop(const ApiFailure(FailureKind.unauthorized));
    await h.settle(tester);
    await h.route(tester);
    expect(find.text('Este celular não está mais pareado'), findsOneWidget);
    await h.close(tester);
  });

  group('parear', () {
    final uri = fixtureMap('pairing_vector')['uri'] as String;

    Future<Harness> openPairing(WidgetTester tester, {Object? failure}) async {
      final h = Harness(pairer: fakePairer(failure: failure));
      await h.pump(tester);
      await tapText(tester, 'Digitar o código');
      await h.route(tester);
      await tester.enterText(find.byType(TextField), uri);
      await tapText(tester, 'Continuar');
      await h.route(tester);
      return h;
    }

    testWidgets('código colado, nome do celular, parear: o app conecta e guarda o telescópio', (tester) async {
      final h = await openPairing(tester);
      expect(find.text('Telescópio tele-6465'), findsOneWidget);
      expect(find.textContaining('Telescopio-6465'), findsOneWidget, reason: 'avisa do WiFi do telescópio');
      await h.shot(tester, 'c5_parear');
      await tapButton(tester, 'Parear');
      await h.settle(tester);
      expect(find.text('Pronto para observar'), findsOneWidget);
      expect((h.store.device!.deviceId, h.store.device!.token), ('tele-6465', 'token-novo'));
      expect(h.store.device!.host, '192.168.3.221');
      expect(h.container.read(prefsProvider).clientName, 'Meu celular');
      await h.close(tester);
    });

    testWidgets('identidade que não confere: para na primeira etapa e não guarda nada', (tester) async {
      final h = await openPairing(tester, failure: const ApiFailure(FailureKind.identityMismatch));
      await tapButton(tester, 'Parear');
      await h.settle(tester);
      expect(find.text('A identidade não confere'), findsOneWidget);
      expect(find.textContaining('Nada foi enviado'), findsOneWidget);
      expect(h.store.device, isNull);
      await h.shot(tester, 'c5_impostor');
      await h.close(tester);
    });

    testWidgets('janela de pareamento fechada: diz o que fazer no telescópio', (tester) async {
      final h = await openPairing(tester, failure: const ApiFailure(FailureKind.pairingClosed));
      await tapButton(tester, 'Parear');
      await h.settle(tester);
      expect(find.text('Não pareou'), findsOneWidget);
      expect(find.textContaining('Abra a janela de pareamento'), findsOneWidget);
      expect(find.text('Tentar de novo'), findsOneWidget);
      await h.close(tester);
    });

    testWidgets('texto que não é código de telescópio é recusado na hora', (tester) async {
      final h = Harness();
      await h.pump(tester);
      await tapText(tester, 'Digitar o código');
      await h.route(tester);
      await tester.enterText(find.byType(TextField), 'https://exemplo.com/qualquer');
      await tapText(tester, 'Continuar');
      expect(find.text('Este não é o código de um telescópio.'), findsOneWidget);
      await h.close(tester);
    });
  });

  testWidgets('todos os ícones do produto desenham', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: Wrap(children: [for (final name in _iconNames) AppIcon(name, size: 40)])),
      ),
    );
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(find.byType(AppIcon), findsNWidgets(_iconNames.length));
  });
}

const _iconNames = [
  'album',
  'atlas',
  'back',
  'camera',
  'chart',
  'check',
  'chevron',
  'chip',
  'clock',
  'close',
  'cluster',
  'disk',
  'dot',
  'download',
  'eye',
  'focus',
  'galaxy',
  'grid',
  'info',
  'keyboard',
  'layers',
  'list',
  'live',
  'lock',
  'moon',
  'mount',
  'nebula',
  'phone',
  'pin',
  'planet',
  'play',
  'plus',
  'power',
  'qr',
  'reticle',
  'satellite',
  'search',
  'share',
  'sliders',
  'square',
  'star',
  'sun',
  'target',
  'thermo',
  'trash',
  'warning',
  'wifi',
]; // ignore_for_file: lines_longer_than_80_chars
