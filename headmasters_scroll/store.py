from __future__ import annotations

import json
import os
import shutil
import time
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

    def fingerprint(self, filename: str) -> tuple[int, int]:
        """Return a cheap change token without decoding the JSON document."""

        stat = self._path(filename).stat()
        return stat.st_mtime_ns, stat.st_size

    @staticmethod
    def _file_identity(path: Path) -> tuple[int, int, int, int]:
        stat = path.stat()
        return (
            int(getattr(stat, "st_dev", 0)),
            int(getattr(stat, "st_ino", 0)),
            stat.st_mtime_ns,
            stat.st_size,
        )

    def read_document(self, filename: str) -> dict:
        """Read and validate a document without creating an editable session.

        Read-only consumers should not pay for the immutable merge base and
        editable working copies that :meth:`load` intentionally creates.
        """

        data = self._read(self._path(filename))
        validate_document(filename, data)
        return data

    @staticmethod
    def _read(path: Path) -> dict:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)

    def load(self, filename: str) -> DataSession:
        path = self._path(filename)
        # A writer may atomically replace the file while another application
        # is opening it.  Pair the bytes with the exact identity they came
        # from; otherwise a snapshot of the old file plus the fingerprint of
        # the new file could incorrectly take the unchanged-file save path.
        for _attempt in range(5):
            identity_before = self._file_identity(path)
            base_snapshot = path.read_bytes()
            loaded_fingerprint = self._file_identity(path)
            if identity_before == loaded_fingerprint:
                break
        else:
            raise OSError(f"{path.name} changed repeatedly while loading")
        data = json.loads(base_snapshot)
        validate_document(filename, data)
        revision = data["_headmasters_scroll"]["revision_id"]
        # Keep one editable dictionary and an immutable byte snapshot.  The
        # snapshot is decoded only if an external revision makes a three-way
        # merge necessary.
        return DataSession(
            filename,
            path,
            None,
            data,
            revision,
            base_snapshot=base_snapshot,
            loaded_fingerprint=loaded_fingerprint,
        )

    def save(self, session: DataSession, app_id: str) -> SaveOutcome:
        self._validate_app_id(app_id)
        with FileLock(session.path, timeout=self.lock_timeout):
            current_fingerprint = self._file_identity(session.path)
            if (
                session.loaded_fingerprint is not None
                and current_fingerprint == session.loaded_fingerprint
            ):
                # The same file identity, size, and nanosecond timestamp under
                # the suite lock means no external atomic commit occurred.
                # Avoid reparsing and revalidating a multi-megabyte document.
                disk_revision = session.loaded_revision
                # The file revision proves no three-way merge is required.
                # Committing the session's isolated working document directly
                # avoids copying a large world merely to serialize it.
                candidate = session.data
            else:
                disk = self._read(session.path)
                validate_document(session.filename, disk)
                disk_revision = disk["_headmasters_scroll"]["revision_id"]
                if disk_revision == session.loaded_revision:
                    candidate = session.data
                else:
                    merge = merge_documents(
                        session.filename,
                        session.merge_base(),
                        session.data,
                        disk,
                    )
                    if merge.conflicts:
                        return SaveOutcome(
                            "conflicts",
                            conflicts=merge.conflicts,
                            disk_revision=disk_revision,
                        )
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
            merge = merge_documents(
                session.filename,
                session.merge_base(),
                session.data,
                disk,
            )
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
        self._create_backup(
            session.path,
            backup_directory / backup_name,
        )
        # Use a unique file for every commit.  A fixed ``.new.json`` (or even a
        # per-process name) can collide with a second autosave and is also a
        # tempting target for indexers and sync clients on Windows.
        temporary = session.path.with_name(
            f".{session.path.name}.{os.getpid()}.{uuid4().hex}.tmp"
        )
        committed_snapshot = None
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(candidate, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            # Read the exact bytes while the private temporary still exists.
            # This replaces the much more expensive full-tree deepcopy that
            # previously ran after every successful commit.
            committed_snapshot = temporary.read_bytes()
            self._replace_with_retry(temporary, session.path)
        finally:
            temporary.unlink(missing_ok=True)
        session.reset_to(
            candidate,
            revision,
            committed_snapshot,
            self._file_identity(session.path),
        )
        return SaveOutcome("saved", revision_id=revision)

    @staticmethod
    def _create_backup(source: Path, destination: Path) -> None:
        """Snapshot the old canonical file without recopying it on NTFS.

        The subsequent atomic replace creates a new file at ``source``, so a
        hard link safely retains the complete previous revision.  Filesystems
        that do not support hard links retain the original copy fallback.
        """
        try:
            os.link(source, destination)
        except OSError:
            shutil.copy2(source, destination)

    @staticmethod
    def _replace_with_retry(temporary: Path, destination: Path) -> None:
        """Atomically replace a JSON file despite brief Windows file locks.

        OneDrive, antivirus scanners, and search indexing can briefly open the
        destination between validation and replacement.  Retrying only the
        Windows sharing/access errors keeps the operation atomic without hiding
        unrelated filesystem failures.
        """

        retry_delays = (0.0, 0.05, 0.10, 0.20, 0.40, 0.80)
        for attempt, delay in enumerate(retry_delays):
            if delay:
                time.sleep(delay)
            try:
                os.replace(temporary, destination)
                return
            except OSError as error:
                retryable = isinstance(error, PermissionError) or getattr(
                    error, "winerror", None
                ) in {5, 32}
                if not retryable or attempt == len(retry_delays) - 1:
                    raise

    @staticmethod
    def _validate_app_id(app_id: str) -> None:
        if not app_id or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in app_id):
            raise ValueError("app_id must contain only lowercase letters, numbers, and hyphens")
