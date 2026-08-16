"""Desktop entry point — frozen by PyInstaller for the Windows/Mac/Linux installers.

NOT used by uvicorn CLI / Docker / systemd, which continue to import `main:app` directly and are
completely unaffected by anything in this file. This is a separate launcher, not a replacement.
"""
import os
import platform
import socket
import threading


def _appdata_dir() -> str:
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    elif system == "Darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "InventoryAndReloading")


# Must happen before `import main` — main.py's startup logic (models.init_db(), the two
# app.mount(...) calls) runs at import time, not inside a function, so DATA_DIR needs to already
# be set in the environment before that module is ever imported.
os.environ.setdefault("INVENTORY_DATA_DIR", _appdata_dir())

import uvicorn  # noqa: E402
import webview  # noqa: E402

import main as app_module  # noqa: E402


def _pick_port() -> int:
    """Try a fixed, predictable port first; fall back to an OS-assigned free one if that's
    taken (e.g. a second instance already running)."""
    for port in (47182, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("No free port available")


def main():
    port = _pick_port()
    config = uvicorn.Config(app_module.app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        pass  # tight-poll — uvicorn.Server sets this once the ASGI app is actually accepting

    window = webview.create_window("Guns & Reloading", f"http://127.0.0.1:{port}")

    def _on_closed():
        server.should_exit = True

    window.events.closed += _on_closed
    webview.start()
    thread.join(timeout=5)


if __name__ == "__main__":
    main()
