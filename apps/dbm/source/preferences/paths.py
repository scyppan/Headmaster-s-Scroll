import os
from pathlib import Path


APPLICATION_DIRECTORY = Path(__file__).resolve().parent.parent
PREFERENCES_DIRECTORY = Path(
    os.environ.get("HEADMASTERS_SCROLL_PREFERENCES_DIRECTORY", APPLICATION_DIRECTORY / "data")
)
PREFERENCES_PATH = PREFERENCES_DIRECTORY / "dbm.json"
