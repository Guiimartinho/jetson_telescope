import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/commands.dart';
import '../../app/link.dart';
import '../../app/network_switch.dart';
import '../../app/prefs.dart';
import '../../app/queries.dart';
import '../../core/errors.dart';
import '../../core/strings.dart';
import '../../core/theme.dart';
import '../../core/widgets/kit.dart';
import '../../domain/models.dart';

Widget _failed(WidgetRef ref, Object error, ProviderOrFamily provider) => Padding(
  padding: const EdgeInsets.all(AppSpace.s2),
  child: Notice(
    title: 'O telescópio não respondeu',
    text: error is ApiFailure ? S.failure(error) : null,
    actions: [AppButton('Tentar de novo', onPressed: () => ref.invalidate(provider))],
  ),
);

/// Q4 — trocar de rede derruba a conexão: avisa antes.
Future<bool> confirmSwitch(BuildContext context) => confirm(
  context,
  title: 'Trocar o WiFi do telescópio?',
  text: 'O telescópio vai trocar de WiFi e esta conexão vai cair por alguns segundos.',
  yes: 'Trocar',
);

/// O que dizer quando o pedido de troca termina.
String _outcomeText(SwitchOutcome outcome) => switch (outcome) {
  Switched(:final info) =>
    info.atHome ? 'O telescópio está em "${info.wifiSsid}".' : 'O telescópio está no WiFi próprio.',
  SwitchRefused(:final failure) => S.failure(failure),
  SwitchFailed(:final code) => S.networkError(code),
  SwitchLost() =>
    'Não reencontrei o telescópio. Veja se o celular está no mesmo WiFi que ele; o app continua procurando.',
};

/// D5 — Rede: como o telescópio está ligado, o WiFi que ele mesmo cria (para o campo) e as
/// redes de casa que ele guarda. Só o dono troca.
///
/// Num aparelho em que isso ainda não foi habilitado (o de verdade, hoje), a tela mostra e
/// explica.
class NetworkScreen extends ConsumerStatefulWidget {
  const NetworkScreen({super.key});

  @override
  ConsumerState<NetworkScreen> createState() => _NetworkScreenState();
}

class _NetworkScreenState extends ConsumerState<NetworkScreen> {
  bool _showPassword = false;
  bool _switching = false;

  /// Uma troca: pergunta (Q4), pede, espera o telescópio reaparecer e conta como terminou.
  Future<void> _switchTo(String mode) async {
    if (!await confirmSwitch(context) || !mounted) return;
    setState(() => _switching = true);
    final outcome = await ref
        .read(networkSwitcherProvider)
        .run((api) => api.setNetworkMode(mode), toField: mode == 'field');
    if (!mounted) return;
    setState(() => _switching = false);
    ref.invalidate(networkProvider);
    ref.read(toastProvider.notifier).state = Toast(_outcomeText(outcome), bad: outcome is! Switched);
  }

  Future<void> _forget(String ssid) async {
    final yes = await confirm(
      context,
      title: 'Esquecer "$ssid"?',
      text: 'O telescópio deixa de entrar nesta rede sozinho. Para voltar, será preciso a senha.',
      yes: 'Esquecer',
      danger: true,
    );
    if (!yes) return;
    final done = await ref.read(commandsProvider).act((api) async {
      await api.forgetNetwork(ssid);
      return true;
    });
    if (done == true) ref.invalidate(networkProvider);
  }

