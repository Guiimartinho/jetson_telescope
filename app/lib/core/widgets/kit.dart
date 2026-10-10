import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../theme.dart';

/// Um ícone do produto (desenhado no `ui_kit`, exportado para `assets/icons`). Nunca emoji,
/// nunca ícone de biblioteca: use os nomes de `AppIcons`.
class AppIcon extends StatelessWidget {
  const AppIcon(this.name, {super.key, this.size = 22, this.color});

  final String name;
  final double size;
  final Color? color;

  @override
  Widget build(BuildContext context) => SvgPicture.asset(
    'assets/icons/$name.svg',
    width: size,
    height: size,
    colorFilter: ColorFilter.mode(color ?? IconTheme.of(context).color ?? AppColors.text, BlendMode.srcIn),
  );
}

/// O símbolo do produto.
class BrandMark extends StatelessWidget {
  const BrandMark({super.key, this.size = 56});

  final double size;

  @override
  Widget build(BuildContext context) => SvgPicture.asset(
    'assets/brand/mark.svg',
    width: size,
    height: size,
    colorFilter: const ColorFilter.mode(AppColors.accent, BlendMode.srcIn),
  );
}

/// Superfície com borda fina (no lugar de sombra): o "cartão" do produto.
class Panel extends StatelessWidget {
  const Panel({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(AppSpace.s2),
    this.onTap,
    this.color,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final box = DecoratedBox(
      decoration: BoxDecoration(
        color: color ?? AppColors.surface,
        borderRadius: BorderRadius.circular(AppSpace.radius),
        border: Border.all(color: AppColors.line),
      ),
      child: Padding(padding: padding, child: child),
    );
    if (onTap == null) return box;
    return Semantics(
      container: true,
      button: true,
      onTap: onTap,
      child: GestureDetector(behavior: HitTestBehavior.opaque, onTap: onTap, excludeFromSemantics: true, child: box),
    );
  }
}

enum ButtonTone { primary, soft, danger }

/// O botão do produto. `big` é a ação principal da tela (64 dp): cabe um polegar com luva.
class AppButton extends StatelessWidget {
  const AppButton(
    this.label, {
    super.key,
    this.onPressed,
    this.icon,
    this.tone = ButtonTone.soft,
    this.big = false,
    this.expand = false,
  });

  final String label;
  final VoidCallback? onPressed;
  final String? icon;
  final ButtonTone tone;
  final bool big;
  final bool expand;

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null;
    final (Color background, Color foreground, Color border) = switch (tone) {
      ButtonTone.primary => (AppColors.accent, AppColors.onAccent, AppColors.accent),
      ButtonTone.danger => (AppColors.bad, const Color(0xFF2A0509), AppColors.bad),
      ButtonTone.soft => (AppColors.elev, AppColors.text, AppColors.line),
    };
    final content = Row(
      mainAxisSize: expand ? MainAxisSize.max : MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (icon != null) ...[AppIcon(icon!, size: big ? 22 : 18, color: foreground), const SizedBox(width: 8)],
        Flexible(
          child: Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(color: foreground, fontSize: big ? 16 : 14, fontWeight: FontWeight.w700),
          ),
        ),
      ],
    );
    return Semantics(
      container: true,
      button: true,
      enabled: enabled,
      label: label,
      onTap: onPressed,
      excludeSemantics: true,
      child: Opacity(
        opacity: enabled ? 1 : 0.4,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onPressed,
          child: Container(
            constraints: BoxConstraints(minHeight: big ? AppSpace.touchMain : AppSpace.touch),
            padding: const EdgeInsets.symmetric(horizontal: 18),
            alignment: expand ? Alignment.center : null,
            decoration: BoxDecoration(
              color: background,
              borderRadius: BorderRadius.circular(big ? AppSpace.radius : AppSpace.radiusSmall),
              border: Border.all(color: border),
            ),
            child: content,
          ),
        ),
      ),
    );
  }
}

/// Um botão só de ícone, com rótulo para leitor de tela e alvo de toque de 48 dp.
class IconAction extends StatelessWidget {
  const IconAction(this.icon, {super.key, required this.label, this.onPressed, this.color, this.size = 22});

  final String icon;
  final String label;
  final VoidCallback? onPressed;
  final Color? color;
  final double size;

