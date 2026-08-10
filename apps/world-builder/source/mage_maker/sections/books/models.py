import uuid
from copy import deepcopy

from mage_maker.sections.events.models import (
    normalize_world_event_date,
    split_world_event_date,
)


BOOK_CONTENT_TYPES = (
    "Spell",
    "Proficiency",
    "Recipe",
)
BOOK_CONTENT_COLLECTIONS = {
    "Spell": ("spells",),
    "Proficiency": ("proficiencies",),
    "Recipe": (
        "potions",
        "preparations",
        "foods_and_drinks",
        "materials",
        "ingredients",
    ),
}
BOOK_HOLDER_TYPES = (
    "Library",
    "Shop",
    "Private owner",
    "Location archive",
)
BOOK_READING_SOURCE_TYPES = (
    "Library",
    "School library",
    "Purchased",
    "Owned copy",
    "Other",
)


def normalize_compact_text(value):
    return " ".join(str(value or "").strip().split())


def normalize_optional_book_date(value):
    date_text = str(value or "").strip()
    return normalize_world_event_date(date_text) if date_text else ""


def book_date_start_key(value):
    year, month, day = split_world_event_date(value)
    return int(year), int(month or 1), int(day or 1)


def book_date_end_key(value):
    year, month, day = split_world_event_date(value)
    return int(year), int(month or 12), int(day or 31)


def book_date_is_on_or_before(candidate_date, target_date):
    if not str(candidate_date or "").strip():
        return True

    if not str(target_date or "").strip():
        return False

    return book_date_start_key(candidate_date) <= book_date_end_key(
        target_date
    )


def book_date_ranges_overlap_start(target_date, ending_date):
    if not str(ending_date or "").strip():
        return True

    if not str(target_date or "").strip():
        return False

    return book_date_start_key(target_date) <= book_date_end_key(
        ending_date
    )


def normalize_choice(value, choices, field_name):
    requested = normalize_compact_text(value)

    for choice in choices:
        if choice.casefold() == requested.casefold():
            return choice

    allowed = ", ".join(choices)
    raise ValueError(f"{field_name} must be one of: {allowed}.")


def normalize_nonnegative_integer(value, field_name, allow_blank=True):
    if value in (None, "") and allow_blank:
        return None

    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a nonnegative whole number.")

    try:
        normalized = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{field_name} must be a nonnegative whole number."
        ) from error

    if normalized < 0:
        raise ValueError(f"{field_name} cannot be negative.")

    return normalized


def normalize_book_content_entry(value):
    if not isinstance(value, dict):
        raise TypeError("A book content entry must be an object.")

    normalized = deepcopy(value)
    normalized["entry_id"] = str(
        normalized.get("entry_id") or uuid.uuid4()
    ).strip()
    normalized["content_type"] = normalize_choice(
        normalized.get("content_type"),
        BOOK_CONTENT_TYPES,
        "Book content type",
    )
    normalized["collection"] = normalize_compact_text(
        normalized.get("collection")
    )

    if normalized["collection"] not in BOOK_CONTENT_COLLECTIONS[
        normalized["content_type"]
    ]:
        raise ValueError(
            "The selected source collection does not match the book "
            "content type."
        )

    normalized["record_id"] = str(
        normalized.get("record_id", "") or ""
    ).strip()
    normalized["name"] = normalize_compact_text(normalized.get("name"))

    if not normalized["name"]:
        raise ValueError("A book content entry needs a name.")

    return normalized


def normalize_book_contents(value):
    if value in (None, ""):
        candidates = []
    elif isinstance(value, (list, tuple)):
        candidates = list(value)
    else:
        raise TypeError("Book contents must be a list.")

    contents = []
    used_entry_ids = set()
    used_sources = set()

    for candidate in candidates:
        entry = normalize_book_content_entry(candidate)

        if entry["entry_id"] in used_entry_ids:
            raise ValueError("Book content entry IDs must be unique.")

        source_key = (
            entry["content_type"].casefold(),
            entry["collection"],
            entry["record_id"] or entry["name"].casefold(),
        )

        if source_key in used_sources:
            continue

        used_entry_ids.add(entry["entry_id"])
        used_sources.add(source_key)
        contents.append(entry)

    contents.sort(key=book_content_sort_key)
    return contents


def book_content_sort_key(entry):
    return (
        BOOK_CONTENT_TYPES.index(entry["content_type"]),
        entry["name"].casefold(),
        entry["entry_id"],
    )


