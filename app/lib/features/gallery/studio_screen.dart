import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/link.dart';
import '../../app/queries.dart';
import '../../core/errors.dart';
import '../../core/format.dart';
import '../../core/strings.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import '../../domain/models.dart';

/// G3 — Estúdio. Presets de um toque e três controles com nome de gente (brilho, cor, ruído).
/// Cada ajuste pede uma prévia à Jetson — o processamento é dela, na GPU —, e a imagem anterior
/// fica na tela até a nova chegar. Segurar a imagem mostra o "antes".
class StudioScreen extends ConsumerStatefulWidget {
  const StudioScreen({super.key, required this.id});

  final String id;

  @override
  ConsumerState<StudioScreen> createState() => _StudioScreenState();
}

class _StudioScreenState extends ConsumerState<StudioScreen> {
  /// Os controles simples, na ordem em que aparecem: rótulo -> nome do controle na API.
  static const _simple = [('Brilho', 'stretch'), ('Cor', 'saturation'), ('Ruído', 'denoise')];
  static const _presetNames = {'natural': 'Natural', 'vivido': 'Vívido', 'nebulosa': 'Nebulosa', 'suave': 'Suave'};

  /// G4 — "mais ajustes": os controles do ofício, na ordem em que se costuma mexer.
  static const _advanced = [
    ('Pretos', 'black'),
    ('Brancos', 'white'),
    ('Gama', 'gamma'),
    ('Tirar o verde', 'scnr'),
    ('Vermelho', 'r_gain'),
    ('Verde', 'g_gain'),
    ('Azul', 'b_gain'),
    ('Deconvolução', 'deconv'),
    ('Ruído de cor', 'ldenoise'),
    ('Reduzir estrelas', 'star_reduce'),
    ('Nitidez', 'sharpen'),
  ];
  static const _toggleNames = {'remove_grad': 'Tirar o gradiente do fundo'};

  String _preset = 'natural';
  final _values = <String, double>{};
  final _toggles = <String, bool>{};
  bool _more = false;
  Uint8List? _image;
  Uint8List? _original;
  bool _busy = false;
  bool _started = false;
  bool _holding = false;
  String? _problem;
  int _request = 0;

  Future<void> _render() async {
    final api = ref.read(apiProvider);
    final mine = ++_request;
    setState(() {
      _busy = true;
      _problem = null;
    });
    try {
      final bytes = await api.render(widget.id, {'preset': _preset, ..._values, ..._toggles});
      if (!mounted || mine != _request) return; // chegou uma prévia mais nova: esta não vale
      setState(() {
        _image = bytes;
        _original ??= bytes;
        _busy = false;
      });
    } on ApiFailure catch (failure) {
      if (!mounted || mine != _request) return;
      setState(() {
        _busy = false;
        _problem = S.failure(failure);
      });
    }
  }

  void _applyPreset(String name, RenderPresets presets) {
    setState(() {
      _preset = name;
      _values.clear(); // o preset define tudo; os controles voltam para os valores dele
      _toggles.clear();
    });
    _render();
  }

  bool? _presetToggle(String name, RenderPresets presets) {
    final value = presets.presets[_preset]?[name];
    return value is bool ? value : null;
  }

  double _value(String control, RenderPresets presets) {
    final preset = presets.presets[_preset]?[control];
    return _values[control] ?? (preset is num ? preset.toDouble() : presets.controls[control]?.initial ?? 0);
  }

