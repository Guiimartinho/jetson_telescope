import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';

/// Onde o celular está.
class GeoFix {
  const GeoFix({required this.lat, required this.lon, this.elevM = 0, this.accuracyM});

  final double lat;
  final double lon;
  final double elevM;
  final double? accuracyM;
}

/// Por que não deu para saber o local — cada caso tem uma saída diferente na tela.
enum LocationProblem { serviceOff, denied, deniedForever, unavailable }

class LocationFailure implements Exception {
  const LocationFailure(this.problem);

  final LocationProblem problem;
}

/// A porta do GPS: as telas pedem o local sem saber de plugin.
abstract interface class LocationSource {
  Future<GeoFix> current();
}

class DeviceLocation implements LocationSource {
  const DeviceLocation();

  @override
  Future<GeoFix> current() async {
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        throw const LocationFailure(LocationProblem.serviceOff);
      }
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied) throw const LocationFailure(LocationProblem.denied);
      if (permission == LocationPermission.deniedForever) {
        throw const LocationFailure(LocationProblem.deniedForever);
      }
      // precisão de bairro basta: a montagem usa o local para saber o que está acima do horizonte
      final p = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.medium, timeLimit: Duration(seconds: 20)),
      );
      return GeoFix(lat: p.latitude, lon: p.longitude, elevM: p.altitude, accuracyM: p.accuracy);
    } on LocationFailure {
      rethrow;
    } on Object {
      throw const LocationFailure(LocationProblem.unavailable);
    }
  }
}

final locationProvider = Provider<LocationSource>((ref) => const DeviceLocation());
