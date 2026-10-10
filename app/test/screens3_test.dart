// As telas da fase 3 (e o que faltava da 2), contra o telescópio falso: câmera ao vivo, foco,
// montagem, câmera, plano da noite, mosaico, Lua e planetas, celulares, exportar.
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:telescope_app/app/queries.dart';
import 'package:telescope_app/core/widgets/charts.dart';
import 'package:telescope_app/core/widgets/kit.dart';
import 'package:telescope_app/domain/models.dart';

import 'harness.dart';

/// Segura um botão de segurar por [time] e solta.
Future<void> hold(WidgetTester tester, String label, Duration time) async {
  final button = find.bySemanticsLabel(label);
  await tester.ensureVisible(button);
  await tester.pump();
  final gesture = await tester.startGesture(tester.getCenter(button));
  await tester.pump(time);
  await gesture.up();
  await tester.pump();
}

/// Volta a lista ao começo (o que saiu da tela deixa de existir para o teste).
Future<void> toTop(WidgetTester tester) async {
  await tester.drag(find.byType(Scrollable).last, const Offset(0, 600));
  await tester.pump();
}

/// O botão "Apontar" do cartão deste corpo.
Finder pointAt(String body) =>
    find.descendant(of: find.widgetWithText(Panel, body), matching: find.widgetWithText(AppButton, 'Apontar'));

