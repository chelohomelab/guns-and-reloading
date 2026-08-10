from pathlib import Path

from fastapi.templating import Jinja2Templates

from paths import BASE_DIR, DATA_DIR

UPLOAD_DIR = str(Path(DATA_DIR) / "static" / "uploads")
templates = Jinja2Templates(directory=str(Path(BASE_DIR) / "templates"))
