// As telas que faltavam, contra o telescópio falso: achar o telescópio na rede, o WiFi dele
// (campo) e o de casa, atualizações, alinhamento polar, captura planetária e os avisos com a
// tela apagada.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:telescope_app/app/link.dart';
import 'package:telescope_app/app/prefs.dart';
import 'package:telescope_app/core/widgets/kit.dart';
import 'package:telescope_app/data/alerts.dart';
import 'package:telescope_app/data/device_store.dart';
import 'package:telescope_app/data/discovery.dart';
import 'package:telescope_app/data/fake_telescope.dart';
import 'package:telescope_app/data/telescope_wifi.dart';

import 'harness.dart';

/// O telescópio pareado, com o WiFi próprio dele já conhecido pelo app.
SavedDevice fieldDevice() =>
    savedDevice().copyWith(wifiSsid: 'Telescopio-0b04', wifiPsk: 'senha-do-campo', wifiHost: '10.42.0.1');

/// Rola a lista da tela até isto existir e estar à vista.
Future<void> reveal(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(finder, 200, scrollable: find.byType(Scrollable).last);
  await tester.pump();
}

/// Deixa o tempo passar, de segundo em segundo (as esperas do app perguntam nesse ritmo).
Future<void> wait(WidgetTester tester, int seconds) async {
  for (var i = 0; i < seconds; i++) {
    await tester.pump(const Duration(seconds: 1));
  }
}

/// O botão deste rótulo dentro do cartão que tem este texto.
Finder buttonIn(String card, String label) =>
    find.descendant(of: find.widgetWithText(Panel, card), matching: find.widgetWithText(AppButton, label));

/// Responde "sim" a um diálogo cujo botão tem o mesmo rótulo de um botão da página.
Future<void> confirmWith(WidgetTester tester, String label) async {
  await tester.tap(find.widgetWithText(AppButton, label).last);
  await tester.pump();
}

