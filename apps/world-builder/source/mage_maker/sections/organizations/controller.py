import hashlib
import re
import uuid
from copy import deepcopy

from mage_maker.core.dates import (
    LATEST_HISTORICAL_YEAR,
    next_historical_date,
    previous_historical_date,
)
from mage_maker.core.wizarding_currency import normalize_monthly_salary
from mage_maker.sections.development.event_eminence import (
    apply_event_eminence_updates,
    prepare_event_eminence_updates,
)
from mage_maker.sections.development.models import (
    job_assignment_active_on,
    job_date_tuple,
    normalize_job_records,
)
from mage_maker.sections.locations.models import (
    ancestor_locations,
    location_paths_by_id,
    normalize_location_record,
    recent_location_label,
)
from mage_maker.sections.events.models import (
    event_linked_person_ids,
    normalize_association_values,
    normalize_eminence_skill_values,
    normalize_world_event,
    normalize_world_event_date,
    normalize_world_event_time,
    split_world_event_date,
    world_event_sort_key,
    world_event_year,
)
from mage_maker.sections.items.links import (
    normalize_item_event_link_types,
    normalize_item_event_new_owners,
)
from mage_maker.sections.settings.simulation import (
    DATABASE_DATE_SETTING_KEY,
    normalize_database_date,
)
from mage_maker.ui.colored_tags import normalize_colored_tags


ORGANIZATION_TYPES = (
    "Governmental",
    "Non-profit",
    "Media",
    "School",
    "Shop",
)
ORGANIZATION_EVENT_FOUNDING = "founding"
SHOP_STOCK_CATEGORIES = (
    ("always_in_stock", "Always in stock"),
    ("regularly_in_stock", "Regularly in stock"),
    ("sometimes_in_stock", "Sometimes in stock"),
    ("rarely_in_stock", "Rarely in stock"),
)


def normalize_storeroom_inventory(value):
    if value in (None, ""):
        candidate_items = []
    elif isinstance(value, (list, tuple)):
        candidate_items = list(value)
    else:
        raise TypeError("Organization storeroom inventory must be a list.")

    normalized_items = []
    used_identities = set()

    for candidate in candidate_items:
        if not isinstance(candidate, dict):
            raise TypeError("Every storeroom item must be an object.")

        collection = str(candidate.get("collection", "") or "").strip()
        record_id = str(candidate.get("record_id", "") or "").strip()

        if not collection or not record_id:
            raise ValueError(
                "Every storeroom item must identify its database collection."
            )

        identity = (collection, record_id)

        if identity in used_identities:
            continue

        used_identities.add(identity)
        normalized_items.append(
            {
                "collection": collection,
                "record_id": record_id,
            }
        )

    return normalized_items


def normalize_organization_event(value):
    if not isinstance(value, dict):
        raise TypeError("An organization event must be an object.")

    event_type = str(
        value.get("event_type", "") or ""
    ).strip().casefold()
    title = str(value.get("title", "") or "").strip()

    if event_type == ORGANIZATION_EVENT_FOUNDING:
        title = "Founding"
    elif not title:
        raise ValueError("An organization event must have a title.")

    event_date = str(value.get("date", "") or "").strip()

    if not event_date:
        year_value = value.get("year")
        month_value = value.get("month")
        day_value = value.get("day")

        if year_value in (None, ""):
            if month_value not in (None, "") or day_value not in (None, ""):
                raise ValueError(
                    "Organization event month and day require a year."
                )
        else:
            event_date = str(year_value).strip()

            if month_value not in (None, ""):
                event_date += f"-{month_value}"

            if day_value not in (None, ""):
                if month_value in (None, ""):
                    raise ValueError(
                        "Organization event day requires a month."
                    )

                event_date += f"-{day_value}"

    if event_date:
        event_date = normalize_world_event_date(event_date)
        year = world_event_year(event_date)
    else:
        year = None

    description = str(
        value.get("description", "") or ""
    ).strip()
    event_time = normalize_world_event_time(value.get("time"))
    person_ids = normalize_association_values(
        value.get("person_ids", [])
    )
    witness_person_ids = normalize_association_values(
        value.get("witness_person_ids", [])
    )
    affected_person_ids = normalize_association_values(
        value.get("affected_person_ids", [])
    )
    item_ids = normalize_association_values(
        value.get("item_ids", [])
    )
    item_link_types = normalize_item_event_link_types(
        value.get("item_link_types"),
        item_ids,
        event_type,
    )
    item_new_owners = normalize_item_event_new_owners(
        value.get("item_new_owners"),
        item_ids,
        item_link_types,
    )
    linked_person_ids = set(
        normalize_association_values(
            [
                *person_ids,
                *witness_person_ids,
                *affected_person_ids,
            ]
        )
    )
    eminence_person_ids = [
        person_id
        for person_id in normalize_association_values(
            value.get("eminence_person_ids", [])
        )
        if person_id in linked_person_ids
    ]
    eminence_skills = normalize_eminence_skill_values(
        value.get("eminence_skills"),
        eminence_person_ids,
    )
    record_id = str(
        value.get("record_id", "") or ""
    ).strip()

    if event_type == ORGANIZATION_EVENT_FOUNDING:
        record_id = "organization-founding"
    elif not record_id:
        identity_parts = (
            title.casefold(),
            event_date,
            description.casefold(),
        )

        if event_time:
            identity_parts = (
                title.casefold(),
                event_date,
                event_time,
                description.casefold(),
            )

        identity_text = "|".join(identity_parts)
        record_id = "organization-event-" + hashlib.sha256(
            identity_text.encode("utf-8")
        ).hexdigest()[:20]

    normalized_event = {
        "record_id": record_id,
        "event_type": event_type or "event",
        "title": title,
        "date": event_date,
        "time": event_time,
        "year": year,
        "description": description,
        "person_ids": person_ids,
        "item_ids": item_ids,
        "item_link_types": item_link_types,
        "item_new_owners": item_new_owners,
        "eminence_person_ids": eminence_person_ids,
        "eminence_skills": eminence_skills,
    }

    if "witness_person_ids" in value:
        normalized_event["witness_person_ids"] = witness_person_ids

    if "affected_person_ids" in value:
        normalized_event["affected_person_ids"] = affected_person_ids

    return normalized_event


def normalize_organization_events(value):
    if value in (None, ""):
        candidate_events = []
    elif isinstance(value, (list, tuple)):
        candidate_events = list(value)
    else:
        raise TypeError("Organization events must be a list.")

    founding_event = None
    other_events = []

    for candidate_event in candidate_events:
        normalized_event = normalize_organization_event(
            candidate_event
        )

        if (
            normalized_event["event_type"]
            == ORGANIZATION_EVENT_FOUNDING
        ):
            if founding_event is None:
                founding_event = normalized_event

            continue

        other_events.append(normalized_event)

    if founding_event is None:
        founding_event = normalize_organization_event(
            {
                "event_type": ORGANIZATION_EVENT_FOUNDING,
                "title": "Founding",
                "year": None,
                "description": "",
            }
        )

    other_events.sort(key=world_event_sort_key)
    return [founding_event, *other_events]


def new_organization_event(
    title,
    year,
    description="",
    person_ids=(),
    eminence_person_ids=(),
    eminence_skills=None,
    month=None,
    day=None,
    witness_person_ids=(),
    affected_person_ids=(),
    item_ids=(),
    item_link_types=None,
    item_new_owners=None,
    time="",
):
    return normalize_organization_event(
        {
            "record_id": str(uuid.uuid4()),
            "event_type": "event",
            "title": title,
            "year": year,
            "month": month,
            "day": day,
            "time": time,
            "description": description,
            "person_ids": list(person_ids),
            "witness_person_ids": list(witness_person_ids),
            "affected_person_ids": list(affected_person_ids),
            "item_ids": list(item_ids),
            "item_link_types": dict(item_link_types or {}),
            "item_new_owners": dict(item_new_owners or {}),
            "eminence_person_ids": list(
                eminence_person_ids
            ),
            "eminence_skills": dict(eminence_skills or {}),
        }
    )


def organization_event_world_id(
    organization_id,
    organization_event_id,
):
    return (
        "organization-event:"
        f"{str(organization_id or '').strip()}:"
        f"{str(organization_event_id or '').strip()}"
    )


def organization_event_as_world_event(
    organization,
    organization_event,
):
    normalized_organization = normalize_organization_record(
        organization
    )
    normalized_event = normalize_organization_event(
        organization_event
    )
    organization_id = str(
        normalized_organization.get("record_id", "") or ""
    ).strip()
    is_founding = (
        normalized_event["event_type"]
        == ORGANIZATION_EVENT_FOUNDING
    )
    world_title = (
        f"Founding of {normalized_organization['name']}"
        if is_founding
        else normalized_event["title"]
    )
    return normalize_world_event(
        {
            "record_id": organization_event_world_id(
                organization_id,
                normalized_event["record_id"],
            ),
            "event_type": (
                "organization_founding"
                if is_founding
                else "other"
            ),
            "title": world_title,
            "date": normalized_event["date"],
            "time": normalized_event["time"],
            "description": normalized_event["description"],
            "person_ids": normalized_event["person_ids"],
            "item_ids": normalized_event["item_ids"],
            "item_link_types": normalized_event["item_link_types"],
            "item_new_owners": normalized_event["item_new_owners"],
            **(
                {
                    "witness_person_ids": normalized_event[
                        "witness_person_ids"
                    ]
                }
                if "witness_person_ids" in normalized_event
                else {}
            ),
            **(
                {
                    "affected_person_ids": normalized_event[
                        "affected_person_ids"
                    ]
                }
                if "affected_person_ids" in normalized_event
                else {}
            ),
            "eminence_person_ids": normalized_event[
                "eminence_person_ids"
            ],
            "eminence_skills": normalized_event[
                "eminence_skills"
            ],
            "location_ids": [],
            "locked_location_ids": [],
            "organization_id": organization_id,
            "organization_name": normalized_organization["name"],
            "organization_event_id": normalized_event["record_id"],
            "organization_event": True,
        }
    )


