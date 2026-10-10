/// Números e horas como se fala em português, sem depender de pacote de tradução.
abstract final class Fmt {
  /// `52,1` — vírgula decimal.
  static String dec(num value, [int digits = 1]) => value.toStringAsFixed(digits).replaceAll('.', ',');

  /// Altitude em graus inteiros: `52°`.
  static String degrees(num value) => '${value.round()}°';

  /// `21 min`, `2 h 05 min`, `45 s`.
  static String duration(int seconds) {
    if (seconds < 60) return '$seconds s';
    final minutes = seconds ~/ 60;
    if (minutes < 60) return '$minutes min';
    final rest = minutes % 60;
    return rest == 0 ? '${minutes ~/ 60} h' : '${minutes ~/ 60} h ${rest.toString().padLeft(2, '0')} min';
  }

  /// Hora local `20:10`.
  static String clock(DateTime time) {
    final t = time.toLocal();
    return '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
  }

  /// Ascensão reta em horas: `18h 03m`.
  static String ra(double degrees) {
    final hours = (degrees % 360) / 15.0;
    final h = hours.floor();
    final m = ((hours - h) * 60).floor();
    return '${h.toString().padLeft(2, '0')}h ${m.toString().padLeft(2, '0')}m';
  }

  /// Declinação: `-24° 23'`.
  static String dec2(double degrees) {
    final sign = degrees < 0 ? '-' : '+';
    final a = degrees.abs();
    final d = a.floor();
    final m = ((a - d) * 60).floor();
    return "$sign${d.toString().padLeft(2, '0')}° ${m.toString().padLeft(2, '0')}'";
  }

  /// Há quanto tempo: `agora`, `há 12 s`, `há 3 min`.
  static String ago(Duration d) {
    if (d.inSeconds < 3) return 'agora';
    if (d.inSeconds < 60) return 'há ${d.inSeconds} s';
    if (d.inMinutes < 60) return 'há ${d.inMinutes} min';
    return 'há ${d.inHours} h';
  }

  /// Tamanho de arquivo: `1,3 MB`.
  static String bytes(int n) {
    if (n < 1024) return '$n B';
    if (n < 1024 * 1024) return '${dec(n / 1024, 0)} kB';
    return '${dec(n / (1024 * 1024))} MB';
  }
}