void main() {
  WidgetController.hitTestWarningShouldBeFatal = true;

  // ---------------------------------------------------------------- achar na rede
  testWidgets('achar: a lista mostra quem se anunciou na rede, e diz o que falta', (tester) async {
    final h = Harness();
    await h.pump(tester);
    expect(find.textContaining('Nenhum telescópio se anunciou nesta rede'), findsOneWidget);
    expect(h.discovery.listeners, 1, reason: 'a busca roda enquanto a tela está aberta');

    h.discovery.announce([
      const FoundTelescope(deviceId: 'tele-9999', host: '192.168.3.77', name: 'Telescópio do vizinho'),
      const FoundTelescope(deviceId: 'tele-4242', host: '192.168.3.78'),
    ]);
    await h.settle(tester);
    expect(find.text('Telescópio do vizinho'), findsOneWidget);
    expect(find.text('Telescópio tele-4242'), findsOneWidget, reason: 'sem nome, mostra o identificador');
    expect(find.textContaining('para usar, leia o código dele'), findsNWidgets(2));
    expect(find.textContaining('Nenhum telescópio se anunciou'), findsNothing);
    await h.shot(tester, 'c2_na_rede');
    await h.close(tester);
  });

  testWidgets('o telescópio mudou de endereço: o app o reencontra pelo anúncio e guarda o novo', (tester) async {
    final h = Harness(device: savedDevice());
    h.hosts.add('192.168.3.50'); // no endereço guardado ninguém responde mais
    await h.pump(tester);
    expect(find.textContaining('sem resposta'), findsOneWidget);
    expect(
      h.asked,
      containsAll(['192.168.3.221', '10.42.0.1', 'telescopio.local']),
      reason: 'procura também no WiFi próprio dele e pelo apelido de casa',
    );

    h.discovery.announce([const FoundTelescope(deviceId: 'tele-0b04', host: '192.168.3.50')]);
    await wait(tester, 1); // um anúncio manda tentar logo, mas não a cada anúncio
    await h.settle(tester);
    await h.route(tester);
    expect(find.text('Pronto para observar'), findsOneWidget);
    expect(h.store.device!.host, '192.168.3.50', reason: 'da próxima vez começa pelo endereço novo');
    expect(h.discovery.listeners, 0, reason: 'achou: a busca para');
    await h.close(tester);
  });

  testWidgets('anúncio não é identidade: quem anuncia o seu telescópio sem o certificado é ignorado', (tester) async {
    final h = Harness(device: savedDevice());
    h.hosts.add('192.168.3.50');
    h.impostors.add('192.168.3.66');
    await h.pump(tester);
    h.discovery.announce([const FoundTelescope(deviceId: 'tele-0b04', host: '192.168.3.66')]);
    await wait(tester, 1);
    await h.settle(tester);
    expect(h.asked, contains('192.168.3.66'), reason: 'o app foi conferir');
    expect(find.text('Achar o telescópio'), findsOneWidget);
    expect(find.text('Este não é o telescópio que você pareou'), findsNothing, reason: 'candidato falso não é alarme');
    expect(find.textContaining('conferindo a identidade'), findsOneWidget);
    expect(h.store.device!.host, '192.168.3.221', reason: 'o endereço guardado não muda');

    // o verdadeiro aparece: aí sim
    h.discovery.announce([
      const FoundTelescope(deviceId: 'tele-0b04', host: '192.168.3.66'),
      const FoundTelescope(deviceId: 'tele-0b04', host: '192.168.3.50'),
    ]);
    await wait(tester, 1);
    await h.settle(tester);
    await h.route(tester);
    expect(find.text('Pronto para observar'), findsOneWidget);
    expect(h.store.device!.host, '192.168.3.50');
    await h.close(tester);
  });

  testWidgets('esquecer no meio da procura: a resposta que chega depois não ressuscita nada', (tester) async {
    final h = Harness(device: savedDevice());
    h.telescope.latency = const Duration(seconds: 3); // rede lenta: a resposta ainda está a caminho
    await h.pump(tester);
    expect(h.container.read(linkProvider).phase, LinkPhase.connecting);
    await h.container.read(linkProvider.notifier).forget();
    await wait(tester, 5); // a resposta atrasada chega agora
    await h.settle(tester);
    expect(h.container.read(linkProvider).phase, LinkPhase.noDevice);
    expect(h.store.device, isNull);
    expect(find.text('Achar o telescópio'), findsOneWidget);
    h.telescope.latency = null;
    await h.close(tester);
  });

  testWidgets('esquecer com uma gravação a caminho: o "esquecer" é sempre o último', (tester) async {
    // O telescópio foi achado em outro endereço e o app está gravando o endereço novo quando
    // a pessoa manda esquecer. Sem fila, a gravação atrasada reescreveria o que foi apagado.
    final store = SlowStore(savedDevice(), delay: const Duration(seconds: 2));
    final h = Harness(device: savedDevice(), store: store)..hosts.add('192.168.3.50');
    await h.pump(tester);
    h.discovery.announce([const FoundTelescope(deviceId: 'tele-0b04', host: '192.168.3.50')]);
    await wait(tester, 1); // achou: começou a gravar (leva 2 s)
    await tester.pump(const Duration(milliseconds: 200));
    expect(h.container.read(linkProvider).device?.host, '192.168.3.50', reason: 'já fala pelo endereço novo');
    expect(store.device!.host, '192.168.3.221', reason: 'a gravação ainda não terminou');
    final forgotten = h.container.read(linkProvider.notifier).forget();
    await wait(tester, 4);
    await forgotten;
    await h.settle(tester);
    expect(store.device, isNull, reason: 'esquecido de verdade');
    expect(h.container.read(linkProvider).phase, LinkPhase.noDevice);
    await h.close(tester);
  });

  testWidgets('anúncios em excesso não viram tentativas em excesso', (tester) async {
    final h = Harness(device: savedDevice())..hosts.add('192.168.3.50');
    await h.pump(tester);
    h.asked.clear();
    // alguém na rede anuncia o identificador do telescópio em vinte endereços, e de novo, e de novo
    for (var round = 0; round < 3; round++) {
      h.discovery.announce([
        for (var i = 0; i < 20; i++) FoundTelescope(deviceId: 'tele-0b04', host: '192.168.9.${100 + round * 20 + i}'),
      ]);
      await tester.pump(const Duration(milliseconds: 100));
    }
    await wait(tester, 1);
    await h.settle(tester);
    final announced = h.asked.where((host) => host.startsWith('192.168.9.')).toSet();
    expect(announced.length, lessThanOrEqualTo(4), reason: 'no máximo quatro candidatos anunciados por vez');
    expect(find.text('Achar o telescópio'), findsOneWidget);
    await h.close(tester);
  });

  testWidgets('conectado, o app aprende o WiFi próprio do telescópio e guarda para o campo', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    final saved = h.store.device!;
    expect((saved.wifiSsid, saved.wifiPsk, saved.wifiHost), (FakeTelescope.hotspotSsid, 'ceu-estrelado', '10.42.0.1'));
    expect(saved.host, '192.168.3.221', reason: 'o endereço de casa continua sendo o primeiro');
    await h.close(tester);
  });

  testWidgets('quem não é dono não recebe a senha do WiFi: nada é guardado', (tester) async {
    final h = Harness(device: savedDevice())..telescope.owner = false;
    await h.pump(tester);
    expect(find.text('Pronto para observar'), findsOneWidget);
    expect(h.store.device!.knowsWifi, isFalse);
    await h.close(tester);
  });

  // ---------------------------------------------------------- C4: WiFi do telescópio
  testWidgets('longe de casa: o app entra no WiFi do telescópio e o acha lá', (tester) async {
    final wifi = FakeWifi();
    final h = Harness(device: fieldDevice(), wifi: wifi);
    h.hosts.add('fora-do-ar'); // ninguém responde em lugar nenhum...
    wifi.onJoin = () => h.hosts
      ..clear()
      ..add('10.42.0.1'); // ...até o celular entrar no WiFi dele
    await h.pump(tester);
    expect(find.textContaining('Fora de casa: ele cria o próprio WiFi'), findsOneWidget);
    await pressButton(tester, 'Entrar no WiFi do telescópio');
    await h.route(tester);
    expect(find.text('Telescopio-0b04'), findsOneWidget);
    expect(find.textContaining('O Android vai pedir sua permissão'), findsOneWidget);
    expect(wifi.joined, isEmpty, reason: 'só pede ao Android depois do toque');
    await h.shot(tester, 'c4_wifi_do_telescopio');

    await pressButton(tester, 'Entrar no WiFi do telescópio');
    await h.settle(tester);
    await h.route(tester);
    expect(wifi.joined, ['Telescopio-0b04']);
    expect(wifi.lastPsk, 'senha-do-campo');
    expect(find.text('Pronto para observar'), findsOneWidget, reason: 'achou: o app segue sozinho');
    expect(h.store.device!.host, '10.42.0.1');
    await h.close(tester);
  });

  testWidgets('WiFi do telescópio: aviso fechado ou rede fora de alcance tem explicação e nova tentativa', (
    tester,
  ) async {
    final wifi = FakeWifi(WifiJoin.unavailable);
    final h = Harness(device: fieldDevice(), wifi: wifi)..hosts.add('fora-do-ar');
    await h.pump(tester);
    await pressButton(tester, 'Entrar no WiFi do telescópio');
    await h.route(tester);
    await pressButton(tester, 'Entrar no WiFi do telescópio');
    await h.settle(tester);
    expect(find.text('Não entrei no WiFi do telescópio'), findsOneWidget);
    expect(find.textContaining('cerca de um minuto para criar o WiFi'), findsOneWidget);
    await h.shot(tester, 'c4_recusado');
    await pressButton(tester, 'Tentar de novo');
    await h.settle(tester);
    expect(wifi.joined, hasLength(2));
    await h.close(tester);
  });

  testWidgets('celular que não entra no WiFi pelo app: o caminho manual, com a senha à mão', (tester) async {
    final wifi = FakeWifi(WifiJoin.unsupported);
    final h = Harness(device: fieldDevice(), wifi: wifi)..hosts.add('fora-do-ar');
    await h.pump(tester);
    await pressButton(tester, 'Entrar no WiFi do telescópio');
    await h.route(tester);
    await pressButton(tester, 'Entrar no WiFi do telescópio');
    await h.settle(tester);
    expect(find.text('Este celular não entra no WiFi pelo app'), findsOneWidget);
    expect(find.text('senha-do-campo'), findsNothing, reason: 'a senha fica escondida até pedirem');
    await tester.tap(find.bySemanticsLabel('Mostrar a senha'));
    await tester.pump();
    expect(find.text('senha-do-campo'), findsOneWidget);

    await pressButton(tester, 'Já entrei: procurar');
    await tester.pump();
    expect(find.text('Dentro do WiFi. Procurando o telescópio.'), findsOneWidget);
    await wait(tester, 16); // passou o prazo e ele não respondeu
    expect(find.text('O telescópio não respondeu'), findsOneWidget);
    expect(find.text('Procurar de novo'), findsOneWidget);
    await h.close(tester);
  });

  testWidgets('sem conhecer o WiFi do telescópio, a tela manda ler o código de novo', (tester) async {
    final h = Harness(device: savedDevice())..telescope.offline = true;
    await h.pump(tester);
    expect(
      find.text('Entrar no WiFi do telescópio'),
      findsNothing,
      reason: 'sem nome nem senha, não há o que oferecer',
    );
    await h.close(tester);
  });

  // ------------------------------------------------------- D5 e C8: a rede do telescópio
  testWidgets('rede: do WiFi próprio para o de casa (senha errada, depois a certa), e de volta', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await openTab(tester, 'Aparelho');
    await pressText(tester, 'Ligação');
    await h.route(tester);
    await h.settle(tester);
    expect(find.text('WiFi do telescópio'), findsOneWidget, reason: 'o modo de agora');
    expect(find.text(FakeTelescope.hotspotSsid), findsOneWidget);
    expect(find.text('ligado agora'), findsOneWidget);
    expect(find.text('ceu-estrelado'), findsNothing);
    await tester.tap(find.bySemanticsLabel('Mostrar a senha'));
    await tester.pump();
    expect(find.text('ceu-estrelado'), findsOneWidget);
    await h.shot(tester, 'd5_rede_campo');
    await reveal(tester, find.text('Passar para o WiFi de casa'));
    expect(
      tester.widget<AppButton>(find.widgetWithText(AppButton, 'Passar para o WiFi de casa')).onPressed,
      isNull,
      reason: 'sem rede de casa guardada, não há para onde ir',
    );

    // C8: as redes que o TELESCÓPIO enxerga
    await pressButton(tester, 'Entrar no WiFi de casa');
    await h.route(tester);
    await h.settle(tester);
    expect(find.text('Casa'), findsOneWidget);
    expect(find.text('sinal forte'), findsOneWidget);
    expect(find.text('sinal médio · aberta, sem senha'), findsOneWidget);
    await h.shot(tester, 'c8_wifi_de_casa');

    await pressText(tester, 'Casa');
    await tester.pump();
    expect(find.text('Senha de "Casa"'), findsOneWidget);
    expect(
      tester.widget<AppButton>(find.widgetWithText(AppButton, 'Entrar nesta rede')).onPressed,
      isNull,
      reason: 'sem senha não envia',
    );
    await tester.enterText(find.byType(TextField), 'senha-errada');
    await tester.pump();
    await pressButton(tester, 'Entrar nesta rede');
    await h.route(tester);
    expect(find.text('O telescópio vai trocar de WiFi e esta conexão vai cair por alguns segundos.'), findsOneWidget);
    expect(h.telescope.commands, isEmpty, reason: 'Q4: antes de confirmar, nada é pedido');
    await pressButton(tester, 'Trocar');
    await tester.pump();
    expect(find.textContaining('está entrando em "Casa"'), findsOneWidget);
    await wait(tester, 3);
    await h.settle(tester);
    expect(find.text('O telescópio não entrou em "Casa"'), findsOneWidget);
    expect(find.text('A senha não confere. O telescópio continuou onde estava.'), findsOneWidget);
    await h.shot(tester, 'c8_senha_errada');

    await pressButton(tester, 'Tentar outra senha');
    await tester.pump();
    await tester.enterText(find.byType(TextField), 'senha-de-casa');
    await tester.pump();
    await pressButton(tester, 'Entrar nesta rede');
    await h.route(tester);
    await pressButton(tester, 'Trocar');
    await wait(tester, 3);
    await h.settle(tester);
    expect(find.text('O telescópio entrou em "Casa"'), findsOneWidget);
    expect(h.telescope.commands, ['net:join:Casa', 'net:join:Casa']);
    await pressButton(tester, 'Concluir');
    await h.route(tester);
    await h.settle(tester);

    // de volta à D5: agora em casa
    expect(find.text('WiFi de casa: Casa'), findsOneWidget);
    expect(find.text('sinal forte'), findsOneWidget);
    expect(find.text('desligado'), findsOneWidget, reason: 'o WiFi próprio some enquanto ele está em casa');
    await reveal(tester, find.text('em uso agora'));
    await h.shot(tester, 'd5_rede_casa');

    await reveal(tester, find.text('Passar para o WiFi do telescópio'));
    await pressButton(tester, 'Passar para o WiFi do telescópio');
    await h.route(tester);
    await pressButton(tester, 'Trocar');
    await wait(tester, 3);
    await h.settle(tester);
    expect(find.text('O telescópio está no WiFi próprio.'), findsOneWidget);
    expect(h.telescope.commands.last, 'net:mode:field');
    await tester.pump(const Duration(seconds: 5)); // o aviso sai sozinho

    // esquecer a rede de casa pergunta antes
    await reveal(tester, find.text('guardada'));
    await pressButton(tester, 'Esquecer');
    await h.route(tester);
    expect(find.text('Esquecer "Casa"?'), findsOneWidget);
    await confirmWith(tester, 'Esquecer');
    await h.route(tester);
    await h.settle(tester);
    expect(h.telescope.commands.last, 'net:forget:Casa');
    expect(find.textContaining('ainda não guarda nenhuma rede de casa'), findsOneWidget);
    await h.close(tester);
  });

  testWidgets('rede: rede de casa aberta ou já guardada entra sem pedir senha', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await openTab(tester, 'Aparelho');
    await pressText(tester, 'Ligação');
    await h.route(tester);
    await h.settle(tester);
    await reveal(tester, find.text('Entrar no WiFi de casa'));
    await pressButton(tester, 'Entrar no WiFi de casa');
    await h.route(tester);
    await h.settle(tester);
    await pressText(tester, 'Visitantes');
    await h.route(tester);
    expect(find.text('Senha de "Visitantes"'), findsNothing);
    await pressButton(tester, 'Trocar');
    await wait(tester, 3);
    await h.settle(tester);
    expect(find.text('O telescópio entrou em "Visitantes"'), findsOneWidget);
    await h.close(tester);
  });

  testWidgets('rede: mudar a senha do WiFi do telescópio, e o app guarda a nova', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await openTab(tester, 'Aparelho');
    await pressText(tester, 'Ligação');
    await h.route(tester);
    await h.settle(tester);
    await pressButton(tester, 'Mudar a senha');
    await h.route(tester);
    expect(
      tester.widget<AppButton>(find.widgetWithText(AppButton, 'Salvar a senha')).onPressed,
      isNull,
      reason: 'senha de WiFi tem de 8 a 63 caracteres',
    );
    await tester.enterText(find.byType(TextField), 'nova-senha-123');
    await tester.pump();
    await pressButton(tester, 'Salvar a senha');
    await h.route(tester);
    await h.settle(tester);
    expect(find.text('Senha do WiFi do telescópio trocada.'), findsOneWidget);
    expect(h.telescope.commands.last, 'net:hotspot');
    expect(h.store.device!.wifiPsk, 'nova-senha-123', reason: 'é com ela que o app o reencontra no campo');
    await h.close(tester);
  });

  testWidgets('rede: quem não é dono vê como o telescópio está ligado, e não troca', (tester) async {
    final h = Harness(device: savedDevice())..telescope.owner = false;
    await h.pump(tester);
    await openTab(tester, 'Aparelho');
    await pressText(tester, 'Ligação');
    await h.route(tester);
    await h.settle(tester);
    expect(find.text('Só o dono troca a rede do telescópio'), findsOneWidget);
    expect(find.text(FakeTelescope.hotspotSsid), findsOneWidget);
    expect(find.bySemanticsLabel('Mostrar a senha'), findsNothing);
    expect(find.text('Mudar a senha'), findsNothing);
    expect(find.text('Entrar no WiFi de casa'), findsNothing);
    expect(find.text('Passar para o WiFi de casa'), findsNothing);
    await h.close(tester);
  });

  testWidgets('trocar para o WiFi do telescópio derruba a ligação: o app entra no WiFi dele e o reencontra', (
    tester,
  ) async {
    final wifi = FakeWifi();
    final h = Harness(device: savedDevice(), wifi: wifi);
    await h.pump(tester);
    // em casa, com a rede guardada
    await h.telescope.joinNetwork('Casa', psk: 'senha-de-casa');
    await wait(tester, 2);
    wifi.onJoin = () => h.telescope.offline = false; // dentro do WiFi dele, ele volta a responder
    await openTab(tester, 'Aparelho');
    await pressText(tester, 'Ligação');
    await h.route(tester);
    await h.settle(tester);
    await reveal(tester, find.text('Passar para o WiFi do telescópio'));
    await pressButton(tester, 'Passar para o WiFi do telescópio');
    await h.route(tester);
    await pressButton(tester, 'Trocar');
    await tester.pump();
    // o telescópio aceitou e sumiu da rede de casa
    await h.loseSignal(tester);
    await wait(tester, 4);
    expect(find.textContaining('reconectando'), findsOneWidget);
    expect(find.textContaining('está trocando de rede'), findsOneWidget);
    expect(wifi.joined, isEmpty, reason: 'espera o prazo que o telescópio deu antes de procurar em outro lugar');
    // passou o prazo (8 s): o app entra no WiFi dele; na consulta seguinte, a troca aparece feita
    await wait(tester, 7);
    await h.settle(tester);
    expect(wifi.joined, [FakeTelescope.hotspotSsid], reason: 'o app pediu ao Android o WiFi do telescópio');
    expect(wifi.lastPsk, 'ceu-estrelado');
    expect(find.text('O telescópio está no WiFi próprio.'), findsOneWidget);
    expect(find.text('conectado'), findsOneWidget);
    await h.close(tester);
  });

  testWidgets('trocar de rede com o telescópio mudo: o prazo corre pelo relógio, não pelas perguntas', (tester) async {
    final wifi = FakeWifi(WifiJoin.unavailable); // o WiFi dele também não aparece
    final h = Harness(device: savedDevice(), wifi: wifi);
    await h.pump(tester);
    await h.telescope.joinNetwork('Casa', psk: 'senha-de-casa');
    await wait(tester, 2);
    await openTab(tester, 'Aparelho');
    await pressText(tester, 'Ligação');
    await h.route(tester);
    await h.settle(tester);
    await reveal(tester, find.text('Passar para o WiFi do telescópio'));
    await pressButton(tester, 'Passar para o WiFi do telescópio');
    await h.route(tester);
    await pressButton(tester, 'Trocar');
    await tester.pump();
    // sumiu, e cada pergunta fica dez segundos sem resposta
    h.telescope.latency = const Duration(seconds: 10);
    await h.loseSignal(tester);
    await wait(tester, 14);
    expect(wifi.joined, hasLength(1), reason: 'passado o prazo que ele deu (8 s), o app já foi procurar no WiFi dele');
    expect(find.textContaining('está trocando de rede'), findsOneWidget);
    // o prazo todo (os 8 s dele mais 40 de paciência) acaba aos 48 s; a pergunta em curso, aos 50
    await wait(tester, 38);
    expect(
      find.textContaining('Não reencontrei o telescópio'),
      findsOneWidget,
      reason: 'em menos de um minuto, não em vários',
    );
    expect(find.textContaining('está trocando de rede'), findsNothing);
    h.telescope
      ..latency = null
      ..offline = false;
    await wait(tester, 12); // as perguntas que ainda estavam no ar terminam
    await h.settle(tester);
    await h.close(tester);
  });

  testWidgets('primeiro uso: quem pareou pelo WiFi do telescópio recebe o convite do WiFi de casa, uma vez', (
    tester,
  ) async {
    final h = Harness(device: savedDevice(), prefs: {'offer.home_wifi': true});
    await h.pump(tester);
    expect(find.text('Quer pôr o telescópio no WiFi de casa?'), findsOneWidget);
    await pressButton(tester, 'Configurar');
    await h.route(tester);
    await h.settle(tester);
    expect(find.textContaining('redes que o TELESCÓPIO enxerga'), findsOneWidget);
    expect(h.container.read(prefsProvider).offerHomeWifi, isFalse, reason: 'viu o convite: não aparece de novo');
    await pressButton(tester, 'Agora não'); // pular
    await h.route(tester);
    await openTab(tester, 'Observar');
    await h.settle(tester);
    expect(find.text('Quer pôr o telescópio no WiFi de casa?'), findsNothing);
    await h.close(tester);
  });

  // ------------------------------------------------------------------ D8: atualizações
  testWidgets('atualizações: procurar, instalar, acompanhar e ver a versão nova', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await openTab(tester, 'Aparelho');
    await reveal(tester, find.text('Atualizações'));
    await pressText(tester, 'Atualizações');
    await h.route(tester);
    await h.settle(tester);
    expect(find.text('1.0.0 (API 1)'), findsOneWidget);
    await pressButton(tester, 'Procurar atualização');
    await tester.pump();
    expect(find.text('Procurando versão nova.'), findsOneWidget);
    await wait(tester, 2);
    expect(find.text('Versão 1.1.0 disponível'), findsOneWidget);
    expect(find.text('Autofoco mais rápido'), findsOneWidget);
    await h.shot(tester, 'd8_versao_nova');

    await pressButton(tester, 'Instalar a versão 1.1.0');
    await h.route(tester);
    expect(find.textContaining('Não o desligue no meio'), findsOneWidget);
    expect(h.telescope.commands, ['update:check'], reason: 'antes de confirmar, nada é instalado');
    await pressButton(tester, 'Instalar');
    await h.route(tester);
    expect(h.telescope.commands.last, 'update:install');
    expect(find.textContaining('Não desligue o telescópio'), findsOneWidget);
    expect(find.text('Instalar a versão 1.1.0'), findsNothing, reason: 'instalando, não há o que instalar');
    await h.shot(tester, 'd8_instalando');
    await wait(tester, 4);
    await h.settle(tester);
    expect(find.text('Telescópio atualizado para a versão 1.1.0'), findsOneWidget);
    expect(find.text('1.1.0 (API 1)'), findsOneWidget);
    await h.close(tester);
  });

  testWidgets('atualização que falha: o telescópio continua na versão anterior, e a tela diz', (tester) async {
    final h = Harness(device: savedDevice())..telescope.updateFails = true;
    await h.pump(tester);
    await openTab(tester, 'Aparelho');
    await reveal(tester, find.text('Atualizações'));
    await pressText(tester, 'Atualizações');
    await h.route(tester);
    await h.settle(tester);
    await pressButton(tester, 'Procurar atualização');
    await wait(tester, 2);
    await pressButton(tester, 'Instalar a versão 1.1.0');
    await h.route(tester);
    await pressButton(tester, 'Instalar');
    await wait(tester, 4);
    await h.settle(tester);
    expect(find.text('A instalação falhou'), findsOneWidget);
    expect(find.text('O telescópio continua na versão 1.0.0, funcionando como antes.'), findsOneWidget);
    expect(find.text('Tentar instalar de novo'), findsOneWidget);
    expect(find.text('1.0.0 (API 1)'), findsOneWidget);
    await h.shot(tester, 'd8_falhou');
    await h.close(tester);
  });

  testWidgets('atualizações: com trabalho em andamento não instala; sem versão nova, diz que está em dia', (
    tester,
  ) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await openTab(tester, 'Aparelho');
    await reveal(tester, find.text('Atualizações'));
    await pressText(tester, 'Atualizações');
    await h.route(tester);
    await h.settle(tester);
    await pressButton(tester, 'Procurar atualização');
    await wait(tester, 2);
    await h.telescope.stack(commandId: 'x');
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('Pare o trabalho em andamento antes de atualizar.'), findsOneWidget);
    expect(tester.widget<AppButton>(find.widgetWithText(AppButton, 'Instalar a versão 1.1.0')).onPressed, isNull);
    await h.telescope.stop(commandId: 'y');
    await h.close(tester);

    // um telescópio que já está na última
    final current = Harness(device: savedDevice());
    await current.pump(tester);
    await current.telescope.checkUpdate();
    await wait(tester, 2);
    await current.telescope.installUpdate();
    await wait(tester, 4);
    await openTab(tester, 'Aparelho');
    await reveal(tester, find.text('Atualizações'));
    await pressText(tester, 'Atualizações');
    await current.route(tester);
    await current.settle(tester);
    expect(find.text('1.1.0 (API 1)'), findsOneWidget);
    await pressButton(tester, 'Procurar atualização');
    await wait(tester, 2);
    expect(find.text('o telescópio está na versão mais nova'), findsOneWidget);
    expect(find.text('O telescópio já está na versão mais nova.'), findsOneWidget, reason: 'e o aviso passageiro');
    await current.close(tester);
  });

  // ------------------------------------------------------------- alinhamento polar
  testWidgets('alinhamento polar: medir, ajustar pelo que a medida pediu, medir de novo até alinhar', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await openTab(tester, 'Aparelho');
    await pressText(tester, 'Montagem');
    await h.route(tester);
    await reveal(tester, find.text('Alinhamento polar'));
    expect(find.textContaining('medir quanto o eixo da montagem erra o polo'), findsOneWidget);
    await pressText(tester, 'Alinhamento polar');
    await h.route(tester);
    expect(find.text('montagem simulada'), findsOneWidget, reason: 'o que é simulado está escrito');

    await pressButton(tester, 'Medir o alinhamento');
    await h.route(tester);
    expect(find.text('O caminho está livre? Cabos, tripé e pessoas longe do tubo.'), findsOneWidget);
    await pressButton(tester, 'Mover');
    await h.route(tester);
    expect(h.telescope.commands, ['polar']);
    expect(find.textContaining('Medindo: campo'), findsOneWidget);
    expect(find.text('PARAR'), findsOneWidget, reason: 'a montagem está se movendo');
    await h.shot(tester, 'polar_medindo');
    await wait(tester, 3);
    await h.settle(tester);

    expect(find.text("1° 04'"), findsOneWidget);
    expect(find.text('falta ajustar'), findsOneWidget);
    expect(find.text('o eixo está alto demais'), findsOneWidget);
    expect(find.text("Baixe 38'"), findsOneWidget);
    expect(find.text('o eixo está a oeste do polo'), findsOneWidget);
    expect(find.text("Gire para leste 52'"), findsOneWidget);
    expect(find.text('PARAR'), findsNothing);
    await h.shot(tester, 'polar_medido');

    await reveal(tester, find.text('Girar o que a medida pediu'));
    await pressButton(tester, 'Girar o que a medida pediu');
    await h.settle(tester);
    expect(h.telescope.commands.last, 'polar:adjust:-38.0:52.0');
    await tester.drag(find.byType(Scrollable).last, const Offset(0, 600));
    await tester.pump();
    await reveal(tester, find.text('Você mexeu nos parafusos'));
    expect(
      tester
          .widget<AppButton>(find.widgetWithText(AppButton, 'Girar o que a medida pediu', skipOffstage: false))
          .onPressed,
      isNull,
      reason: 'a medida velha não serve para girar de novo',
    );

    await reveal(tester, find.text('Medir de novo'));
    await pressButton(tester, 'Medir de novo');
    await wait(tester, 4);
    await h.settle(tester);
    await tester.drag(find.byType(Scrollable).last, const Offset(0, 600));
    await tester.pump();
    expect(find.text("3,2'"), findsOneWidget, reason: 'a mão nunca gira exatamente o pedido');
    expect(find.text("Baixe 1,9'"), findsOneWidget);
    expect(find.text('Você mexeu nos parafusos'), findsNothing);

    await reveal(tester, find.text('Girar o que a medida pediu'));
    await pressButton(tester, 'Girar o que a medida pediu');
    await h.settle(tester);
    await tester.drag(find.byType(Scrollable).last, const Offset(0, 600));
    await tester.pump();
    await reveal(tester, find.text('Medir de novo'));
    await pressButton(tester, 'Medir de novo');
    await wait(tester, 4);
    await h.settle(tester);
    await tester.drag(find.byType(Scrollable).last, const Offset(0, 600));
    await tester.pump();
    expect(find.text('alinhado: dá para fotografar'), findsOneWidget);
    expect(find.text('no lugar'), findsNWidgets(2));
    await h.shot(tester, 'polar_alinhado');

    // a tela da montagem passa a mostrar a última medida
    await tester.tap(find.bySemanticsLabel('Voltar'));
    await h.route(tester);
    await reveal(tester, find.text('Alinhamento polar'));
    expect(find.textContaining('alinhada: o eixo erra o polo por'), findsOneWidget);
    await h.close(tester);
  });

  testWidgets('alinhamento polar: medida que não fecha, e a montagem de verdade', (tester) async {
    final h = Harness(device: savedDevice())..telescope.polarFails = true;
    await h.pump(tester);
    await openTab(tester, 'Aparelho');
    await pressText(tester, 'Montagem');
    await h.route(tester);
    await reveal(tester, find.text('Alinhamento polar'));
    await pressText(tester, 'Alinhamento polar');
    await h.route(tester);
    await pressButton(tester, 'Medir o alinhamento');
    await h.route(tester);
    await pressButton(tester, 'Mover');
    await wait(tester, 4);
    await h.settle(tester);
    expect(find.text('Não deu para medir'), findsOneWidget);
    expect(find.textContaining('os três campos ficaram juntos demais'), findsOneWidget);
    expect(find.text('Medir de novo'), findsOneWidget);

    h.telescope.pretendRealMount();
    await h.settle(tester);
    expect(find.text('Ainda não existe nesta montagem'), findsOneWidget);
    expect(find.text('Medir de novo'), findsNothing);
    expect(find.text('montagem simulada'), findsNothing);
    await h.close(tester);
  });

  // ------------------------------------------------------------- captura planetária
  testWidgets('Lua e planetas: fotografar grava muitos quadros e fica com os mais nítidos', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await openTab(tester, 'Planejar');
    await h.settle(tester);
    await pressText(tester, 'Lua, planetas e Sol');
    await h.route(tester);
    await h.settle(tester);
    await reveal(tester, buttonIn('Saturno', 'Fotografar'));
    await tester.ensureVisible(buttonIn('Saturno', 'Fotografar'));
    await tester.pump();
    await tester.tap(buttonIn('Saturno', 'Fotografar'));
    await h.route(tester);
    expect(find.text('Fotografar Saturno'), findsOneWidget);
    expect(find.text('Ficam os 45 quadros mais nítidos de 300.'), findsOneWidget);
    await pressText(tester, '600');
    await pressText(tester, '10%');
    expect(find.text('Ficam os 60 quadros mais nítidos de 600.'), findsOneWidget);
    await h.shot(tester, 'p5_fotografar');
    await pressButton(tester, 'Gravar');
    await h.route(tester);
    expect(find.text('A montagem vai se mover'), findsOneWidget, reason: 'vai apontar antes de gravar');
    await pressButton(tester, 'Mover');
    await h.route(tester);
    expect(h.telescope.commands, ['planetary:saturn:600:10']);
    expect(find.text('Saturno'), findsOneWidget, reason: 'a tela Observar mostra o que está sendo fotografado');

    await wait(tester, 3); // apontou e centralizou; já está gravando
    expect(find.textContaining('de 600 quadros'), findsOneWidget);
    expect(find.textContaining('mais nítidos até agora (10% do total)'), findsOneWidget);
    expect(find.text('Gravar os quadros'), findsOneWidget, reason: 'a etapa em curso');
    expect(find.text('PARAR'), findsOneWidget);
    await h.shot(tester, 'o_captura_planetaria');
    await wait(tester, 4);
    await h.settle(tester);
    expect(find.text('Captura pronta: 60 de 600 quadros'), findsOneWidget);
    expect(find.text('60 quadros aproveitados'), findsOneWidget);
    expect(find.text('PARAR'), findsNothing);
    await h.shot(tester, 'o_captura_pronta');

    await pressButton(tester, 'Gravar de novo');
    await h.settle(tester);
    expect(h.telescope.commands.last, 'planetary:saturn:600:10:here', reason: 'o alvo já está no quadro: não aponta');
    await pressButton(tester, 'PARAR');
    await h.settle(tester);
    await h.close(tester);
  });

  testWidgets('Lua e planetas: sem "apontar antes" a montagem não se move, e nada é perguntado', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await openTab(tester, 'Planejar');
    await h.settle(tester);
    await pressText(tester, 'Lua, planetas e Sol');
    await h.route(tester);
    await h.settle(tester);
    await reveal(tester, buttonIn('Saturno', 'Fotografar'));
    await tester.ensureVisible(buttonIn('Saturno', 'Fotografar'));
    await tester.pump();
    await tester.tap(buttonIn('Saturno', 'Fotografar'));
    await h.route(tester);
    await pressText(tester, 'Apontar antes');
    await pressButton(tester, 'Gravar');
    await h.route(tester);
    expect(find.text('A montagem vai se mover'), findsNothing);
    expect(h.telescope.commands, ['planetary:saturn:300:15:here']);
    expect(find.textContaining('de 300 quadros'), findsOneWidget);
    await pressButton(tester, 'PARAR');
    await h.settle(tester);
    await h.close(tester);
  });

  // ------------------------------------------------------- avisos com a tela apagada
  testWidgets('avisos: aviso fixo enquanto o telescópio trabalha, e o desfecho quando ninguém olha', (tester) async {
    addTearDown(() => tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed));
    final h = Harness(device: savedDevice(), prefs: {'notify': true})..telescope.gotoFails = true;
    await h.pump(tester);
    expect(h.alerts.ongoingNow, isNull, reason: 'parado, não há o que acompanhar');
    await pressButton(tester, 'Observar este alvo');
    await tester.pump(const Duration(milliseconds: 500));
    expect(h.alerts.ongoingNow!.$2, startsWith('Apontando'));

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused); // a tela apagou
    await wait(tester, 3);
    expect(h.alerts.notices, hasLength(1));
    expect(h.alerts.notices.single.title, startsWith('Não deu certo'));
    expect(h.alerts.notices.single.bad, isTrue);
    expect(h.alerts.ongoingNow, isNotNull, reason: 'o aviso fixo não sai no mesmo instante em que subiu');
    await wait(tester, 3);
    expect(h.alerts.ongoingNow, isNull, reason: 'acabou o trabalho: o aviso fixo sai');
    expect(h.alerts.ongoingLog.toSet().length, greaterThan(1), reason: 'o aviso fixo acompanhou as etapas');
    await h.close(tester);
  });

  testWidgets('avisos: com o app na frente a tela já conta, e o sinal que cai no meio do trabalho avisa', (
    tester,
  ) async {
    addTearDown(() => tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed));
    final h = Harness(device: savedDevice(), prefs: {'notify': true});
    await h.pump(tester);
    await pressButton(tester, 'Observar este alvo');
    await wait(tester, 3); // apontou e já empilha
    expect(h.alerts.notices, isEmpty, reason: 'com o app na frente, nenhum aviso');
    expect(h.alerts.ongoingNow!.$2, startsWith('Empilhando'));

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await h.loseSignal(tester);
    expect(h.alerts.notices.single.title, 'Sem sinal do telescópio');
    expect(
      h.alerts.notices.single.slot,
      AppNotice.signalSlot,
      reason: 'um lugar só: WiFi oscilando não empilha avisos',
    );
    expect(h.alerts.ongoingNow!.$2, startsWith('Sem sinal'));
    h.telescope.offline = false;
    await wait(tester, 3);
    expect(h.alerts.ongoingNow!.$2, startsWith('Empilhando'), reason: 'voltou: o aviso fixo volta a contar');
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    await pressButton(tester, 'PARAR');
    await wait(tester, 3);
    expect(h.alerts.ongoingNow, isNull);
    expect(h.alerts.notices, hasLength(1), reason: 'o que a própria pessoa parou não vira aviso');
    await h.close(tester);
  });

  testWidgets('avisos: sem sinal por tempo demais, o app solta o celular e diz por quê', (tester) async {
    addTearDown(() => tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed));
    final h = Harness(
      device: savedDevice(),
      prefs: {'notify': true},
      noticeGiveUp: const Duration(seconds: 20), // o app espera 10 minutos; o teste, menos
    );
    await h.pump(tester);
    await pressButton(tester, 'Observar este alvo');
    await wait(tester, 3);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await h.loseSignal(tester);
    await wait(tester, 10);
    expect(h.alerts.ongoingNow, isNotNull, reason: 'ainda dentro do prazo: continua tentando');
    await wait(tester, 14);
    expect(
      h.alerts.ongoingNow,
      isNull,
      reason: 'o telescópio pode estar sem bateria: não segura o celular a noite toda',
    );
    expect(h.alerts.notices.last.title, 'O app parou de acompanhar o telescópio');
    expect(h.alerts.notices.last.slot, AppNotice.signalSlot, reason: 'substitui o "sem sinal"');

    // o sinal volta: o acompanhamento também
    h.telescope.offline = false;
    await wait(tester, 10);
    expect(h.alerts.ongoingNow!.$2, startsWith('Empilhando'));
    await h.telescope.stop(commandId: 'fim');
    await wait(tester, 3);
    await h.close(tester);
  });

  testWidgets('avisos: a câmera ao vivo não segura o celular acordado', (tester) async {
    final h = Harness(device: savedDevice(), prefs: {'notify': true});
    await h.pump(tester);
    await pressButton(tester, 'Câmera ao vivo');
    await wait(tester, 2);
    expect(find.text('PARAR'), findsOneWidget, reason: 'a câmera ao vivo está rodando');
    expect(h.alerts.ongoingNow, isNull, reason: 'ela não termina sozinha, e não há o que contar');
    expect(h.alerts.ongoingLog, isEmpty);
    await pressButton(tester, 'PARAR');
    await h.settle(tester);
    await h.close(tester);
  });

  testWidgets('avisos: desligados de fábrica; ligar pede a permissão do Android, e sem ela fica desligado', (
    tester,
  ) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await pressButton(tester, 'Observar este alvo');
    await tester.pump(const Duration(milliseconds: 500));
    expect(h.alerts.ongoingNow, isNull, reason: 'sem a preferência, o app não põe aviso nenhum');
    await pressButton(tester, 'PARAR');
    await h.settle(tester);

    await openTab(tester, 'Aparelho');
    await reveal(tester, find.text('Preferências do app'));
    await pressText(tester, 'Preferências do app');
    await h.route(tester);
    h.alerts.allowed = false;
    await pressText(tester, 'Avisar com a tela apagada');
    await h.settle(tester);
    expect(h.alerts.asked, 1);
    expect(h.container.read(prefsProvider).notify, isFalse);
    expect(find.textContaining('O Android não deixou este app mostrar avisos'), findsOneWidget);
    await tester.pump(const Duration(seconds: 5));

    h.alerts.allowed = true;
    await pressText(tester, 'Avisar com a tela apagada');
    await h.settle(tester);
    expect(h.container.read(prefsProvider).notify, isTrue);
    await h.shot(tester, 'd9_avisos');
    await pressText(tester, 'Avisar com a tela apagada');
    await h.settle(tester);
    expect(h.container.read(prefsProvider).notify, isFalse, reason: 'desligar não pede nada');
    expect(h.alerts.asked, 2);
    await h.close(tester);
  });
}
