from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIRECTORY = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIRECTORY.parent.parent
SOURCE_DIRECTORY = APP_DIRECTORY / "source"
DATA_DIRECTORY = PROJECT_ROOT / "data"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SOURCE_DIRECTORY))
os.environ["HEADMASTERS_SCROLL_DATA_DIRECTORY"] = str(DATA_DIRECTORY)

from mage_maker.shell.application import MageMakerApp


if __name__ == "__main__":
    MageMakerApp(
        database_path=DATA_DIRECTORY / "world.json",
        game_database_directory=DATA_DIRECTORY / "db.json",
    ).mainloop()
