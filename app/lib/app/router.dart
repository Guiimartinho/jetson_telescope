import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../domain/pairing.dart';
import '../features/atlas/atlas_screen.dart';
import '../features/atlas/coords_screen.dart';
import '../features/atlas/my_targets_screen.dart';
import '../features/atlas/target_screen.dart';
import '../features/connect/code_screen.dart';
import '../features/connect/find_screen.dart';
import '../features/connect/identity_screen.dart';
import '../features/connect/pairing_screen.dart';
import '../features/connect/scan_screen.dart';
import '../features/connect/site_screen.dart';
import '../features/connect/splash_screen.dart';
import '../features/connect/wifi_screen.dart';
import '../features/device/camera_screen.dart';
import '../features/device/device_screen.dart';
import '../features/device/focus_screen.dart';
import '../features/device/more_screens.dart';
import '../features/device/mount_screen.dart';
import '../features/device/network_screen.dart';
import '../features/device/phones_screen.dart';
import '../features/device/polar_screen.dart';
import '../features/device/prefs_screen.dart';
import '../features/device/system_screen.dart';
import '../features/device/updates_screen.dart';
import '../features/gallery/export_screen.dart';
import '../features/gallery/gallery_screen.dart';
import '../features/gallery/session_screen.dart';
import '../features/gallery/studio_screen.dart';
import '../features/observe/observe_screen.dart';
import '../features/plan/plan_more_screens.dart';
import '../features/plan/plan_screen.dart';
import '../features/shell/shell.dart';
import 'link.dart';

/// Para onde a fase da ligação manda: quem não tem telescópio vai achar um; quem tem, observa.
String? redirectFor(LinkPhase phase, String location) {
  final connecting = location.startsWith('/connect');
  switch (phase) {
    case LinkPhase.starting:
    case LinkPhase.connecting:
      return location == '/' ? null : '/';
    case LinkPhase.noDevice:
    case LinkPhase.offline:
    case LinkPhase.revoked:
      return connecting && location != '/connect/identity' ? null : '/connect';
    case LinkPhase.identityChanged:
      return location == '/connect/identity' ? null : '/connect/identity';
    case LinkPhase.online:
      return (location == '/' || connecting) ? '/observe' : null;
    case LinkPhase.reconnecting:
      // sem sinal, ainda dá para ir entrar no WiFi do próprio telescópio (ele saiu de casa)
      if (location == '/connect/wifi') return null;
      return (location == '/' || connecting) ? '/observe' : null;
  }
}

final routerProvider = Provider<GoRouter>((ref) {
  // o roteador reavalia o destino sempre que a fase da ligação muda
  final phase = ValueNotifier(ref.read(linkProvider).phase);
  ref.listen(linkProvider.select((l) => l.phase), (_, next) => phase.value = next);
  ref.onDispose(phase.dispose);

  return GoRouter(
    initialLocation: '/',
    refreshListenable: phase,
    redirect: (context, state) => redirectFor(ref.read(linkProvider).phase, state.matchedLocation),
    routes: [
      GoRoute(path: '/', builder: (_, _) => const SplashScreen()),
      GoRoute(
        path: '/connect',
        builder: (_, _) => const FindScreen(),
        routes: [
          GoRoute(path: 'scan', builder: (_, _) => const ScanScreen()),
          GoRoute(path: 'code', builder: (_, _) => const CodeScreen()),
          GoRoute(
            path: 'pairing',
            builder: (_, state) => PairingScreen(code: state.extra! as PairingCode),
          ),
          GoRoute(path: 'identity', builder: (_, _) => const IdentityChangedScreen()),
          GoRoute(path: 'wifi', builder: (_, _) => const TelescopeWifiScreen()),
        ],
      ),
      StatefulShellRoute.indexedStack(
        builder: (_, _, navigationShell) => Shell(navigationShell: navigationShell),
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/atlas',
                builder: (_, _) => const AtlasScreen(),
                routes: [
                  GoRoute(
                    path: 'target/:id',
                    builder: (_, state) => TargetScreen(id: state.pathParameters['id']!),
                  ),
                  GoRoute(path: 'coords', builder: (_, _) => const CoordsScreen()),
                  GoRoute(path: 'mine', builder: (_, _) => const MyTargetsScreen()),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/plan',
                builder: (_, _) => const PlanScreen(),
                routes: [
                  GoRoute(
                    path: 'item/:id',
                    builder: (_, state) => PlanItemScreen(id: state.pathParameters['id']!),
                  ),
                  GoRoute(
                    path: 'mosaic/:target',
                    builder: (_, state) => MosaicScreen(
                      target: state.pathParameters['target']!,
                      itemId: state.uri.queryParameters['item'],
                    ),
                  ),
                  GoRoute(path: 'special', builder: (_, _) => const SpecialScreen()),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/observe',
                builder: (_, _) => const ObserveScreen(),
                routes: [
                  GoRoute(
                    path: 'focus',
                    builder: (_, _) => const FocusScreen(back: '/observe'),
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/gallery',
                builder: (_, _) => const GalleryScreen(),
                routes: [
                  GoRoute(
                    path: ':id',
                    builder: (_, state) => SessionScreen(id: state.pathParameters['id']!),
                    routes: [
                      GoRoute(
                        path: 'studio',
                        builder: (_, state) => StudioScreen(id: state.pathParameters['id']!),
                      ),
                      GoRoute(
                        path: 'export',
                        builder: (_, state) => ExportScreen(id: state.pathParameters['id']!),
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/device',
                builder: (_, _) => const DeviceScreen(),
                routes: [
                  GoRoute(path: 'system', builder: (_, _) => const SystemScreen()),
                  GoRoute(path: 'prefs', builder: (_, _) => const PrefsScreen()),
                  GoRoute(path: 'site', builder: (_, _) => const SiteScreen()),
                  GoRoute(
                    path: 'mount',
                    builder: (_, _) => const MountScreen(),
                    routes: [GoRoute(path: 'polar', builder: (_, _) => const PolarScreen())],
                  ),
                  GoRoute(path: 'focus', builder: (_, _) => const FocusScreen()),
                  GoRoute(path: 'camera', builder: (_, _) => const CameraScreen()),
                  GoRoute(
                    path: 'network',
                    builder: (_, _) => const NetworkScreen(),
                    routes: [GoRoute(path: 'home', builder: (_, _) => const HomeWifiScreen())],
                  ),
                  GoRoute(path: 'phones', builder: (_, _) => const PhonesScreen()),
                  GoRoute(path: 'updates', builder: (_, _) => const UpdatesScreen()),
                  GoRoute(path: 'about', builder: (_, _) => const AboutScreen()),
                  GoRoute(path: 'name', builder: (_, _) => const NameScreen()),
                ],
              ),
            ],
          ),
        ],
      ),
    ],
  );
});
