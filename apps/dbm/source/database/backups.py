import shutil
from datetime import datetime

from database.paths import BACKUP_DIRECTORY


def create_database_backup(database_path):
    if not database_path.exists():
        return None

    BACKUP_DIRECTORY.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIRECTORY / f"charms_check_db_{timestamp}.json"
    shutil.copy2(database_path, backup_path)

    return backup_path
