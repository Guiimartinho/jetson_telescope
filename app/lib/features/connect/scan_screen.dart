import 'dart:io' show Platform;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import '../../domain/pairing.dart';

/// C3 — Ler o QR do telescópio. Sem câmera (ou sem permissão), o mesmo código pode ser
/// digitado: é o plano B, sempre à mão.
class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  static final _cameraSupported = Platform.isAndroid || Platform.isIOS || Platform.isMacOS;
  late final MobileScannerController? _controller = _cameraSupported
      ? MobileScannerController(formats: const [BarcodeFormat.qrCode])
      : null;
  String? _problem;
  bool _done = false;

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  void _onDetect(BarcodeCapture capture) {
    if (_done) return;
    final text = capture.barcodes.map((b) => b.rawValue).whereType<String>().firstOrNull;
    if (text == null) return;
    try {
      final code = PairingCode.parse(text);
      _done = true;
      context.go('/connect/pairing', extra: code);
    } on FormatException catch (e) {
      if (_problem != e.message) setState(() => _problem = e.message);
    }
  }

  @override
  Widget build(BuildContext context) => SubPage(
    title: 'Ler o QR do telescópio',
    onBack: () => context.go('/connect'),
    child: Column(
      children: [
        Expanded(
          child: Padding(
            padding: const EdgeInsets.all(AppSpace.s2),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(AppSpace.radius),
              child: _controller == null
                  ? const _NoCamera(text: 'Este aparelho não lê QR pelo app. Digite o código.')
                  : MobileScanner(
                      controller: _controller,
                      onDetect: _onDetect,
                      placeholderBuilder: (_) => const ColoredBox(color: AppColors.surface2, child: Busy()),
                      errorBuilder: (_, error) => _NoCamera(
                        text: error.errorCode == MobileScannerErrorCode.permissionDenied
                            ? 'O app não tem permissão para usar a câmera. Libere nas configurações do '
                                  'celular, ou digite o código.'
                            : 'Não consegui abrir a câmera. Digite o código.',
                      ),
                      overlayBuilder: (_, _) => const _Frame(),
                    ),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(AppSpace.s2, 0, AppSpace.s2, AppSpace.s2),
          child: Column(
            children: [
              Text(
                _problem ?? 'Aponte para o código que o telescópio mostra ao abrir o pareamento.',
                textAlign: TextAlign.center,
                style: AppText.small.copyWith(color: _problem == null ? AppColors.muted : AppColors.gold),
              ),
              const SizedBox(height: AppSpace.s2),
              AppButton(
                'Digitar o código',
                icon: 'keyboard',
                expand: true,
                onPressed: () => context.go('/connect/code'),
              ),
            ],
          ),
        ),
      ],
    ),
  );
}

class _NoCamera extends StatelessWidget {
  const _NoCamera({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => ColoredBox(
    color: AppColors.surface,
    child: EmptyState(icon: 'camera', title: 'Sem câmera', text: text),
  );
}

/// A moldura que mostra onde enquadrar o código.
class _Frame extends StatelessWidget {
  const _Frame();

  @override
  Widget build(BuildContext context) => Center(
    child: FractionallySizedBox(
      widthFactor: 0.7,
      child: AspectRatio(
        aspectRatio: 1,
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: AppColors.accent, width: 2),
          ),
        ),
      ),
    ),
  );
}
