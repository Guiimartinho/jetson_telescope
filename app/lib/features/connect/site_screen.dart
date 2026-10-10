import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/link.dart';
import '../../core/errors.dart';
import '../../core/format.dart';
import '../../core/strings.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import '../../data/location.dart';

/// C7 — Local e hora. No campo a Jetson não tem internet nem GPS, e a montagem acorda achando
/// que é o ano 2000: quem sabe onde e quando estamos é o celular. A hora vai junto, sempre a
/// do celular; o local é o GPS dele ou o que for digitado.
class SiteScreen extends ConsumerStatefulWidget {
  const SiteScreen({super.key});

  @override
  ConsumerState<SiteScreen> createState() => _SiteScreenState();
}

class _SiteScreenState extends ConsumerState<SiteScreen> {
  final _lat = TextEditingController();
  final _lon = TextEditingController();
  bool _busy = false;
  String? _problem;
  String? _done;

  @override
  void dispose() {
    _lat.dispose();
    _lon.dispose();
    super.dispose();
  }

  Future<void> _send(double lat, double lon, {double elevM = 0, double? accuracyM}) async {
    setState(() {
      _busy = true;
      _problem = _done = null;
    });
    try {
      final result = await ref
          .read(linkProvider.notifier)
          .sendSite(lat: lat, lon: lon, elevM: elevM, accuracyM: accuracyM);
      if (!mounted) return;
      setState(
        () => _done = result.mountUpdated
            ? 'Enviado. A montagem já recebeu a hora e o local.'
            : 'Enviado. A montagem recebe assim que estiver conectada.',
      );
    } on ApiFailure catch (failure) {
      if (mounted) setState(() => _problem = S.failure(failure));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _useGps() async {
    setState(() {
      _busy = true;
      _problem = _done = null;
    });
    try {
      final fix = await ref.read(locationProvider).current();
      _lat.text = fix.lat.toStringAsFixed(5);
      _lon.text = fix.lon.toStringAsFixed(5);
      await _send(fix.lat, fix.lon, elevM: fix.elevM, accuracyM: fix.accuracyM);
    } on LocationFailure catch (failure) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _problem = switch (failure.problem) {
          LocationProblem.serviceOff => 'A localização do celular está desligada. Ligue-a, ou digite as coordenadas.',
          LocationProblem.denied => 'Sem permissão de localização. Você pode digitar as coordenadas.',
          LocationProblem.deniedForever =>
            'A permissão de localização foi negada nas configurações do celular. Digite as coordenadas.',
          LocationProblem.unavailable => 'Não consegui o local agora. Digite as coordenadas.',
        };
      });
    }
  }

  void _sendTyped() {
    final lat = double.tryParse(_lat.text.trim().replaceAll(',', '.'));
    final lon = double.tryParse(_lon.text.trim().replaceAll(',', '.'));
    if (lat == null || lon == null || lat.abs() > 90 || lon.abs() > 180) {
      setState(() => _problem = 'Latitude de -90 a 90 e longitude de -180 a 180, em graus (sul e oeste negativos).');
      return;
    }
    _send(lat, lon);
  }

  @override
  Widget build(BuildContext context) {
    final info = ref.watch(linkProvider.select((l) => l.info));
    final synced = info?.clockSynced ?? false;
    return SubPage(
      title: 'Local e hora',
      child: ListView(
        padding: const EdgeInsets.all(AppSpace.s2),
        children: [
          Panel(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                StatusText(
                  synced ? 'o telescópio sabe a hora e o local' : 'o telescópio ainda não sabe onde está',
                  color: synced ? AppColors.ok : AppColors.gold,
                ),
                const SizedBox(height: 6),
                if (info != null)
                  InfoLine(
                    icon: 'pin',
                    label: 'No telescópio',
                    value: '${Fmt.dec(info.site.lat, 3)}°, ${Fmt.dec(info.site.lon, 3)}°',
                  ),
                InfoLine(icon: 'clock', label: 'Hora do celular', value: Fmt.clock(DateTime.now())),
              ],
            ),
          ),
          const SizedBox(height: AppSpace.s2),
          const Text(
            'O telescópio usa a hora e o local para saber o que está acima do horizonte e para '
            'apontar. A hora enviada é sempre a deste celular.',
            style: AppText.small,
          ),
          const SizedBox(height: AppSpace.s2),
          AppButton(
            'Usar o local deste celular',
            icon: 'pin',
            tone: ButtonTone.primary,
            big: true,
            expand: true,
            onPressed: _busy ? null : _useGps,
          ),
          const SizedBox(height: AppSpace.s3),
          const SectionLabel('Ou digite as coordenadas'),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _lat,
                  keyboardType: const TextInputType.numberWithOptions(signed: true, decimal: true),
                  decoration: const InputDecoration(labelText: 'Latitude', hintText: '-23,55'),
                ),
              ),
              const SizedBox(width: AppSpace.s1),
              Expanded(
                child: TextField(
                  controller: _lon,
                  keyboardType: const TextInputType.numberWithOptions(signed: true, decimal: true),
                  decoration: const InputDecoration(labelText: 'Longitude', hintText: '-46,63'),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpace.s1),
          AppButton('Enviar', expand: true, onPressed: _busy ? null : _sendTyped),
          const SizedBox(height: AppSpace.s2),
          if (_busy) const Busy(),
          if (_done != null) Notice(title: _done!, bad: false, icon: 'check'),
          if (_problem != null) Notice(title: _problem!),
        ],
      ),
    );
  }
}
