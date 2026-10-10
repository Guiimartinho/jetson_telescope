import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

/// base64 seguro para URL sem preenchimento: o formato de tudo que vai no QR e na API.
String b64u(List<int> bytes) => base64Url.encode(bytes).replaceAll('=', '');

Uint8List b64uDecode(String text) => base64Url.decode(base64Url.normalize(text));

/// O conteúdo do QR do aparelho: `tele://pair?v=1&id=…&fp=…&s=…&port=…[&host=…&ssid=…&psk=…]`.
///
/// Traz tudo que o app precisa para confiar no telescópio ANTES de falar com ele: a impressão
/// digital do certificado ([fingerprint]) e o segredo de pareamento ([secret]). O segredo nunca
/// é enviado: só a prova de que o temos ([pairingProof]). Ver `app/docs/07-seguranca.md`.
class PairingCode {
  const PairingCode({
    required this.deviceId,
    required this.fingerprint,
    required this.secret,
    this.port = 8443,
    this.host,
    this.ssid,
    this.psk,
  });

  final String deviceId;
  final Uint8List fingerprint;
  final Uint8List secret;
  final int port;
  final String? host;

  /// WiFi próprio do telescópio (modo campo), quando o QR o traz.
  final String? ssid;
  final String? psk;

  /// Lê o texto do QR (ou o código colado à mão). Lança [FormatException] com o motivo, em
  /// linguagem de gente, quando não é um código deste produto.
  static PairingCode parse(String text) {
    final uri = Uri.tryParse(text.trim());
    if (uri == null || uri.scheme != 'tele' || uri.host != 'pair') {
      throw const FormatException('Este não é o código de um telescópio.');
    }
    final q = uri.queryParameters;
    if (q['v'] != '1') {
      throw const FormatException('Este código é de outra versão. Atualize o app.');
    }
    final Uint8List fingerprint;
    final Uint8List secret;
    try {
      fingerprint = b64uDecode(q['fp'] ?? '');
      secret = b64uDecode(q['s'] ?? '');
    } on FormatException {
      throw const FormatException('O código está incompleto. Leia de novo.');
    }
    final port = int.tryParse(q['port'] ?? '8443');
    if (fingerprint.length != 32 || secret.length < 16 || (q['id'] ?? '').isEmpty || port == null) {
      throw const FormatException('O código está incompleto. Leia de novo.');
    }
    String? opt(String key) => (q[key] ?? '').isEmpty ? null : q[key];
    return PairingCode(
      deviceId: q['id']!,
      fingerprint: fingerprint,
      secret: secret,
      port: port,
      host: opt('host'),
      ssid: opt('ssid'),
      psk: opt('psk'),
    );
  }
}

/// A prova do pareamento — a MESMA conta dos dois lados (`src/api/pairing.py` na Jetson):
///
///     HMAC-SHA256(segredo, número sorteado + impressão digital + nome do celular)
Uint8List pairingProof(Uint8List secret, Uint8List nonce, Uint8List fingerprint, String clientName) {
  final message = <int>[...nonce, ...fingerprint, ...utf8.encode(clientName)];
  return Uint8List.fromList(Hmac(sha256, secret).convert(message).bytes);
}

/// Impressão digital de um certificado: SHA-256 do DER.
Uint8List certificateFingerprint(List<int> der) => Uint8List.fromList(sha256.convert(der).bytes);

/// Compara sem parar no primeiro byte diferente.
bool sameBytes(List<int> a, List<int> b) {
  if (a.length != b.length) return false;
  var diff = 0;
  for (var i = 0; i < a.length; i++) {
    diff |= a[i] ^ b[i];
  }
  return diff == 0;
}
