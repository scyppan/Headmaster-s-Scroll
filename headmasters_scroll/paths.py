from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIRECTORY = PROJECT_ROOT / "data"
ASSETS_DIRECTORY = DATA_DIRECTORY / "assets"
PORTRAIT_ASSETS_DIRECTORY = ASSETS_DIRECTORY / "portraits"
MAP_ASSETS_DIRECTORY = ASSETS_DIRECTORY / "maps"
APPS_DIRECTORY = PROJECT_ROOT / "apps"
RUNTIME_DIRECTORY = PROJECT_ROOT / "runtime"
PREFERENCES_DIRECTORY = RUNTIME_DIRECTORY / "preferences"
ALLOWED_DATA_FILES = frozenset({"db.json", "world.json", "periods.json"})


def data_path(filename: str) -> Path:
    if filename not in ALLOWED_DATA_FILES:
        raise ValueError(f"Unknown shared data file: {filename}")
    return DATA_DIRECTORY / filename
