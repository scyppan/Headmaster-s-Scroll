from __future__ import annotations

from pathlib import Path

from headmasters_scroll.paths import PROJECT_ROOT


ITEM_ASSET_DIRECTORY = PROJECT_ROOT / "assets" / "items"
SUPPORTED_IMAGE_EXTENSIONS = frozenset(
    {".gif", ".jpeg", ".jpg", ".png", ".webp"}
)


def normalize_item_image_reference(
    reference: str | Path | None,
    *,
    require_exists: bool = False,
) -> str:
    """Return a portable project-relative item-image reference.

    DBM deliberately stores only one shared path. It never copies or embeds
    the selected image, so any number of records can reuse the same asset.
    """

    raw_reference = str(reference or "").strip()
    if not raw_reference:
        return ""

    candidate = Path(raw_reference)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate

    resolved = candidate.resolve(strict=False)
    asset_root = ITEM_ASSET_DIRECTORY.resolve(strict=False)
    try:
        resolved.relative_to(asset_root)
    except ValueError as error:
        raise ValueError(
            "Item images must live under the project's assets/items folder."
        ) from error

    if resolved.suffix.casefold() not in SUPPORTED_IMAGE_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_IMAGE_EXTENSIONS))
        raise ValueError(f"Unsupported item image type. Use one of: {supported}.")

    if require_exists and not resolved.is_file():
        raise ValueError("The selected item image does not exist.")

    return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()


def resolve_item_image_reference(reference: str | Path | None) -> Path | None:
    normalized = normalize_item_image_reference(reference)
    if not normalized:
        return None
    return (PROJECT_ROOT / normalized).resolve(strict=False)


def list_item_image_assets(query: str = "") -> list[str]:
    """List reusable item images as portable references."""

    if not ITEM_ASSET_DIRECTORY.is_dir():
        return []

    search_terms = tuple(
        term for term in str(query or "").casefold().split() if term
    )
    references = []
    for candidate in ITEM_ASSET_DIRECTORY.rglob("*"):
        if (
            not candidate.is_file()
            or candidate.suffix.casefold() not in SUPPORTED_IMAGE_EXTENSIONS
        ):
            continue
        reference = normalize_item_image_reference(candidate)
        searchable = reference.casefold()
        if all(term in searchable for term in search_terms):
            references.append(reference)

    return sorted(references, key=str.casefold)
