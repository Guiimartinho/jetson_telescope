import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/prefs.dart';
import '../../app/queries.dart';
import '../../core/errors.dart';
import '../../core/format.dart';
import '../../core/strings.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import '../../domain/models.dart';

/// A1 — Atlas: o que dá para observar. "Hoje" já vem ligado e ordena pelo que está melhor
/// agora; o que está baixo ou não cabe no campo aparece na busca, mas diz por quê.
class AtlasScreen extends ConsumerStatefulWidget {
  const AtlasScreen({super.key});

  @override
  ConsumerState<AtlasScreen> createState() => _AtlasScreenState();
}

class _AtlasScreenState extends ConsumerState<AtlasScreen> {
  final _search = TextEditingController();
  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  void _onSearch(String text) {
    _debounce?.cancel();
    // espera a pessoa parar de digitar: uma busca por tecla seria tráfego à toa
    _debounce = Timer(const Duration(milliseconds: 350), () {
      ref.read(atlasFilterProvider.notifier).update((f) => f.copyWith(query: text));
    });
  }

  @override
  Widget build(BuildContext context) {
    final filter = ref.watch(atlasFilterProvider);
    final page = ref.watch(atlasProvider(filter));
    void set(AtlasFilter next) => ref.read(atlasFilterProvider.notifier).state = next;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(AppSpace.s2, AppSpace.s2, AppSpace.s2, AppSpace.s1),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _search,
                  onChanged: _onSearch,
                  textInputAction: TextInputAction.search,
                  decoration: const InputDecoration(
                    hintText: 'Buscar: M42, Orion...',
                    prefixIcon: Padding(
                      padding: EdgeInsets.all(13),
                      child: AppIcon('search', size: 18, color: AppColors.muted),
                    ),
                  ),
                ),
              ),
              IconAction('star', label: 'Meus alvos', onPressed: () => context.go('/atlas/mine')),
              IconAction('target', label: 'Apontar por coordenadas', onPressed: () => context.go('/atlas/coords')),
            ],
          ),
        ),
        SizedBox(
          height: 44,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: AppSpace.s2),
            children: [
              Choice(
                'Hoje',
                selected: filter.tonight,
                onTap: () => set(filter.copyWith(tonight: !filter.tonight)),
              ),
              const SizedBox(width: 8),
              for (final (type, icon) in const [
                ('nebula', 'nebula'),
                ('galaxy', 'galaxy'),
                ('cluster', 'cluster'),
              ]) ...[
                Choice(
                  S.targetType(type),
                  icon: icon,
                  selected: filter.type == type,
                  onTap: () => set(filter.copyWith(type: filter.type == type ? '' : type)),
                ),
                const SizedBox(width: 8),
              ],
              Choice(
                'Cabe no campo',
                selected: filter.fits,
                onTap: () => set(filter.copyWith(fits: !filter.fits)),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppSpace.s1),
        Expanded(
          child: page.when(
            loading: () => const Busy(),
            error: (error, _) => Padding(
              padding: const EdgeInsets.all(AppSpace.s2),
              child: Notice(
                title: 'Não consegui consultar o catálogo',
                text: error is ApiFailure ? S.failure(error) : null,
                actions: [AppButton('Tentar de novo', onPressed: () => ref.invalidate(atlasProvider(filter)))],
              ),
            ),
            data: (data) => data.items.isEmpty
                ? EmptyState(
                    icon: 'atlas',
                    title: filter.query.trim().isEmpty ? 'Nada alto no céu agora' : 'Nenhum alvo com esse nome',
                    text: filter.query.trim().isEmpty
                        ? 'Desligue "Hoje" para ver o catálogo inteiro, ou tire um filtro.'
                        : 'Tente o número do catálogo (M42, NGC 253) ou o nome em inglês.',
                  )
                : ListView.separated(
                    padding: const EdgeInsets.fromLTRB(AppSpace.s2, 0, AppSpace.s2, 96),
                    itemCount: data.items.length + 1,
                    separatorBuilder: (_, _) => const SizedBox(height: 8),
                    itemBuilder: (context, index) => index == data.items.length
                        ? Padding(
                            padding: const EdgeInsets.symmetric(vertical: 8),
                            child: Text(
                              data.total > data.items.length
                                  ? 'Mostrando ${data.items.length} de ${data.total}. Refine a busca para ver outros.'
                                  : (data.total == 1 ? '1 alvo' : '${data.total} alvos'),
                              textAlign: TextAlign.center,
                              style: AppText.small,
                            ),
                          )
                        : TargetRow(target: data.items[index]),
                  ),
          ),
        ),
      ],
    );
  }
}

/// Uma linha do Atlas: miniatura, nome, e por que vale (ou não) a pena agora.
class TargetRow extends ConsumerWidget {
  const TargetRow({super.key, required this.target});

  final Target target;

  static String typeIcon(String type) => switch (type) {
    'galaxy' => 'galaxy',
    'cluster' => 'cluster',
    _ => 'nebula',
  };

  /// A altitude em palavras: "alto 52°", "baixo 12°", "abaixo do horizonte".
  static (String, Color) altitude(Target t) {
    if (!t.isUp) return ('abaixo do horizonte', AppColors.dim);
    if (t.isHigh) return ('alto ${Fmt.degrees(t.altDeg)}', AppColors.ok);
    return ('baixo ${Fmt.degrees(t.altDeg)}', AppColors.gold);
  }

  /// O catálogo diz se o alvo cabe com folga no lado MENOR do sensor (não se sabe para que
  /// lado ele está virado). Quando não cabe, ou é grande ou é pequeno demais.
  static String framing(Target t) => switch (t.fits) {
    true => 'cabe no campo',
    false => (t.sizeArcmin ?? 0) > 60 ? 'grande para o campo' : 'pequeno no campo',
    null => 'tamanho não catalogado',
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final favorite = ref.watch(prefsProvider.select((p) => p.favorites.contains(target.id)));
    final (altText, altColor) = altitude(target);
    final title = target.name == target.id ? target.id : '${target.id}  ${target.name}';
    return Panel(
      padding: const EdgeInsets.fromLTRB(10, 10, 0, 10),
      onTap: () => context.go('/atlas/target/${target.id}'),
      child: Row(
        children: [
          SizedBox.square(
            dimension: 54,
            child: target.hasThumb
                ? LazyImage(load: ref.watch(targetThumbProvider(target.id).future), placeholder: typeIcon(target.type))
                : DecoratedBox(
                    decoration: BoxDecoration(
                      color: AppColors.surface2,
                      borderRadius: BorderRadius.circular(AppSpace.radiusSmall),
                    ),
                    child: Center(child: AppIcon(typeIcon(target.type), color: AppColors.dim)),
                  ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: AppText.heading.copyWith(fontSize: 15),
                ),
                const SizedBox(height: 3),
                Text('${S.targetType(target.type)} · ${framing(target)}', maxLines: 1, style: AppText.small),
                const SizedBox(height: 3),
                StatusText(altText, color: altColor),
              ],
            ),
          ),
          IconAction(
            'star',
            label: favorite ? 'Tirar dos meus alvos' : 'Guardar nos meus alvos',
            color: favorite ? AppColors.gold : AppColors.dim,
            onPressed: () => ref.read(prefsProvider.notifier).toggleFavorite(target.id),
          ),
        ],
      ),
    );
  }
}
