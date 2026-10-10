import 'dart:async';
import 'dart:typed_data';

/// Separa os quadros JPEG de um fluxo MJPEG (`multipart/x-mixed-replace`).
///
/// A rede entrega pedaços de qualquer tamanho: um quadro pode vir em dez pedaços, ou dois
/// quadros num só. Aqui eles são remontados pelos marcadores do próprio JPEG (início `FF D8`,
/// fim `FF D9`), sem depender dos cabeçalhos de cada parte. Um quadro maior que [maxFrameBytes]
/// é descartado: fluxo corrompido não pode crescer sem limite na memória do celular.
class MjpegSplitter extends StreamTransformerBase<List<int>, Uint8List> {
  const MjpegSplitter({this.maxFrameBytes = 8 * 1024 * 1024});

  final int maxFrameBytes;

  @override
  Stream<Uint8List> bind(Stream<List<int>> stream) async* {
    final buffer = BytesBuilder(copy: false);
    var inside = false;
    var previous = -1;
    await for (final chunk in stream) {
      for (final byte in chunk) {
        if (!inside) {
          if (previous == 0xFF && byte == 0xD8) {
            inside = true;
            buffer
              ..addByte(0xFF)
              ..addByte(0xD8);
          }
        } else {
          buffer.addByte(byte);
          if (previous == 0xFF && byte == 0xD9) {
            inside = false;
            yield buffer.takeBytes();
          } else if (buffer.length > maxFrameBytes) {
            inside = false;
            buffer.clear();
          }
        }
        previous = byte;
      }
    }
  }
}