void main() {
  WidgetController.hitTestWarningShouldBeFatal = true;

  testWidgets('câmera ao vivo: enquadrar, focar e ajustar antes de empilhar', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await pressButton(tester, 'Câmera ao vivo');
    await tester.pump(const Duration(milliseconds: 500));
    expect(h.telescope.commands, ['preview']);
    expect(find.text('nitidez boa'), findsOneWidget);
    expect(find.text('PARAR'), findsOneWidget);
    expect(find.textContaining('Câmera simulada'), findsOneWidget, reason: 'o que não vale ainda está dito');
    await h.shot(tester, 'o3_camera_ao_vivo');

    // Q1: antes do primeiro movimento, a pergunta
    await pressButton(tester, 'Mover a montagem');
    await h.settle(tester);
    expect(find.text('A montagem vai se mover'), findsOneWidget);
    await pressButton(tester, 'Mover');
    await h.settle(tester);

    await hold(tester, 'Mover para o leste', const Duration(milliseconds: 800));
    final jogs = h.telescope.commands.where((c) => c == 'jog:E:2').length;
    expect(jogs, greaterThanOrEqualTo(2), reason: 'segurando, o comando é renovado');
    expect(h.telescope.commands.last, 'halt', reason: 'soltou, parou');

    await pressButton(tester, '+100');
    await h.settle(tester);
    expect(h.telescope.commands.last, 'focus:6400');
    await tester.tap(find.bySemanticsLabel('Mais Ganho'));
    await h.settle(tester);
    expect(find.text('130'), findsOneWidget);

    await pressButton(tester, 'Empilhar');
    await tester.pump(const Duration(milliseconds: 500));
    expect(h.telescope.commands.last, 'stack');
    await h.close(tester);
  });

  testWidgets('foco: passos à mão, autofoco com a curva, e quando não acha', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await openTab(tester, 'Aparelho');
    await pressText(tester, 'Foco');
    await h.route(tester);
    expect(find.text('6300'), findsOneWidget);
    expect(find.text('ligue a câmera'), findsOneWidget, reason: 'sem imagem não há nitidez para mostrar');
    await pressButton(tester, '+100');
    await h.settle(tester);
    expect(find.text('6400'), findsOneWidget);

    await pressButton(tester, 'Focar sozinho');
    await tester.pump(const Duration(milliseconds: 900));
    expect(find.text('PARAR'), findsOneWidget, reason: 'enquanto varre, dá para parar');
    await tester.pump(const Duration(seconds: 4));
    await tester.pump();
    expect(find.text('Foco achado na posição 6300.'), findsOneWidget);
    expect(find.byType(FocusCurve), findsOneWidget);
    expect(find.text('6300'), findsOneWidget);
    await h.shot(tester, 'o6_foco');

    h.telescope.focusFails = true;
    await pressButton(tester, 'Focar sozinho');
    await tester.pump(const Duration(seconds: 5));
    await tester.pump();
    expect(find.text('Não achei o foco'), findsOneWidget);
    expect(find.textContaining('sem estrelas para medir'), findsOneWidget);
    await h.close(tester);
  });

  testWidgets('montagem: segurar para mover, estacionar, e a montagem real só se olha', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await openTab(tester, 'Aparelho');
    await pressText(tester, 'Montagem');
    await h.route(tester);
    expect(find.text('acompanhando o céu'), findsOneWidget);

    await tester.tap(find.bySemanticsLabel('Mover para o norte'));
    await h.settle(tester);
    expect(find.text('O caminho está livre? Cabos, tripé e pessoas longe do tubo.'), findsOneWidget);
    expect(h.telescope.commands, isEmpty, reason: 'o primeiro toque só pergunta');
    await pressButton(tester, 'Mover');
    await h.settle(tester);

    await pressText(tester, 'Rápida');
    await hold(tester, 'Mover para o norte', const Duration(milliseconds: 400));
    expect(h.telescope.commands.first, 'jog:N:3');
    expect(h.telescope.commands.last, 'halt');
    await h.shot(tester, 'd2_montagem');

    await tester.tap(find.text('Rastreio').last);
    await h.settle(tester);
    expect(h.telescope.commands.last, 'tracking:off');
    await toTop(tester);
    expect(find.text('parado'), findsOneWidget);

    await pressButton(tester, 'Estacionar');
    await h.settle(tester);
    expect(h.telescope.commands.last, 'park');
    await toTop(tester);
    expect(find.text('estacionada'), findsOneWidget);
    final before = h.telescope.commands.length;
    await hold(tester, 'Mover para o norte', const Duration(milliseconds: 200));
    expect(h.telescope.commands.length, before, reason: 'estacionada, as setas não mandam nada');
    await pressButton(tester, 'Tirar do repouso');
    await h.settle(tester);
    expect(h.telescope.commands.last, 'unpark');

    h.telescope.pretendRealMount();
    await h.settle(tester);
    expect(find.text('Mover à mão pelo app ainda não existe nesta montagem'), findsOneWidget);
    expect(find.bySemanticsLabel('Mover para o norte'), findsNothing);
    expect(find.text('conectada'), findsOneWidget);
    await h.close(tester);
  });

  testWidgets('câmera: os ajustes ficam guardados, e a tela diz que ainda não valem', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await openTab(tester, 'Aparelho');
    await pressText(tester, 'Câmera');
    await h.route(tester);
    await h.settle(tester);
    expect(find.text('30 s'), findsOneWidget);
    await tester.tap(find.bySemanticsLabel('Mais Exposição'));
    await h.settle(tester);
    expect(find.text('60 s'), findsOneWidget);
    await tester.tap(find.bySemanticsLabel('Menos Ganho'));
    await h.settle(tester);
    expect(find.text('110'), findsOneWidget);
    expect(find.text('Câmera simulada'), findsOneWidget);
    expect(find.text('sem leitura'), findsOneWidget, reason: 'temperatura do sensor: não inventa número');
    await h.shot(tester, 'd4_camera');
    await h.close(tester);
  });

  testWidgets('plano da noite: montar a fila, reordenar, rodar, pular e fechar', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await openTab(tester, 'Planejar');
    await h.settle(tester);
    expect(find.text('O plano está vazio'), findsOneWidget);
    await h.shot(tester, 'p1_plano_vazio');

    // um alvo entra pelo Atlas...
    await pressButton(tester, 'Escolher no Atlas');
    await h.route(tester);
    await tester.enterText(find.byType(TextField), 'escultor');
    await tester.pump(const Duration(milliseconds: 400));
    await h.settle(tester);
    await tester.tap(find.textContaining('Escultor'));
    await h.route(tester);
    await h.settle(tester);
    await tester.scrollUntilVisible(find.text('Pôr no plano'), 300, scrollable: find.byType(Scrollable).last);
    await pressButton(tester, 'Pôr no plano');
    await h.settle(tester);
    expect(find.text('NGC253 entrou no plano da noite.'), findsOneWidget);
    await tester.pump(const Duration(seconds: 5)); // o aviso sai sozinho
    // ...e os outros dois chegam direto (um deles não sobe nesta noite)
    await h.telescope.savePlan([
      ...(await h.telescope.plan()).items,
      const PlanItem(target: 'M13'),
      const PlanItem(target: 'M42', frames: 20),
    ]);
    h.container.invalidate(planProvider);

    await openTab(tester, 'Planejar');
    await h.settle(tester);
    expect(find.textContaining('Galáxia do Escultor'), findsOneWidget);
    expect(find.textContaining('40 fotos de 30 s'), findsNWidgets(2));
    expect(find.text('não sobe o bastante nesta noite'), findsOneWidget, reason: 'M13 já se pôs');
    expect(find.textContaining('sobram'), findsOneWidget);
    await h.shot(tester, 'p1_plano');

    await tester.tap(find.bySemanticsLabel('Subir M42 na fila'));
    await h.settle(tester);
    expect([for (final i in (await h.telescope.plan()).items) i.target], ['NGC253', 'M42', 'M13']);

    await pressButton(tester, 'Começar a noite');
    await h.settle(tester);
    await pressButton(tester, 'Mover');
    await tester.pump(const Duration(milliseconds: 900));
    expect(h.telescope.commands.last, 'night');
    expect(find.text('Noite em andamento'), findsOneWidget);
    expect(find.text('PARAR'), findsOneWidget, reason: 'um PARAR só: o flutuante, como em toda tela');
    expect(find.text('agora'), findsOneWidget);
    expect(find.text('na fila'), findsNWidgets(2));
    await h.shot(tester, 'p3_noite');

    await pressButton(tester, 'Pular este alvo');
    await tester.pump(const Duration(milliseconds: 500));
    expect(h.telescope.commands.last, 'skip');
    expect(find.text('pulado por você'), findsOneWidget);

    await tester.pump(const Duration(seconds: 5)); // o M42 termina e o M13 é pulado
    await tester.pump();
    expect(find.text('A noite terminou'), findsOneWidget);
    expect(find.text('pulado: não sobe nesta noite'), findsOneWidget);
    expect(find.text('feito'), findsOneWidget);
    expect(find.text('1 de 3 alvos fotografados.'), findsOneWidget);
    await pressButton(tester, 'Fechar');
    await h.settle(tester);
    expect(find.text('Plano da noite'), findsOneWidget);
    await h.close(tester);
  });

  testWidgets('item do plano e mosaico: mudar as fotos, virar grade, voltar ao plano', (tester) async {
    final h = Harness(device: savedDevice());
    await h.telescope.savePlan(const [PlanItem(target: 'M31')]);
    await h.pump(tester);
    await openTab(tester, 'Planejar');
    await h.settle(tester);
    await tester.tap(find.textContaining('Andrômeda'));
    await h.route(tester);
    expect(find.text('Item do plano'), findsOneWidget);
    await tester.tap(find.bySemanticsLabel('Mais Fotos'));
    await tester.pump();
    expect(find.text('50'), findsOneWidget);
    await pressButton(tester, 'Salvar');
    await h.route(tester);
    expect((await h.telescope.plan()).items.single.frames, 50);

    await tester.tap(find.textContaining('Andrômeda'));
    await h.route(tester);
    await pressButton(tester, 'Transformar em mosaico');
    await h.route(tester);
    await h.settle(tester);
    expect(find.text('Mosaico de M31'), findsOneWidget);
    expect(find.textContaining('4 painéis'), findsOneWidget);
    await tester.tap(find.bySemanticsLabel('Mais Colunas'));
    await h.settle(tester);
    expect(find.textContaining('6 painéis'), findsOneWidget);
    await h.shot(tester, 'p4_mosaico');
    await tester.tap(find.bySemanticsLabel('Menos Linhas'));
    await h.settle(tester);
    await tester.tap(find.bySemanticsLabel('Menos Colunas'));
    await h.settle(tester);
    await tester.tap(find.bySemanticsLabel('Menos Colunas'));
    await h.settle(tester);
    expect(find.textContaining('1 painel'), findsOneWidget);
    expect(find.textContaining('transborda a grade'), findsOneWidget, reason: "Andrômeda (178') não cabe num quadro");
    await tester.tap(find.bySemanticsLabel('Mais Colunas'));
    await h.settle(tester);
    await pressButton(tester, 'Usar esta grade');
    await h.route(tester);
    await h.settle(tester);
    final item = (await h.telescope.plan()).items.single;
    expect((item.rows, item.cols, item.frames), (1, 2, 50), reason: 'a grade muda; as fotos ficam');
    expect(find.textContaining('mosaico 1×2'), findsOneWidget);
    await h.close(tester);
  });

  testWidgets('Lua, planetas e Sol: aponta para o que está no céu; o Sol pede o filtro', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await openTab(tester, 'Planejar');
    await h.settle(tester);
    await pressText(tester, 'Lua, planetas e Sol');
    await h.route(tester);
    await h.settle(tester);
    expect(find.textContaining('nova'), findsOneWidget, reason: 'a Lua de 9 de outubro de 2026');
    await h.shot(tester, 'p5_lua_e_planetas');
    // o Sol é o último da lista: rola até ele
    await tester.scrollUntilVisible(find.text('Sol'), 200, scrollable: find.byType(Scrollable).last);
    expect(tester.widget<AppButton>(pointAt('Sol')).onPressed, isNull, reason: 'de noite o Sol está embaixo');
    expect(
      find.descendant(of: find.widgetWithText(Panel, 'Sol'), matching: find.widgetWithText(AppButton, 'Fotografar')),
      findsNothing,
      reason: 'o Sol não entra na captura planetária',
    );

    await tester.scrollUntilVisible(pointAt('Saturno'), -200, scrollable: find.byType(Scrollable).last);
    await tester.ensureVisible(pointAt('Saturno'));
    await tester.pump();
    await tester.tap(pointAt('Saturno'));
    await h.settle(tester);
    await pressButton(tester, 'Mover');
    await h.route(tester);
    expect(h.telescope.commands, ['body:saturn']);
    expect(find.text('Saturno'), findsOneWidget, reason: 'a tela Observar mostra para onde vai');
    await h.close(tester);
  });

  testWidgets('satélite: o rastreio começa daqui e aparece em Observar', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await openTab(tester, 'Planejar');
    await h.settle(tester);
    await pressText(tester, 'Lua, planetas e Sol');
    await h.route(tester);
    await h.settle(tester);
    await tester.scrollUntilVisible(find.text('Rastrear'), 300, scrollable: find.byType(Scrollable).last);
    await pressButton(tester, 'Rastrear');
    await h.settle(tester);
    await pressButton(tester, 'Mover');
    await h.route(tester);
    await tester.pump(const Duration(milliseconds: 900));
    expect(h.telescope.commands, ['tracking']);
    expect(find.text('Rastreando'), findsOneWidget);
    expect(find.text('Rastrear'), findsOneWidget, reason: 'a etapa em curso');
    expect(find.text('PARAR'), findsOneWidget);
    await h.close(tester);
  });

  testWidgets('Sol: sem confirmar o filtro, nada se move', (tester) async {
    // o mesmo instante, visto de Tóquio: lá são 10h30 da manhã
    final h = Harness(device: savedDevice());
    h.telescope
      ..lat = 35.7
      ..lon = 139.7;
    await h.pump(tester);
    await openTab(tester, 'Planejar');
    await h.settle(tester);
    await pressText(tester, 'Lua, planetas e Sol');
    await h.route(tester);
    await h.settle(tester);
    await tester.scrollUntilVisible(find.text('Sol'), 200, scrollable: find.byType(Scrollable).last);
    await tester.ensureVisible(pointAt('Sol'));
    await tester.pump();
    await tester.tap(pointAt('Sol'));
    await h.settle(tester);
    expect(find.text('O filtro solar está na frente?'), findsOneWidget);
    await pressButton(tester, 'Cancelar');
    await h.settle(tester);
    expect(h.telescope.commands, isEmpty);

    await tester.tap(pointAt('Sol'));
    await h.settle(tester);
    await pressButton(tester, 'Sim, está');
    await h.settle(tester);
    await pressButton(tester, 'Mover');
    await h.route(tester);
    expect(h.telescope.commands, ['body:sun']);
    await h.close(tester);
  });

  testWidgets('celulares pareados: convidar com um papel, mudar o papel, revogar', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await openTab(tester, 'Aparelho');
    await pressText(tester, 'Celulares pareados');
    await h.route(tester);
    await h.settle(tester);
    expect(find.text('Este celular (este celular)'), findsOneWidget);
    expect(find.textContaining('Dono'), findsOneWidget);

    // (h.route: as folhas e os diálogos sobem e descem animados; tocar no meio erra o alvo)
    await pressButton(tester, 'Convidar outro celular');
    await h.route(tester);
    await pressText(tester, 'Visitante');
    await h.route(tester);
    expect(find.text('Convite de visitante'), findsOneWidget);
    expect(find.byType(SvgPicture), findsWidgets);
    expect(find.textContaining('tele://pair'), findsOneWidget, reason: 'o código também vai escrito');
    await h.shot(tester, 'd6_convite');
    await pressButton(tester, 'Fechar');
    await h.route(tester);
    expect(h.telescope.commands, ['invite:viewer']);
    expect(find.text('Celular convidado'), findsOneWidget);

    await pressText(tester, 'Celular convidado');
    await h.route(tester);
    await pressText(tester, 'Operador');
    await h.route(tester);
    expect(h.telescope.commands.last, startsWith('role:'));
    expect(find.textContaining('Operador'), findsOneWidget);

    await pressText(tester, 'Celular convidado');
    await h.route(tester);
    await pressButton(tester, 'Revogar');
    await h.route(tester);
    expect(find.text('Revogar Celular convidado?'), findsOneWidget);
    await pressButton(tester, 'Revogar');
    await h.route(tester);
    expect(find.text('Celular convidado'), findsNothing);

    // o próprio celular: duas perguntas antes de trancar a porta por fora
    await pressText(tester, 'Este celular (este celular)');
    await h.route(tester);
    await pressButton(tester, 'Revogar este celular');
    await h.route(tester);
    await pressButton(tester, 'Revogar');
    await h.route(tester);
    expect(find.text('Tem certeza?'), findsOneWidget);
    await pressButton(tester, 'Cancelar');
    await h.route(tester);
    expect(h.telescope.commands.where((c) => c == 'revoke:c-demo'), isEmpty);
    await h.close(tester);
  });

  testWidgets('nome, rede, atualizações e ajuda', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await openTab(tester, 'Aparelho');
    await tester.tap(find.bySemanticsLabel('Mudar o nome do telescópio'));
    await h.route(tester);
    await tester.enterText(find.byType(TextField), 'Tucana do quintal');
    await pressButton(tester, 'Salvar');
    await h.route(tester);
    expect(h.telescope.commands, ['rename:Tucana do quintal']);
    expect(find.text('Tucana do quintal'), findsWidgets, reason: 'o nome novo aparece no topo');
    expect(find.text('O telescópio agora se chama Tucana do quintal.'), findsOneWidget);
    await tester.pump(const Duration(seconds: 5)); // o aviso sai sozinho

    // o telescópio de verdade, hoje: ainda não troca de rede nem se atualiza pelo app
    h.telescope
      ..networkEnabled = false
      ..updatesEnabled = false;
    await pressText(tester, 'Ligação');
    await h.route(tester);
    await h.settle(tester);
    expect(find.text('Trocar de rede pelo app ainda não está habilitado'), findsOneWidget);
    expect(find.text('Entrar no WiFi de casa'), findsNothing);
    expect(find.text('192.168.3.221:8443'), findsOneWidget);
    await tester.tap(find.bySemanticsLabel('Voltar'));
    await h.route(tester);

    await pressText(tester, 'Atualizações');
    await h.route(tester);
    await h.settle(tester);
    expect(find.text('Atualizar pelo app ainda não existe'), findsOneWidget);
    expect(find.text('Procurar atualização'), findsNothing);
    expect(find.text('ainda não lido'), findsOneWidget, reason: 'o firmware da montagem');
    await tester.tap(find.bySemanticsLabel('Voltar'));
    await h.route(tester);

    await pressText(tester, 'Ajuda e sobre');
    await h.route(tester);
    expect(find.text('UMA NOITE, PASSO A PASSO'), findsOneWidget);
    expect(find.text('Empilhar'), findsOneWidget);
    await h.shot(tester, 'd10_ajuda');
    await h.close(tester);
  });

  testWidgets('galeria: exportar entrega o arquivo ao celular; apagar pergunta antes', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await openTab(tester, 'Galeria');
    await h.settle(tester);
    await pressText(tester, 'M8 Lagoa');
    await h.route(tester);
    await h.settle(tester);
    await pressButton(tester, 'Exportar');
    await h.route(tester);
    expect(find.text('Tela (2000 px)'), findsOneWidget);
    await pressText(tester, 'TIFF 16 bits');
    await pressButton(tester, 'Salvar ou compartilhar');
    await h.settle(tester);
    final (name, mime, bytes) = h.sharer.shared.single;
    expect((name, mime), ('demo-m8.tif', 'image/tiff'));
    expect(bytes, greaterThan(1000));
    expect(find.textContaining('Entregue ao Android'), findsOneWidget);
    await pressText(tester, 'FITS');
    await tester.pump();
    expect(find.text('Tela (2000 px)'), findsNothing, reason: 'o FITS vai como está: não tem tamanho para escolher');
    await h.shot(tester, 'g5_exportar');
    await tester.tap(find.bySemanticsLabel('Voltar'));
    await h.route(tester);
    await h.settle(tester);

    await pressButton(tester, 'Apagar');
    await h.settle(tester);
    expect(find.text('Apagar M8 Lagoa?'), findsOneWidget);
    await pressButton(tester, 'Manter');
    await h.settle(tester);
    expect(h.telescope.commands.where((c) => c.startsWith('delete')), isEmpty);
    await pressButton(tester, 'Apagar');
    await h.route(tester);
    // agora há dois "Apagar": o da página, atrás, e o da pergunta, na frente
    await tester.tap(find.widgetWithText(AppButton, 'Apagar').last);
    await h.route(tester);
    await h.settle(tester);
    expect(h.telescope.commands.last, 'delete:demo-m8');
    expect(find.text('M8 Lagoa'), findsNothing);
    expect(find.text('M51 Redemoinho'), findsOneWidget);
    await h.close(tester);
  });

  testWidgets('estúdio: "mais ajustes" abre os controles do ofício e volta ao preset', (tester) async {
    final h = Harness(device: savedDevice());
    await h.pump(tester);
    await openTab(tester, 'Galeria');
    await h.settle(tester);
    await pressText(tester, 'M8 Lagoa');
    await h.route(tester);
    await h.settle(tester);
    await pressButton(tester, 'Abrir no estúdio');
    await h.route(tester);
    await h.settle(tester);
    expect(find.text('Pretos'), findsNothing);
    await pressButton(tester, 'Mais ajustes');
    await h.settle(tester);
    expect(find.text('Pretos'), findsOneWidget);
    expect(find.text('Reduzir estrelas'), findsOneWidget);
    await h.shot(tester, 'g4_mais_ajustes');
    await tester.scrollUntilVisible(
      find.text('Tirar o gradiente do fundo'),
      200,
      scrollable: find.byType(Scrollable).last,
    );
    expect(find.text('Voltar ao preset'), findsNothing);
    await tester.tap(find.text('Tirar o gradiente do fundo'));
    await h.settle(tester);
    expect(find.text('Voltar ao preset'), findsOneWidget, reason: 'mexeu, pode desfazer');
    await pressButton(tester, 'Voltar ao preset');
    await h.settle(tester);
    expect(find.text('Voltar ao preset'), findsNothing);
    await h.close(tester);
  });
}
