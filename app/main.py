"""gunjop-net — gestor de red web para Raspberry Pi (envuelve NetworkManager)."""
from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from . import network

BASE = Path(__file__).resolve().parent
app = FastAPI(title="gunjop-net")
templates = Jinja2Templates(directory=str(BASE / "templates"))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "devices": network.get_devices(),
            "networks": network.scan_wifi(),
        },
    )


@app.post("/wifi/connect", response_class=HTMLResponse)
def wifi_connect(request: Request, ssid: str = Form(...), password: str = Form("")):
    ok, msg = network.connect_wifi(ssid, password or None)
    return _result(request, ok, f"WiFi '{ssid}': {msg}")


@app.post("/ethernet/static", response_class=HTMLResponse)
def ethernet_static(
    request: Request,
    con_name: str = Form(...),
    ip_cidr: str = Form(...),
    gateway: str = Form(...),
    dns: str = Form(...),
):
    ok, msg = network.set_ethernet_static(con_name, ip_cidr, gateway, dns)
    return _result(request, ok, f"Ethernet estática: {msg}")


@app.post("/ethernet/dhcp", response_class=HTMLResponse)
def ethernet_dhcp(request: Request, con_name: str = Form(...)):
    ok, msg = network.set_ethernet_dhcp(con_name)
    return _result(request, ok, f"Ethernet DHCP: {msg}")


def _result(request: Request, ok: bool, msg: str) -> HTMLResponse:
    return templates.TemplateResponse(
        "_result.html", {"request": request, "ok": ok, "msg": msg}
    )


def run():
    cfg = network.load_config()["web"]
    uvicorn.run(app, host=cfg["host"], port=cfg["port"])


if __name__ == "__main__":
    run()