  @override
  Widget build(BuildContext context) => Semantics(
    container: true,
    button: true,
    label: label,
    onTap: onPressed,
    excludeSemantics: true,
    child: GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onPressed,
      child: SizedBox.square(
        dimension: AppSpace.touch,
        child: Center(
          child: AppIcon(icon, size: size, color: color ?? AppColors.text),
        ),
      ),
    ),
  );
}

/// Seletor em forma de pílula (filtros do Atlas, presets do estúdio).
class Choice extends StatelessWidget {
  const Choice(this.label, {super.key, required this.selected, required this.onTap, this.icon});

  final String label;
  final bool selected;
  final VoidCallback onTap;
  final String? icon;

  @override
  Widget build(BuildContext context) {
    final foreground = selected ? AppColors.onAccent : AppColors.muted;
    return Semantics(
      container: true,
      button: true,
      selected: selected,
      label: label,
      onTap: onTap,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          constraints: const BoxConstraints(minHeight: 40),
          padding: const EdgeInsets.symmetric(horizontal: 14),
          decoration: BoxDecoration(
            color: selected ? AppColors.accent : AppColors.elev,
            borderRadius: BorderRadius.circular(99),
            border: Border.all(color: selected ? AppColors.accent : AppColors.line),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (icon != null) ...[AppIcon(icon!, size: 16, color: foreground), const SizedBox(width: 6)],
              Text(
                label,
                style: TextStyle(color: foreground, fontSize: 13, fontWeight: FontWeight.w600),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Estado em uma linha: um ponto colorido e SEMPRE o texto junto (nada depende só de cor).
class StatusText extends StatelessWidget {
  const StatusText(this.text, {super.key, this.color = AppColors.muted, this.style});

  final String text;
  final Color color;
  final TextStyle? style;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Container(
        width: 8,
        height: 8,
        decoration: BoxDecoration(color: color, shape: BoxShape.circle),
      ),
      const SizedBox(width: 7),
      Flexible(
        child: Text(
          text,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: (style ?? AppText.small).copyWith(color: color),
        ),
      ),
    ],
  );
}

class SectionLabel extends StatelessWidget {
  const SectionLabel(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: AppSpace.s1),
    child: Text(text.toUpperCase(), style: AppText.label),
  );
}

/// Uma linha "ícone, rótulo, valor" (saúde do aparelho, dados do alvo).
class InfoLine extends StatelessWidget {
  const InfoLine({super.key, required this.icon, required this.label, required this.value, this.color});

  final String icon;
  final String label;
  final String value;
  final Color? color;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 7),
    child: Row(
      children: [
        AppIcon(icon, size: 18, color: AppColors.muted),
        const SizedBox(width: 10),
        Text(label, style: AppText.small),
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            value,
            textAlign: TextAlign.right,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: AppText.number.copyWith(color: color ?? AppColors.text),
          ),
        ),
      ],
    ),
  );
}

/// Aviso de origem (X5): "câmera simulada", "dados de referência". Some quando o dado é real.
class SourceNote extends StatelessWidget {
  const SourceNote(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    decoration: BoxDecoration(
      color: const Color(0x22F5B95C),
      borderRadius: BorderRadius.circular(8),
      border: Border.all(color: const Color(0x55F5B95C)),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        const AppIcon('info', size: 14, color: AppColors.gold),
        const SizedBox(width: 6),
        Flexible(
          child: Text(
            text,
            style: const TextStyle(color: AppColors.gold, fontSize: 12, fontWeight: FontWeight.w600),
          ),
        ),
      ],
    ),
  );
}

/// Erro com saída (X6): o que aconteceu, em linguagem direta, e os botões do que fazer agora.
class Notice extends StatelessWidget {
  const Notice({super.key, required this.title, this.text, this.actions = const [], this.bad = true, this.icon});

  final String title;
  final String? text;
  final List<Widget> actions;
  final bool bad;
  final String? icon;

  @override
  Widget build(BuildContext context) {
    final color = bad ? AppColors.bad : AppColors.gold;
    return Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              AppIcon(icon ?? 'warning', size: 20, color: color),
              const SizedBox(width: 10),
              Expanded(
                child: Text(title, style: AppText.heading.copyWith(color: color)),
              ),
            ],
          ),
          if (text != null) ...[const SizedBox(height: 8), Text(text!, style: AppText.body)],
          if (actions.isNotEmpty) ...[
            const SizedBox(height: AppSpace.s2),
            Wrap(spacing: AppSpace.s1, runSpacing: AppSpace.s1, children: actions),
          ],
        ],
      ),
    );
  }
}