def organization_event_from_world_event(
    world_event,
    existing_event,
):
    normalized_world_event = normalize_world_event(world_event)
    normalized_existing = normalize_organization_event(
        existing_event
    )
    return normalize_organization_event(
        {
            **normalized_existing,
            "title": normalized_world_event["title"],
            "date": normalized_world_event["date"],
            "time": normalized_world_event["time"],
            "description": normalized_world_event["description"],
            "person_ids": normalized_world_event["person_ids"],
            "item_ids": normalized_world_event["item_ids"],
            "item_link_types": normalized_world_event["item_link_types"],
            "item_new_owners": normalized_world_event[
                "item_new_owners"
            ],
            "witness_person_ids": normalized_world_event.get(
                "witness_person_ids",
                [],
            ),
            "affected_person_ids": normalized_world_event.get(
                "affected_person_ids",
                [],
            ),
            "eminence_person_ids": normalized_world_event[
                "eminence_person_ids"
            ],
            "eminence_skills": normalized_world_event[
                "eminence_skills"
            ],
        }
    )


def organization_events_as_world_events(organizations):
    world_events = []

    for organization in organizations or []:
        if not isinstance(organization, dict):
            continue

        for organization_event in normalize_organization_events(
            organization.get("events", [])
        ):
            world_events.append(
                organization_event_as_world_event(
                    organization,
                    organization_event,
                )
            )

    return world_events


def normalize_organization_job(value):
    if not isinstance(value, dict):
        raise TypeError("An organization job must be an object.")

    title = str(value.get("title", "") or "").strip()
    if not title:
        raise ValueError("An organization job must have a title.")

    level_value = value.get("level", 0)

    if isinstance(level_value, bool):
        raise ValueError("Position level must be a non-negative whole number.")

    try:
        level = int(level_value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Position level must be a non-negative whole number."
        ) from error

    if level < 0:
        raise ValueError("Position level cannot be negative.")

    opened_date = organization_job_date(
        value,
        "opened",
        required=True,
    )
    closed_date = organization_job_date(
        value,
        "closed",
        required=False,
    )
    opened_year_text, opened_month_text, opened_day_text = (
        split_world_event_date(opened_date)
    )
    closed_year_text, closed_month_text, closed_day_text = (
        split_world_event_date(closed_date)
    )
    opened_year = int(opened_year_text)

    if closed_date and organization_job_date_tuple(
        closed_date,
        end_boundary=True,
    ) < organization_job_date_tuple(opened_date):
        raise ValueError(
            "A position cannot close before it opened."
        )

    record_id = str(
        value.get("record_id", "") or ""
    ).strip()

    if not record_id:
        identity_text = "|".join(
            (
                str(
                    value.get("organization_id", "") or ""
                ).strip().casefold(),
                title.casefold(),
                opened_date,
            )
        )
        record_id = "organization-job-" + hashlib.sha256(
            identity_text.encode("utf-8")
        ).hexdigest()[:20]

    return {
        "record_id": record_id,
        "title": title,
        "level": level,
        "opened_date": opened_date,
        "opened_year": opened_year,
        "opened_month": (
            int(opened_month_text) if opened_month_text else None
        ),
        "opened_day": (
            int(opened_day_text) if opened_day_text else None
        ),
        "closed_date": closed_date,
        "closed_year": (
            int(closed_year_text) if closed_year_text else None
        ),
        "closed_month": (
            int(closed_month_text) if closed_month_text else None
        ),
        "closed_day": (
            int(closed_day_text) if closed_day_text else None
        ),
    }


def organization_job_date(value, prefix, required=False):
    date_value = str(
        value.get(f"{prefix}_date", "") or ""
    ).strip()

    if not date_value:
        year_value = value.get(
            f"{prefix}_year",
            value.get("start_year") if prefix == "opened" else None,
        )
        month_value = value.get(f"{prefix}_month")
        day_value = value.get(f"{prefix}_day")

        if year_value not in (None, ""):
            date_value = str(year_value).strip()

            if month_value not in (None, ""):
                date_value += f"-{month_value}"

            if day_value not in (None, ""):
                if month_value in (None, ""):
                    raise ValueError(
                        f"Position {prefix} day requires a month."
                    )

                date_value += f"-{day_value}"
        elif month_value not in (None, "") or day_value not in (None, ""):
            raise ValueError(
                f"Position {prefix} month and day require a year."
            )

    if not date_value:
        if required:
            raise ValueError("Enter the year this position opened.")

        return ""

    try:
        return normalize_world_event_date(date_value)
    except ValueError as error:
        field_name = f"Position {prefix}"
        message = str(error).replace("Event", field_name).replace(
            "event",
            field_name.casefold(),
        )
        raise ValueError(message) from error


def organization_job_date_tuple(value, end_boundary=False):
    year_text, month_text, day_text = split_world_event_date(value)
    return job_date_tuple(
        int(year_text),
        int(month_text) if month_text else None,
        int(day_text) if day_text else None,
        end_boundary=end_boundary,
    )


def normalize_organization_jobs(value):
    if value in (None, ""):
        candidate_jobs = []
    elif isinstance(value, (list, tuple)):
        candidate_jobs = list(value)
    else:
        raise TypeError("Organization jobs must be a list.")

    normalized_jobs = []
    seen_ids = set()

    for candidate_job in candidate_jobs:
        normalized_job = normalize_organization_job(
            candidate_job
        )

        if normalized_job["record_id"] in seen_ids:
            raise ValueError(
                "Organization job record IDs must be unique."
            )

        normalized_jobs.append(normalized_job)
        seen_ids.add(normalized_job["record_id"])

    normalized_jobs.sort(
        key=lambda job: (
            job["level"],
            job["title"].casefold(),
            organization_job_date_tuple(job["opened_date"]),
            job["record_id"],
        )
    )
    return normalized_jobs


def new_organization_job(
    title,
    opened_year,
    opened_month=None,
    opened_day=None,
    closed_year=None,
    closed_month=None,
    closed_day=None,
    level=0,
):
    return normalize_organization_job(
        {
            "record_id": str(uuid.uuid4()),
            "title": title,
            "level": level,
            "opened_year": opened_year,
            "opened_month": opened_month,
            "opened_day": opened_day,
            "closed_year": closed_year,
            "closed_month": closed_month,
            "closed_day": closed_day,
        }
    )


def normalize_shop_inventory(value):
    if value in (None, ""):
        candidate_inventory = {}
    elif isinstance(value, dict):
        candidate_inventory = value
    else:
        raise TypeError("Organization shop inventory must be an object.")

    normalized_inventory = {}

    for category_key, category_label in SHOP_STOCK_CATEGORIES:
        candidate_products = candidate_inventory.get(category_key, [])

        if candidate_products in (None, ""):
            candidate_products = []
        elif not isinstance(candidate_products, (list, tuple, set)):
            raise TypeError(
                f"{category_label} products must be stored as a list."
            )

        normalized_products = []

        for product_id in candidate_products:
            normalized_product_id = str(product_id or "").strip()

            if (
                normalized_product_id
                and normalized_product_id not in normalized_products
            ):
                normalized_products.append(normalized_product_id)

        normalized_inventory[category_key] = normalized_products

    return normalized_inventory


def normalize_organization_extinction_date(value, extinct):
    if not extinct:
        return ""

    extinction_date = str(value or "").strip()

    if not extinction_date:
        raise ValueError("Enter the date this organization became extinct.")

    try:
        return normalize_world_event_date(extinction_date)
    except ValueError as error:
        message = str(error).replace("Event", "Extinction").replace(
            "event",
            "extinction",
        )
        raise ValueError(message) from error


