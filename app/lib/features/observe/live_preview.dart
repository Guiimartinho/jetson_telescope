import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/link.dart';
import '../../core/format.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import '../../data/telescope_api.dart';

/// A imagem ao vivo. Recebe os quadros que a Jetson empurra e troca um pelo outro sem piscar.
/// Pinça dá zoom e arrasta sobre o último quadro (a Jetson não é consultada a cada gesto).
/// Se o sinal cair, o último quadro fica na tela com a hora em que chegou, e a escuta recomeça
/// sozinha quando a ligação volta.
class LivePreview extends ConsumerStatefulWidget {
  const LivePreview({super.key, this.maxSide = 1280});

  final int maxSide;

  @override
  ConsumerState<LivePreview> createState() => _LivePreviewState();
}

class _LivePreviewState extends ConsumerState<LivePreview> {
  StreamSubscription<Uint8List>? _subscription;
  TelescopeApi? _api;
  Timer? _retry;
  Uint8List? _frame;
  DateTime? _at;

  @override
  void dispose() {
    _retry?.cancel();
    unawaited(_subscription?.cancel());
    super.dispose();
  }

  void _listen(TelescopeApi api) {
    _retry?.cancel();
    unawaited(_subscription?.cancel());
    _api = api;
    _subscription = api
        .preview(maxSide: widget.maxSide)
        .listen(
          (frame) {
            if (mounted) {
              setState(() {
                _frame = frame;
                _at = DateTime.now();
              });
            }
          },
          onError: (Object _) => _again(api),
          onDone: () => _again(api),
          cancelOnError: true,
        );
  }

  void _again(TelescopeApi api) {
    _retry?.cancel();
    _retry = Timer(const Duration(seconds: 2), () {
      if (mounted && identical(api, _api)) _listen(api);
    });
  }

  @override
  Widget build(BuildContext context) {
    final api = ref.watch(linkProvider.select((l) => l.api));
    final online = ref.watch(linkProvider.select((l) => l.online));
    if (api != null && !identical(api, _api)) {
      // agenda para depois deste build: assinar um fluxo não é coisa de se fazer no meio dele
      Future.microtask(() {
        if (mounted) _listen(api);
      });
    }
    return ColoredBox(
      color: Colors.black,
      child: Stack(
        fit: StackFit.expand,
        children: [
          if (_frame == null)
            const Center(child: Text('Esperando a imagem...', style: AppText.small))
          else
            InteractiveViewer(
              maxScale: 6,
              child: BytesImage(_frame, fit: BoxFit.contain, label: 'Imagem ao vivo do telescópio'),
            ),
          if (!online && _at != null)
            Positioned(left: 10, bottom: 10, child: SourceNote('imagem de ${Fmt.clock(_at!)} (sem sinal)')),
        ],
      ),
    );
  }
}