def normalize_book_holding(value):
    if not isinstance(value, dict):
        raise TypeError("A book holding must be an object.")

    normalized = deepcopy(value)
    normalized["entry_id"] = str(
        normalized.get("entry_id") or uuid.uuid4()
    ).strip()
    normalized["holder_type"] = normalize_choice(
        normalized.get("holder_type"),
        BOOK_HOLDER_TYPES,
        "Book holder type",
    )
    normalized["organization_id"] = str(
        normalized.get("organization_id", "") or ""
    ).strip()
    normalized["person_id"] = str(
        normalized.get("person_id", "") or ""
    ).strip()
    normalized["location_id"] = str(
        normalized.get("location_id", "") or ""
    ).strip()
    normalized["holder_name"] = normalize_compact_text(
        normalized.get("holder_name")
    )
    normalized["available_from"] = normalize_optional_book_date(
        normalized.get("available_from")
    )
    normalized["available_until"] = normalize_optional_book_date(
        normalized.get("available_until")
    )
    normalized["sold_out_date"] = normalize_optional_book_date(
        normalized.get("sold_out_date")
    )
    normalized["copies"] = normalize_nonnegative_integer(
        normalized.get("copies"),
        "Book copies",
    )
    normalized["price_sickles"] = normalize_nonnegative_integer(
        normalized.get("price_sickles"),
        "Book price",
    )
    normalized["notes"] = str(
        normalized.get("notes", "") or ""
    ).strip()

    if normalized["holder_type"] in ("Library", "Shop"):
        if not normalized["organization_id"] and not normalized["holder_name"]:
            raise ValueError(
                f"A {normalized['holder_type'].casefold()} holding needs "
                "an organization."
            )
    elif normalized["holder_type"] == "Private owner":
        if not normalized["person_id"] and not normalized["holder_name"]:
            raise ValueError("A private holding needs an owner.")
    elif not normalized["location_id"] and not normalized["holder_name"]:
        raise ValueError("A location archive holding needs a location.")

    if (
        normalized["available_from"]
        and normalized["available_until"]
        and not book_date_is_on_or_before(
            normalized["available_from"],
            normalized["available_until"],
        )
    ):
        raise ValueError("A book holding cannot end before it begins.")

    return normalized


def normalize_book_holdings(value):
    if value in (None, ""):
        candidates = []
    elif isinstance(value, (list, tuple)):
        candidates = list(value)
    else:
        raise TypeError("Book holdings must be a list.")

    holdings = []
    used_entry_ids = set()

    for candidate in candidates:
        holding = normalize_book_holding(candidate)

        if holding["entry_id"] in used_entry_ids:
            raise ValueError("Book holding entry IDs must be unique.")

        used_entry_ids.add(holding["entry_id"])
        holdings.append(holding)

    holdings.sort(key=book_holding_sort_key)
    return holdings


def book_holding_sort_key(holding):
    return (
        book_date_start_key(holding["available_from"])
        if holding["available_from"]
        else (-100000, 1, 1),
        BOOK_HOLDER_TYPES.index(holding["holder_type"]),
        holding["holder_name"].casefold(),
        holding["entry_id"],
    )


def normalize_book_record(value):
    if not isinstance(value, dict):
        raise TypeError("A book must be an object.")

    normalized = deepcopy(value)
    normalized["record_id"] = str(
        normalized.get("record_id") or uuid.uuid4()
    ).strip()
    normalized["title"] = normalize_compact_text(normalized.get("title"))

    if not normalized["title"]:
        raise ValueError("A book needs a title.")

    normalized["author_person_id"] = str(
        normalized.get("author_person_id", "") or ""
    ).strip()
    normalized["author_name"] = normalize_compact_text(
        normalized.get("author_name")
    )

    if not normalized["author_name"]:
        raise ValueError("A book needs an author.")

    publication_date = str(
        normalized.get("publication_date", "") or ""
    ).strip()

    if not publication_date:
        raise ValueError("A book needs a publication date.")

    normalized["publication_date"] = normalize_world_event_date(
        publication_date
    )
    normalized["publication_location_id"] = str(
        normalized.get("publication_location_id", "") or ""
    ).strip()
    normalized["publication_location_name"] = normalize_compact_text(
        normalized.get("publication_location_name")
    )
    normalized["mass_printed"] = bool(normalized.get("mass_printed", False))
    normalized["description"] = str(
        normalized.get("description", "") or ""
    ).strip()
    normalized["notes"] = str(
        normalized.get("notes", "") or ""
    ).strip()
    normalized["contents"] = normalize_book_contents(
        normalized.get("contents", [])
    )
    normalized["holdings"] = normalize_book_holdings(
        normalized.get("holdings", [])
    )

    if (
        not normalized["mass_printed"]
        and not normalized["publication_location_id"]
        and not normalized["holdings"]
    ):
        raise ValueError(
            "A book must be mass printed or begin with a publication "
            "location or possession entry."
        )

    return normalized


