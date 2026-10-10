/// Falha ao falar com o telescópio, já classificada: a tela decide o que dizer e o que
/// oferecer pelo [kind], nunca por um texto solto vindo da rede.
enum FailureKind {
  /// Sem resposta: fora da rede, desligado, WiFi errado.
  unreachable,

  /// O certificado não é o do aparelho pareado: possível impostor, ou a Jetson foi regravada.
  identityMismatch,

  /// O token não vale mais (celular revogado ou pareamento zerado).
  unauthorized,

  /// O papel deste celular não permite a ação.
  forbidden,

  /// O aparelho recusou a entrada (campo fora da faixa, alvo inexistente).
  invalid,

  /// Não existe (alvo, sessão, imagem).
  notFound,

  /// A janela de pareamento está fechada.
  pairingClosed,

  /// O código de pareamento não confere.
  pairingRejected,

  /// O número do pareamento expirou.
  pairingExpired,

  /// Muitas tentativas: é preciso esperar.
  pairingLocked,

  /// Função ainda não disponível neste aparelho.
  notSupported,

  /// Agora não dá: há um trabalho em andamento, a montagem está estacionada, é o último dono...
  /// O `code` diz qual (`busy`, `parked`, `not_running`, `protected`, `last_owner`,
  /// `no_known_network`, `in_use`, `nothing_to_install`).
  conflict,

  /// Qualquer outra coisa.
  unknown,
}

class ApiFailure implements Exception {
  const ApiFailure(this.kind, {this.code = '', this.message = '', this.status = 0});

  final FailureKind kind;
  final String code;
  final String message;
  final int status;

  /// Traduz a resposta de erro da API (`{"error": {"code", "message"}}`).
  factory ApiFailure.fromApi(int status, String code, String message) {
    final kind = switch (code) {
      'unauthorized' => FailureKind.unauthorized,
      'forbidden' => FailureKind.forbidden,
      'invalid_argument' => FailureKind.invalid,
      'not_found' => FailureKind.notFound,
      'pairing_closed' => FailureKind.pairingClosed,
      'pairing_rejected' => FailureKind.pairingRejected,
      'pairing_expired' => FailureKind.pairingExpired,
      'pairing_locked' => FailureKind.pairingLocked,
      'not_supported' || 'not_enabled' => FailureKind.notSupported,
      'busy' || 'parked' || 'not_running' || 'protected' || 'last_owner' => FailureKind.conflict,
      'no_known_network' || 'in_use' || 'nothing_to_install' => FailureKind.conflict,
      _ => switch (status) {
        409 => FailureKind.conflict,
        401 => FailureKind.unauthorized,
        403 => FailureKind.forbidden,
        404 => FailureKind.notFound,
        400 => FailureKind.invalid,
        _ => FailureKind.unknown,
      },
    };
    return ApiFailure(kind, code: code, message: message, status: status);
  }

  @override
  String toString() => 'ApiFailure(${kind.name}, $code, $status, $message)';
}
