from __future__ import annotations

import hashlib
import io
import math
import os
import re
import shutil
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import ASSETS_DIRECTORY, MAP_ASSETS_DIRECTORY, PORTRAIT_ASSETS_DIRECTORY


PORTRAIT_SIZE = 512
MAP_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAP_IMPORT_EXTENSIONS = MAP_EXTENSIONS | {".svg"}
MAX_MAP_SIDE = 8_192
MAX_MAP_PIXELS = 32_000_000
MAX_SVG_BYTES = 10 * 1024 * 1024
MAP_CANVAS_WIDTH = 3_840
MAP_CANVAS_HEIGHT = 2_960
MAP_CANVAS_SIZE = (MAP_CANVAS_WIDTH, MAP_CANVAS_HEIGHT)
MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


_SVG_NUMBER = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(?:px)?\s*$", re.IGNORECASE)


def _svg_dimension(value: Any) -> float | None:
    if value is None:
        return None
    match = _SVG_NUMBER.fullmatch(str(value))
    if not match:
        return None
    number = float(match.group(1))
    return number if math.isfinite(number) and number > 0 else None


def _bounded_dimensions(width: float, height: float) -> tuple[int, int]:
    if not math.isfinite(width) or not math.isfinite(height) or width <= 0 or height <= 0:
        raise ValueError("The map image has invalid dimensions")
    scale = min(
        1.0,
        MAX_MAP_SIDE / width,
        MAX_MAP_SIDE / height,
        math.sqrt(MAX_MAP_PIXELS / (width * height)),
    )
    return max(1, round(width * scale)), max(1, round(height * scale))


def _safe_svg(source: Path) -> tuple[str, int, int]:
    raw = source.read_bytes()
    if not raw or len(raw) > MAX_SVG_BYTES:
        raise ValueError("The SVG is empty or too large to import")
    lowered = raw.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValueError("SVG document types and entities are not allowed")
    if b"<?xml-stylesheet" in lowered:
        raise ValueError("External SVG stylesheets are not allowed")
    try:
        text = raw.decode("utf-8-sig")
        root = ElementTree.fromstring(text)
    except (UnicodeDecodeError, ElementTree.ParseError) as error:
        raise ValueError("The SVG is malformed") from error
    if root.tag.rsplit("}", 1)[-1].casefold() != "svg":
        raise ValueError("The selected file is not an SVG image")
    unsafe_elements = {"script", "foreignobject", "iframe", "audio", "video"}
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].casefold() in unsafe_elements:
            raise ValueError("The SVG contains unsupported active content")
        for raw_name, raw_value in element.attrib.items():
            name = raw_name.rsplit("}", 1)[-1].casefold()
            value = str(raw_value or "").strip()
            lower_value = value.casefold()
            if name.startswith("on"):
                raise ValueError("The SVG contains event handlers")
            if name in {"href", "src"} and value and not lower_value.startswith("#"):
                raise ValueError("The SVG references an external resource")
            if "url(" in lower_value:
                references = re.findall(r"url\(\s*['\"]?([^)'\"\s]+)", value, re.IGNORECASE)
                if any(not reference.startswith("#") for reference in references):
                    raise ValueError("The SVG references an external resource")
        css_text = str(element.text or "")
        if "@import" in css_text.casefold():
            raise ValueError("External SVG stylesheets are not allowed")
        references = re.findall(r"url\(\s*['\"]?([^)'\"\s]+)", css_text, re.IGNORECASE)
        if any(not reference.startswith("#") for reference in references):
            raise ValueError("The SVG references an external resource")

    width = _svg_dimension(root.get("width"))
    height = _svg_dimension(root.get("height"))
    view_box = str(root.get("viewBox", "") or "").replace(",", " ").split()
    if len(view_box) == 4:
        try:
            box_width, box_height = float(view_box[2]), float(view_box[3])
        except ValueError as error:
            raise ValueError("The SVG viewBox is invalid") from error
        if box_width <= 0 or box_height <= 0 or not math.isfinite(box_width) or not math.isfinite(box_height):
            raise ValueError("The SVG viewBox is invalid")
        if width is not None and height is None:
            height = width * box_height / box_width
        elif height is not None and width is None:
            width = height * box_width / box_height
        else:
            width = width or box_width
            height = height or box_height
    if width is None or height is None:
        raise ValueError("The SVG must provide supported width, height, or viewBox dimensions")
    rendered_width, rendered_height = _bounded_dimensions(width, height)
    return text, rendered_width, rendered_height