def normalize_organization_record(values):
    if not isinstance(values, dict):
        raise TypeError("An organization must be an object.")

    normalized = deepcopy(values)
    normalized["name"] = str(
        normalized.get("name", "") or ""
    ).strip()
    normalized["organization_type"] = str(
        normalized.get("organization_type", "") or ""
    ).strip()
    has_explicit_shop_flag = "has_shop" in normalized
    normalized["has_shop"] = (
        bool(normalized.get("has_shop"))
        if has_explicit_shop_flag
        else normalized["organization_type"] == "Shop"
    )
    normalized["shop_inventory"] = normalize_shop_inventory(
        normalized.get("shop_inventory", {})
    )
    normalized["famous_organization"] = bool(
        normalized.get("famous_organization", False)
    )
    normalized["is_faction"] = bool(
        normalized.get("is_faction", False)
    )
    faction_color = str(
        normalized.get("faction_color", "#808080") or "#808080"
    ).strip().upper()
    if not re.fullmatch(r"#[0-9A-F]{6}", faction_color):
        raise ValueError("Faction color must use #RRGGBB format.")
    normalized["faction_color"] = faction_color
    normalized["has_storeroom"] = bool(
        normalized.get("has_storeroom", False)
    )
    normalized["includes_library"] = bool(
        normalized.get("includes_library", False)
    )
    normalized["library_open_to_outsiders"] = bool(
        normalized.get("library_open_to_outsiders", False)
    ) and normalized["includes_library"]
    normalized["storeroom_inventory"] = (
        normalize_storeroom_inventory(
            normalized.get("storeroom_inventory", [])
        )
    )
    normalized["extinct"] = bool(normalized.get("extinct", False))
    normalized["extinction_date"] = (
        normalize_organization_extinction_date(
            normalized.get("extinction_date", ""),
            normalized["extinct"],
        )
    )
    normalized["location_id"] = str(
        normalized.get("location_id", "") or ""
    ).strip()
    normalized["campus_location_id"] = str(
        normalized.get("campus_location_id", "") or ""
    ).strip()
    normalized["also_location"] = (
        normalized["organization_type"] == "School"
        or bool(normalized.get("also_location", False))
    )
    normalized["parent_organization_id"] = str(
        normalized.get("parent_organization_id", "") or ""
    ).strip()
    normalized["school_id"] = str(
        normalized.get("school_id", "") or ""
    ).strip()
    normalized["overview"] = str(
        normalized.get("overview", "") or ""
    ).strip()
    normalized["notes"] = str(
        normalized.get("notes", "") or ""
    ).strip()
    normalized["tags"] = normalize_colored_tags(
        normalized.get("tags", [])
    )
    normalized["events"] = normalize_organization_events(
        normalized.get("events", [])
    )
    job_values = []

    for organization_job in normalized.get("jobs", []) or []:
        if not isinstance(organization_job, dict):
            job_values.append(organization_job)
            continue

        prepared_job = {
            **organization_job,
            "organization_id": str(
                normalized.get("record_id", "") or ""
            ),
        }

        if (
            normalized["extinct"]
            and normalized["extinction_date"]
            and not organization_job_date(
                prepared_job,
                "closed",
                required=False,
            )
        ):
            prepared_job["closed_date"] = normalized[
                "extinction_date"
            ]

        job_values.append(prepared_job)

    normalized["jobs"] = normalize_organization_jobs(job_values)
    return normalized


def school_campus_name(organization):
    organization_name = str(
        (organization or {}).get("name", "")
        or "Unnamed school"
    ).strip()
    if str((organization or {}).get("organization_type", "")) == "School":
        return f"Campus of {organization_name}"

    return organization_name


def school_campus_foundation_event(organization):
    normalized = normalize_organization_record(organization)
    organization_id = str(
        normalized.get("record_id", "") or ""
    ).strip()
    founding_event = normalize_organization_events(
        normalized.get("events", [])
    )[0]
    campus_name = school_campus_name(normalized)
    return {
        "event_id": f"school-campus-founding:{organization_id}",
        "event_type": "founding",
        "title": f"Founding of {campus_name}",
        "date": str(founding_event.get("date", "") or ""),
        "time": str(founding_event.get("time", "") or ""),
        "note": f"Location linked to {normalized['name']}.",
    }


def synchronize_school_campus_locations(database_data):
    if not isinstance(database_data, dict):
        return False

    stored_locations = database_data.get("locations", [])
    stored_organizations = database_data.get("organizations", [])

    if not isinstance(stored_locations, list) or not isinstance(
        stored_organizations,
        list,
    ):
        return False

    locations = [
        deepcopy(location)
        for location in stored_locations
        if isinstance(location, dict)
    ]
    organizations = [
        normalize_organization_record(organization)
        for organization in stored_organizations
        if isinstance(organization, dict)
    ]
    locations_by_id = {
        str(location.get("record_id", "") or "").strip(): location
        for location in locations
        if str(location.get("record_id", "") or "").strip()
    }
    changed = False

    for organization in organizations:
        if not organization.get("also_location"):
            continue

        organization_id = str(
            organization.get("record_id", "") or ""
        ).strip()
        home_location_id = str(
            organization.get("location_id", "") or ""
        ).strip()

        if (
            not organization_id
            or not home_location_id
            or home_location_id not in locations_by_id
        ):
            continue

        campus_location_id = str(
            organization.get("campus_location_id", "") or ""
        ).strip()
        campus = (
            locations_by_id.get(campus_location_id)
            if campus_location_id != home_location_id
            else None
        )

        if campus is None:
            campus = next(
                (
                    location
                    for location in locations
                    if str(
                        location.get("campus_organization_id", "")
                        or ""
                    ).strip()
                    == organization_id
                ),
                None,
            )

        if campus is None:
            desired_name = school_campus_name(organization)
            campus = next(
                (
                    location
                    for location in locations
                    if str(location.get("name", "") or "")
                    .strip()
                    .casefold()
                    == desired_name.casefold()
                    and str(
                        location.get("parent_location_id", "") or ""
                    ).strip()
                    == home_location_id
                ),
                None,
            )

        if campus is None:
            campus_location_id = f"organization-location:{organization_id}"

            if campus_location_id in locations_by_id:
                campus_location_id = str(uuid.uuid4())

            campus = {
                "record_id": campus_location_id,
                "name": school_campus_name(organization),
                "parent_location_id": home_location_id,
                "campus_organization_id": organization_id,
                "demographics": "",
                "notes": "",
                "extinct": False,
                "extinction_year": "",
                "timeline_events": [],
            }
            locations.append(campus)
            locations_by_id[campus_location_id] = campus
            changed = True

        campus_location_id = str(
            campus.get("record_id", "") or ""
        ).strip()
        generated_event_id = (
            f"school-campus-founding:{organization_id}"
        )
        timeline_events = [
            deepcopy(event)
            for event in campus.get("timeline_events", []) or []
            if isinstance(event, dict)
            and str(event.get("event_id", "") or "").strip()
            != generated_event_id
        ]
        has_other_foundation = any(
            str(event.get("event_type", "") or "")
            in ("founding", "wizarding_community_established")
            for event in timeline_events
        )

        if not has_other_foundation:
            timeline_events.append(
                school_campus_foundation_event(organization)
            )

        updated_campus = normalize_location_record(
            {
                **campus,
                "name": school_campus_name(organization),
                "parent_location_id": home_location_id,
                "campus_organization_id": organization_id,
                "timeline_events": timeline_events,
            }
        )
        updated_campus["record_id"] = campus_location_id

        if campus != updated_campus:
            campus.clear()
            campus.update(updated_campus)
            changed = True

        if organization.get("campus_location_id") != campus_location_id:
            organization["campus_location_id"] = campus_location_id
            changed = True

    normalized_organizations = [
        normalize_organization_record(organization)
        for organization in organizations
    ]

    if stored_locations != locations:
        database_data["locations"] = locations
        changed = True

    if stored_organizations != normalized_organizations:
        database_data["organizations"] = normalized_organizations
        changed = True

    return changed


def organization_path(record_id, organizations):
    organizations_by_id = {
        str(organization.get("record_id", "") or ""): organization
        for organization in organizations
        if isinstance(organization, dict)
        and str(organization.get("record_id", "") or "")
    }
    return organization_path_from_records(
        record_id,
        organizations_by_id,
    )


def organization_path_from_records(record_id, organizations_by_id):
    current_id = str(record_id or "").strip()
    path_names = []
    visited_ids = set()

    while current_id and current_id not in visited_ids:
        organization = organizations_by_id.get(current_id)

        if organization is None:
            break

        path_names.append(
            str(
                organization.get("name", "Unnamed")
                or "Unnamed"
            ).strip()
        )
        visited_ids.add(current_id)
        current_id = str(
            organization.get(
                "parent_organization_id",
                "",
            )
            or ""
        ).strip()

    path_names.reverse()
    return " / ".join(path_names)


def organization_paths_by_id(organizations):
    organizations_by_id = {
        str(organization.get("record_id", "") or ""): organization
        for organization in organizations
        if isinstance(organization, dict)
        and str(organization.get("record_id", "") or "")
    }
    return {
        record_id: organization_path_from_records(
            record_id,
            organizations_by_id,
        )
        for record_id in organizations_by_id
    }


def organizations_by_id(organizations):
    return {
        str(organization.get("record_id", "") or "").strip(): organization
        for organization in organizations or []
        if isinstance(organization, dict)
        and str(organization.get("record_id", "") or "").strip()
    }


def organization_root_ancestor(record_id, organizations):
    records = organizations_by_id(organizations)
    current_id = str(record_id or "").strip()
    root = records.get(current_id)
    visited_ids = set()

    while current_id and current_id not in visited_ids:
        visited_ids.add(current_id)
        current = records.get(current_id)

        if current is None:
            break

        root = current
        parent_id = str(
            current.get("parent_organization_id", "") or ""
        ).strip()

        if not parent_id or parent_id not in records:
            break

        current_id = parent_id

    return root


def organization_context_label(record_id, organizations, locations=None):
    records = organizations_by_id(organizations)
    selected_id = str(record_id or "").strip()
    organization = records.get(selected_id)

    if organization is None:
        return "Unknown organization"

    name = str(
        organization.get("name", "") or "Unnamed organization"
    ).strip()
    home_location_id = str(
        organization.get("location_id", "") or ""
    ).strip()

    if (
        organization.get("organization_type") == "School"
        and home_location_id
        and locations is not None
    ):
        return (
            f"{name} (a school in "
            f"{recent_location_label(home_location_id, locations)})"
        )

    parent_id = str(
        organization.get("parent_organization_id", "") or ""
    ).strip()

    if not parent_id or parent_id not in records:
        return name

    root = organization_root_ancestor(selected_id, organizations)
    root_name = str(
        (root or {}).get("name", "") or "Unnamed organization"
    ).strip()
    return f"{name} (within {root_name})"


