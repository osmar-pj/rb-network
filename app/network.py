"""Wrappers sobre nmcli (NetworkManager). Toda la lógica de red vive aquí."""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as fh:
        return yaml.safe_load(fh)


def _run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Ejecuta nmcli y devuelve el resultado. Lanza excepción si check=True y falla."""
    return subprocess.run(
        ["nmcli", *args],
        capture_output=True,
        text=True,
        check=check,
    )


def _parse_terse(output: str) -> list[list[str]]:
    """Parsea la salida '-t' de nmcli (campos separados por ':')."""
    rows = []
    for line in output.strip().splitlines():
        if line:
            # nmcli escapa los ':' internos como '\:'
            rows.append(line.replace(r"\:", "\x00").split(":"))
    return [[c.replace("\x00", ":") for c in row] for row in rows]


# ---------------------------------------------------------------- estado

def get_devices() -> list[dict]:
    """Estado de cada interfaz física: nombre, tipo, estado, conexión activa e IP."""
    res = _run(["-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"])
    devices = []
    for dev, typ, state, con in _parse_terse(res.stdout):
        if typ in ("loopback", "wifi-p2p"):
            continue
        ipv4 = _con_ipv4(con) if con else {}
        devices.append(
            {
                "device": dev,
                "type": typ,
                "state": state,
                "connection": con or None,
                "ip": _device_ip(dev),
                "method": ipv4.get("method"),   # "auto" (DHCP) o "manual" (estática)
                "gateway": ipv4.get("gateway", ""),
                "dns": ipv4.get("dns", ""),
            }
        )
    return devices


def _con_ipv4(con_name: str) -> dict:
    """Devuelve la configuración IPv4 de un perfil: método, gateway y DNS."""
    res = _run(
        ["-t", "-f", "ipv4.method,ipv4.gateway,ipv4.dns", "con", "show", con_name],
        check=False,
    )
    out: dict[str, str] = {}
    for row in _parse_terse(res.stdout):
        if len(row) >= 2:
            out[row[0].split(".")[-1]] = row[1]  # ipv4.method -> "method", etc.
    return out


def _device_ip(device: str) -> str | None:
    res = _run(["-t", "-f", "IP4.ADDRESS", "device", "show", device], check=False)
    for row in _parse_terse(res.stdout):
        if len(row) >= 2 and row[1]:
            return row[1]  # ej. "192.168.1.50/24"
    return None


# ---------------------------------------------------------------- wifi

def scan_wifi() -> list[dict]:
    """Lista las redes WiFi visibles, ordenadas por señal (sin duplicados)."""
    _run(["device", "wifi", "rescan"], check=False)
    res = _run(["-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE", "device", "wifi", "list"])
    seen: dict[str, dict] = {}
    for row in _parse_terse(res.stdout):
        if len(row) < 4:
            continue
        ssid, signal, security, in_use = row[0], row[1], row[2], row[3]
        if not ssid:
            continue
        entry = {
            "ssid": ssid,
            "signal": int(signal) if signal.isdigit() else 0,
            "secured": security.strip() not in ("", "--"),
            "active": in_use.strip() == "*",
        }
        if ssid not in seen or entry["signal"] > seen[ssid]["signal"]:
            seen[ssid] = entry
    return sorted(seen.values(), key=lambda e: e["signal"], reverse=True)


def connect_wifi(
    ssid: str,
    password: str | None,
    ip_cidr: str | None = None,
    gateway: str | None = None,
    dns: str | None = None,
) -> tuple[bool, str]:
    """Conecta a una red WiFi. Si se pasa ip_cidr, fija IP estática en el perfil."""
    args = ["device", "wifi", "connect", ssid]
    if password:
        args += ["password", password]
    res = _run(args, check=False)
    if res.returncode != 0:
        return False, res.stderr.strip()

    if not ip_cidr:
        return True, res.stdout.strip()

    # nmcli nombra el perfil recién creado igual que el SSID: le aplicamos IP fija.
    mod = _run(
        ["con", "modify", ssid, "ipv4.method", "manual",
         "ipv4.addresses", ip_cidr, "ipv4.gateway", gateway or "",
         "ipv4.dns", dns or ""],
        check=False,
    )
    if mod.returncode != 0:
        return False, mod.stderr.strip()
    up = _run(["con", "up", ssid], check=False)
    return up.returncode == 0, (up.stdout if up.returncode == 0 else up.stderr).strip()


# ---------------------------------------------------------------- ethernet

def set_ethernet_static(
    con_name: str, ip_cidr: str, gateway: str, dns: str
) -> tuple[bool, str]:
    """Configura IP estática en una conexión existente (ip_cidr ej. '192.168.1.10/24')."""
    res = _run(
        [
            "con", "modify", con_name,
            "ipv4.method", "manual",
            "ipv4.addresses", ip_cidr,
            "ipv4.gateway", gateway,
            "ipv4.dns", dns,
        ],
        check=False,
    )
    if res.returncode != 0:
        return False, res.stderr.strip()
    up = _run(["con", "up", con_name], check=False)
    return up.returncode == 0, (up.stdout if up.returncode == 0 else up.stderr).strip()


def set_ethernet_dhcp(con_name: str) -> tuple[bool, str]:
    res = _run(
        ["con", "modify", con_name, "ipv4.method", "auto",
         "ipv4.addresses", "", "ipv4.gateway", "", "ipv4.dns", ""],
        check=False,
    )
    if res.returncode != 0:
        return False, res.stderr.strip()
    up = _run(["con", "up", con_name], check=False)
    return up.returncode == 0, (up.stdout if up.returncode == 0 else up.stderr).strip()


# ---------------------------------------------------------------- access point

def ensure_ap() -> tuple[bool, str]:
    """Crea (si no existe) y levanta el AP definido en config.yaml."""
    cfg = load_config()["ap"]
    if not cfg.get("enabled", True):
        return True, "AP deshabilitado en config"

    con = cfg["con_name"]
    exists = con in {r[0] for r in _parse_terse(_run(["-t", "-f", "NAME", "con", "show"]).stdout)}

    if not exists:
        create = _run(
            [
                "con", "add", "type", "wifi", "ifname", cfg["interface"],
                "con-name", con, "autoconnect", "yes", "ssid", cfg["ssid"],
                "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg",
                "ipv4.method", "shared", "ipv4.addresses", f"{cfg['ip']}/24",
            ],
            check=False,
        )
        if create.returncode != 0:
            return False, create.stderr.strip()

    # (re)aplica seguridad según config
    if cfg.get("password"):
        _run(["con", "modify", con, "wifi-sec.key-mgmt", "wpa-psk",
              "wifi-sec.psk", cfg["password"]], check=False)
    else:
        _run(["con", "modify", con, "wifi-sec.key-mgmt", ""], check=False)

    up = _run(["con", "up", con], check=False)
    return up.returncode == 0, (up.stdout if up.returncode == 0 else up.stderr).strip()
