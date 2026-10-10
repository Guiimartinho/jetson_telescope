import 'dart:io' show zlib;
import 'dart:typed_data';

/// Um PNG mínimo (RGB de 8 bits) a partir de pixels, sem dependência nenhuma.
///
/// Serve ao modo demonstração: o telescópio falso desenha as próprias imagens, então o app
/// funciona sem aparelho e sem embutir fotos de terceiros.
Uint8List encodePng(int width, int height, Uint8List rgb) {
  assert(rgb.length == width * height * 3);
  final raw = Uint8List(height * (1 + width * 3));
  for (var y = 0; y < height; y++) {
    final row = y * (1 + width * 3);
    raw[row] = 0; // filtro "nenhum"
    raw.setRange(row + 1, row + 1 + width * 3, rgb, y * width * 3);
  }
  final header = ByteData(13)
    ..setUint32(0, width)
    ..setUint32(4, height)
    ..setUint8(8, 8) // bits por canal
    ..setUint8(9, 2); // RGB
  final out = BytesBuilder()
    ..add(const [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
    ..add(_chunk('IHDR', header.buffer.asUint8List()))
    ..add(_chunk('IDAT', zlib.encode(raw)))
    ..add(_chunk('IEND', const []));
  return out.takeBytes();
}

List<int> _chunk(String type, List<int> data) {
  final body = <int>[...type.codeUnits, ...data];
  final framed = ByteData(4)..setUint32(0, data.length);
  final crc = ByteData(4)..setUint32(0, _crc32(body));
  return [...framed.buffer.asUint8List(), ...body, ...crc.buffer.asUint8List()];
}

final List<int> _crcTable = List<int>.generate(256, (n) {
  var c = n;
  for (var k = 0; k < 8; k++) {
    c = (c & 1) != 0 ? 0xEDB88320 ^ (c >> 1) : c >> 1;
  }
  return c;
});

int _crc32(List<int> bytes) {
  var c = 0xFFFFFFFF;
  for (final b in bytes) {
    c = _crcTable[(c ^ b) & 0xFF] ^ (c >> 8);
  }
  return c ^ 0xFFFFFFFF;
}