def organization_ids_in_scope(organizations, scope_organization_id=""):
    records = organizations_by_id(organizations)
    scope_id = str(scope_organization_id or "").strip()

    if not scope_id:
        return set(records)

    if scope_id not in records:
        return set()

    scoped_ids = organization_descendant_ids(
        scope_id,
        organizations,
    )
    scoped_ids.add(scope_id)
    return scoped_ids


def organization_id_is_in_scope(
    organization_id,
    organizations,
    scope_organization_id="",
):
    selected_id = str(organization_id or "").strip()

    if not selected_id:
        return not str(scope_organization_id or "").strip()

    return selected_id in organization_ids_in_scope(
        organizations,
        scope_organization_id,
    )


def organization_descendant_ids(record_id, organizations):
    selected_id = str(record_id or "").strip()
    descendants = set()
    changed = True

    while changed:
        changed = False

        for organization in organizations:
            if not isinstance(organization, dict):
                continue

            organization_id = str(
                organization.get("record_id", "") or ""
            ).strip()
            parent_id = str(
                organization.get(
                    "parent_organization_id",
                    "",
                )
                or ""
            ).strip()

            if (
                organization_id
                and organization_id not in descendants
                and (
                    parent_id == selected_id
                    or parent_id in descendants
                )
            ):
                descendants.add(organization_id)
                changed = True

    return descendants