/// Lista ou área vazia, com um convite em vez de um vazio mudo.
class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.icon, required this.title, this.text, this.action});

  final String icon;
  final String title;
  final String? text;
  final Widget? action;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(AppSpace.s3),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AppIcon(icon, size: 40, color: AppColors.dim),
          const SizedBox(height: AppSpace.s2),
          Text(title, textAlign: TextAlign.center, style: AppText.heading),
          if (text != null) ...[
            const SizedBox(height: 6),
            Text(text!, textAlign: TextAlign.center, style: AppText.small),
          ],
          if (action != null) ...[const SizedBox(height: AppSpace.s2), action!],
        ],
      ),
    ),
  );
}

/// Indicador de espera discreto (sem clarão).
class Busy extends StatelessWidget {
  const Busy({super.key, this.size = 22});

  final double size;

  @override
  Widget build(BuildContext context) => Center(
    child: SizedBox.square(
      dimension: size,
      child: const CircularProgressIndicator(strokeWidth: 2, color: AppColors.accent),
    ),
  );
}

/// Uma imagem vinda da Jetson. Troca sem piscar: mantém a anterior até a nova estar pronta.
class BytesImage extends StatelessWidget {
  const BytesImage(this.bytes, {super.key, this.fit = BoxFit.cover, this.label});

  final Uint8List? bytes;
  final BoxFit fit;
  final String? label;

  @override
  Widget build(BuildContext context) {
    if (bytes == null) return const ColoredBox(color: AppColors.surface2);
    return Image.memory(
      bytes!,
      fit: fit,
      gaplessPlayback: true,
      filterQuality: FilterQuality.medium,
      semanticLabel: label,
      excludeFromSemantics: label == null,
      errorBuilder: (_, _, _) => const ColoredBox(color: AppColors.surface2),
    );
  }
}

/// Uma imagem que ainda vai chegar (miniatura de alvo, de sessão). Enquanto não chega, um
/// ícone no lugar; se não houver imagem, o ícone fica.
class LazyImage extends StatelessWidget {
  const LazyImage({super.key, required this.load, this.placeholder = 'nebula', this.radius = AppSpace.radiusSmall});

  final Future<Uint8List?> load;
  final String placeholder;
  final double radius;

  @override
  Widget build(BuildContext context) => ClipRRect(
    borderRadius: BorderRadius.circular(radius),
    child: ColoredBox(
      color: AppColors.surface2,
      child: FutureBuilder<Uint8List?>(
        future: load,
        builder: (context, snapshot) => snapshot.data == null
            ? Center(child: AppIcon(placeholder, size: 24, color: AppColors.dim))
            : BytesImage(snapshot.data),
      ),
    ),
  );
}

/// Botão de segurar: age enquanto o dedo está nele. [onHold] é chamado ao encostar e depois a
/// cada [every]; [onRelease], ao soltar (ou se o dedo escorregar para fora). É o botão do
/// movimento manual: soltou, parou.
class HoldButton extends StatefulWidget {
  const HoldButton({
    super.key,
    required this.label,
    required this.child,
    required this.onHold,
    required this.onRelease,
    this.every = const Duration(milliseconds: 350),
    this.enabled = true,
    this.size = 64,
  });

  final String label;
  final Widget child;
  final VoidCallback onHold;
  final VoidCallback onRelease;
  final Duration every;
  final bool enabled;
  final double size;

  @override
  State<HoldButton> createState() => _HoldButtonState();
}

class _HoldButtonState extends State<HoldButton> {
  Timer? _timer;
  bool _down = false;

  void _press() {
    if (!widget.enabled || _down) return;
    setState(() => _down = true);
    widget.onHold();
    _timer = Timer.periodic(widget.every, (_) => widget.onHold());
  }

  void _release() {
    if (!_down) return;
    _timer?.cancel();
    setState(() => _down = false);
    widget.onRelease();
  }

