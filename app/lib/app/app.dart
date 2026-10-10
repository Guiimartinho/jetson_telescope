import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/strings.dart';
import '../core/theme.dart';
import 'link.dart';
import 'notices.dart';
import 'prefs.dart';
import 'router.dart';

/// O app: tema escuro sempre, e o modo vermelho como um filtro sobre TUDO — inclusive as
/// imagens —, para não estragar a visão noturna de quem está no escuro.
class TelescopeApp extends ConsumerStatefulWidget {
  const TelescopeApp({super.key});

  @override
  ConsumerState<TelescopeApp> createState() => _TelescopeAppState();
}

class _TelescopeAppState extends ConsumerState<TelescopeApp> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    ref.read(noticeWatcherProvider); // os avisos com a tela apagada acompanham a ligação
    SystemChrome.setSystemUIOverlayStyle(
      const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.light,
        systemNavigationBarColor: AppColors.bg,
        systemNavigationBarIconBrightness: Brightness.light,
      ),
    );
    Future.microtask(() => ref.read(linkProvider.notifier).start());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  /// Fora da vista (tela apagada, outro app na frente) é quando os avisos fazem sentido. Um
  /// instante "inativo" (a cortina de avisos, um diálogo do sistema) não conta.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final hidden = state == AppLifecycleState.paused || state == AppLifecycleState.hidden;
    if (state == AppLifecycleState.resumed || hidden) ref.read(appHiddenProvider.notifier).state = hidden;
  }

  @override
  Widget build(BuildContext context) {
    final red = ref.watch(prefsProvider.select((p) => p.redMode));
    return MaterialApp.router(
      title: S.appName,
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      routerConfig: ref.watch(routerProvider),
      builder: (context, child) {
        final page = child ?? const SizedBox.shrink();
        return red ? ColorFiltered(colorFilter: redModeFilter, child: page) : page;
      },
    );
  }
}