def normalize_book_records(value):
    if value in (None, ""):
        candidates = []
    elif isinstance(value, (list, tuple)):
        candidates = list(value)
    else:
        raise TypeError("Books must be a list.")

    books = []
    used_record_ids = set()
    used_titles = set()

    for candidate in candidates:
        book = normalize_book_record(candidate)
        title_key = book["title"].casefold()

        if book["record_id"] in used_record_ids:
            raise ValueError(
                f"Duplicate books record_id: {book['record_id']}"
            )

        if title_key in used_titles:
            raise ValueError(f"Duplicate book title: {book['title']}")

        used_record_ids.add(book["record_id"])
        used_titles.add(title_key)
        books.append(book)

    books.sort(key=book_sort_key)
    return books


def book_sort_key(book):
    return (
        book_date_start_key(book["publication_date"]),
        book["title"].casefold(),
        book["record_id"],
    )


def normalize_book_reading(value):
    if not isinstance(value, dict):
        raise TypeError("A book reading must be an object.")

    normalized = deepcopy(value)
    normalized["record_id"] = str(
        normalized.get("record_id") or uuid.uuid4()
    ).strip()
    normalized["person_id"] = str(
        normalized.get("person_id", "") or ""
    ).strip()
    normalized["person_name"] = normalize_compact_text(
        normalized.get("person_name")
    )
    normalized["book_id"] = str(
        normalized.get("book_id", "") or ""
    ).strip()
    normalized["book_title"] = normalize_compact_text(
        normalized.get("book_title")
    )
    normalized["author_name"] = normalize_compact_text(
        normalized.get("author_name")
    )
    normalized["date"] = normalize_world_event_date(
        normalized.get("date")
    )
    normalized["source_type"] = normalize_choice(
        normalized.get("source_type"),
        BOOK_READING_SOURCE_TYPES,
        "Book reading source",
    )
    normalized["source_entry_id"] = str(
        normalized.get("source_entry_id", "") or ""
    ).strip()
    normalized["source_organization_id"] = str(
        normalized.get("source_organization_id", "") or ""
    ).strip()
    normalized["source_person_id"] = str(
        normalized.get("source_person_id", "") or ""
    ).strip()
    normalized["source_location_id"] = str(
        normalized.get("source_location_id", "") or ""
    ).strip()
    normalized["source_name"] = normalize_compact_text(
        normalized.get("source_name")
    )
    normalized["price_sickles"] = normalize_nonnegative_integer(
        normalized.get("price_sickles"),
        "Book purchase price",
    )
    normalized["notes"] = str(
        normalized.get("notes", "") or ""
    ).strip()

    if not normalized["person_id"]:
        raise ValueError("A book reading needs a reader.")

    if not normalized["book_id"]:
        raise ValueError("A book reading needs a book.")

    if not normalized["book_title"]:
        raise ValueError("A book reading needs a stored book title.")

    return normalized


def normalize_book_readings(value):
    if value in (None, ""):
        candidates = []
    elif isinstance(value, (list, tuple)):
        candidates = list(value)
    else:
        raise TypeError("Book readings must be a list.")

    readings = []
    used_record_ids = set()

    for candidate in candidates:
        reading = normalize_book_reading(candidate)

        if reading["record_id"] in used_record_ids:
            raise ValueError(
                f"Duplicate book_readings record_id: {reading['record_id']}"
            )

        used_record_ids.add(reading["record_id"])
        readings.append(reading)

    readings.sort(key=book_reading_sort_key)
    return readings


def book_reading_sort_key(reading):
    return (
        book_date_start_key(reading["date"]),
        reading["book_title"].casefold(),
        reading["record_id"],
    )


def book_is_published_on(book, target_date):
    normalized = normalize_book_record(book)
    return book_date_is_on_or_before(
        normalized["publication_date"],
        target_date,
    )


def book_holding_is_active(holding, target_date):
    normalized = normalize_book_holding(holding)

    if not book_date_is_on_or_before(
        normalized["available_from"],
        target_date,
    ):
        return False

    if not book_date_ranges_overlap_start(
        target_date,
        normalized["available_until"],
    ):
        return False

    if normalized["sold_out_date"] and book_date_is_on_or_before(
        normalized["sold_out_date"],
        target_date,
    ):
        return False

    return normalized["copies"] is None or normalized["copies"] > 0


def book_reading_source_text(reading):
    normalized = normalize_book_reading(reading)
    source_name = normalized["source_name"] or "Unknown source"

    if normalized["source_type"] == "Purchased":
        return f"Purchased at {source_name}"

    if normalized["source_type"] == "School library":
        return f"Read at {source_name} library"

    if normalized["source_type"] == "Library":
        return f"Read at {source_name} library"

    if normalized["source_type"] == "Owned copy":
        return f"Read from {source_name}"

    return f"Read via {source_name}"
