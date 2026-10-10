import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/commands.dart';
import '../../core/format.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';

/// Lê "18 03 36", "18h03m36s", "18:03:36" ou "18,06" como um número (horas ou graus). O sinal
/// vale para o valor inteiro: "-24 23" é -24,38. Devolve nulo se não for um número.
double? parseSexagesimal(String text) {
  final clean = text.trim().replaceAll(',', '.');
  if (clean.isEmpty) return null;
  final negative = clean.startsWith('-');
  final parts = RegExp(r'\d+(?:\.\d+)?').allMatches(clean).map((m) => double.parse(m.group(0)!)).toList();
  if (parts.isEmpty || parts.length > 3) return null;
  if (parts.length > 1 && parts.skip(1).any((p) => p >= 60)) return null;
  var value = 0.0;
  for (var i = parts.length - 1; i >= 0; i--) {
    value = value / 60 + parts[i];
  }
  return negative ? -value : value;
}

/// A3 — Apontar por coordenadas: para o que não está no catálogo (um cometa, uma supernova).
class CoordsScreen extends ConsumerStatefulWidget {
  const CoordsScreen({super.key});

  @override
  ConsumerState<CoordsScreen> createState() => _CoordsScreenState();
}

class _CoordsScreenState extends ConsumerState<CoordsScreen> {
  final _ra = TextEditingController();
  final _dec = TextEditingController();
  String? _problem;
  bool _busy = false;

  @override
  void dispose() {
    _ra.dispose();
    _dec.dispose();
    super.dispose();
  }

  Future<void> _go() async {
    final hours = parseSexagesimal(_ra.text);
    final dec = parseSexagesimal(_dec.text);
    if (hours == null || hours < 0 || hours >= 24) {
      setState(() => _problem = 'Ascensão reta em horas, de 0 a 24. Exemplo: 18 03 36');
      return;
    }
    if (dec == null || dec.abs() > 90) {
      setState(() => _problem = 'Declinação em graus, de -90 a +90. Exemplo: -24 23 00');
      return;
    }
    setState(() {
      _problem = null;
      _busy = true;
    });
    final job = await ref.read(commandsProvider).goToCoordinates(hours * 15, dec);
    if (!mounted) return;
    setState(() => _busy = false);
    if (job != null) context.go('/observe');
  }

  @override
  Widget build(BuildContext context) {
    final hours = parseSexagesimal(_ra.text);
    final dec = parseSexagesimal(_dec.text);
    return SubPage(
      title: 'Apontar por coordenadas',
      onBack: () => context.go('/atlas'),
      child: ListView(
        padding: const EdgeInsets.all(AppSpace.s2),
        children: [
          const Text('Coordenadas equatoriais (J2000).', style: AppText.small),
          const SizedBox(height: AppSpace.s2),
          TextField(
            controller: _ra,
            keyboardType: TextInputType.text,
            onChanged: (_) => setState(() {}),
            decoration: const InputDecoration(labelText: 'Ascensão reta (horas)', hintText: '18 03 36'),
          ),
          const SizedBox(height: AppSpace.s1),
          TextField(
            controller: _dec,
            keyboardType: TextInputType.text,
            onChanged: (_) => setState(() {}),
            decoration: const InputDecoration(labelText: 'Declinação (graus)', hintText: '-24 23 00'),
          ),
          const SizedBox(height: AppSpace.s1),
          if (hours != null && dec != null && hours >= 0 && hours < 24 && dec.abs() <= 90)
            Text('Entendi: ${Fmt.ra(hours * 15)}, ${Fmt.dec2(dec)}', style: AppText.small),
          if (_problem != null) ...[const SizedBox(height: AppSpace.s1), Notice(title: _problem!)],
          const SizedBox(height: AppSpace.s2),
          AppButton(
            'Apontar',
            icon: 'reticle',
            tone: ButtonTone.primary,
            big: true,
            expand: true,
            onPressed: _busy ? null : _go,
          ),
        ],
      ),
    );
  }
}
