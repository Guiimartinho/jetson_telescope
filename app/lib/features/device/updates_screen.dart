import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/commands.dart';
import '../../app/link.dart';
import '../../app/queries.dart';
import '../../core/errors.dart';
import '../../core/format.dart';
import '../../core/strings.dart';
import '../../core/theme.dart';
import '../../core/version.dart';
import '../../core/widgets/kit.dart';
import '../../domain/models.dart';

/// D8 — Atualizações: as versões de cada parte e, onde isso existe, atualizar o software do
/// telescópio daqui: procurar, instalar, acompanhar. Durante a instalação a tela pede para não
/// desligar; se algo der errado, o telescópio continua na versão anterior, e a tela diz.
///
/// No aparelho de verdade isso ainda não foi habilitado (o software chega pelo computador): a
/// tela mostra as versões e explica.
class UpdatesScreen extends ConsumerStatefulWidget {
  const UpdatesScreen({super.key});

  @override
  ConsumerState<UpdatesScreen> createState() => _UpdatesScreenState();
}

class _UpdatesScreenState extends ConsumerState<UpdatesScreen> {
  UpdateInfo? _info;
  ApiFailure? _failure;
  Timer? _poll;

  /// A versão que mandamos instalar: é o que deixa a tela dizer "atualizado" no fim.
  String? _installing;
  String? _installed;

  /// Já procurou nesta visita (para poder dizer "já está na mais nova").
  bool _checked = false;

