import 'models.dart';

/// Aplica uma mensagem do canal em tempo real ao estado que o app tem.
///
/// A Jetson manda o retrato inteiro (`state`) ao conectar e quando o estado geral muda; depois,
/// só a parte que mudou (`stack`, `mount`, `progress`...). Assim, durante o empilhamento, o
/// app recebe os números e não redesenha tudo. Mensagem desconhecida não altera nada: uma
/// Jetson mais nova não derruba um app mais velho.
TelescopeState applyLiveMessage(TelescopeState? current, Json message) {
  final type = message['type'];
  final data = message['data'];
  if (type == 'state' && data is Map) {
    return TelescopeState.fromJson(data.cast<String, dynamic>());
  }
  final now = current ?? const TelescopeState();
  if (type == 'night' && data is List) {
    // o andamento da noite é uma lista: um registro por item do plano
    return now.copyWith(
      night: [
        for (final item in data)
          if (item is Map) NightItem.fromJson(item.cast<String, dynamic>()),
      ],
    );
  }
  // estes dois também chegam VAZIOS: a captura acabou e outro modo começou
  if (type == 'capture') {
    return now.copyWith(capture: () => data is Map ? CaptureState.fromJson(data.cast<String, dynamic>()) : null);
  }
  if (type == 'polar') {
    return now.copyWith(polar: () => data is Map ? PolarState.fromJson(data.cast<String, dynamic>()) : null);
  }
  if (data is! Map) return now;
  final part = data.cast<String, dynamic>();
  return switch (type) {
    'progress' => now.copyWith(job: Job.fromJson(part)),
    'mount' => now.copyWith(mount: MountState.fromJson(part)),
    'camera' => now.copyWith(camera: CameraState.fromJson(part)),
    'stack' => now.copyWith(stack: StackState.fromJson(part)),
    'pointing' => now.copyWith(pointing: Pointing.fromJson(part)),
    'queue' => now.copyWith(queue: QueueState.fromJson(part)),
    'system' => now.copyWith(system: SystemState.fromJson(part)),
    'focus' => now.copyWith(focus: FocusState.fromJson(part)),
    _ => now,
  };
}
