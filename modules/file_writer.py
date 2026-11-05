import json
import os
from collections.abc import Mapping
from pathlib import Path

SETTINGS_FILE = Path(__file__).parent.parent / "device_settings.json"


def load_settings(path: Path = SETTINGS_FILE) -> dict[str, object] | None:
    if not path.exists():
        return None

    with path.open(encoding="utf-8") as settings_file:
        settings = json.load(settings_file)
    if not isinstance(settings, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return settings


def write_settings(settings: Mapping[str, object], path: Path = SETTINGS_FILE) -> None:
    temporary_file = path.with_name(f".{path.name}.tmp")
    try:
        with temporary_file.open("w", encoding="utf-8") as settings_file:
            json.dump(settings, settings_file, indent=2)
            settings_file.write("\n")
            settings_file.flush()
            os.fsync(settings_file.fileno())
        os.replace(temporary_file, path)
    finally:
        temporary_file.unlink(missing_ok=True)
