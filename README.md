# gunjop-net

Gestor de red web para Raspberry Pi. Envuelve **NetworkManager** (`nmcli`) con una
interfaz web para configurar WiFi y Ethernet, y levanta un **AP por defecto** siempre
activo para poder entrar aunque no recuerdes la IP.

- 📶 AP fijo: SSID `wapsi` (clave `12345678`), `http://192.168.4.1:3000`
- 🌐 Web accesible también por la IP de WiFi/Ethernet (`0.0.0.0:3000`)
- 🔁 Replicable en otra RPi con 2 comandos

## Instalar (replicar en otra Raspberry Pi)

Un solo comando — descarga, instala y arranca solo:

```bash
curl -sSL https://raw.githubusercontent.com/osmar-pj/rb-network/main/install.sh | sudo bash
```

Luego conéctate al WiFi **wapsi** (clave `12345678`) y abre `http://192.168.4.1:3000`.

<details>
<summary>Alternativa: instalar desde una copia local</summary>

```bash
git clone https://github.com/osmar-pj/rb-network.git
cd rb-network
sudo ./install.sh
```
</details>

## Personalizar

Edita `config.yaml` (SSID, contraseña, IP, puerto, interfaz del AP) y reinstala:

```bash
sudo ./install.sh          # respeta el config.yaml ya instalado en /opt/gunjop-net
```

> Si tu driver necesita interfaz virtual para AP+cliente simultáneo, pon
> `interface: "ap0"` en `config.yaml`.

## Requisitos

- Raspberry Pi OS Bookworm (o cualquier distro con NetworkManager)
- Python 3.9+

## Comandos útiles

```bash
systemctl status gunjop-net gunjop-ap   # estado
journalctl -u gunjop-net -f             # logs de la web
sudo ./uninstall.sh                     # quitar todo
```
