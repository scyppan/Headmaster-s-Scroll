import os
from pathlib import Path


APPLICATION_DIRECTORY = Path(__file__).resolve().parent.parent
DATA_DIRECTORY = Path(os.environ.get("HEADMASTERS_SCROLL_DATA_DIRECTORY", APPLICATION_DIRECTORY / "data"))
DATABASE_PATH = DATA_DIRECTORY / "db.json"
BACKUP_DIRECTORY = DATA_DIRECTORY / "backups" / "db"