  Future<void> _changePassword() async {
    final psk = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: AppColors.surface,
      isScrollControlled: true,
      builder: (_) => const _PasswordSheet(),
    );
    if (psk == null) return;
    final commands = ref.read(commandsProvider);
    final done = await commands.act((api) async {
      await api.setHotspotPassword(psk);
      return true;
    });
    if (done != true) return;
    await ref.read(linkProvider.notifier).refreshWifi(); // o app guarda a senha nova
    ref.invalidate(networkProvider);
    commands.say('Senha do WiFi do telescópio trocada.');
  }

  @override
  Widget build(BuildContext context) {
    final network = ref.watch(networkProvider);
    final link = ref.watch(linkProvider);
    return SubPage(
      title: 'Rede',
      onBack: () => context.go('/device'),
      child: network.when(
        loading: () => const Busy(),
        error: (error, _) => ListView(
          children: [
            _failed(ref, error, networkProvider),
            // fora de casa o telescópio está no WiFi que ele mesmo cria: o caminho é entrar nele
            if (link.device?.knowsWifi ?? false)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: AppSpace.s2),
                child: AppButton(
                  'Entrar no WiFi do telescópio',
                  icon: 'wifi',
                  expand: true,
                  onPressed: () => context.go('/connect/wifi'),
                ),
              ),
          ],
        ),
        data: (n) {
          final hotspot = n.hotspot;
          // a senha do WiFi próprio só chega para o dono: é assim que a tela sabe quem é
          final owner = hotspot?.psk != null;
          return ListView(
            padding: const EdgeInsets.fromLTRB(AppSpace.s2, 0, AppSpace.s2, 96),
            children: [
              Panel(
                padding: const EdgeInsets.symmetric(horizontal: AppSpace.s2, vertical: 8),
                child: Column(
                  children: [
                    InfoLine(
                      icon: 'wifi',
                      label: 'Modo',
                      value: switch (n.mode) {
                        'home' => n.wifiSsid == null ? 'WiFi de casa' : 'WiFi de casa: ${n.wifiSsid}',
                        'field' => 'WiFi do telescópio',
                        _ => 'não informado',
                      },
                    ),
                    if (n.atHome && n.wifiSsid != null)
                      InfoLine(icon: 'chart', label: 'Sinal', value: S.signal(n.wifiSignal)),
                    if (n.hostname.isNotEmpty) InfoLine(icon: 'chip', label: 'Nome na rede', value: n.hostname),
                    InfoLine(
                      icon: 'lock',
                      label: 'Este celular fala com',
                      value: link.demo
                          ? 'demonstração'
                          : '${link.device?.host ?? n.address}:${link.device?.port ?? n.port}',
                    ),
                  ],
                ),
              ),
              const SizedBox(height: AppSpace.s3),
              if (!n.enabled)
                const Notice(
                  bad: false,
                  icon: 'info',
                  title: 'Trocar de rede pelo app ainda não está habilitado',
                  text:
                      'O telescópio vai poder criar o próprio WiFi para o campo e entrar no WiFi de casa por '
                      'aqui. Como uma troca malfeita corta o acesso a ele, isso só é ligado depois de testado '
                      'na bancada, com você ao lado. Por enquanto a rede dele é configurada no próprio aparelho.',
                )
              else ...[
                if (_switching) ...[
                  const Panel(
                    child: Row(
                      children: [
                        Busy(),
                        SizedBox(width: 14),
                        Expanded(
                          child: Text(
                            'O telescópio está trocando de rede. A conexão cai por alguns segundos; o app o '
                            'reencontra sozinho.',
                            style: AppText.body,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: AppSpace.s2),
                ],
                if (n.lastError != null && !_switching) ...[
                  Notice(title: 'A última troca não deu certo', text: S.networkError(n.lastError)),
                  const SizedBox(height: AppSpace.s2),
                ],
                if (!owner) ...[
                  const Notice(
                    bad: false,
                    icon: 'lock',
                    title: 'Só o dono troca a rede do telescópio',
                    text: 'Este celular pode ver como ele está ligado, mas não mudar.',
                  ),
                  const SizedBox(height: AppSpace.s2),
                ],
                if (hotspot != null) ...[
                  const SectionLabel('WiFi do telescópio'),
                  Panel(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(child: Text(hotspot.ssid, style: AppText.heading.copyWith(fontSize: 15))),
                            StatusText(
                              hotspot.active ? 'ligado agora' : 'desligado',
                              color: hotspot.active ? AppColors.ok : AppColors.muted,
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),
                        const Text(
                          'É o WiFi que o telescópio cria onde não há roteador. Não tem internet: serve só para '
                          'o celular falar com ele.',
                          style: AppText.small,
                        ),
                        if (owner) ...[
                          const SizedBox(height: AppSpace.s1),
                          Row(
                            children: [
                              const Text('Senha', style: AppText.small),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Text(
                                  _showPassword ? hotspot.psk! : '•' * 10,
                                  style: AppText.number.copyWith(fontSize: 15),
                                ),
                              ),
                              IconAction(
                                'eye',
                                label: _showPassword ? 'Esconder a senha' : 'Mostrar a senha',
                                color: _showPassword ? AppColors.accent : AppColors.muted,
                                onPressed: () => setState(() => _showPassword = !_showPassword),
                              ),
                            ],
                          ),
                          AppButton('Mudar a senha', onPressed: _switching ? null : _changePassword),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(height: AppSpace.s3),
                ],
                const SectionLabel('WiFi de casa'),
                if (n.known.isEmpty)
                  const Padding(
                    padding: EdgeInsets.only(bottom: AppSpace.s1),
                    child: Text(
                      'O telescópio ainda não guarda nenhuma rede de casa. Com uma guardada, ele entra nela '
                      'sozinho quando estiver ao alcance.',
                      style: AppText.small,
                    ),
                  ),
                for (final ssid in n.known) ...[
                  Panel(
                    child: Row(
                      children: [
                        const AppIcon('wifi', color: AppColors.muted),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(ssid, style: AppText.heading.copyWith(fontSize: 15)),
                              Text(ssid == n.wifiSsid ? 'em uso agora' : 'guardada', style: AppText.small),
                            ],
                          ),
                        ),
                        if (owner) AppButton('Esquecer', onPressed: _switching ? null : () => _forget(ssid)),
                      ],
                    ),
                  ),
                  const SizedBox(height: 8),
                ],
                if (owner) ...[
                  AppButton(
                    n.known.isEmpty ? 'Entrar no WiFi de casa' : 'Entrar em outra rede',
                    icon: 'wifi',
                    expand: true,
                    onPressed: _switching ? null : () => context.go('/device/network/home'),
                  ),
                  const SizedBox(height: AppSpace.s3),
                  const SectionLabel('Trocar'),
                  if (n.inField)
                    AppButton(
                      'Passar para o WiFi de casa',
                      tone: ButtonTone.primary,
                      big: true,
                      expand: true,
                      onPressed: _switching || n.known.isEmpty ? null : () => _switchTo('home'),
                    )
                  else
                    AppButton(
                      'Passar para o WiFi do telescópio',
                      tone: ButtonTone.primary,
                      big: true,
                      expand: true,
                      onPressed: _switching ? null : () => _switchTo('field'),
                    ),
                  const Padding(
                    padding: EdgeInsets.only(top: 6),
                    child: Text(
                      'Trocar derruba esta conexão por alguns segundos. O app avisa antes e reencontra o '
                      'telescópio depois.',
                      style: AppText.small,
                    ),
                  ),
                ],
              ],
            ],
          );
        },
      ),
    );
  }
}

