import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/commands.dart';
import '../../app/queries.dart';
import '../../core/format.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import '../../data/file_sharer.dart';

/// G5 — Exportar: levar o resultado para fora do telescópio. Três formatos, cada um para uma
/// coisa; o arquivo é montado na Jetson e entregue ao Android, que salva ou envia.
class ExportScreen extends ConsumerStatefulWidget {
  const ExportScreen({super.key, required this.id});

  final String id;

  @override
  ConsumerState<ExportScreen> createState() => _ExportScreenState();
}

class _ExportScreenState extends ConsumerState<ExportScreen> {
  static const _formats = [
    ('jpg', 'JPEG', 'A imagem já tratada, pronta para mostrar e mandar.', 'image/jpeg'),
    ('tif', 'TIFF 16 bits', 'Linear, sem esticar: para tratar em outro programa.', 'image/tiff'),
    ('fits', 'FITS', 'O empilhamento como está no telescópio. Pode passar de 300 MB.', 'application/fits'),
  ];
  static const _sizes = [(2000, 'Tela (2000 px)'), (4000, 'Grande (4000 px)'), (0, 'Cheio')];

  String _format = 'jpg';
  int _maxSide = 2000;
  bool _busy = false;
  String? _done;

  Future<void> _export() async {
    setState(() {
      _busy = true;
      _done = null;
    });
    final commands = ref.read(commandsProvider);
    final bytes = await commands.act(
      (api) => api.exportSession(widget.id, format: _format, maxSide: _format == 'fits' ? 0 : _maxSide),
    );
    if (!mounted) return;
    if (bytes == null) {
      setState(() => _busy = false);
      commands.say('O telescópio não tem este arquivo para exportar.');
      return;
    }
    final mime = _formats.firstWhere((f) => f.$1 == _format).$4;
    final shared = await ref.read(fileSharerProvider).share(bytes, name: '${widget.id}.$_format', mimeType: mime);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _done = shared
          ? 'Entregue ao Android: ${Fmt.bytes(bytes.length)}.'
          : 'Arquivo pronto (${Fmt.bytes(bytes.length)}), mas nada foi escolhido.';
    });
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionsProvider).valueOrNull?.where((s) => s.id == widget.id).firstOrNull;
    return SubPage(
      title: 'Exportar ${session?.target ?? ''}'.trim(),
      onBack: () => context.go('/gallery/${widget.id}'),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(AppSpace.s2, 0, AppSpace.s2, 96),
        children: [
          const SectionLabel('Formato'),
          for (final (id, name, text, _) in _formats) ...[
            Panel(
              onTap: () => setState(() => _format = id),
              color: _format == id ? AppColors.elev : null,
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(name, style: AppText.heading.copyWith(fontSize: 15)),
                        const SizedBox(height: 2),
                        Text(text, style: AppText.small),
                      ],
                    ),
                  ),
                  if (_format == id) const AppIcon('check', size: 18, color: AppColors.accent),
                ],
              ),
            ),
            const SizedBox(height: 8),
          ],
          if (_format != 'fits') ...[
            const SizedBox(height: AppSpace.s1),
            const SectionLabel('Tamanho'),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final (side, label) in _sizes)
                  Choice(label, selected: _maxSide == side, onTap: () => setState(() => _maxSide = side)),
              ],
            ),
          ],
          const SizedBox(height: AppSpace.s3),
          AppButton(
            _busy ? 'Preparando...' : 'Salvar ou compartilhar',
            icon: 'share',
            tone: ButtonTone.primary,
            big: true,
            expand: true,
            onPressed: _busy ? null : _export,
          ),
          const SizedBox(height: 8),
          Text(
            _done ??
                'O Android abre as opções: salvar em Arquivos, mandar por mensagem, abrir em outro app. '
                    'Arquivos grandes demoram um pouco para chegar.',
            style: AppText.small,
          ),
        ],
      ),
    );
  }
}