  @override
  void initState() {
    super.initState();
    Future.microtask(_refresh);
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  /// Enquanto houver procura ou instalação, pergunta de novo a cada segundo. No reinício o
  /// telescópio some por um instante: isso não é erro, é só esperar.
  void _watch(UpdateInfo info) {
    _poll?.cancel();
    if (info.working) _poll = Timer(const Duration(seconds: 1), _refresh);
  }

  void _take(UpdateInfo info) {
    final before = _info;
    if (_installing != null && info.current == _installing && !info.working) {
      _installed = _installing;
      _installing = null;
      ref.invalidate(systemProvider);
      unawaited(ref.read(linkProvider.notifier).refreshInfo().catchError((Object _) {}));
    }
    if (info.failed) _installing = null;
    if (before?.state == 'checking' && info.state == 'idle') {
      _checked = true;
      if (info.available == null) ref.read(commandsProvider).say('O telescópio já está na versão mais nova.');
    }
    setState(() {
      _info = info;
      _failure = null;
    });
    _watch(info);
  }

  Future<void> _refresh() async {
    final api = ref.read(linkProvider).api;
    if (api == null || !mounted) return;
    try {
      final info = await api.update();
      if (mounted) _take(info);
    } on ApiFailure catch (failure) {
      if (!mounted) return;
      if (_info?.working ?? false) {
        _poll = Timer(const Duration(seconds: 1), _refresh); // reiniciando: tenta de novo
      } else {
        setState(() => _failure = failure);
      }
    }
  }

  Future<void> _check() async {
    final info = await ref.read(commandsProvider).act((api) => api.checkUpdate());
    if (info != null && mounted) _take(info);
  }

  Future<void> _install(String version) async {
    final yes = await confirm(
      context,
      title: 'Instalar a versão $version?',
      text:
          'Leva alguns minutos e o telescópio reinicia no fim. Não o desligue no meio. Se algo der '
          'errado, ele continua na versão de agora.',
      yes: 'Instalar',
    );
    if (!yes || !mounted) return;
    final info = await ref.read(commandsProvider).act((api) => api.installUpdate());
    if (info == null || !mounted) return;
    _installing = version;
    _installed = null;
    _take(info);
  }

  @override
  Widget build(BuildContext context) {
    final system = ref.watch(systemProvider).valueOrNull;
    final busy = ref.watch(telescopeProvider.select((t) => t.busy));
    final info = _info;
    return SubPage(
      title: 'Atualizações',
      onBack: () => context.go('/device'),
      child: info == null
          ? (_failure == null
                ? const Busy()
                : Padding(
                    padding: const EdgeInsets.all(AppSpace.s2),
                    child: Notice(
                      title: 'O telescópio não respondeu',
                      text: S.failure(_failure!),
                      actions: [AppButton('Tentar de novo', onPressed: _refresh)],
                    ),
                  ))
          : ListView(
              padding: const EdgeInsets.fromLTRB(AppSpace.s2, 0, AppSpace.s2, 96),
              children: [
                Panel(
                  padding: const EdgeInsets.symmetric(horizontal: AppSpace.s2, vertical: 8),
                  child: Column(
                    children: [
                      const InfoLine(icon: 'phone', label: 'Este app', value: appVersion),
                      InfoLine(
                        icon: 'chip',
                        label: 'Software do telescópio',
                        value: system == null ? info.current : '${info.current} (API ${system.api})',
                      ),
                      InfoLine(
                        icon: 'mount',
                        label: 'Firmware da montagem',
                        value: system?.firmware ?? 'ainda não lido',
                      ),
                      if (system?.uptimeS != null)
                        InfoLine(icon: 'clock', label: 'No ar há', value: Fmt.duration(system!.uptimeS!)),
                    ],
                  ),
                ),
                const SizedBox(height: AppSpace.s3),
                if (!info.enabled)
                  const Notice(
                    bad: false,
                    icon: 'info',
                    title: 'Atualizar pelo app ainda não existe',
                    text:
                        'Por enquanto o software do telescópio e o firmware da montagem são atualizados pelo '
                        'computador. Quando a atualização pelo app chegar, ela volta sozinha à versão anterior '
                        'se algo der errado.',
                  )
                else
                  ..._body(info, busy),
              ],
            ),
    );
  }

  List<Widget> _body(UpdateInfo info, bool telescopeBusy) {
    if (info.installing) {
      final restarting = info.state == 'restarting';
      return [
        Panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Busy(size: 18),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      restarting
                          ? 'Reiniciando o telescópio'
                          : '${info.state == 'downloading' ? 'Baixando' : 'Instalando'} a versão ${info.available ?? ''}'
                                .trim(),
                      style: AppText.heading.copyWith(fontSize: 15),
                    ),
                  ),
                  if (info.progress != null)
                    Text('${(info.progress! * 100).round()}%', style: AppText.number.copyWith(fontSize: 15)),
                ],
              ),
              const SizedBox(height: AppSpace.s1),
              ClipRRect(
                borderRadius: BorderRadius.circular(3),
                child: LinearProgressIndicator(
                  value: restarting ? null : info.progress,
                  minHeight: 6,
                  color: AppColors.accent,
                  backgroundColor: AppColors.elev,
                ),
              ),
              const SizedBox(height: AppSpace.s1),
              Text(
                restarting
                    ? 'A conexão cai por um instante; o app reconecta sozinho.'
                    : 'Não desligue o telescópio. Se algo der errado, ele continua na versão ${info.current}.',
                style: AppText.small,
              ),
            ],
          ),
        ),
      ];
    }
    return [
      if (info.failed) ...[
        Notice(
          title: 'A instalação falhou',
          text: 'O telescópio continua na versão ${info.current}, funcionando como antes.',
        ),
        const SizedBox(height: AppSpace.s2),
      ],
      if (_installed != null) ...[
        Notice(bad: false, icon: 'check', title: 'Telescópio atualizado para a versão $_installed'),
        const SizedBox(height: AppSpace.s2),
      ],
      if (info.available case final String version) ...[
        Panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const AppIcon('download', color: AppColors.accent),
                  const SizedBox(width: 12),
                  Expanded(child: Text('Versão $version disponível', style: AppText.heading.copyWith(fontSize: 15))),
                ],
              ),
              if (info.notes.isNotEmpty) ...[
                const SizedBox(height: AppSpace.s1),
                for (final note in info.notes)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Padding(
                          padding: const EdgeInsets.only(top: 7, right: 10),
                          child: Container(
                            width: 5,
                            height: 5,
                            decoration: const BoxDecoration(color: AppColors.muted, shape: BoxShape.circle),
                          ),
                        ),
                        Expanded(child: Text(note, style: AppText.body)),
                      ],
                    ),
                  ),
              ],
            ],
          ),
        ),
        const SizedBox(height: AppSpace.s2),
        AppButton(
          info.failed ? 'Tentar instalar de novo' : 'Instalar a versão $version',
          icon: 'download',
          tone: ButtonTone.primary,
          big: true,
          expand: true,
          onPressed: telescopeBusy ? null : () => _install(version),
        ),
        Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Text(
            telescopeBusy
                ? 'Pare o trabalho em andamento antes de atualizar.'
                : 'Leva alguns minutos e o telescópio reinicia no fim.',
            style: AppText.small,
          ),
        ),
      ] else ...[
        if (info.state == 'checking')
          const Panel(
            child: Row(
              children: [
                Busy(size: 18),
                SizedBox(width: 12),
                Expanded(child: Text('Procurando versão nova.', style: AppText.body)),
              ],
            ),
          )
        else ...[
          if (_checked && _installed == null && !info.failed)
            const Padding(
              padding: EdgeInsets.only(bottom: AppSpace.s1),
              child: StatusText('o telescópio está na versão mais nova', color: AppColors.ok),
            ),
          AppButton(
            'Procurar atualização',
            icon: 'download',
            tone: ButtonTone.primary,
            big: true,
            expand: true,
            onPressed: _check,
          ),
        ],
      ],
    ];
  }
}