/// A senha nova do WiFi do telescópio: de 8 a 63 caracteres, como todo WiFi.
class _PasswordSheet extends StatefulWidget {
  const _PasswordSheet();

  @override
  State<_PasswordSheet> createState() => _PasswordSheetState();
}

class _PasswordSheetState extends State<_PasswordSheet> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final length = _controller.text.length;
    final valid = length >= 8 && length <= 63;
    return SafeArea(
      child: SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(
          AppSpace.s2,
          AppSpace.s2,
          AppSpace.s2,
          AppSpace.s2 + MediaQuery.viewInsetsOf(context).bottom,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Senha do WiFi do telescópio', style: AppText.heading),
            const SizedBox(height: 4),
            const Text(
              'Os outros celulares vão precisar da senha nova para entrar no WiFi dele.',
              style: AppText.small,
            ),
            const SizedBox(height: AppSpace.s2),
            TextField(
              controller: _controller,
              autofocus: true,
              maxLength: 63,
              onChanged: (_) => setState(() {}),
              decoration: const InputDecoration(labelText: 'Senha nova', helperText: 'de 8 a 63 caracteres'),
            ),
            const SizedBox(height: AppSpace.s1),
            AppButton(
              'Salvar a senha',
              tone: ButtonTone.primary,
              big: true,
              expand: true,
              onPressed: valid ? () => Navigator.of(context).pop(_controller.text) : null,
            ),
          ],
        ),
      ),
    );
  }
}

