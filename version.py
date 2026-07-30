from paths import BASE_DIR


def _read_version() -> str:
    try:
        return (BASE_DIR / "VERSION").read_text().strip()
    except FileNotFoundError:
        return "0.0.0-unknown"


__version__ = _read_version()