  @override
  Widget build(BuildContext context) {
    final presets = ref.watch(presetsProvider);
    final session = ref.watch(sessionsProvider).valueOrNull?.where((s) => s.id == widget.id).firstOrNull;
    if (!_started && presets.hasValue) {
      // a primeira prévia, uma vez só: se a sessão não tiver imagem, não fica pedindo sem parar
      _started = true;
      Future.microtask(() {
        if (mounted) _render();
      });
    }
    return SubPage(
      title: session?.target ?? 'Estúdio',
      onBack: () => context.go('/gallery/${widget.id}'),
      actions: [
        if (_image != null)
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: Text(Fmt.bytes(_image!.length), style: AppText.small),
          ),
      ],
      child: Column(
        children: [
          Expanded(
            child: GestureDetector(
              onLongPressStart: (_) => setState(() => _holding = true),
              onLongPressEnd: (_) => setState(() => _holding = false),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  ColoredBox(
                    color: Colors.black,
                    child: BytesImage(_holding ? _original : _image, fit: BoxFit.contain, label: 'Prévia do estúdio'),
                  ),
                  if (_busy) const Positioned(right: 12, top: 12, child: Busy(size: 20)),
                  if (_holding) const Positioned(left: 12, top: 12, child: SourceNote('antes')),
                ],
              ),
            ),
          ),
          presets.when(
            loading: () => const Padding(padding: EdgeInsets.all(AppSpace.s3), child: Busy()),
            error: (error, _) => Padding(
              padding: const EdgeInsets.all(AppSpace.s2),
              child: Notice(title: 'O estúdio não respondeu', text: error is ApiFailure ? S.failure(error) : null),
            ),
            data: (p) => _controls(p),
          ),
        ],
      ),
    );
  }

  Widget _slider(String label, String control, RenderPresets presets, {double labelWidth = 62}) {
    final limits = presets.controls[control];
    if (limits == null) return const SizedBox.shrink();
    // passos pequenos pedem mais casas: 0,005 não cabe em uma
    final digits = limits.step < 0.01 ? 3 : (limits.step < 0.1 ? 2 : 1);
    return Row(
      children: [
        SizedBox(
          width: labelWidth,
          child: Text(label, style: AppText.body),
        ),
        Expanded(
          child: Slider(
            value: _value(control, presets).clamp(limits.min, limits.max),
            min: limits.min,
            max: limits.max,
            semanticFormatterCallback: (v) => '$label ${Fmt.dec(v, digits)}',
            onChanged: (v) => setState(() => _values[control] = (v / limits.step).round() * limits.step),
            onChangeEnd: (_) => _render(), // só ao soltar: uma prévia por gesto
          ),
        ),
        SizedBox(
          width: 48,
          child: Text(Fmt.dec(_value(control, presets), digits), textAlign: TextAlign.right, style: AppText.number),
        ),
      ],
    );
  }

  Widget _controls(RenderPresets presets) {
    final touched = _values.isNotEmpty || _toggles.isNotEmpty;
    final advanced = [
      for (final entry in _advanced)
        if (presets.controls.containsKey(entry.$2)) entry,
    ];
    return ConstrainedBox(
      // com "mais ajustes" aberto os controles rolam; a imagem não some da tela
      constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.5),
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(AppSpace.s2, AppSpace.s1, AppSpace.s2, AppSpace.s2),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (_problem != null) ...[Notice(title: _problem!), const SizedBox(height: AppSpace.s1)],
            SizedBox(
              height: 42,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: [
                  for (final name in presets.presets.keys) ...[
                    Choice(
                      _presetNames[name] ?? name,
                      selected: _preset == name && !touched,
                      onTap: () => _applyPreset(name, presets),
                    ),
                    const SizedBox(width: 8),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 4),
            for (final (label, control) in _simple) _slider(label, control, presets),
            if (advanced.isNotEmpty || presets.toggles.isNotEmpty) ...[
              const SizedBox(height: 4),
              Row(
                children: [
                  Expanded(
                    child: AppButton(
                      _more ? 'Menos ajustes' : 'Mais ajustes',
                      icon: 'sliders',
                      expand: true,
                      onPressed: () => setState(() => _more = !_more),
                    ),
                  ),
                  if (touched) ...[
                    const SizedBox(width: 8),
                    Expanded(
                      child: AppButton(
                        'Voltar ao preset',
                        expand: true,
                        onPressed: () => _applyPreset(_preset, presets),
                      ),
                    ),
                  ],
                ],
              ),
            ],
            // G4 — os controles do ofício, para quem quer ir além dos três de cima
            if (_more) ...[
              const SizedBox(height: 4),
              for (final (label, control) in advanced) _slider(label, control, presets, labelWidth: 124),
              for (final entry in presets.toggles.entries)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: SwitchPanel(
                    icon: 'layers',
                    title: _toggleNames[entry.key] ?? entry.key,
                    value: _toggles[entry.key] ?? _presetToggle(entry.key, presets) ?? entry.value,
                    onChanged: (on) {
                      setState(() => _toggles[entry.key] = on);
                      _render();
                    },
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}
