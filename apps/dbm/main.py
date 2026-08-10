from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIRECTORY = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIRECTORY.parent.parent
SOURCE_DIRECTORY = APP_DIRECTORY / "source"
DATA_DIRECTORY = PROJECT_ROOT / "data"
PREFERENCES_DIRECTORY = PROJECT_ROOT / "runtime" / "preferences"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SOURCE_DIRECTORY))
os.environ["HEADMASTERS_SCROLL_DATA_DIRECTORY"] = str(DATA_DIRECTORY)
os.environ["HEADMASTERS_SCROLL_PREFERENCES_DIRECTORY"] = str(PREFERENCES_DIRECTORY)

from app import App


if __name__ == "__main__":
    App().mainloop()
