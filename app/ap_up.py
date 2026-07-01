"""Entrypoint para levantar el AP al arrancar (usado por gunjop-ap.service)."""
from . import network

if __name__ == "__main__":
    ok, msg = network.ensure_ap()
    print(("OK: " if ok else "ERROR: ") + msg)
    raise SystemExit(0 if ok else 1)
