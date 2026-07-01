"""gunjop-net — gestor de red web para Raspberry Pi (envuelve NetworkManager)."""
from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import network

BASE = Path(__file__).resolve().parent
app = FastAPI(title="gunjop-net")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(BASE / "static" / "favicon.svg", media_type="image/svg+xml")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    # No escaneamos WiFi al cargar: la página abre al instante y el usuario
    # busca redes cuando pulsa "Buscar redes" (ruta /wifi/scan).
    return templates.TemplateResponse(
        request, "index.html", {"devices": network.get_devices()}
    )


@app.get("/wifi/scan", response_class=HTMLResponse)
def wifi_scan(request: Request):
    return templates.TemplateResponse(
        request, "_networks.html", {"networks": network.scan_wifi()}
    )


@app.post("/wifi/connect", response_class=HTMLResponse)
def wifi_connect(
    request: Request,
    ssid: str = Form(...),
    password: str = Form(""),
    ip: str = Form(""),
    mask: str = Form(""),
    gateway: str = Form(""),
    dns1: str = Form(""),
    dns2: str = Form(""),
):
    ok, msg = network.connect_wifi(
        ssid, password or None,
        ip or None, mask or None, gateway or None, [dns1, dns2],
    )
    modo = "IP estática" if ip else "DHCP"
    return _result(request, ok, f"WiFi '{ssid}' ({modo}): {msg}")


@app.post("/connection/static", response_class=HTMLResponse)
def connection_static(
    request: Request,
    con_name: str = Form(...),
    ip: str = Form(...),
    mask: str = Form(...),
    gateway: str = Form(...),
    dns1: str = Form(...),
    dns2: str = Form(""),
):
    ok, msg = network.apply_static(con_name, ip, mask, gateway, [dns1, dns2])
    return _result(request, ok, f"'{con_name}': {msg}")


@app.post("/connection/dhcp", response_class=HTMLResponse)
def connection_dhcp(request: Request, con_name: str = Form(...)):
    ok, msg = network.set_ethernet_dhcp(con_name)
    return _result(request, ok, f"'{con_name}' → DHCP (automática): {msg}")


def _result(request: Request, ok: bool, msg: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "_result.html", {"ok": ok, "msg": msg}
    )


def run():
    cfg = network.load_config()["web"]
    uvicorn.run(app, host=cfg["host"], port=cfg["port"])


if __name__ == "__main__":
    run()