def render_svg(source: Path) -> tuple[bytes, int, int]:
    """Safely validate and render an SVG to bounded PNG bytes."""

    try:
        import resvg_py
    except ImportError as error:
        raise RuntimeError("SVG map import requires resvg_py") from error
    svg_text, width, height = _safe_svg(Path(source))
    try:
        png = resvg_py.svg_to_bytes(svg_string=svg_text, width=width, height=height)
    except Exception as error:
        raise ValueError("The SVG could not be rendered") from error
    if not isinstance(png, (bytes, bytearray)) or not png:
        raise ValueError("The SVG renderer produced no image")
    return bytes(png), width, height


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

    @staticmethod
    def inspect_map_source(source: Path) -> tuple[int, int, str]:
        """Return the dimensions and stored extension for a supported import."""

        source = Path(source)
        extension = source.suffix.casefold()
        if not source.is_file() or extension not in MAP_IMPORT_EXTENSIONS:
            raise ValueError("Map images must be PNG, JPEG, WebP, or SVG files")
        if extension == ".svg":
            _, width, height = _safe_svg(source)
            return width, height, ".png"
        try:
            from PIL import Image, ImageOps
        except ImportError as error:
            raise RuntimeError("Map import requires Pillow") from error
        with Image.open(source) as opened:
            normalized = ImageOps.exif_transpose(opened)
            width, height = normalized.size
            normalized.load()
        if width <= 0 or height <= 0:
            raise ValueError("The map image has invalid dimensions")
        if width > MAX_MAP_SIDE or height > MAX_MAP_SIDE or width * height > MAX_MAP_PIXELS:
            raise ValueError("The map image exceeds the 8,192-pixel or 32-megapixel limit")
        return width, height, extension

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
        if extension not in MAP_IMPORT_EXTENSIONS or not source.is_file():
            raise ValueError("Map images must be PNG, JPEG, WebP, or SVG files")
        self.maps.mkdir(parents=True, exist_ok=True)
        stored_extension = ".png"
        destination = self.maps / f"{map_id}{stored_extension}"
        temporary = destination.with_suffix(destination.suffix + f".{os.getpid()}.tmp")
        try:
            if extension == ".svg":
                png, source_width, source_height = render_svg(source)
                opened_source = Image.open(io.BytesIO(png))
            else:
                opened_source = Image.open(source)
                raw_width, raw_height = opened_source.size
                if raw_width <= 0 or raw_height <= 0:
                    raise ValueError("The map image has invalid dimensions")
                if raw_width > MAX_MAP_SIDE or raw_height > MAX_MAP_SIDE or raw_width * raw_height > MAX_MAP_PIXELS:
                    raise ValueError("The map image exceeds the 8,192-pixel or 32-megapixel limit")
            try:
                normalized = ImageOps.exif_transpose(opened_source).convert("RGBA")
                source_width, source_height = normalized.size
                fitted = ImageOps.contain(normalized, MAP_CANVAS_SIZE, Image.Resampling.LANCZOS)
                canvas = Image.new("RGBA", MAP_CANVAS_SIZE, (36, 29, 22, 255))
                left = (MAP_CANVAS_WIDTH - fitted.width) // 2
                top = (MAP_CANVAS_HEIGHT - fitted.height) // 2
                canvas.alpha_composite(fitted, (left, top))
                canvas.convert("RGB").save(temporary, format="PNG", optimize=True)
            finally:
                opened_source.close()
            with temporary.open("rb+") as target_stream:
                target_stream.flush()
                os.fsync(target_stream.fileno())
            with Image.open(temporary) as verified:
                verified.load()
                if verified.size != MAP_CANVAS_SIZE:
                    raise ValueError("The imported map dimensions changed unexpectedly")
            if temporary.stat().st_size <= 0:
                raise ValueError("The imported map image is empty")
            self._replace_with_backup(destination, temporary)
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "asset_id": self.map_asset_id(map_id),
            "sha256": _sha256(destination),
            "width": MAP_CANVAS_WIDTH,
            "height": MAP_CANVAS_HEIGHT,
            "source_width": source_width,
            "source_height": source_height,
            "mime_type": MIME_TYPES[stored_extension],
            "file_extension": stored_extension,
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