class OrganizationController:
    def __init__(
        self,
        database,
        locations_provider,
        schools_provider=None,
        items_provider=None,
        location_controller=None,
    ):
        self.database = database
        self.locations_provider = locations_provider
        self.schools_provider = schools_provider
        self.items_provider = items_provider
        self.location_controller = location_controller
        self._storeroom_item_options_cache = None

    def list_organizations(self):
        organizations = [
            self.apply_school_link(organization)
            for organization in self.database.list_records("organizations")
        ]
        paths_by_id = organization_paths_by_id(organizations)
        decorated = [
            (
                self.organization_sort_key_for(
                    organization,
                    organizations,
                    paths_by_id,
                ),
                organization,
            )
            for organization in organizations
        ]
        decorated.sort(key=self.decorated_organization_sort_key)
        return [
            organization
            for sort_key, organization in decorated
        ]

    def decorated_organization_sort_key(self, decorated):
        return decorated[0]

    def organization_sort_key_for(
        self,
        organization,
        organizations,
        paths_by_id=None,
    ):
        organization_id = str(
            organization.get("record_id", "") or ""
        )
        return (
            (
                paths_by_id.get(organization_id, "")
                if paths_by_id is not None
                else organization_path(
                    organization_id,
                    organizations,
                )
            ).casefold(),
            str(
                organization.get("organization_type", "") or ""
            ).casefold(),
        )

    def organization_sort_key(self, organization):
        return self.organization_sort_key_for(
            organization,
            self.list_organizations(),
        )

    def get_organization(self, record_id):
        organization = self.database.read_record(
            "organizations",
            record_id,
        )

        if organization is None:
            return None

        return self.apply_school_link(organization)

    def create_organization(self, values):
        normalized = self.normalize_organization(values)

        if not str(normalized.get("record_id", "") or "").strip():
            normalized["record_id"] = str(uuid.uuid4())

        self.validate_organization(normalized)
        eminence_updates = prepare_event_eminence_updates(
            self.database,
            (),
            organization_events_as_world_events((normalized,)),
        )
        created = self.database.create_record("organizations", normalized)
        created = self.ensure_school_campus(created)
        apply_event_eminence_updates(
            self.database,
            eminence_updates,
        )
        self.database.save()
        return created

    def create_default_organization(
        self,
        parent_organization_id="",
        location_id="",
    ):
        existing_names = {
            str(organization.get("name", "") or "").strip().casefold()
            for organization in self.list_organizations()
        }
        organization_name = "New Organization"
        suffix = 2

        while organization_name.casefold() in existing_names:
            organization_name = f"New Organization {suffix}"
            suffix += 1

        database_data = getattr(self.database, "data", {})
        application_settings = (
            database_data.get("_application_settings", {})
            if isinstance(database_data, dict)
            else {}
        )
        database_date = normalize_database_date(
            application_settings.get(DATABASE_DATE_SETTING_KEY)
            if isinstance(application_settings, dict)
            else None
        )
        selected_parent_id = str(
            parent_organization_id or ""
        ).strip()
        selected_location_id = str(location_id or "").strip()
        parent = self.get_organization(selected_parent_id)

        if parent is None:
            selected_parent_id = ""
        elif not selected_location_id:
            selected_location_id = str(
                parent.get("location_id", "") or ""
            ).strip()

        return self.create_organization(
            {
                "name": organization_name,
                "organization_type": ORGANIZATION_TYPES[0],
                "location_id": selected_location_id,
                "parent_organization_id": selected_parent_id,
                "school_id": "",
                "also_location": False,
                "has_shop": False,
                "shop_inventory": normalize_shop_inventory({}),
                "famous_organization": False,
                "has_storeroom": False,
                "storeroom_inventory": [],
                "includes_library": False,
                "library_open_to_outsiders": False,
                "extinct": False,
                "extinction_date": "",
                "overview": "",
                "notes": "",
                "tags": [],
                "events": [
                    {
                        "record_id": "organization-founding",
                        "event_type": ORGANIZATION_EVENT_FOUNDING,
                        "title": "Founding",
                        "date": (
                            f"{database_date['year']}-"
                            f"{database_date['month']:02d}-"
                            f"{database_date['day']:02d}"
                        ),
                        "year": database_date["year"],
                        "description": "",
                        "person_ids": [],
                    }
                ],
                "jobs": [],
            }
        )

    def update_organization(self, record_id, values):
        current = self.get_organization(record_id)

        if current is None:
            raise KeyError(f"Unknown organization record_id: {record_id}")

        prospective = deepcopy(current)
        prospective.update(deepcopy(values))
        normalized = self.normalize_organization(prospective)
        self.validate_organization(normalized, record_id)
        eminence_updates = prepare_event_eminence_updates(
            self.database,
            organization_events_as_world_events((current,)),
            organization_events_as_world_events((normalized,)),
        )
        updated = self.database.update_record(
            "organizations",
            record_id,
            normalized,
        )
        updated = self.ensure_school_campus(updated)
        apply_event_eminence_updates(
            self.database,
            eminence_updates,
        )
        self.database.save()
        return updated

    def delete_organization(self, record_id):
        organization = self.get_organization(record_id)

        if organization is None:
            raise KeyError(
                f"Unknown organization record_id: {record_id}"
            )

        child_names = [
            str(child.get("name", "Unnamed") or "Unnamed")
            for child in self.list_organizations()
            if str(
                child.get("parent_organization_id", "") or ""
            )
            == str(record_id)
        ]

        if child_names:
            raise ValueError(
                "Move or delete nested organizations before deleting "
                f"this organization: {', '.join(child_names)}."
            )

        referenced_job_ids = {
            job["organization_job_id"]
            for job in self.job_assignments()
            if job["organization_id"] == str(record_id)
        }

        if referenced_job_ids:
            raise ValueError(
                "This organization cannot be deleted while people have "
                "job assignments in it."
            )

        linked_book_titles = [
            str(book.get("title", "Untitled book") or "Untitled book")
            for book in self.database.data.get("books", [])
            if any(
                str(holding.get("organization_id", "") or "")
                == str(record_id)
                for holding in book.get("holdings", [])
                if isinstance(holding, dict)
            )
        ]

        if linked_book_titles:
            raise ValueError(
                "Move or remove this organization's book holdings before "
                "deleting it: "
                f"{', '.join(linked_book_titles)}."
            )

        eminence_updates = prepare_event_eminence_updates(
            self.database,
            organization_events_as_world_events((organization,)),
            (),
        )
        deleted = self.database.delete_record("organizations", record_id)
        apply_event_eminence_updates(
            self.database,
            eminence_updates,
        )
        self.database.save()
        return deleted

    def normalize_organization(self, values):
        normalized = self.apply_school_link(
            normalize_organization_record(values)
        )

        if not normalized.get("also_location"):
            normalized["campus_location_id"] = ""

        return normalized

    def apply_school_link(self, organization):
        normalized = normalize_organization_record(organization)
        school = self.school_by_id(normalized.get("school_id"))

        if school is not None:
            normalized["name"] = str(
                school.get("name", "") or ""
            ).strip()
            normalized["organization_type"] = "School"

        return normalized

    def validate_organization(self, values, record_id=""):
        name = str(values.get("name", "") or "").strip()
        organization_type = str(
            values.get("organization_type", "") or ""
        ).strip()
        location_id = str(values.get("location_id", "") or "").strip()
        parent_organization_id = str(
            values.get("parent_organization_id", "") or ""
        ).strip()
        school_id = str(values.get("school_id", "") or "").strip()

        if not name:
            raise ValueError("An organization must have a name.")

        if organization_type not in ORGANIZATION_TYPES:
            raise ValueError("Choose one of the available organization types.")

        if bool(values.get("also_location")) and not location_id:
            raise ValueError(
                "Choose a home location before making this organization "
                "a location."
            )

        if (
            bool(values.get("also_location"))
            and location_id
            == str(values.get("campus_location_id", "") or "").strip()
        ):
            raise ValueError(
                "Choose the organization's home region, not its linked "
                "location entry."
            )

        if school_id and self.school_by_id(school_id) is None:
            raise ValueError("The linked school no longer exists.")

        if school_id:
            school = self.school_by_id(school_id)
            school_name = str(
                (school or {}).get("name", "") or ""
            ).strip()

            if name != school_name or organization_type != "School":
                raise ValueError(
                    "A linked school controls the organization name and type."
                )

        if location_id and not any(
            location.get("record_id") == location_id
            for location in self.locations_provider()
        ):
            raise ValueError("The selected organization location no longer exists.")

        organizations = self.list_organizations()
        organization_ids = {
            str(organization.get("record_id", "") or "")
            for organization in organizations
        }

        if parent_organization_id:
            if parent_organization_id == str(record_id):
                raise ValueError(
                    "An organization cannot be nested within itself."
                )

            if parent_organization_id not in organization_ids:
                raise ValueError(
                    "The selected parent organization no longer exists."
                )

            if (
                record_id
                and parent_organization_id
                in organization_descendant_ids(
                    record_id,
                    organizations,
                )
            ):
                raise ValueError(
                    "An organization cannot be nested within one of "
                    "its own descendants."
                )

        events = normalize_organization_events(
            values.get("events", [])
        )

        if events[0]["year"] is None:
            raise ValueError(
                "Every organization must have a founding year."
            )

        for event in events[1:]:
            if event["year"] is None:
                raise ValueError(
                    "Every organization event must have a year."
                )

        people = (
            self.database.list_people()
            if hasattr(self.database, "list_people")
            else []
        )
        known_person_ids = {
            str(person.get("record_id", "") or "").strip()
            for person in people
            if isinstance(person, dict)
            and str(person.get("record_id", "") or "").strip()
        }
        non_magical_person_ids = {
            str(person.get("record_id", "") or "").strip()
            for person in people
            if isinstance(person, dict)
            and bool(person.get("non_magical"))
            and str(person.get("record_id", "") or "").strip()
        }

        for event in events:
            if any(
                person_id not in known_person_ids
                for person_id in event_linked_person_ids(event)
            ):
                raise ValueError(
                    "Every person linked to an organization event "
                    "must exist."
                )

            event_role_ids = [
                *event.get("person_ids", []),
                *event.get("witness_person_ids", []),
                *event.get("affected_person_ids", []),
            ]

            if len(event_role_ids) != len(set(event_role_ids)):
                raise ValueError(
                    "Each person can belong to only one event category."
                )

            if non_magical_person_ids.intersection(
                event.get("eminence_person_ids", [])
            ):
                raise ValueError(
                    "Non-magical people cannot earn Eminence."
                )

        founding_year = int(events[0]["year"])
        founding_date = organization_job_date_tuple(
            events[0]["date"]
        )
        extinction_date_value = str(
            values.get("extinction_date", "") or ""
        ).strip()
        extinction_year = world_event_year(extinction_date_value)
        extinction_date = (
            organization_job_date_tuple(
                extinction_date_value,
                end_boundary=True,
            )
            if extinction_date_value
            else None
        )

        if (
            bool(values.get("extinct"))
            and extinction_year is not None
            and extinction_year < founding_year
        ):
            raise ValueError(
                "An organization cannot become extinct before it was founded."
            )

        organization_jobs = normalize_organization_jobs(
            values.get("jobs", [])
        )
        organization_jobs_by_id = {
            organization_job["record_id"]: organization_job
            for organization_job in organization_jobs
        }

        for organization_job in organization_jobs:
            opened_date = organization_job_date_tuple(
                organization_job["opened_date"]
            )
            closed_date = (
                organization_job_date_tuple(
                    organization_job["closed_date"],
                    end_boundary=True,
                )
                if organization_job["closed_date"]
                else None
            )

            if opened_date < founding_date:
                raise ValueError(
                    f"{organization_job['title']} cannot open before "
                    "the organization was founded."
                )

            if (
                extinction_date is not None
                and closed_date is not None
                and closed_date > extinction_date
            ):
                raise ValueError(
                    f"{organization_job['title']} cannot close after "
                    "the organization became extinct."
                )

        for assignment in self.job_assignments():
            if assignment["organization_id"] != str(record_id):
                continue

            organization_job = organization_jobs_by_id.get(
                assignment["organization_job_id"]
            )

            if organization_job is None:
                raise ValueError(
                    "An assigned organization job cannot be removed."
                )

            assignment_start = job_date_tuple(
                assignment["start_year"],
                assignment["start_month"],
                assignment["start_day"],
            )
            assignment_end = job_date_tuple(
                assignment["end_year"],
                assignment["end_month"],
                assignment["end_day"],
                end_boundary=True,
            )
            opened_date = organization_job_date_tuple(
                organization_job["opened_date"]
            )
            closed_date = (
                organization_job_date_tuple(
                    organization_job["closed_date"],
                    end_boundary=True,
                )
                if organization_job["closed_date"]
                else None
            )

            if assignment_start < opened_date:
                raise ValueError(
                    f"{organization_job['title']} cannot be moved to "
                    "an opening date after an existing assignment began."
                )

            if (
                closed_date is not None
                and (
                    assignment_end is not None
                    and assignment_end > closed_date
                )
            ):
                raise ValueError(
                    f"{organization_job['title']} cannot close before "
                    "an existing assignment ended."
                )

        for organization in self.list_organizations():
            if organization.get("record_id") == record_id:
                continue

            if (
                school_id
                and str(organization.get("school_id", "") or "").strip()
                == school_id
            ):
                raise ValueError(
                    "That school is already linked to another organization."
                )

            if str(organization.get("name", "") or "").strip().casefold() == name.casefold():
                raise ValueError(f'An organization named "{name}" already exists.')

    def ensure_school_campus(self, organization):
        normalized = normalize_organization_record(organization)

        if (
            not normalized.get("also_location")
            or self.location_controller is None
        ):
            return normalized

        organization_id = str(
            normalized.get("record_id", "") or ""
        ).strip()
        home_location_id = str(
            normalized.get("location_id", "") or ""
        ).strip()

        if not organization_id or not home_location_id:
            return normalized

        campus_location_id = str(
            normalized.get("campus_location_id", "") or ""
        ).strip()
        campus = (
            self.location_controller.get_location(campus_location_id)
            if campus_location_id
            and campus_location_id != home_location_id
            else None
        )

        if campus is None:
            campus = next(
                (
                    location
                    for location in self.location_controller.list_locations()
                    if str(
                        location.get("campus_organization_id", "")
                        or ""
                    ).strip()
                    == organization_id
                ),
                None,
            )

        foundation_event = school_campus_foundation_event(normalized)
        campus_values = {
            "name": school_campus_name(normalized),
            "parent_location_id": home_location_id,
            "campus_organization_id": organization_id,
            "demographics": "",
            "notes": "",
            "extinct": False,
            "extinction_year": "",
            "timeline_events": [foundation_event],
        }

        if campus is None:
            campus = self.location_controller.create_location(
                campus_values,
                save_database=False,
            )
        else:
            existing_events = [
                deepcopy(event)
                for event in campus.get("timeline_events", []) or []
                if isinstance(event, dict)
                and str(event.get("event_id", "") or "").strip()
                != foundation_event["event_id"]
            ]
            has_other_foundation = any(
                str(event.get("event_type", "") or "")
                in ("founding", "wizarding_community_established")
                for event in existing_events
            )
            campus_values = {
                "name": school_campus_name(normalized),
                "parent_location_id": home_location_id,
                "campus_organization_id": organization_id,
                "demographics": str(
                    campus.get("demographics", "") or ""
                ),
                "notes": str(campus.get("notes", "") or ""),
                "extinct": bool(campus.get("extinct")),
                "extinction_year": campus.get(
                    "extinction_year",
                    "",
                ),
                "timeline_events": (
                    existing_events
                    if has_other_foundation
                    else [*existing_events, foundation_event]
                ),
            }
            campus = self.location_controller.update_location(
                campus.get("record_id", ""),
                campus_values,
                save_database=False,
            )

        resolved_campus_id = str(
            campus.get("record_id", "") or ""
        ).strip()

        if normalized.get("campus_location_id") == resolved_campus_id:
            return normalized

        normalized["campus_location_id"] = resolved_campus_id
        updated = self.database.update_record(
            "organizations",
            organization_id,
            normalized,
        )
        return normalize_organization_record(updated)

    def school_records(self):
        if self.schools_provider is None:
            return []

        schools = self.schools_provider()
        return [
            deepcopy(school)
            for school in schools or []
            if isinstance(school, dict)
            and str(school.get("record_id", "") or "").strip()
        ]

    def storeroom_item_options(self):
        if self.items_provider is None:
            return []

        if self._storeroom_item_options_cache is not None:
            return deepcopy(self._storeroom_item_options_cache)

        items = []

        for candidate in self.items_provider() or []:
            if not isinstance(candidate, dict):
                continue

            collection = str(
                candidate.get("collection", "") or ""
            ).strip()
            record_id = str(
                candidate.get("record_id", "") or ""
            ).strip()
            name = str(candidate.get("name", "") or "").strip()
            category = str(
                candidate.get("category", "") or collection
            ).strip()

            if not collection or not record_id or not name:
                continue

            items.append(
                {
                    "collection": collection,
                    "record_id": record_id,
                    "name": name,
                    "category": category,
                    "label": f"{name} · {category}",
                }
            )

        items.sort(key=self.storeroom_item_sort_key)
        self._storeroom_item_options_cache = items
        return deepcopy(items)

    def storeroom_item_sort_key(self, item):
        return (
            item["category"].casefold(),
            item["name"].casefold(),
            item["record_id"],
        )

    def storeroom_item_label(self, reference):
        normalized_reference = normalize_storeroom_inventory(
            [reference]
        )[0]

        for item in self.storeroom_item_options():
            if (
                item["collection"]
                == normalized_reference["collection"]
                and item["record_id"]
                == normalized_reference["record_id"]
            ):
                return item["label"]

        return (
            f"Missing item · {normalized_reference['collection']} / "
            f"{normalized_reference['record_id']}"
        )

    def school_by_id(self, school_id):
        selected_id = str(school_id or "").strip()

        if not selected_id:
            return None

        return next(
            (
                school
                for school in self.school_records()
                if str(school.get("record_id", "") or "").strip()
                == selected_id
            ),
            None,
        )

    def school_label(self, school_id):
        school = self.school_by_id(school_id)

        if school is None:
            return "Choose a school"

        location = str(school.get("location", "") or "").strip()
        name = str(school.get("name", "") or "Unnamed school").strip()
        return f"{name} · {location}" if location else name

    def location_records(self):
        return [
            deepcopy(location)
            for location in self.locations_provider()
            if isinstance(location, dict)
        ]

    def create_placeholder_location(self, name, parent_location_id=""):
        if self.location_controller is None:
            raise ValueError("Location creation is not available here.")

        return self.location_controller.create_placeholder_location(
            str(name or "").strip(),
            str(parent_location_id or "").strip(),
        )

    def location_options(self):
        locations = self.locations_provider()
        decorated = []

        for location in locations:
            record_id = str(location.get("record_id", "") or "")
            decorated.append(
                {
                    "record_id": record_id,
                    "label": recent_location_label(
                        record_id,
                        locations,
                    ),
                }
            )

        decorated.sort(key=self.location_option_sort_key)
        return decorated

    def location_option_sort_key(self, option):
        return str(option.get("label", "") or "").casefold()

    def location_label(self, location_id):
        selected_id = str(location_id or "").strip()

        if not selected_id:
            return "No location selected"

        return next(
            (
                option["label"]
                for option in self.location_options()
                if option["record_id"] == selected_id
            ),
            "Unknown location",
        )

    def organization_founding_year(self, organization):
        for event in organization.get("events", []) or []:
            if not isinstance(event, dict):
                continue

            if str(event.get("event_type", "") or "").casefold() != (
                ORGANIZATION_EVENT_FOUNDING
            ):
                continue

            try:
                return int(event.get("year"))
            except (TypeError, ValueError):
                return None

        return None

    def organization_extinction_year(self, organization):
        if not bool(organization.get("extinct")):
            return None

        return world_event_year(
            organization.get("extinction_date", "")
        )

    def organization_search_text(
        self,
        organization,
        organizations=None,
        paths_by_id=None,
        locations=None,
        location_paths=None,
        location_labels=None,
        school_labels=None,
        storeroom_labels=None,
    ):
        organization_id = str(
            organization.get("record_id", "") or ""
        ).strip()
        location_id = str(
            organization.get("location_id", "") or ""
        ).strip()
        resolved_locations = (
            self.locations_provider()
            if locations is None
            else locations
        )
        resolved_location_paths = (
            location_paths_by_id(resolved_locations)
            if location_paths is None
            else location_paths
        )
        location_label = (
            location_labels.get(location_id, "Unknown location")
            if location_labels is not None
            else recent_location_label(location_id, resolved_locations)
        )
        school_id = str(
            organization.get("school_id", "") or ""
        ).strip()
        school_label = (
            school_labels.get(school_id, "")
            if school_labels is not None
            else self.school_label(school_id)
        )
        searchable_values = [
            organization.get("name"),
            organization.get("organization_type"),
            organization.get("overview"),
            organization.get("notes"),
            (
                paths_by_id.get(organization_id, "")
                if paths_by_id is not None
                else organization_path(
                    organization_id,
                    (
                        organizations
                        if organizations is not None
                        else self.list_organizations()
                    ),
                )
            ),
            resolved_location_paths.get(location_id, ""),
            location_label,
            school_label,
            "Has a shop" if organization.get("has_shop") else "",
            (
                "Famous organization"
                if organization.get("famous_organization")
                else ""
            ),
            "Has a storeroom" if organization.get("has_storeroom") else "",
            (
                "Includes a library"
                if organization.get("includes_library")
                else ""
            ),
            (
                "Library open to outsiders"
                if organization.get("library_open_to_outsiders")
                else ""
            ),
            "Extinct" if organization.get("extinct") else "Active",
            organization.get("extinction_date"),
        ]

        for event in organization.get("events", []) or []:
            if isinstance(event, dict):
                searchable_values.extend(
                    (
                        event.get("title"),
                        event.get("year"),
                        event.get("description"),
                    )
                )

        for job in organization.get("jobs", []) or []:
            if isinstance(job, dict):
                searchable_values.extend(
                    (
                        job.get("title"),
                        job.get("opened_date"),
                        job.get("closed_date"),
                    )
                )

        for stored_item in organization.get(
            "storeroom_inventory",
            [],
        ):
            if isinstance(stored_item, dict):
                collection = str(
                    stored_item.get("collection", "") or ""
                ).strip()
                record_id = str(
                    stored_item.get("record_id", "") or ""
                ).strip()
                searchable_values.append(
                    storeroom_labels.get(
                        (collection, record_id),
                        f"Missing item · {collection} / {record_id}",
                    )
                    if storeroom_labels is not None
                    else self.storeroom_item_label(stored_item)
                )

        return " ".join(
            str(value or "").strip()
            for value in searchable_values
            if str(value or "").strip()
        ).casefold()

    def organization_matches_location(
        self,
        organization,
        location_id,
        locations=None,
    ):
        selected_id = str(location_id or "").strip()

        if not selected_id:
            return True

        organization_location_id = str(
            organization.get("location_id", "") or ""
        ).strip()

        if not organization_location_id:
            return False

        return any(
            str(location.get("record_id", "") or "").strip()
            == selected_id
            for location in ancestor_locations(
                organization_location_id,
                (
                    self.locations_provider()
                    if locations is None
                    else locations
                ),
            )
        )

    def search_organizations(
        self,
        search_text="",
        organization_type="",
        existing_year=None,
        location_id="",
        school_link="all",
        organizations=None,
    ):
        query_terms = [
            term
            for term in str(search_text or "").casefold().split()
            if term
        ]
        selected_type = str(organization_type or "").strip()
        selected_school_link = str(
            school_link or "all"
        ).strip().casefold()
        matching = []
        available_organizations = (
            self.list_organizations()
            if organizations is None
            else list(organizations)
        )
        paths_by_id = organization_paths_by_id(
            available_organizations
        )
        selected_location_id = str(location_id or "").strip()
        locations = (
            self.locations_provider()
            if query_terms or selected_location_id
            else []
        )
        location_paths = (
            location_paths_by_id(locations)
            if query_terms
            else {}
        )
        organization_location_ids = {
            str(
                organization.get("location_id", "") or ""
            ).strip()
            for organization in available_organizations
            if str(
                organization.get("location_id", "") or ""
            ).strip()
        }
        location_labels = {
            organization_location_id: recent_location_label(
                organization_location_id,
                locations,
            )
            for organization_location_id in organization_location_ids
        }
        school_labels = {}
        storeroom_labels = {}

        if query_terms:
            for school in self.school_records():
                school_id = str(
                    school.get("record_id", "") or ""
                ).strip()

                if not school_id:
                    continue

                school_name = str(
                    school.get("name", "") or "Unnamed school"
                ).strip()
                school_location = str(
                    school.get("location", "") or ""
                ).strip()
                school_labels[school_id] = (
                    f"{school_name} · {school_location}"
                    if school_location
                    else school_name
                )

            if any(
                organization.get("storeroom_inventory")
                for organization in available_organizations
            ):
                storeroom_labels = {
                    (
                        str(
                            item.get("collection", "") or ""
                        ).strip(),
                        str(
                            item.get("record_id", "") or ""
                        ).strip(),
                    ): str(item.get("label", "") or "").strip()
                    for item in self.storeroom_item_options()
                    if str(
                        item.get("collection", "") or ""
                    ).strip()
                    and str(
                        item.get("record_id", "") or ""
                    ).strip()
                }

        for organization in available_organizations:
            if (
                selected_type
                and selected_type != "All types"
                and organization.get("organization_type") != selected_type
            ):
                continue

            if existing_year is not None:
                founding_year = self.organization_founding_year(
                    organization
                )
                extinction_year = self.organization_extinction_year(
                    organization
                )

                if founding_year is None or founding_year > int(existing_year):
                    continue

                if (
                    extinction_year is not None
                    and extinction_year < int(existing_year)
                ):
                    continue

            if not self.organization_matches_location(
                organization,
                location_id,
                locations,
            ):
                continue

            has_school = bool(
                str(organization.get("school_id", "") or "").strip()
            )

            if selected_school_link == "linked" and not has_school:
                continue

            if selected_school_link == "unlinked" and has_school:
                continue

            if query_terms:
                search_text_value = self.organization_search_text(
                    organization,
                    available_organizations,
                    paths_by_id,
                    locations,
                    location_paths,
                    location_labels,
                    school_labels,
                    storeroom_labels,
                )

                if not all(
                    term in search_text_value
                    for term in query_terms
                ):
                    continue

            matching.append(organization)

        decorated = [
            (
                self.organization_sort_key_for(
                    organization,
                    available_organizations,
                    paths_by_id,
                ),
                organization,
            )
            for organization in matching
        ]
        decorated.sort(key=self.decorated_organization_sort_key)
        return [
            organization
            for sort_key, organization in decorated
        ]

    def first_order_children(self, record_id):
        selected_id = str(record_id or "").strip()
        organizations = self.list_organizations()
        children = [
            organization
            for organization in organizations
            if str(
                organization.get(
                    "parent_organization_id",
                    "",
                )
                or ""
            ).strip()
            == selected_id
        ]
        paths_by_id = organization_paths_by_id(organizations)
        decorated = [
            (
                self.organization_sort_key_for(
                    organization,
                    organizations,
                    paths_by_id,
                ),
                organization,
            )
            for organization in children
        ]
        decorated.sort(key=self.decorated_organization_sort_key)
        return [
            organization
            for sort_key, organization in decorated
        ]

    def parent_options(self, record_id=""):
        organizations = self.list_organizations()
        descendant_ids = (
            organization_descendant_ids(
                record_id,
                organizations,
            )
            if str(record_id or "").strip()
            else set()
        )
        excluded_ids = {
            str(record_id or "").strip(),
            *descendant_ids,
        }
        options = [
            {
                "record_id": "",
                "label": "No parent organization",
            }
        ]

        for organization in organizations:
            organization_id = str(
                organization.get("record_id", "") or ""
            )

            if organization_id in excluded_ids:
                continue

            options.append(
                {
                    "record_id": organization_id,
                    "label": organization_context_label(
                        organization_id,
                        organizations,
                    ),
                }
            )

        options[1:] = sorted(
            options[1:],
            key=self.location_option_sort_key,
        )
        return options

    def job_assignments(self):
        assignments = []

        for person in self.database.list_people():
            development_plan = person.get(
                "development_plan",
                {},
            )

            if not isinstance(development_plan, dict):
                continue

            for adult_year in development_plan.get(
                "adult_years",
                [],
            ):
                if not isinstance(adult_year, dict):
                    continue

                assignments.extend(
                    normalize_job_records(
                        adult_year.get("jobs", [])
                    )
                )

        return assignments

    def job_assignments_with_people(self, organization_job_id):
        selected_job_id = str(
            organization_job_id or ""
        ).strip()
        assignments = []
        seen_assignment_ids = set()
        started_events = [
            normalize_world_event(event)
            for event in self.database.list_records("events")
            if isinstance(event, dict)
            and str(event.get("event_type", "") or "").strip()
            == "started_job"
            and str(
                event.get("organization_job_id", "") or ""
            ).strip()
            == selected_job_id
        ]
        started_events_by_assignment_id = {
            str(event.get("job_assignment_id", "") or "").strip(): event
            for event in started_events
            if str(event.get("job_assignment_id", "") or "").strip()
        }

        for person in self.database.list_people():
            person_id = str(
                person.get("record_id", "") or ""
            ).strip()
            person_name = str(
                person.get("displayed_name", "")
                or "Unnamed magician"
            ).strip()
            development_plan = person.get(
                "development_plan",
                {},
            )

            if not isinstance(development_plan, dict):
                continue

            for adult_year in development_plan.get(
                "adult_years",
                [],
            ):
                if not isinstance(adult_year, dict):
                    continue

                for assignment in normalize_job_records(
                    adult_year.get("jobs", [])
                ):
                    assignment_id = str(
                        assignment.get("record_id", "") or ""
                    ).strip()

                    if (
                        assignment["organization_job_id"]
                        != selected_job_id
                        or assignment_id in seen_assignment_ids
                    ):
                        continue

                    source_event = started_events_by_assignment_id.get(
                        assignment_id,
                        {},
                    )

                    assignments.append(
                        {
                            **assignment,
                            "person_id": person_id,
                            "person_name": person_name,
                            "event_id": str(
                                source_event.get("record_id", "") or ""
                            ).strip(),
                            "special_appointment_name": "",
                            "died_in_office": bool(
                                source_event.get("died_in_office", False)
                            ),
                            "died_in_office_death_event_id": str(
                                source_event.get(
                                    "died_in_office_death_event_id",
                                    "",
                                )
                                or ""
                            ).strip(),
                            "died_in_office_created_death_event": bool(
                                source_event.get(
                                    "died_in_office_created_death_event",
                                    False,
                                )
                            ),
                        }
                    )
                    seen_assignment_ids.add(assignment_id)

        for event in started_events:
            special_name = str(
                event.get("special_appointment_name", "") or ""
            ).strip()

            if not special_name:
                continue

            start_year, start_month, start_day = split_world_event_date(
                event.get("date", "")
            )
            end_year, end_month, end_day = split_world_event_date(
                event.get("job_end_date", "")
            )
            assignment_id = str(
                event.get("job_assignment_id", "")
                or f"event-job:{event.get('record_id', '')}"
            ).strip()

            if assignment_id in seen_assignment_ids:
                continue

            assignment = normalize_job_records(
                [
                    {
                        "record_id": assignment_id,
                        "organization_id": event.get(
                            "organization_id",
                            "",
                        ),
                        "organization_name": event.get(
                            "organization_name",
                            "",
                        ),
                        "organization_job_id": selected_job_id,
                        "title": event.get("job_title", ""),
                        "salary": event.get("salary"),
                        "start_year": start_year,
                        "start_month": start_month or None,
                        "start_day": start_day or None,
                        "end_year": end_year or None,
                        "end_month": end_month or None,
                        "end_day": end_day or None,
                    }
                ]
            )[0]
            assignments.append(
                {
                    **assignment,
                    "person_id": "",
                    "person_name": special_name,
                    "event_id": str(
                        event.get("record_id", "") or ""
                    ).strip(),
                    "special_appointment_name": special_name,
                    "died_in_office": False,
                    "died_in_office_death_event_id": "",
                    "died_in_office_created_death_event": False,
                }
            )
            seen_assignment_ids.add(assignment_id)

        assignments.sort(
            key=self.job_assignment_person_sort_key
        )
        return assignments

    def job_assignment_person_sort_key(self, assignment):
        return (
            job_date_tuple(
                assignment["start_year"],
                assignment["start_month"],
                assignment["start_day"],
            ),
            assignment["person_name"].casefold(),
            assignment["record_id"],
        )

    def last_salary_for_organization_job(
        self,
        organization_job_id,
        before_date=None,
    ):
        assignments = self.job_assignments_with_people(
            organization_job_id
        )
        individual_assignments = [
            assignment
            for assignment in assignments
            if str(assignment.get("person_id", "") or "").strip()
        ]

        if individual_assignments:
            assignments = individual_assignments

        if not assignments:
            return normalize_monthly_salary(
                {"galleons": 0, "sickles": 0, "knuts": 0}
            )

        boundary = tuple(before_date) if before_date is not None else None
        eligible_assignments = []

        for assignment in assignments:
            assignment_start = job_date_tuple(
                assignment["start_year"],
                assignment["start_month"],
                assignment["start_day"],
            )

            if boundary is not None and assignment_start >= boundary:
                continue

            assignment_end = job_date_tuple(
                assignment["end_year"],
                assignment["end_month"],
                assignment["end_day"],
                end_boundary=True,
            )
            eligible_assignments.append(
                (
                    assignment_end or assignment_start,
                    assignment_start,
                    assignment,
                )
            )

        if not eligible_assignments:
            return normalize_monthly_salary(
                {"galleons": 0, "sickles": 0, "knuts": 0}
            )

        eligible_assignments.sort(
            key=lambda entry: (entry[0], entry[1])
        )
        selected_assignment = eligible_assignments[-1][2]
        salary = normalize_monthly_salary(
            selected_assignment.get("salary")
        )
        assignment_id = str(
            selected_assignment.get("record_id", "") or ""
        ).strip()
        raise_events = []

        for event in self.database.list_records("events"):
            if (
                not isinstance(event, dict)
                or str(event.get("event_type", "") or "").strip()
                != "received_raise"
                or str(event.get("job_assignment_id", "") or "").strip()
                != assignment_id
            ):
                continue

            year, month, day = split_world_event_date(
                event.get("date", "")
            )

            if not year:
                continue

            raise_date = job_date_tuple(year, month, day)

            if boundary is not None and raise_date >= boundary:
                continue

            raise_events.append((raise_date, event))

        if raise_events:
            raise_events.sort(key=lambda entry: entry[0])
            salary = normalize_monthly_salary(
                raise_events[-1][1].get("salary")
            )

        return salary

    def organization_job_yearly_timeline(self, organization_job):
        normalized_job = normalize_organization_job(
            organization_job
        )
        assignments = self.job_assignments_with_people(
            normalized_job["record_id"]
        )
        database_date = normalize_database_date(
            self.database.data.get(
                "_application_settings",
                {},
            ).get(DATABASE_DATE_SETTING_KEY)
        )
        timeline_start = organization_job_date_tuple(
            normalized_job["opened_date"]
        )
        timeline_end = (
            database_date["year"],
            database_date["month"],
            database_date["day"],
        )

        if timeline_end < timeline_start:
            timeline_end = timeline_start

        for assignment in assignments:
            assignment_start = job_date_tuple(
                assignment["start_year"],
                assignment["start_month"],
                assignment["start_day"],
            )
            assignment_end = job_date_tuple(
                assignment["end_year"],
                assignment["end_month"],
                assignment["end_day"],
                end_boundary=True,
            )

            if assignment_start > timeline_end:
                timeline_end = assignment_start

            if assignment_end is not None and assignment_end > timeline_end:
                timeline_end = assignment_end

        if normalized_job["closed_date"]:
            timeline_end = min(
                timeline_end,
                organization_job_date_tuple(
                    normalized_job["closed_date"],
                    end_boundary=True,
                ),
            )

        assignments.sort(key=self.job_assignment_person_sort_key)
        timeline = []
        cursor = timeline_start

        for assignment in assignments:
            assignment_start = job_date_tuple(
                assignment["start_year"],
                assignment["start_month"],
                assignment["start_day"],
            )
            assignment_end = job_date_tuple(
                assignment["end_year"],
                assignment["end_month"],
                assignment["end_day"],
                end_boundary=True,
            )

            if assignment_start > cursor:
                vacant_end = previous_historical_date(
                    *assignment_start
                )
                timeline.append(
                    self.job_timeline_entry(
                        cursor,
                        vacant_end,
                        [],
                        [],
                        True,
                    )
                )

            visible_assignment_end = (
                assignment_end
                if assignment_end is not None
                else timeline_end
            )
            timeline.append(
                self.job_timeline_entry(
                    assignment_start,
                    visible_assignment_end,
                    (
                        [assignment["person_id"]]
                        if assignment["person_id"]
                        else []
                    ),
                    [assignment["person_name"]],
                    False,
                    assignment_ids=[assignment["record_id"]],
                    event_ids=[assignment.get("event_id", "")],
                    open_ended=assignment_end is None,
                    salary=assignment.get("salary"),
                    special_appointment_name=assignment.get(
                        "special_appointment_name",
                        "",
                    ),
                    concurrent=assignment.get("concurrent", False),
                    died_in_office=assignment.get(
                        "died_in_office",
                        False,
                    ),
                    died_in_office_death_event_id=assignment.get(
                        "died_in_office_death_event_id",
                        "",
                    ),
                    died_in_office_created_death_event=assignment.get(
                        "died_in_office_created_death_event",
                        False,
                    ),
                )
            )
            if visible_assignment_end == (
                LATEST_HISTORICAL_YEAR,
                12,
                31,
            ):
                cursor = None
                break

            next_cursor = next_historical_date(*visible_assignment_end)

            if next_cursor > cursor:
                cursor = next_cursor

        if cursor is not None and cursor <= timeline_end:
            timeline.append(
                self.job_timeline_entry(
                    cursor,
                    timeline_end,
                    [],
                    [],
                    True,
                    open_ended=not bool(normalized_job["closed_date"]),
                )
            )

        return self.combine_job_timeline_entries(timeline)

    def combine_job_timeline_entries(self, timeline):
        combined = []

        for entry in timeline:
            if not combined:
                combined.append(deepcopy(entry))
                continue

            previous = combined[-1]
            same_holder = (
                previous.get("vacant") == entry.get("vacant")
                and previous.get("person_ids") == entry.get("person_ids")
                and previous.get("holder_names")
                == entry.get("holder_names")
                and previous.get("assignment_ids")
                == entry.get("assignment_ids")
                and previous.get("event_ids") == entry.get("event_ids")
            )
            previous_end = (
                previous["end_year"],
                previous["end_month"],
                previous["end_day"],
            )
            entry_start = (
                entry["start_year"],
                entry["start_month"],
                entry["start_day"],
            )

            entries_touch = entry_start <= previous_end

            if (
                not entries_touch
                and previous_end
                != (LATEST_HISTORICAL_YEAR, 12, 31)
            ):
                entries_touch = (
                    entry_start == next_historical_date(*previous_end)
                )

            if same_holder and entries_touch:
                entry_end = (
                    entry["end_year"],
                    entry["end_month"],
                    entry["end_day"],
                )
                merged_end = max(previous_end, entry_end)
                combined[-1] = self.job_timeline_entry(
                    (
                        previous["start_year"],
                        previous["start_month"],
                        previous["start_day"],
                    ),
                    merged_end,
                    previous["person_ids"],
                    previous["holder_names"],
                    previous["vacant"],
                    assignment_ids=previous.get("assignment_ids", []),
                    event_ids=previous.get("event_ids", []),
                    open_ended=bool(
                        previous.get("open_ended")
                        or entry.get("open_ended")
                    ),
                    salary=previous.get("salary"),
                    special_appointment_name=previous.get(
                        "special_appointment_name",
                        "",
                    ),
                    concurrent=previous.get("concurrent", False),
                    died_in_office=previous.get("died_in_office", False),
                    died_in_office_death_event_id=previous.get(
                        "died_in_office_death_event_id",
                        "",
                    ),
                    died_in_office_created_death_event=previous.get(
                        "died_in_office_created_death_event",
                        False,
                    ),
                )
                continue

            combined.append(deepcopy(entry))

        return combined

    def job_timeline_entry(
        self,
        start_date,
        end_date,
        person_ids,
        holder_names,
        vacant,
        assignment_ids=(),
        event_ids=(),
        open_ended=False,
        salary=None,
        special_appointment_name="",
        concurrent=False,
        died_in_office=False,
        died_in_office_death_event_id="",
        died_in_office_created_death_event=False,
    ):
        start_year, start_month, start_day = start_date
        end_year, end_month, end_day = end_date
        range_text = self.job_timeline_range_text(
            start_year,
            start_month,
            start_day,
            end_year,
            end_month,
            end_day,
        )
        holder_text = (
            " → ".join(holder_names)
            if holder_names
            else "Vacant"
        )
        return {
            "year": start_year,
            "start_year": start_year,
            "start_month": start_month,
            "start_day": start_day,
            "end_year": end_year,
            "end_month": end_month,
            "end_day": end_day,
            "person_ids": list(person_ids),
            "holder_names": list(holder_names),
            "vacant": bool(vacant),
            "assignment_ids": [
                str(assignment_id or "").strip()
                for assignment_id in assignment_ids
                if str(assignment_id or "").strip()
            ],
            "event_ids": [
                str(event_id or "").strip()
                for event_id in event_ids
                if str(event_id or "").strip()
            ],
            "open_ended": bool(open_ended),
            "salary": (
                normalize_monthly_salary(salary)
                if salary is not None
                else None
            ),
            "special_appointment_name": str(
                special_appointment_name or ""
            ).strip(),
            "concurrent": bool(concurrent),
            "died_in_office": bool(died_in_office),
            "died_in_office_death_event_id": str(
                died_in_office_death_event_id or ""
            ).strip(),
            "died_in_office_created_death_event": bool(
                died_in_office_created_death_event
            ),
            "label": f"{range_text} • {holder_text}",
        }

    def job_timeline_range_text(
        self,
        start_year,
        start_month,
        start_day,
        end_year,
        end_month,
        end_day,
    ):
        start_text = self.job_timeline_date_text(
            start_year,
            start_month,
            start_day,
        )
        end_text = self.job_timeline_date_text(
            end_year,
            end_month,
            end_day,
        )

        if start_text == end_text:
            return start_text

        if start_year == end_year:
            if (
                start_month == 1
                and start_day == 1
                and end_month == 12
                and end_day == 31
            ):
                return str(start_year)

        if (
            start_month == 1
            and start_day == 1
            and end_month == 12
            and end_day == 31
        ):
            return f"{start_year}-{end_year}"

        if start_month == 1 and start_day == 1:
            return f"{start_year}–{end_text}"

        if end_month == 12 and end_day == 31:
            return f"{start_text}–{end_year}"

        return f"{start_text}–{end_text}"

    def job_timeline_date_text(self, year, month, day):
        date_text = str(year)

        if month not in (None, ""):
            date_text += f"-{int(month):02d}"

        if day not in (None, ""):
            date_text += f"-{int(day):02d}"

        return date_text

    def organization_job_is_referenced(self, organization_job_id):
        selected_id = str(
            organization_job_id or ""
        ).strip()
        return any(
            assignment["organization_job_id"] == selected_id
            for assignment in self.job_assignments()
        ) or any(
            isinstance(event, dict)
            and str(event.get("event_type", "") or "").strip()
            in ("started_job", "received_raise")
            and str(
                event.get("organization_job_id", "") or ""
            ).strip()
            == selected_id
            for event in self.database.list_records("events")
        )

    def organization_job_status(self, organization_job):
        database_date = normalize_database_date(
            self.database.data.get(
                "_application_settings",
                {},
            ).get(DATABASE_DATE_SETTING_KEY)
        )
        job_id = str(
            organization_job.get("record_id", "") or ""
        )
        normalized_job = normalize_organization_job(
            organization_job
        )
        current_date = (
            database_date["year"],
            database_date["month"],
            database_date["day"],
        )
        opened_date = organization_job_date_tuple(
            normalized_job["opened_date"]
        )
        closed_date = (
            organization_job_date_tuple(
                normalized_job["closed_date"],
                end_boundary=True,
            )
            if normalized_job["closed_date"]
            else None
        )

        if current_date < opened_date:
            return f"Opens {normalized_job['opened_date']}"

        if closed_date is not None and current_date > closed_date:
            return f"Closed {normalized_job['closed_date']}"

        active_assignment = next(
            (
                assignment
                for assignment in self.job_assignments_with_people(job_id)
                if job_assignment_active_on(
                    assignment,
                    database_date["year"],
                    database_date["month"],
                    database_date["day"],
                )
            ),
            None,
        )

        if active_assignment is None:
            return "Open"

        return "Filled"
