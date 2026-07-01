#!/usr/bin/env bash
# Instalador idempotente de gunjop-net. Ejecutar con: sudo ./install.sh
set -euo pipefail

APP_DIR="/opt/gunjop-net"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "Ejecuta con sudo: sudo ./install.sh" >&2
  exit 1
fi

echo "==> 1/6 Verificando NetworkManager..."
if ! command -v nmcli >/dev/null 2>&1; then
  echo "    Instalando NetworkManager..."
  apt-get update -qq && apt-get install -y network-manager
fi
systemctl enable --now NetworkManager >/dev/null 2>&1 || true

echo "==> 2/6 Instalando dependencias del sistema (python3, venv)..."
apt-get install -y python3 python3-venv python3-pip >/dev/null

echo "==> 3/6 Copiando aplicación a ${APP_DIR}..."
mkdir -p "$APP_DIR"
cp -r "$SRC_DIR/app" "$APP_DIR/"
cp "$SRC_DIR/requirements.txt" "$APP_DIR/"
# No sobrescribir config.yaml existente (respeta la personalización de esta RPi)
if [[ ! -f "$APP_DIR/config.yaml" ]]; then
  cp "$SRC_DIR/config.yaml" "$APP_DIR/"
else
  echo "    config.yaml ya existe, se conserva el actual."
fi

echo "==> 4/6 Creando entorno virtual e instalando paquetes Python..."
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

echo "==> 5/6 Instalando servicios systemd..."
cp "$SRC_DIR/systemd/gunjop-ap.service"  /etc/systemd/system/
cp "$SRC_DIR/systemd/gunjop-net.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now gunjop-ap.service
systemctl enable --now gunjop-net.service

echo "==> 6/6 Listo."
PORT=$(grep -E '^\s*port:' "$APP_DIR/config.yaml" | grep -oE '[0-9]+' | head -1)
SSID=$(grep -E '^\s*ssid:' "$APP_DIR/config.yaml" | head -1 | cut -d'"' -f2)
IP=$(grep -E '^\s*ip:'   "$APP_DIR/config.yaml" | head -1 | cut -d'"' -f2)
echo ""
echo "  ✅ Instalación completa."
echo "  📶 Conéctate al WiFi '${SSID}' y abre  http://${IP}:${PORT}"
echo "  🔎 Estado:  systemctl status gunjop-net gunjop-ap"