// ------------------------------------------------------------- C8: WiFi de casa
enum _Stage { choose, password, switching, done, failed }

/// C8 — WiFi de casa: as redes que o TELESCÓPIO enxerga, a senha, e a troca. O telescópio
/// guarda a rede e passa a entrar nela sozinho; no campo, volta a criar o próprio WiFi.
///
/// Se a senha estiver errada ele continua onde estava e a tela diz; se ele trocar de rede, o
/// app o reencontra.
class HomeWifiScreen extends ConsumerStatefulWidget {
  const HomeWifiScreen({super.key});

  @override
  ConsumerState<HomeWifiScreen> createState() => _HomeWifiScreenState();
}

class _HomeWifiScreenState extends ConsumerState<HomeWifiScreen> {
  final _password = TextEditingController();
  _Stage _stage = _Stage.choose;
  WifiNetwork? _chosen;
  SwitchOutcome? _outcome;
  bool _showPassword = false;

  @override
  void initState() {
    super.initState();
    // quem chegou aqui pelo convite do primeiro uso já o viu: não precisa aparecer de novo
    Future.microtask(() {
      if (mounted && ref.read(prefsProvider).offerHomeWifi) ref.read(prefsProvider.notifier).setOfferHomeWifi(false);
    });
  }

  @override
  void dispose() {
    _password.dispose();
    super.dispose();
  }

  void _pick(WifiNetwork network) {
    _password.clear();
    setState(() {
      _chosen = network;
      _outcome = null;
      _stage = network.secure && !network.known ? _Stage.password : _Stage.choose;
    });
    if (!network.secure || network.known) _join(); // aberta, ou a senha já está guardada
  }

  Future<void> _join() async {
    final network = _chosen;
    if (network == null) return;
    final psk = _password.text;
    if (!await confirmSwitch(context) || !mounted) return;
    setState(() => _stage = _Stage.switching);
    final outcome = await ref
        .read(networkSwitcherProvider)
        .run((api) => api.joinNetwork(network.ssid, psk: psk.isEmpty ? null : psk));
    if (!mounted) return;
    ref.invalidate(networkProvider);
    setState(() {
      _outcome = outcome;
      _stage = outcome is Switched && outcome.info.wifiSsid == network.ssid ? _Stage.done : _Stage.failed;
    });
  }

  @override
  Widget build(BuildContext context) => SubPage(
    title: 'WiFi de casa',
    onBack: () => context.go('/device/network'),
    child: ListView(
      padding: const EdgeInsets.fromLTRB(AppSpace.s2, 0, AppSpace.s2, 96),
      children: switch (_stage) {
        _Stage.choose => _choose(),
        _Stage.password => _askPassword(),
        _Stage.switching => [
          Panel(
            child: Row(
              children: [
                const Busy(),
                const SizedBox(width: 14),
                Expanded(
                  child: Text(
                    'O telescópio está entrando em "${_chosen?.ssid}". A conexão cai por alguns segundos; '
                    'o app o reencontra sozinho.',
                    style: AppText.body,
                  ),
                ),
              ],
            ),
          ),
        ],
        _Stage.done => [
          Notice(
            bad: false,
            icon: 'check',
            title: 'O telescópio entrou em "${_chosen?.ssid}"',
            text:
                'Daqui em diante ele entra nesta rede sozinho quando estiver em casa. No campo, volta a '
                'criar o próprio WiFi.',
            actions: [AppButton('Concluir', tone: ButtonTone.primary, onPressed: () => context.go('/device/network'))],
          ),
        ],
        _Stage.failed => [
          Notice(
            title: 'O telescópio não entrou em "${_chosen?.ssid}"',
            text: _outcomeText(_outcome ?? const SwitchLost()),
            actions: [
              if (_chosen?.secure ?? false)
                AppButton(
                  'Tentar outra senha',
                  tone: ButtonTone.primary,
                  onPressed: () => setState(() => _stage = _Stage.password),
                ),
              AppButton('Escolher outra rede', onPressed: () => setState(() => _stage = _Stage.choose)),
            ],
          ),
        ],
      },
    ),
  );

