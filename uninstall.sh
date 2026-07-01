#!/usr/bin/env bash
# Desinstalador limpio de gunjop-net. Ejecutar con: sudo ./uninstall.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Ejecuta con sudo: sudo ./uninstall.sh" >&2
  exit 1
fi

echo "==> Deteniendo servicios..."
systemctl disable --now gunjop-net.service gunjop-ap.service 2>/dev/null || true
rm -f /etc/systemd/system/gunjop-net.service /etc/systemd/system/gunjop-ap.service
systemctl daemon-reload

echo "==> Eliminando perfil de AP en NetworkManager..."
CON=$(grep -E '^\s*con_name:' /opt/gunjop-net/config.yaml 2>/dev/null | cut -d'"' -f2 || true)
[[ -n "${CON:-}" ]] && nmcli con delete "$CON" 2>/dev/null || true

echo "==> Eliminando archivos..."
rm -rf /opt/gunjop-net

echo "  ✅ Desinstalado. (Las conexiones WiFi/Ethernet guardadas se conservan.)"
