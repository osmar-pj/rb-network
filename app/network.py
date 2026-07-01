"""Wrappers sobre nmcli (NetworkManager). Toda la lógica de red vive aquí."""
from __future__ import annotations

import ipaddress
import subprocess
import threading
import time
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
        ip_full = _device_ip(dev)                       # ej. "192.168.1.50/24"
        ip_addr, mask = "", ""
        if ip_full and "/" in ip_full:
            addr, prefix = ip_full.split("/", 1)
            ip_addr = addr
            try:
                mask = str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)
            except ValueError:
                mask = ""
        dns_list = [d for d in ipv4.get("dns", "").split(",") if d.strip()]
        devices.append(
            {
                "device": dev,
                "type": typ,
                "state": state,
                "connection": con or None,
                "ip": ip_full,
                "ip_addr": ip_addr,               # IP sin prefijo, para precargar
                "mask": mask,                      # máscara en formato 255.255.255.0
                "method": ipv4.get("method"),      # "auto" (DHCP) o "manual" (estática)
                "gateway": ipv4.get("gateway", ""),
                "dns1": dns_list[0] if len(dns_list) > 0 else "",
                "dns2": dns_list[1] if len(dns_list) > 1 else "",
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
    ip: str | None = None,
    mask: str | None = None,
    gateway: str | None = None,
    dns_list: list[str] | None = None,
) -> tuple[bool, str]:
    """Conecta a una red WiFi. Si se pasa 'ip', fija IP estática (validada) en el perfil."""
    args = ["device", "wifi", "connect", ssid]
    if password:
        args += ["password", password]
    res = _run(args, check=False)
    if res.returncode != 0:
        return False, res.stderr.strip()

    if not ip:
        return True, res.stdout.strip()

    # nmcli nombra el perfil recién creado igual que el SSID.
    return apply_static(ssid, ip, mask or "", gateway or "", dns_list or [])


# ---------------------------------------------------------------- IP estática (validada)

def validate_static(
    ip: str, mask: str, gateway: str, dns_list: list[str]
) -> tuple[str, str, str]:
    """Valida IP/máscara/gateway/DNS. Devuelve (ip_cidr, gateway, dns_csv).

    Lanza ValueError con un mensaje claro si algo es inválido. Es la capa
    autoritativa: aunque el navegador falle, aquí nunca pasa una config mala.
    """
    try:
        ip_addr = ipaddress.IPv4Address(ip.strip())
    except ValueError:
        raise ValueError(f"La IP «{ip}» no es válida.")
    try:
        # IPv4Network valida que la máscara sea contigua (rechaza 255.255.255.5, etc.)
        prefix = ipaddress.IPv4Network(f"0.0.0.0/{mask.strip()}").prefixlen
    except ValueError:
        raise ValueError(f"La máscara «{mask}» no es válida.")

    net = ipaddress.IPv4Network(f"{ip_addr}/{prefix}", strict=False)
    if prefix <= 30:
        if ip_addr == net.network_address:
            raise ValueError("La IP no puede ser la dirección de red.")
        if ip_addr == net.broadcast_address:
            raise ValueError("La IP no puede ser la dirección de difusión (broadcast).")

    try:
        gw = ipaddress.IPv4Address(gateway.strip())
    except ValueError:
        raise ValueError(f"La puerta de enlace «{gateway}» no es válida.")
    if gw not in net:
        raise ValueError(
            f"La puerta de enlace {gw} no está en la misma red que la IP "
            f"(según la máscara {mask}). Revisa que coincidan."
        )

    dns_clean: list[str] = []
    for d in dns_list:
        d = d.strip()
        if not d:
            continue
        try:
            ipaddress.IPv4Address(d)
        except ValueError:
            raise ValueError(f"El DNS «{d}» no es válido.")
        dns_clean.append(d)
    if not dns_clean:
        raise ValueError("Indica al menos un DNS.")

    return f"{ip_addr}/{prefix}", str(gw), ",".join(dns_clean)


def _ipv4_snapshot(con_name: str) -> dict:
    """Captura la config IPv4 actual de un perfil, para poder revertir."""
    res = _run(
        ["-t", "-f", "ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns",
         "con", "show", con_name],
        check=False,
    )
    out: dict[str, str] = {}
    for row in _parse_terse(res.stdout):
        if row:
            out[row[0].split(".")[-1]] = row[1] if len(row) >= 2 else ""
    return out


def _ipv4_apply(con_name: str, method: str, addresses="", gateway="", dns="") -> subprocess.CompletedProcess:
    return _run(
        ["con", "modify", con_name, "ipv4.method", method,
         "ipv4.addresses", addresses, "ipv4.gateway", gateway, "ipv4.dns", dns],
        check=False,
    )


def _rollback_watch(con_name: str, snapshot: dict, gateway: str, delay: int = 40) -> None:
    """Tras 'delay' s, si no hay conexión con el gateway, revierte a 'snapshot'."""
    time.sleep(delay)
    ok = subprocess.run(
        ["ping", "-c", "2", "-W", "3", gateway], capture_output=True
    ).returncode == 0
    if ok:
        return  # la nueva config funciona; no tocamos nada
    _ipv4_apply(
        con_name,
        snapshot.get("method") or "auto",
        snapshot.get("addresses", ""),
        snapshot.get("gateway", ""),
        snapshot.get("dns", ""),
    )
    _run(["con", "up", con_name], check=False)


def apply_static(
    con_name: str, ip: str, mask: str, gateway: str, dns_list: list[str],
    rollback: bool = True,
) -> tuple[bool, str]:
    """Valida y aplica IP estática. Con rollback automático si deja sin conexión."""
    try:
        ip_cidr, gw, dns = validate_static(ip, mask, gateway, dns_list)
    except ValueError as e:
        return False, str(e)

    snapshot = _ipv4_snapshot(con_name)
    mod = _ipv4_apply(con_name, "manual", ip_cidr, gw, dns)
    if mod.returncode != 0:
        return False, mod.stderr.strip()

    up = _run(["con", "up", con_name], check=False)
    if up.returncode != 0:
        # ni siquiera levanta: revertimos de inmediato
        _ipv4_apply(con_name, snapshot.get("method") or "auto",
                    snapshot.get("addresses", ""), snapshot.get("gateway", ""),
                    snapshot.get("dns", ""))
        _run(["con", "up", con_name], check=False)
        return False, up.stderr.strip()

    if rollback:
        threading.Thread(
            target=_rollback_watch, args=(con_name, snapshot, gw), daemon=True
        ).start()

    return True, (
        f"IP {ip_cidr} aplicada correctamente. Si en ~40 s no hay conexión, "
        f"se revertirá sola a la configuración anterior."
    )


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
