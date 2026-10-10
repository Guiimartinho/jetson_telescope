import 'errors.dart';

/// O vocabulário comum do app, em português do Brasil: estados, etapas, tipos de alvo e o que
/// dizer quando algo dá errado. Fica num lugar só para o inglês entrar depois pela mesma porta.
///
/// Modo simples fala como gente ("Reconhecendo o céu"); os termos do ofício (plate solve, FWHM)
/// ficam para o modo Pro.
abstract final class S {
  static const appName = 'Telescópio';

  /// Estado do Controller -> o que o telescópio está fazendo.
  static String activity(String state) => switch (state) {
    'IDLE' => 'pronto',
    'SLEWING' => 'apontando',
    'SOLVING' => 'reconhecendo o céu',
    'FOCUSING' => 'focando',
    'STACKING' => 'empilhando',
    'SCHEDULING' => 'seguindo o plano',
    'TRACKING' => 'rastreando',
    'PREVIEW' => 'câmera ao vivo',
    'CAPTURING' => 'gravando',
    'ERROR' => 'com erro',
    'STOPPED' => 'parado',
    _ => state.toLowerCase(),
  };

  /// Etapa de um trabalho -> nome da etapa.
  static String step(String name) => switch (name) {
    'slew' => 'Apontar',
    'solve' => 'Reconhecer o céu',
    'focus' => 'Focar',
    'stack' => 'Empilhar',
    'schedule' => 'Seguir o plano',
    'track' => 'Rastrear',
    'preview' => 'Câmera ao vivo',
    'capture' => 'Gravar os quadros',
    _ => name,
  };

  static String stepState(String state) => switch (state) {
    'running' => 'agora...',
    'done' => 'feito',
    'failed' => 'falhou',
    'stopped' => 'parado',
    _ => 'falta',
  };

  static String targetType(String type) => switch (type) {
    'nebula' => 'Nebulosa',
    'galaxy' => 'Galáxia',
    'cluster' => 'Aglomerado',
    _ => 'Outro',
  };

  /// Por que um trabalho falhou, em linguagem direta.
  static String jobError(String? code) => switch (code) {
    'not_converged' => 'Não consegui centralizar o alvo: o céu reconhecido não bateu com o esperado.',
    'focus_failed' =>
      'Não achei o foco: sem estrelas para medir, ou o focalizador chegou ao fim do curso. '
          'Aponte para um campo com estrelas e tente de novo.',
    'polar_failed' =>
      'Não consegui medir o eixo: os três campos ficaram juntos demais, ou o céu não foi reconhecido. '
          'Tente de novo com o céu limpo.',
    'internal' => 'O telescópio teve um erro interno nesta etapa.',
    _ => 'A etapa não terminou.',
  };

  /// Parâmetro que o aparelho ainda não aplica.
  static String ignoredParam(String name) => switch (name) {
    'exposure_s' => 'exposição',
    'gain' => 'ganho',
    'frames' => 'número de fotos',
    _ => name,
  };

  /// O que aconteceu, para mostrar a quem usa. Nunca um código solto.
  static String failure(ApiFailure f) => switch (f.kind) {
    FailureKind.unreachable => 'O telescópio não respondeu. Veja se o celular está no mesmo WiFi que ele.',
    FailureKind.identityMismatch =>
      'Quem respondeu não é o telescópio que você pareou. Por segurança, nada foi enviado.',
    FailureKind.unauthorized => 'Este celular não está mais pareado com o telescópio.',
    FailureKind.forbidden => 'Este celular não tem permissão para isso.',
    FailureKind.invalid => 'O telescópio não aceitou esse valor.',
    FailureKind.notFound => 'Não encontrei isso no telescópio.',
    FailureKind.pairingClosed =>
      'O telescópio não está aceitando pareamento agora. Abra a janela de pareamento e leia o código de novo.',
    FailureKind.pairingRejected => 'O código não confere com este telescópio. Leia o QR de novo.',
    FailureKind.pairingExpired => 'O pareamento demorou demais. Tente de novo.',
    FailureKind.pairingLocked => 'Muitas tentativas erradas. Espere um pouco antes de tentar de novo.',
    FailureKind.notSupported => 'Este telescópio ainda não faz isso.',
    FailureKind.conflict => switch (f.code) {
      'busy' => 'O telescópio está ocupado. Pare o trabalho em andamento primeiro.',
      'parked' => 'A montagem está estacionada. Tire-a do repouso primeiro.',
      'not_running' => 'Não há noite em andamento.',
      'protected' => 'Esta imagem é de referência e não pode ser apagada.',
      'last_owner' => 'Este é o único dono. Escolha outro dono antes de mudar este.',
      'no_known_network' => 'O telescópio não tem nenhuma rede de casa guardada ao alcance.',
      'in_use' => 'O telescópio está nesta rede. Passe para o WiFi próprio antes de esquecê-la.',
      'nothing_to_install' => 'Não há versão nova para instalar.',
      _ => 'Agora não dá para fazer isso.',
    },
    FailureKind.unknown => 'Algo deu errado no telescópio.',
  };

