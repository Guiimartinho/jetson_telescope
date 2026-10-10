import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import '../../domain/pairing.dart';

/// O plano B do QR: colar ou digitar o mesmo código (a linha `tele://pair?...` que o comando de
/// pareamento do telescópio mostra).
class CodeScreen extends StatefulWidget {
  const CodeScreen({super.key});

  @override
  State<CodeScreen> createState() => _CodeScreenState();
}

class _CodeScreenState extends State<CodeScreen> {
  final _text = TextEditingController();
  String? _problem;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  void _submit() {
    try {
      final code = PairingCode.parse(_text.text);
      context.go('/connect/pairing', extra: code);
    } on FormatException catch (e) {
      setState(() => _problem = e.message);
    }
  }

  @override
  Widget build(BuildContext context) => SubPage(
    title: 'Digitar o código',
    onBack: () => context.go('/connect'),
    child: ListView(
      padding: const EdgeInsets.all(AppSpace.s2),
      children: [
        const Text(
          'Cole aqui a linha que o telescópio mostra abaixo do QR. Ela começa com tele://pair',
          style: AppText.body,
        ),
        const SizedBox(height: AppSpace.s2),
        TextField(
          controller: _text,
          minLines: 3,
          maxLines: 6,
          autocorrect: false,
          enableSuggestions: false,
          keyboardType: TextInputType.visiblePassword, // sem correção nem sugestões
          style: const TextStyle(fontSize: 14, fontFamily: 'monospace'),
          decoration: InputDecoration(hintText: 'tele://pair?v=1&id=...', errorText: _problem, errorMaxLines: 3),
          onChanged: (_) {
            if (_problem != null) setState(() => _problem = null);
          },
        ),
        const SizedBox(height: AppSpace.s2),
        AppButton('Continuar', tone: ButtonTone.primary, big: true, expand: true, onPressed: _submit),
        const SizedBox(height: AppSpace.s2),
        const Text('Este código dá acesso ao telescópio. Não o envie por mensagem.', style: AppText.small),
      ],
    ),
  );
}
