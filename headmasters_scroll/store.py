from __future__ import annotations

import json
import os
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from .locking import FileLock
from .merge import apply_disk_resolution, merge_documents
from .models import DataSession, SaveOutcome
from .paths import data_path
from .validation import validate_document


class SharedJsonStore:
    def __init__(self, data_directory: Path | None = None, lock_timeout: float = 5.0):
        self.data_directory = data_directory
        self.lock_timeout = lock_timeout

    def _path(self, filename: str) -> Path:
        return self.data_directory / filename if self.data_directory else data_path(filename)

    @staticmethod
    def _read(path: Path) -> dict:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)

    def load(self, filename: str) -> DataSession:
        path = self._path(filename)
        data = self._read(path)
        validate_document(filename, data)
        revision = data["_headmasters_scroll"]["revision_id"]
        return DataSession(filename, path, deepcopy(data), deepcopy(data), revision)

    def save(self, session: DataSession, app_id: str) -> SaveOutcome:
        self._validate_app_id(app_id)
        with FileLock(session.path, timeout=self.lock_timeout):
            disk = self._read(session.path)
            validate_document(session.filename, disk)
            disk_revision = disk["_headmasters_scroll"]["revision_id"]
            if disk_revision == session.loaded_revision:
                candidate = deepcopy(session.data)
            else:
                merge = merge_documents(session.filename, session.base_data, session.data, disk)
                if merge.conflicts:
                    return SaveOutcome("conflicts", conflicts=merge.conflicts, disk_revision=disk_revision)
                candidate = merge.data
            return self._commit(session, candidate, app_id)

    def save_with_resolutions(
        self,
        session: DataSession,
        resolutions: dict[str, Literal["app", "disk"]],
        app_id: str,
        expected_disk_revision: str,
    ) -> SaveOutcome:
        self._validate_app_id(app_id)
        with FileLock(session.path, timeout=self.lock_timeout):
            disk = self._read(session.path)
            validate_document(session.filename, disk)
            disk_revision = disk["_headmasters_scroll"]["revision_id"]
            merge = merge_documents(session.filename, session.base_data, session.data, disk)
            if disk_revision != expected_disk_revision:
                if merge.conflicts:
                    return SaveOutcome("conflicts", conflicts=merge.conflicts, disk_revision=disk_revision)
                return self._commit(session, merge.data, app_id)
            unresolved = [item for item in merge.conflicts if item.conflict_id not in resolutions]
            if unresolved:
                return SaveOutcome("conflicts", conflicts=unresolved, disk_revision=disk_revision)
            for conflict in merge.conflicts:
                choice = resolutions[conflict.conflict_id]
                if choice not in {"app", "disk"}:
                    raise ValueError(f"Invalid resolution for {conflict.conflict_id}: {choice}")
                if choice == "disk":
                    apply_disk_resolution(merge.data, conflict)
            return self._commit(session, merge.data, app_id)

    def _commit(self, session: DataSession, candidate: dict, app_id: str) -> SaveOutcome:
        now = datetime.now(timezone.utc)
        revision = str(uuid4())
        candidate["_headmasters_scroll"] = {
            "revision_id": revision,
            "last_modified_at": now.isoformat().replace("+00:00", "Z"),
            "last_modified_by": app_id,
        }
        validate_document(session.filename, candidate)
        backup_directory = session.path.parent / "backups" / session.path.stem
        backup_directory.mkdir(parents=True, exist_ok=True)
        backup_name = f"{now.strftime('%Y%m%dT%H%M%S%fZ')}-{session.loaded_revision}.json"
        shutil.copy2(session.path, backup_directory / backup_name)
        temporary = session.path.with_suffix(session.path.suffix + f".{os.getpid()}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(candidate, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, session.path)
        finally:
            temporary.unlink(missing_ok=True)
        session.reset_to(candidate, revision)
        return SaveOutcome("saved", revision_id=revision)

    @staticmethod
    def _validate_app_id(app_id: str) -> None:
        if not app_id or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in app_id):
            raise ValueError("app_id must contain only lowercase letters, numbers, and hyphens")
