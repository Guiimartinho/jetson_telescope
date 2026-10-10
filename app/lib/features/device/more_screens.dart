import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/commands.dart';
import '../../app/link.dart';
import '../../core/strings.dart';
import '../../core/theme.dart';
import '../../core/version.dart';
import '../../core/widgets/kit.dart';

/// D10 — Ajuda e sobre: o caminho de uma noite, as palavras do ofício e as licenças.
class AboutScreen extends StatelessWidget {
  const AboutScreen({super.key});

  static const _guide = [
    ('Conectar', 'Leia o QR do telescópio uma vez. Depois o app o reencontra sozinho.'),
    ('Dizer onde e quando', 'O celular manda a hora e o local: sem isso o telescópio não sabe o que está no céu.'),
    ('Escolher', 'No Atlas, "Hoje" mostra o que está alto agora e cabe no campo.'),
    ('Observar', 'Um toque aponta, reconhece o céu, centraliza e começa a empilhar.'),
    ('Parar', 'O botão PARAR está em todas as telas e nunca pede confirmação.'),
    ('Rever', 'A Galeria guarda cada sessão; o Estúdio ajusta brilho, cor e ruído.'),
  ];

  static const _glossary = [
    ('Empilhar', 'Somar muitas fotos curtas do mesmo alvo. O sinal cresce, o ruído cai.'),
    (
      'Reconhecer o céu',
      'Comparar as estrelas da foto com o mapa do céu para saber para onde se aponta (plate solve).',
    ),
    ('Nitidez (FWHM)', 'O tamanho das estrelas na foto, em pixels. Quanto menor, melhor o foco e a atmosfera.'),
    ('SNR', 'Quanto o sinal está acima do ruído. Dobra a cada quatro vezes mais fotos.'),
    ('Rastreio', 'A montagem acompanhando a rotação do céu para o alvo não sair do campo.'),
    ('Mosaico', 'Vários quadros vizinhos costurados, para um alvo maior que o campo.'),
    ('Altitude', 'A altura do alvo acima do horizonte. Abaixo de 25 graus a atmosfera estraga a imagem.'),
  ];

  @override
  Widget build(BuildContext context) => SubPage(
    title: 'Ajuda e sobre',
    onBack: () => context.go('/device'),
    child: ListView(
      padding: const EdgeInsets.fromLTRB(AppSpace.s2, 0, AppSpace.s2, 96),
      children: [
        const SectionLabel('Uma noite, passo a passo'),
        Panel(
          child: Column(
            children: [
              for (final (n, (title, text)) in _guide.indexed)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SizedBox(
                        width: 24,
                        child: Text('${n + 1}', style: AppText.number.copyWith(color: AppColors.accent)),
                      ),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(title, style: AppText.body.copyWith(fontWeight: FontWeight.w700)),
                            Text(text, style: AppText.small),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: AppSpace.s3),
        const SectionLabel('As palavras'),
        Panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (final (term, meaning) in _glossary)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(term, style: AppText.body.copyWith(fontWeight: FontWeight.w700)),
                      Text(meaning, style: AppText.small),
                    ],
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: AppSpace.s3),
        const SectionLabel('Sobre'),
        const Panel(
          padding: EdgeInsets.symmetric(horizontal: AppSpace.s2, vertical: 8),
          child: Column(
            children: [
              InfoLine(icon: 'phone', label: 'Versão do app', value: appVersion),
              InfoLine(icon: 'lock', label: 'Com quem o app fala', value: 'só com o telescópio'),
              InfoLine(icon: 'wifi', label: 'Internet', value: 'não usa'),
            ],
          ),
        ),
        const SizedBox(height: AppSpace.s1),
        AppButton(
          'Licenças de código aberto',
          expand: true,
          onPressed: () =>
              showLicensePage(context: context, applicationName: S.appName, applicationVersion: appVersion),
        ),
      ],
    ),
  );
}

/// C6 — o nome do telescópio. É o que aparece no topo do app e na rede.
class NameScreen extends ConsumerStatefulWidget {
  const NameScreen({super.key});

  @override
  ConsumerState<NameScreen> createState() => _NameScreenState();
}

class _NameScreenState extends ConsumerState<NameScreen> {
  late final _controller = TextEditingController(text: ref.read(linkProvider).name);
  bool _saving = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final wanted = _controller.text.trim();
    if (wanted.isEmpty) return;
    setState(() => _saving = true);
    final name = await ref.read(commandsProvider).act((api) => api.rename(wanted));
    if (!mounted) return;
    setState(() => _saving = false);
    if (name == null) return;
    await ref.read(linkProvider.notifier).refreshInfo();
    ref.read(commandsProvider).say('O telescópio agora se chama $name.');
    if (mounted) context.go('/device');
  }

  @override
  Widget build(BuildContext context) => SubPage(
    title: 'Nome do telescópio',
    onBack: () => context.go('/device'),
    child: ListView(
      padding: const EdgeInsets.fromLTRB(AppSpace.s2, 0, AppSpace.s2, 96),
      children: [
        const Text('É o nome que aparece no topo do app e para os outros celulares.', style: AppText.small),
        const SizedBox(height: AppSpace.s2),
        TextField(
          controller: _controller,
          maxLength: 40,
          textInputAction: TextInputAction.done,
          onSubmitted: (_) => _save(),
          decoration: const InputDecoration(labelText: 'Nome'),
        ),
        const SizedBox(height: AppSpace.s2),
        AppButton('Salvar', tone: ButtonTone.primary, big: true, expand: true, onPressed: _saving ? null : _save),
      ],
    ),
  );
}
