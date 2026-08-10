from __future__ import annotations

import hashlib
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import ASSETS_DIRECTORY, MAP_ASSETS_DIRECTORY, PORTRAIT_ASSETS_DIRECTORY


PORTRAIT_SIZE = 512
MAP_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _safe_record_id(value: str) -> str:
    value = str(value or "").strip()
    if not value or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for character in value):
        raise ValueError("Asset record IDs may contain only letters, numbers, hyphens, underscores, and periods")
    if value in {".", ".."}:
        raise ValueError("Invalid asset record ID")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class AssetStore:
    """Private project-local image storage addressed only by opaque asset IDs."""

    def __init__(self, root: Path | None = None):
        self.root = Path(root or ASSETS_DIRECTORY)
        self.portraits = self.root / PORTRAIT_ASSETS_DIRECTORY.name
        self.maps = self.root / MAP_ASSETS_DIRECTORY.name

    @staticmethod
    def portrait_asset_id(person_id: str) -> str:
        return f"portrait:{_safe_record_id(person_id)}"

    @staticmethod
    def map_asset_id(map_id: str) -> str:
        return f"map:{_safe_record_id(map_id)}"

    def import_portrait(
        self,
        person_id: str,
        source: Path,
        crop_box: tuple[int, int, int, int],
    ) -> dict[str, Any]:
        try:
            from PIL import Image, ImageOps
        except ImportError as error:
            raise RuntimeError("Portrait import requires Pillow") from error

        person_id = _safe_record_id(person_id)
        source = Path(source)
        if not source.is_file():
            raise ValueError("Choose an existing portrait image")
        self.portraits.mkdir(parents=True, exist_ok=True)
        destination = self.portraits / f"{person_id}.webp"
        temporary = destination.with_suffix(f".webp.{os.getpid()}.tmp")
        try:
            with Image.open(source) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
                left, top, right, bottom = (int(value) for value in crop_box)
                if left < 0 or top < 0 or right > image.width or bottom > image.height:
                    raise ValueError("The portrait crop falls outside the image")
                if right <= left or bottom <= top or right - left != bottom - top:
                    raise ValueError("Portrait crops must be non-empty squares")
                cropped = image.crop((left, top, right, bottom)).resize(
                    (PORTRAIT_SIZE, PORTRAIT_SIZE), Image.Resampling.LANCZOS
                )
                cropped.save(temporary, format="WEBP", quality=90, method=6)
            self._replace_with_backup(destination, temporary)
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "asset_id": self.portrait_asset_id(person_id),
            "sha256": _sha256(destination),
            "width": PORTRAIT_SIZE,
            "height": PORTRAIT_SIZE,
            "mime_type": "image/webp",
            "updated_at": _utc_now(),
        }

    def import_map(self, map_id: str, source: Path) -> dict[str, Any]:
        try:
            from PIL import Image, ImageOps
        except ImportError as error:
            raise RuntimeError("Map import requires Pillow") from error

        map_id = _safe_record_id(map_id)
        source = Path(source)
        extension = source.suffix.casefold()
        if extension not in MAP_EXTENSIONS or not source.is_file():
            raise ValueError("Map images must be PNG, JPEG, or WebP files")
        self.maps.mkdir(parents=True, exist_ok=True)
        destination = self.maps / f"{map_id}{extension}"
        temporary = destination.with_suffix(destination.suffix + f".{os.getpid()}.tmp")
        try:
            with Image.open(source) as opened:
                normalized = ImageOps.exif_transpose(opened)
                width, height = normalized.size
                normalized.load()
            if width <= 0 or height <= 0:
                raise ValueError("The map image has invalid dimensions")
            with source.open("rb") as source_stream, temporary.open("wb") as target_stream:
                shutil.copyfileobj(source_stream, target_stream)
                target_stream.flush()
                os.fsync(target_stream.fileno())
            self._replace_with_backup(destination, temporary)
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "asset_id": self.map_asset_id(map_id),
            "sha256": _sha256(destination),
            "width": width,
            "height": height,
            "mime_type": MIME_TYPES[extension],
            "file_extension": extension,
            "updated_at": _utc_now(),
        }

    def prune_map_variants(self, map_id: str, keep_extension: str) -> None:
        """Retire old-format variants only after canonical metadata was saved."""

        map_id = _safe_record_id(map_id)
        keep_extension = str(keep_extension or "").casefold()
        for old in self.maps.glob(f"{map_id}.*"):
            if old.suffix.casefold() == keep_extension or ".tmp" in old.suffixes:
                continue
            try:
                self._backup(old)
                old.unlink(missing_ok=True)
            except OSError:
                # A stale private variant is harmless; never risk the active asset.
                continue

    def resolve(self, asset_id: str, metadata: dict[str, Any] | None = None) -> Path:
        kind, separator, record_id = str(asset_id or "").partition(":")
        if not separator:
            raise ValueError("Invalid asset ID")
        record_id = _safe_record_id(record_id)
        if kind == "portrait":
            candidate = self.portraits / f"{record_id}.webp"
        elif kind == "map":
            extension = str((metadata or {}).get("file_extension", "")).casefold()
            if extension not in MAP_EXTENSIONS:
                raise ValueError("Map asset metadata has an invalid file type")
            candidate = self.maps / f"{record_id}{extension}"
        else:
            raise ValueError("Unknown asset kind")
        resolved = candidate.resolve()
        root = self.root.resolve()
        if root not in resolved.parents or not resolved.is_file():
            raise FileNotFoundError("The requested local asset is unavailable")
        return resolved

    def _replace_with_backup(self, destination: Path, temporary: Path) -> None:
        if destination.exists():
            self._backup(destination)
        os.replace(temporary, destination)

    def _backup(self, path: Path) -> None:
        backup_dir = self.root / "backups" / path.parent.name
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        shutil.copy2(path, backup_dir / f"{stamp}-{path.name}")