  List<Widget> _choose() {
    final scan = ref.watch(networkScanProvider);
    return [
      const Text(
        'Estas são as redes que o TELESCÓPIO enxerga de onde ele está. Escolha a da sua casa: ele guarda a '
        'senha e passa a entrar nela sozinho.',
        style: AppText.small,
      ),
      const SizedBox(height: AppSpace.s2),
      ...scan.when(
        loading: () => [const Padding(padding: EdgeInsets.all(AppSpace.s3), child: Busy())],
        error: (error, _) => [_failed(ref, error, networkScanProvider)],
        data: (networks) => [
          if (networks.isEmpty)
            const EmptyState(
              icon: 'wifi',
              title: 'Nenhuma rede ao alcance do telescópio',
              text: 'Aproxime o telescópio do roteador e procure de novo.',
            ),
          for (final network in networks) ...[
            Panel(
              onTap: () => _pick(network),
              child: Row(
                children: [
                  const AppIcon('wifi', color: AppColors.muted),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(network.ssid, style: AppText.heading.copyWith(fontSize: 15)),
                        Text(
                          '${S.signal(network.signal)}'
                          '${network.secure ? '' : ' · aberta, sem senha'}'
                          '${network.known ? ' · senha guardada' : ''}',
                          style: AppText.small,
                        ),
                      ],
                    ),
                  ),
                  if (network.secure) const AppIcon('lock', size: 16, color: AppColors.muted),
                  const SizedBox(width: 6),
                  const AppIcon('chevron', size: 18, color: AppColors.muted),
                ],
              ),
            ),
            const SizedBox(height: 8),
          ],
          const SizedBox(height: AppSpace.s1),
          AppButton('Procurar de novo', expand: true, onPressed: () => ref.invalidate(networkScanProvider)),
        ],
      ),
      const SizedBox(height: AppSpace.s1),
      AppButton('Agora não', expand: true, onPressed: () => context.go('/device/network')),
    ];
  }

  List<Widget> _askPassword() => [
    Text('Senha de "${_chosen?.ssid}"', style: AppText.heading),
    const SizedBox(height: 4),
    const Text(
      'A senha vai para o telescópio pelo canal cifrado e fica guardada nele, não no celular.',
      style: AppText.small,
    ),
    const SizedBox(height: AppSpace.s2),
    TextField(
      controller: _password,
      autofocus: true,
      obscureText: !_showPassword,
      enableSuggestions: false,
      autocorrect: false,
      maxLength: 63,
      onChanged: (_) => setState(() {}),
      onSubmitted: (_) => _password.text.isEmpty ? null : _join(),
      decoration: InputDecoration(
        labelText: 'Senha do WiFi',
        suffixIcon: IconAction(
          'eye',
          label: _showPassword ? 'Esconder a senha' : 'Mostrar a senha',
          color: _showPassword ? AppColors.accent : AppColors.muted,
          onPressed: () => setState(() => _showPassword = !_showPassword),
        ),
      ),
    ),
    const SizedBox(height: AppSpace.s1),
    AppButton(
      'Entrar nesta rede',
      icon: 'wifi',
      tone: ButtonTone.primary,
      big: true,
      expand: true,
      onPressed: _password.text.isEmpty ? null : _join,
    ),
    const SizedBox(height: AppSpace.s1),
    AppButton('Escolher outra rede', expand: true, onPressed: () => setState(() => _stage = _Stage.choose)),
  ];
}
