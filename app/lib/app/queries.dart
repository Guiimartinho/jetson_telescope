import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../domain/models.dart';
import 'link.dart';

/// O que as telas buscam no telescópio. Tudo depende do `apiProvider`: trocar de telescópio
/// (ou entrar na demonstração) refaz as buscas sozinho.

/// Filtros do Atlas.
class AtlasFilter {
  const AtlasFilter({this.query = '', this.type = '', this.tonight = true, this.fits = false});

  final String query;
  final String type;

  /// "Hoje": só o que está alto agora, do mais alto para o mais baixo.
  final bool tonight;
  final bool fits;

  AtlasFilter copyWith({String? query, String? type, bool? tonight, bool? fits}) => AtlasFilter(
    query: query ?? this.query,
    type: type ?? this.type,
    tonight: tonight ?? this.tonight,
    fits: fits ?? this.fits,
  );

  @override
  bool operator ==(Object other) =>
      other is AtlasFilter &&
      other.query == query &&
      other.type == type &&
      other.tonight == tonight &&
      other.fits == fits;

  @override
  int get hashCode => Object.hash(query, type, tonight, fits);
}

final atlasFilterProvider = StateProvider<AtlasFilter>((ref) => const AtlasFilter());

final atlasProvider = FutureProvider.autoDispose.family<TargetPage, AtlasFilter>((ref, filter) {
  // quem digita uma busca quer achar o alvo, esteja ele alto ou não
  final searching = filter.query.trim().isNotEmpty;
  return ref
      .watch(apiProvider)
      .targets(
        query: filter.query.trim(),
        type: filter.type,
        visible: filter.tonight && !searching,
        fits: filter.fits,
        limit: 60,
      );
});

/// O melhor alvo para agora: o mais alto que cabe no nosso campo.
final suggestedTargetProvider = FutureProvider.autoDispose<Target?>((ref) async {
  final page = await ref.watch(apiProvider).targets(visible: true, fits: true, limit: 1);
  return page.items.firstOrNull;
});

final targetDetailProvider = FutureProvider.autoDispose.family<TargetDetail, String>(
  (ref, id) => ref.watch(apiProvider).target(id),
);

/// Miniaturas: ficam guardadas enquanto o telescópio for o mesmo (a lista rola sem rebuscar).
final targetThumbProvider = FutureProvider.family<Uint8List?, String>(
  (ref, id) => ref.watch(apiProvider).targetThumb(id),
);

final sessionsProvider = FutureProvider.autoDispose<List<Session>>((ref) => ref.watch(apiProvider).sessions());

final sessionThumbProvider = FutureProvider.family<Uint8List?, String>(
  (ref, id) => ref.watch(apiProvider).sessionImage(id, thumb: true),
);

final sessionImageProvider = FutureProvider.autoDispose.family<Uint8List?, String>(
  (ref, id) => ref.watch(apiProvider).sessionImage(id),
);

final presetsProvider = FutureProvider.autoDispose<RenderPresets>((ref) => ref.watch(apiProvider).presets());

final systemProvider = FutureProvider.autoDispose<SystemInfo>((ref) => ref.watch(apiProvider).system());

/// A fila da noite, com os horários que o telescópio calculou.
final planProvider = FutureProvider.autoDispose<NightPlan>((ref) => ref.watch(apiProvider).plan());

final solarProvider = FutureProvider.autoDispose<List<SolarBody>>((ref) => ref.watch(apiProvider).solar());

final cameraProvider = FutureProvider.autoDispose<CameraInfo>((ref) => ref.watch(apiProvider).camera());

final networkProvider = FutureProvider.autoDispose<NetworkInfo>((ref) => ref.watch(apiProvider).network());

/// As redes que o TELESCÓPIO enxerga agora.
final networkScanProvider = FutureProvider.autoDispose<List<WifiNetwork>>(
  (ref) => ref.watch(apiProvider).scanNetworks(),
);

final updateProvider = FutureProvider.autoDispose<UpdateInfo>((ref) => ref.watch(apiProvider).update());

final clientsProvider = FutureProvider.autoDispose<List<PairedClient>>((ref) => ref.watch(apiProvider).clients());

/// A grade de um mosaico: (alvo, linhas, colunas, sobreposição).
final mosaicProvider = FutureProvider.autoDispose.family<MosaicGrid, (String, int, int, double)>(
  (ref, key) => ref.watch(apiProvider).mosaic(target: key.$1, rows: key.$2, cols: key.$3, overlap: key.$4),
);

final histogramProvider = FutureProvider.autoDispose.family<List<double>, int>(
  // a chave é um contador de fotos: o histograma é rebuscado conforme a imagem cresce
  (ref, tick) => ref.watch(apiProvider).histogram(),
);
