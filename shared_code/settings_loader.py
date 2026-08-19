import json
import os
from pathlib import Path


def load_local_settings():
    settings_path = Path(__file__).resolve().parents[1] / "local.settings.json"

    if not settings_path.exists():
        return

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    values = data.get("Values", {})

    for key, value in values.items():
        if value is not None and key not in os.environ:
            os.environ[key] = str(value)