  @override
  void dispose() {
    _timer?.cancel();
    if (_down) widget.onRelease(); // a tela fechou com o dedo no botão: para do mesmo jeito
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Semantics(
    container: true,
    button: true,
    enabled: widget.enabled,
    label: widget.label,
    // o leitor de tela não segura: um toque dá um passo curto
    onTap: widget.enabled
        ? () {
            widget.onHold();
            widget.onRelease();
          }
        : null,
    excludeSemantics: true,
    child: Opacity(
      opacity: widget.enabled ? 1 : 0.35,
      child: Listener(
        onPointerDown: (_) => _press(),
        onPointerUp: (_) => _release(),
        onPointerCancel: (_) => _release(),
        child: Container(
          width: widget.size,
          height: widget.size,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: _down ? AppColors.accent : AppColors.elev,
            borderRadius: BorderRadius.circular(AppSpace.radius),
            border: Border.all(color: _down ? AppColors.accent : AppColors.line),
          ),
          child: IconTheme(
            data: IconThemeData(color: _down ? AppColors.onAccent : AppColors.text),
            child: widget.child,
          ),
        ),
      ),
    ),
  );
}

/// Um número com "menos" e "mais": exposição, ganho, fotos, linhas do mosaico.
class StepRow extends StatelessWidget {
  const StepRow({super.key, required this.label, required this.value, this.onMinus, this.onPlus, this.hint});

  final String label;
  final String value;
  final VoidCallback? onMinus;
  final VoidCallback? onPlus;
  final String? hint;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 2),
    child: Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: AppText.body),
              if (hint != null) Text(hint!, style: AppText.small.copyWith(fontSize: 12)),
            ],
          ),
        ),
        Opacity(
          opacity: onMinus == null ? 0.3 : 1,
          child: IconAction('minus', label: 'Menos $label', onPressed: onMinus),
        ),
        SizedBox(
          width: 76,
          child: Text(value, textAlign: TextAlign.center, style: AppText.number.copyWith(fontSize: 16)),
        ),
        Opacity(
          opacity: onPlus == null ? 0.3 : 1,
          child: IconAction('plus', label: 'Mais $label', onPressed: onPlus),
        ),
      ],
    ),
  );
}

/// Liga e desliga com título e explicação (rastreio, modo vermelho...).
class SwitchPanel extends StatelessWidget {
  const SwitchPanel({
    super.key,
    required this.icon,
    required this.title,
    required this.value,
    required this.onChanged,
    this.text,
  });

  final String icon;
  final String title;
  final String? text;
  final bool value;
  final ValueChanged<bool>? onChanged;

  @override
  Widget build(BuildContext context) => MergeSemantics(
    child: Opacity(
      opacity: onChanged == null ? 0.45 : 1,
      child: Panel(
        onTap: onChanged == null ? null : () => onChanged!(!value),
        child: Row(
          children: [
            AppIcon(icon, color: value ? AppColors.accent : AppColors.muted),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: AppText.heading.copyWith(fontSize: 15)),
                  if (text != null) ...[const SizedBox(height: 3), Text(text!, style: AppText.small)],
                ],
              ),
            ),
            const SizedBox(width: 8),
            Switch(
              value: value,
              onChanged: onChanged,
              activeThumbColor: AppColors.onAccent,
              activeTrackColor: AppColors.accent,
              inactiveThumbColor: AppColors.muted,
              inactiveTrackColor: AppColors.elev,
            ),
          ],
        ),
      ),
    ),
  );
}

/// Pergunta de sim ou não, no visual do produto. Devolve verdadeiro só no "sim".
Future<bool> confirm(
  BuildContext context, {
  required String title,
  String? text,
  required String yes,
  String no = 'Cancelar',
  bool danger = false,
}) async {
  final answer = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      backgroundColor: AppColors.surface,
      title: Text(title),
      content: text == null ? null : Text(text),
      actions: [
        AppButton(no, onPressed: () => Navigator.of(context).pop(false)),
        AppButton(
          yes,
          tone: danger ? ButtonTone.danger : ButtonTone.primary,
          onPressed: () => Navigator.of(context).pop(true),
        ),
      ],
    ),
  );
  return answer == true;
}

/// Página de segundo nível: barra com o nosso "voltar", título e ações.
class SubPage extends StatelessWidget {
  const SubPage({super.key, required this.title, required this.child, this.actions = const [], this.onBack});

  final String title;
  final Widget child;
  final List<Widget> actions;
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: Column(
        children: [
          SizedBox(
            height: 56,
            child: Row(
              children: [
                IconAction('back', label: 'Voltar', onPressed: onBack ?? () => Navigator.of(context).maybePop()),
                Expanded(
                  child: Text(title, maxLines: 1, overflow: TextOverflow.ellipsis, style: AppText.heading),
                ),
                ...actions,
                const SizedBox(width: 4),
              ],
            ),
          ),
          Expanded(child: child),
        ],
      ),
    ),
  );
}
