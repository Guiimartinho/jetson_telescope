import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:share_plus/share_plus.dart';

/// Entrega um arquivo ao sistema do celular: a folha de compartilhar do Android, de onde se
/// salva em Arquivos, manda por mensagem ou abre em outro app. É uma porta para os testes de
/// tela não dependerem do sistema.
abstract interface class FileSharer {
  /// Devolve falso se a pessoa fechou a folha sem escolher nada.
  Future<bool> share(Uint8List bytes, {required String name, required String mimeType});
}

class PlatformFileSharer implements FileSharer {
  @override
  Future<bool> share(Uint8List bytes, {required String name, required String mimeType}) async {
    final result = await SharePlus.instance.share(
      ShareParams(
        files: [XFile.fromData(bytes, mimeType: mimeType)],
        // um arquivo criado na memória não tem nome: é este que o Android mostra e grava
        fileNameOverrides: [name],
      ),
    );
    return result.status != ShareResultStatus.dismissed;
  }
}

final fileSharerProvider = Provider<FileSharer>((ref) => PlatformFileSharer());