  /// Força do sinal do WiFi (0 a 100), em palavras.
  static String signal(int percent) => switch (percent) {
    >= 67 => 'sinal forte',
    >= 34 => 'sinal médio',
    _ => 'sinal fraco',
  };

  /// Por que o telescópio não entrou na rede pedida.
  static String networkError(String? code) => switch (code) {
    'wrong_password' => 'A senha não confere. O telescópio continuou onde estava.',
    'not_found' => 'A rede sumiu do alcance do telescópio. Ele continuou onde estava.',
    _ => 'O telescópio não conseguiu entrar na rede e continuou onde estava.',
  };

  /// Em que pé está a atualização do telescópio.
  static String updateState(String state) => switch (state) {
    'checking' => 'procurando versão nova',
    'downloading' => 'baixando',
    'installing' => 'instalando',
    'restarting' => 'reiniciando',
    'failed' => 'a instalação falhou',
    _ => 'em dia',
  };

  /// Um ângulo pequeno, em minutos de arco, do jeito que se fala: 64,2' vira "1° 04'".
  static String arcmin(double value) {
    final total = value.abs();
    if (total < 9.95) return "${total.toStringAsFixed(1).replaceAll('.', ',')}'";
    final whole = total.round(); // arredonda ANTES de separar: 119,6' é 2° 00', não 1° 60'
    if (whole < 60) return "$whole'";
    return "${whole ~/ 60}° ${(whole % 60).toString().padLeft(2, '0')}'";
  }

  /// O nome de um corpo do sistema solar pelo identificador da API.
  static String body(String id) => switch (id) {
    'moon' => 'Lua',
    'sun' => 'Sol',
    'mercury' => 'Mercúrio',
    'venus' => 'Vênus',
    'mars' => 'Marte',
    'jupiter' => 'Júpiter',
    'saturn' => 'Saturno',
    'uranus' => 'Urano',
    'neptune' => 'Netuno',
    _ => id,
  };

  static String role(String role) => switch (role) {
    'owner' => 'Dono',
    'operator' => 'Operador',
    'viewer' => 'Visitante',
    _ => role,
  };

  static String roleHint(String role) => switch (role) {
    'owner' => 'faz tudo, inclusive parear e revogar celulares',
    'operator' => 'observa e comanda, mas não administra',
    'viewer' => 'só acompanha',
    _ => '',
  };

  /// Por que um item do plano não cabe na noite.
  static String planStatus(String status) => switch (status) {
    'never_up' => 'não sobe o bastante nesta noite',
    'after_dawn' => 'termina depois do amanhecer',
    'sets_early' => 'desce antes de terminar',
    'unknown' => 'sem coordenadas',
    _ => '',
  };

  /// O que aconteceu com um alvo da noite autônoma.
  static String nightStatus(String status, String reason) => switch (status) {
    'pending' => 'na fila',
    'running' => 'agora',
    'done' => 'feito',
    'stopped' => 'parado',
    'failed' => reason == 'not_found' ? 'não achei o alvo' : 'falhou',
    'skipped' => switch (reason) {
      'below_horizon' => 'pulado: não sobe nesta noite',
      'user' => 'pulado por você',
      _ => 'pulado',
    },
    _ => status,
  };
}
