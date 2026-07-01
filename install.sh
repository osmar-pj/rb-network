#!/usr/bin/env bash
# Instalador de rb-network. Uso:
#   curl -sSL https://raw.githubusercontent.com/osmar-pj/rb-network/main/install.sh | sudo bash
# o localmente:  sudo ./install.sh
set -euo pipefail

REPO_URL="https://github.com/osmar-pj/rb-network.git"
APP_DIR="/opt/gunjop-net"

# --- colores ---
G='\033[0;32m'; C='\033[0;36m'; Y='\033[1;33m'; B='\033[1m'; N='\033[0m'

banner() {
  printf "${C}"
  cat <<'EOF'
   __      __  _   ___  ___ ___
   \ \    / / /_\ | _ \/ __|_ _|
    \ \/\/ / / _ \|  _/\__ \| |
     \_/\_/ /_/ \_\_|  |___/___|

EOF
  printf "${N}${B}   rb-network${N} · gestor de red WiFi / Ethernet para Raspberry Pi\n\n"
}

step() { printf "${G}==>${N} ${B}%s${N}\n" "$1"; }

banner

# --- requiere root ---
if [[ $EUID -ne 0 ]]; then
  printf "${Y}Necesito permisos de administrador. Vuelve a ejecutar con:${N}\n"
  printf "   curl -sSL %s | sudo bash\n" "https://raw.githubusercontent.com/osmar-pj/rb-network/main/install.sh"
  exit 1
fi

# --- 1. dependencias del sistema ---
step "1/6  Instalando dependencias (git, python, NetworkManager)..."
apt-get update -qq
apt-get install -y -qq git python3 python3-venv python3-pip network-manager >/dev/null
systemctl enable --now NetworkManager >/dev/null 2>&1 || true

# --- 2. obtener el código ---
step "2/6  Descargando rb-network desde GitHub..."
# ¿estamos ya dentro de una copia local del proyecto? -> úsala. Si no, clónala.
if [[ -f "$PWD/app/network.py" ]]; then
  SRC_DIR="$PWD"
else
  SRC_DIR="$(mktemp -d)"
  git clone --depth 1 -q "$REPO_URL" "$SRC_DIR"
fi

# --- 3. copiar aplicación ---
step "3/6  Instalando en ${APP_DIR}..."
mkdir -p "$APP_DIR"
cp -r "$SRC_DIR/app" "$APP_DIR/"
cp "$SRC_DIR/requirements.txt" "$APP_DIR/"
# no sobrescribir la config si ya existe (respeta la personalización de esta RPi)
if [[ -f "$APP_DIR/config.yaml" ]]; then
  printf "     config.yaml ya existe, se conserva el actual.\n"
else
  cp "$SRC_DIR/config.yaml" "$APP_DIR/"
fi

# --- 4. entorno de python ---
step "4/6  Preparando entorno de Python..."
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# --- 5. servicios systemd ---
step "5/6  Instalando servicios (arranque automático)..."
cp "$SRC_DIR/systemd/gunjop-ap.service"  /etc/systemd/system/
cp "$SRC_DIR/systemd/gunjop-net.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now gunjop-ap.service  >/dev/null 2>&1 || true
systemctl enable --now gunjop-net.service >/dev/null 2>&1 || true

# --- 6. listo ---
step "6/6  Listo."
PORT=$(grep -E '^\s*port:' "$APP_DIR/config.yaml" | grep -oE '[0-9]+' | head -1)
SSID=$(grep -E '^\s*ssid:' "$APP_DIR/config.yaml" | head -1 | cut -d'"' -f2)
PASS=$(grep -E '^\s*password:' "$APP_DIR/config.yaml" | head -1 | cut -d'"' -f2)
IP=$(grep -E '^\s*ip:'   "$APP_DIR/config.yaml" | head -1 | cut -d'"' -f2)

printf "\n${G}${B}  ✅ Instalación completa${N}\n\n"
printf "   ${B}Conéctate al WiFi:${N}  ${C}%s${N}   (clave: %s)\n" "$SSID" "${PASS:-sin clave}"
printf "   ${B}Abre en el navegador:${N}  ${C}http://%s:%s${N}\n\n" "$IP" "$PORT"
printf "   Estado:  systemctl status gunjop-net\n\n"
