#!/usr/bin/env bash
# Liga, na Jetson, a API protegida que o app do celular usa (app/docs/04-api.md, 07-seguranca.md):
#   1. confere (e instala, se faltar) as bibliotecas da API para o usuário do serviço;
#   2. cria a identidade do aparelho (chave, certificado, segredo de pareamento), se não existe;
#   3. liga a API no telescope-console (porta 8443) — o console web passa a ser só leitura;
#   4. anuncia o serviço na rede (_telescope._tcp), para o app achar o aparelho sem IP.
# NÃO mexe na rede da Jetson (nem WiFi, nem ponto de acesso): isso é outro passo, combinado.
# Idempotente. Precisa de internet só se faltar biblioteca.
#
# Uso (na Jetson):  sudo bash scripts/jetson_setup_api.sh
# Depois, para parear um celular (sem sudo):  cd ~/telescope && python3 -m src.api.cli pair
# Desfazer:  sudo rm /etc/systemd/system/telescope-console.service.d/api.conf
#            sudo rm /etc/avahi/services/telescope-api.service
#            sudo systemctl daemon-reload && sudo systemctl restart telescope-console
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "ERRO: precisa de root (sudo bash $0)." >&2
  exit 1
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
OWNER="${SUDO_USER:-$(id -un)}"
PORT="${TELE_API_PORT:-8443}"
as_owner() { sudo -u "$OWNER" -H "$@"; }

if ! systemctl cat telescope-console.service >/dev/null 2>&1; then
  echo "ERRO: o serviço telescope-console não existe nesta máquina." >&2
  exit 1
fi

# 1. bibliotecas (do usuário do serviço, sem tocar no Python do sistema)
MISSING=""
for mod in fastapi uvicorn cryptography; do
  as_owner python3 -c "import $mod" 2>/dev/null || MISSING="$MISSING $mod"
done
if [ -n "$MISSING" ]; then
  echo ">> instalando para $OWNER:$MISSING"
  as_owner python3 -m pip install --user $MISSING
fi
as_owner python3 -c "import segno" 2>/dev/null \
  || as_owner python3 -m pip install --user segno \
  || echo "AVISO: sem 'segno' o QR não é desenhado; o código de pareamento sai em texto."
if ! (cd "$REPO" && as_owner python3 -c "from src.api.server import ApiServer"); then
  echo "ERRO: a API não importa neste Python (veja o erro acima)." >&2
  exit 1
fi

# 2. identidade do aparelho (fica em ~/.config/telescope/identity, só o dono lê)
DEVICE_ID="$(cd "$REPO" && as_owner python3 -m src.api.cli info --id-only)"
echo ">> aparelho: $DEVICE_ID"

# 3. API ligada no console
install -D -m 0644 "$REPO/deploy/jetson/telescope-console.api.conf" \
    /etc/systemd/system/telescope-console.service.d/api.conf

# 4. anúncio na rede (DNS-SD pelo avahi): o app procura por _telescope._tcp
if [ -d /etc/avahi/services ]; then
  cat > /etc/avahi/services/telescope-api.service <<XML
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name>Telescopio $DEVICE_ID</name>
  <service>
    <type>_telescope._tcp</type>
    <port>$PORT</port>
    <txt-record>id=$DEVICE_ID</txt-record>
    <txt-record>api=1</txt-record>
  </service>
</service-group>
XML
  chmod 0644 /etc/avahi/services/telescope-api.service
else
  echo "AVISO: sem /etc/avahi/services — o app não vai achar o aparelho sozinho (use o QR)."
fi

systemctl daemon-reload
systemctl restart telescope-console.service
sleep 4
echo ">> telescope-console: $(systemctl is-active telescope-console.service || true)"
if (exec 3<>/dev/tcp/127.0.0.1/"$PORT") 2>/dev/null; then
  echo ">> API no ar: https://$(hostname -I | awk '{print $1}'):$PORT/api/v1  (TLS 1.3, só celular pareado)"
else
  echo "ERRO: a porta $PORT não abriu. Veja: journalctl -u telescope-console -n 40" >&2
  exit 1
fi
echo ">> o console web agora é só leitura; os comandos vão pelo app."
echo ">> para parear um celular:  cd $REPO && python3 -m src.api.cli pair"
