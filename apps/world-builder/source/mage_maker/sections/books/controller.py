from copy import deepcopy

from mage_maker.sections.books.models import (
    BOOK_CONTENT_COLLECTIONS,
    book_date_end_key,
    book_date_is_on_or_before,
    book_date_start_key,
    book_holding_is_active,
    book_reading_source_text,
    normalize_book_content_entry,
    normalize_book_holding,
    normalize_book_reading,
    normalize_book_readings,
    normalize_book_record,
    normalize_book_records,
)
from mage_maker.sections.development.models import (
    ADULT_YEAR_MAX_BOOK_COUNT,
    SCHOOL_YEAR_BOOK_COUNT,
    calculate_development_start_year,
    normalize_development_plan,
    school_year_calendar_year_range,
)
from mage_maker.sections.events.models import (
    normalize_world_event_date,
    split_world_event_date,
    world_event_sort_key,
)
from mage_maker.sections.ledger.models import (
    LEDGER_KIND_BOUGHT,
    LEDGER_KIND_EARNED,
    visible_ledger_entries,
)
from mage_maker.sections.locations.models import (
    ancestor_locations,
    location_paths_by_id,
    recent_location_label,
)
from mage_maker.sections.organizations.controller import (
    organization_context_label,
)
from mage_maker.sections.timeline.events import normalize_timeline_events


class BookController:
    def __init__(
        self,
        database,
        game_database,
        people_provider,
        location_provider,
        organization_provider,
        event_controller=None,
    ):
        self.database = database
        self.game_database = game_database
        self.people_provider = people_provider
        self.location_provider = location_provider
        self.organization_provider = organization_provider
        self.event_controller = event_controller
        self._content_options = None

    def list_books(self):
        return normalize_book_records(
            self.database.list_records("books")
        )

    def get_book(self, record_id):
        book = self.database.read_record("books", record_id)
        return normalize_book_record(book) if book is not None else None

    def list_readings(self):
        return normalize_book_readings(
            self.database.list_records("book_readings")
        )

    def readings_for_person(self, person_id):
        normalized_person_id = str(person_id or "").strip()
        return [
            reading
            for reading in self.list_readings()
            if reading["person_id"] == normalized_person_id
        ]

    def readings_for_book(self, book_id):
        normalized_book_id = str(book_id or "").strip()
        return [
            reading
            for reading in self.list_readings()
            if reading["book_id"] == normalized_book_id
        ]

    def create_book(self, values):
        book = self.prepare_book(values)
        self.ensure_unique_title(book["title"])
        created = self.database.create_record("books", book)
        self.database.save()
        return normalize_book_record(created)

    def update_book(self, record_id, values):
        current = self.get_book(record_id)

        if current is None:
            raise KeyError(f"Unknown book record_id: {record_id}")

        candidate = deepcopy(current)
        candidate.update(deepcopy(values))
        candidate["record_id"] = record_id
        book = self.prepare_book(candidate)
        self.ensure_unique_title(book["title"], record_id)
        updated = self.database.update_record("books", record_id, book)
        self.database.save()
        return normalize_book_record(updated)

    def delete_book(self, record_id):
        book = self.require_book(record_id)

        if self.readings_for_book(record_id):
            raise ValueError(
                "A book with reading history cannot be deleted. Its dated "
                "history must remain available to the readers."
            )

        self.database.delete_record("books", record_id)
        self.database.save()
        return book

    def prepare_book(self, values):
        candidate = deepcopy(values) if isinstance(values, dict) else {}
        people_by_id = self.people_by_id()
        author_id = str(candidate.get("author_person_id", "") or "").strip()

        if author_id in people_by_id:
            candidate["author_name"] = str(
                people_by_id[author_id].get("displayed_name", "")
                or candidate.get("author_name", "")
            ).strip()

        locations_by_id = self.locations_by_id()
        publication_location_id = str(
            candidate.get("publication_location_id", "") or ""
        ).strip()

        if publication_location_id in locations_by_id:
            candidate["publication_location_name"] = recent_location_label(
                publication_location_id,
                list(locations_by_id.values()),
            )

        prepared_holdings = []

        for stored_holding in candidate.get("holdings", []) or []:
            holding = deepcopy(stored_holding)
            holding["holder_name"] = self.holding_name(holding)
            prepared_holdings.append(holding)

        candidate["holdings"] = prepared_holdings
        return normalize_book_record(candidate)

    def ensure_unique_title(self, title, excluded_record_id=None):
        normalized_title = str(title or "").strip().casefold()

        for book in self.list_books():
            if book["record_id"] == excluded_record_id:
                continue

            if book["title"].casefold() == normalized_title:
                raise ValueError(f'A book titled "{title}" already exists.')

    def require_book(self, record_id):
        book = self.get_book(record_id)

        if book is None:
            raise KeyError(f"Unknown book record_id: {record_id}")

        return book

    def add_content(self, book_id, values):
        book = self.require_book(book_id)
        entry = normalize_book_content_entry(values)
        book["contents"].append(entry)
        return self.update_book(book_id, book)

    def remove_content(self, book_id, entry_id):
        book = self.require_book(book_id)
        retained = [
            entry
            for entry in book["contents"]
            if entry["entry_id"] != str(entry_id or "").strip()
        ]

        if len(retained) == len(book["contents"]):
            raise KeyError(f"Unknown book content entry_id: {entry_id}")

        book["contents"] = retained
        return self.update_book(book_id, book)

    def add_holding(self, book_id, values):
        book = self.require_book(book_id)
        book["holdings"].append(self.prepare_holding(values))
        return self.update_book(book_id, book)

    def update_holding(self, book_id, entry_id, values):
        book = self.require_book(book_id)
        replacement = deepcopy(values)
        replacement["entry_id"] = str(entry_id or "").strip()
        normalized_replacement = self.prepare_holding(replacement)
        found = False
        holdings = []

        for holding in book["holdings"]:
            if holding["entry_id"] == normalized_replacement["entry_id"]:
                holdings.append(normalized_replacement)
                found = True
            else:
                holdings.append(holding)

        if not found:
            raise KeyError(f"Unknown book holding entry_id: {entry_id}")

        book["holdings"] = holdings
        return self.update_book(book_id, book)

    def prepare_holding(self, values):
        candidate = deepcopy(values) if isinstance(values, dict) else {}
        candidate["holder_name"] = self.holding_name(candidate)
        holding = normalize_book_holding(candidate)

        if holding["holder_type"] in ("Library", "Shop"):
            organization = self.organizations_by_id().get(
                holding["organization_id"]
            )

            if organization is None:
                raise ValueError("The selected organization no longer exists.")

            if (
                holding["holder_type"] == "Library"
                and not organization.get("includes_library")
            ):
                raise ValueError(
                    "The selected organization is not marked Includes a "
                    "library."
                )

            if (
                holding["holder_type"] == "Shop"
                and not organization.get("has_shop")
            ):
                raise ValueError(
                    "The selected organization is not marked Includes a "
                    "shop."
                )

        return holding

    def remove_holding(self, book_id, entry_id):
        book = self.require_book(book_id)
        retained = [
            holding
            for holding in book["holdings"]
            if holding["entry_id"] != str(entry_id or "").strip()
        ]

        if len(retained) == len(book["holdings"]):
            raise KeyError(f"Unknown book holding entry_id: {entry_id}")

        book["holdings"] = retained
        return self.update_book(book_id, book)

    def record_reading(self, person_id, book_id, reading_date, source_entry_id):
        normalized_person_id = str(person_id or "").strip()
        normalized_book_id = str(book_id or "").strip()
        normalized_date = normalize_world_event_date(reading_date)
        normalized_source_id = str(source_entry_id or "").strip()
        source = next(
            (
                option
                for option in self.available_sources_for_person(
                    normalized_person_id,
                    normalized_date,
                )
                if option["book_id"] == normalized_book_id
                and option["source_entry_id"] == normalized_source_id
            ),
            None,
        )

        if source is None:
            raise ValueError(
                "That book is not available to this person on the "
                "selected date."
            )

        person = self.people_by_id().get(normalized_person_id)
        book = self.require_book(normalized_book_id)
        reading = normalize_book_reading(
            {
                "person_id": normalized_person_id,
                "person_name": str(
                    (person or {}).get("displayed_name", "")
                    or "Unknown person"
                ).strip(),
                "book_id": normalized_book_id,
                "book_title": book["title"],
                "author_name": book["author_name"],
                "date": normalized_date,
                "source_type": source["source_type"],
                "source_entry_id": source["source_entry_id"],
                "source_organization_id": source[
                    "source_organization_id"
                ],
                "source_person_id": source["source_person_id"],
                "source_location_id": source["source_location_id"],
                "source_name": source["source_name"],
                "price_sickles": source["price_sickles"],
                "notes": "",
            }
        )
        created = self.database.create_record("book_readings", reading)
        self.database.save()
        return normalize_book_reading(created)

    def delete_reading(self, record_id, person_id=None):
        reading = self.database.read_record("book_readings", record_id)

        if reading is None:
            raise KeyError(f"Unknown book reading record_id: {record_id}")

        normalized = normalize_book_reading(reading)

        if (
            person_id is not None
            and normalized["person_id"] != str(person_id or "").strip()
        ):
            raise ValueError("That reading belongs to another person.")

        self.database.delete_record("book_readings", record_id)
        self.database.save()
        return normalized

    def reading_history_entries_for_person(self, person_id):
        return [
            {
                "record_id": reading["record_id"],
                "date": reading["date"],
                "name": reading["book_title"],
                "author": reading["author_name"],
                "source": book_reading_source_text(reading),
                "source_kind": "catalog",
                "book_id": reading["book_id"],
            }
            for reading in self.readings_for_person(person_id)
        ]

    def content_options(self):
        if self._content_options is not None:
            return deepcopy(self._content_options)

        options = []

        for content_type, collections in BOOK_CONTENT_COLLECTIONS.items():
            for collection_name in collections:
                for record in self.game_database.collection(collection_name):
                    record_id = str(
                        record.get("record_id", "") or ""
                    ).strip()
                    name = str(
                        record.get("name", "")
                        or record.get("title", "")
                        or ""
                    ).strip()

                    if not record_id or not name:
                        continue

                    options.append(
                        {
                            "content_type": content_type,
                            "collection": collection_name,
                            "record_id": record_id,
                            "name": name,
                            "search_text": self.content_search_text(
                                content_type,
                                collection_name,
                                record,
                            ),
                        }
                    )

        options.sort(key=self.content_option_sort_key)
        self._content_options = options
        return deepcopy(options)

    def content_search_text(self, content_type, collection_name, record):
        searchable_values = [
            content_type,
            collection_name.replace("_", " "),
            record.get("name"),
            record.get("title"),
            record.get("skill"),
            record.get("subtype"),
            record.get("tradition"),
            record.get("description"),
        ]
        return " ".join(
            str(value or "").strip().casefold()
            for value in searchable_values
            if str(value or "").strip()
        )

    def content_option_sort_key(self, option):
        return (
            option["content_type"],
            option["name"].casefold(),
            option["record_id"],
        )

    def people_by_id(self):
        return {
            str(person.get("record_id", "") or "").strip(): person
            for person in self.people_provider()
            if isinstance(person, dict)
            and str(person.get("record_id", "") or "").strip()
        }

    def locations_by_id(self):
        return {
            str(location.get("record_id", "") or "").strip(): location
            for location in self.location_provider()
            if isinstance(location, dict)
            and str(location.get("record_id", "") or "").strip()
        }

    def organizations_by_id(self):
        return {
            str(organization.get("record_id", "") or "").strip(): organization
            for organization in self.organization_provider()
            if isinstance(organization, dict)
            and str(organization.get("record_id", "") or "").strip()
        }

    def people_options(self):
        if self.event_controller is not None:
            return self.event_controller.people_options()

        options = [
            {
                "value": person_id,
                "label": str(
                    person.get("displayed_name", "") or "Unknown person"
                ).strip(),
                "person": deepcopy(person),
                "group_name": "",
            }
            for person_id, person in self.people_by_id().items()
        ]
        options.sort(key=self.person_option_sort_key)
        return options

    def recent_people_options(self):
        if self.event_controller is not None:
            return self.event_controller.recent_people_options()

        return self.people_options()[:5]

    def person_option_sort_key(self, option):
        return (
            str(option.get("label", "") or "").casefold(),
            str(option.get("value", "") or ""),
        )

    def mage_groups(self):
        if self.event_controller is not None:
            return self.event_controller.mage_groups()

        return []

    def holding_name(self, holding):
        holder_type = str(holding.get("holder_type", "") or "").strip()

        if holder_type in ("Library", "Shop"):
            organization_id = str(
                holding.get("organization_id", "") or ""
            ).strip()
            organizations_by_id = self.organizations_by_id()

            if organization_id in organizations_by_id:
                return organization_context_label(
                    organization_id,
                    list(organizations_by_id.values()),
                    list(self.locations_by_id().values()),
                )

            return str(
                holding.get("holder_name", "") or "Unknown organization"
            ).strip()

        if holder_type == "Private owner":
            person_id = str(holding.get("person_id", "") or "").strip()
            person = self.people_by_id().get(person_id)
            return str(
                (person or {}).get("displayed_name", "")
                or holding.get("holder_name", "")
                or "Unknown owner"
            ).strip()

        location_id = str(
            holding.get("location_id", "") or ""
        ).strip()
        locations = list(self.locations_by_id().values())

        if location_id in self.locations_by_id():
            return recent_location_label(location_id, locations)

        return str(
            holding.get("holder_name", "") or "Unknown location"
        ).strip()

    def location_region_id(self, location_id):
        locations = list(self.locations_by_id().values())
        ancestors = ancestor_locations(location_id, locations)

        if not ancestors:
            return ""

        return str(ancestors[-1].get("record_id", "") or "").strip()

    def effective_organization_location_id(self, organization_id):
        organizations = self.organizations_by_id()
        current_id = str(organization_id or "").strip()
        visited = set()

        while current_id and current_id not in visited:
            visited.add(current_id)
            organization = organizations.get(current_id)

            if organization is None:
                break

            location_id = str(
                organization.get("campus_location_id", "")
                or organization.get("location_id", "")
                or ""
            ).strip()

            if location_id:
                return location_id

            current_id = str(
                organization.get("parent_organization_id", "") or ""
            ).strip()

        return ""

    def person_location_id_on_date(self, person_id, target_date):
        person = self.people_by_id().get(str(person_id or "").strip())

        if person is None:
            return ""

        normalized_target_date = normalize_world_event_date(target_date)
        locations = list(self.locations_by_id().values())
        location_paths = location_paths_by_id(locations)
        location_ids_by_label = {}

        for location in locations:
            location_id = str(
                location.get("record_id", "") or ""
            ).strip()
            location_name = str(location.get("name", "") or "").strip()
            path_name = str(location_paths.get(location_id, "") or "").strip()

            if location_name:
                location_ids_by_label.setdefault(
                    location_name.casefold(),
                    location_id,
                )

            if path_name:
                location_ids_by_label[path_name.casefold()] = location_id

        candidates = []

        for event in normalize_timeline_events(
            person.get("timeline_events", [])
        ):
            if event.get("event_type") not in (
                "starting_location",
                "relocated",
            ):
                continue

            self.add_person_location_candidate(
                candidates,
                event,
                normalized_target_date,
                location_ids_by_label,
            )

        if self.event_controller is not None:
            for event in self.event_controller.events_for_person(
                str(person_id or "").strip()
            ):
                if event.get("event_type") != "relocated":
                    continue

                self.add_person_location_candidate(
                    candidates,
                    event,
                    normalized_target_date,
                    location_ids_by_label,
                )

        if candidates:
            candidates.sort(key=self.person_location_candidate_sort_key)
            return candidates[-1][1]

        for field_name in (
            "current_location",
            "location",
            "starting_location",
            "birth_location",
        ):
            stored_location = str(person.get(field_name, "") or "").strip()

            if stored_location in self.locations_by_id():
                return stored_location

            matched_id = location_ids_by_label.get(
                stored_location.casefold(),
                "",
            )

            if matched_id:
                return matched_id

        return ""

    def add_person_location_candidate(
        self,
        candidates,
        event,
        target_date,
        location_ids_by_label,
    ):
        event_date = str(event.get("date", "") or "").strip()

        if not event_date or not book_date_is_on_or_before(
            event_date,
            target_date,
        ):
            return

        location_id = next(
            (
                str(candidate_id or "").strip()
                for candidate_id in reversed(
                    event.get("location_ids", []) or []
                )
                if str(candidate_id or "").strip()
                in self.locations_by_id()
            ),
            "",
        )

        if not location_id:
            detail = str(
                event.get("detail", "")
                or event.get("title", "")
                or ""
            ).strip()

            for prefix in ("Relocated to ", "Relocated: ", "Relocated "):
                if detail.casefold().startswith(prefix.casefold()):
                    detail = detail[len(prefix):].strip()
                    break

            location_id = location_ids_by_label.get(
                detail.casefold(),
                "",
            )

        if not location_id:
            return

        candidates.append((world_event_sort_key(event), location_id))

    def person_location_candidate_sort_key(self, candidate):
        return candidate[0]

    def reading_slot_state(self, person_id, target_date):
        person = self.people_by_id().get(str(person_id or "").strip())

        if person is None:
            return {"maximum": 0, "used": 0, "remaining": 0}

        target_year_text, target_month_text, target_day_text = (
            split_world_event_date(target_date)
        )
        target_year = int(target_year_text)
        target_month = int(target_month_text or 12)
        target_day = int(target_day_text or 31)
        plan = normalize_development_plan(person.get("development_plan"))
        academic_start_year = calculate_development_start_year(
            person.get("birth_year"),
            person.get("birth_month"),
            person.get("birth_day"),
            school_attended=bool(str(person.get("school", "") or "").strip()),
        )
        maximum = ADULT_YEAR_MAX_BOOK_COUNT
        legacy_used = 0
        slot_start = (target_year, 1, 1)
        slot_end = (target_year, 12, 31)

        for record in plan.get("school_years", []):
            calendar_range = school_year_calendar_year_range(
                academic_start_year,
                record.get("year"),
            )

            if calendar_range is None:
                continue

            start_year, end_year = calendar_range
            starts_in_target_year = target_year == start_year and (
                target_month > 7
                or (target_month == 7 and target_day >= 1)
            )
            ends_in_target_year = target_year == end_year and target_month < 7

            if not starts_in_target_year and not ends_in_target_year:
                continue

            maximum = SCHOOL_YEAR_BOOK_COUNT
            legacy_used = len(record.get("assigned_books", [])) + len(
                record.get("books", [])
            )
            slot_start = (start_year, 7, 1)
            slot_end = (end_year, 6, 30)
            break

        catalog_used = 0

        for reading in self.readings_for_person(person_id):
            reading_key = book_date_end_key(reading["date"])

            if slot_start <= reading_key <= slot_end:
                catalog_used += 1

        used = legacy_used + catalog_used
        return {
            "maximum": maximum,
            "used": used,
            "remaining": max(0, maximum - used),
        }

    def available_money_sickles(self, person_id, target_date):
        person = self.people_by_id().get(str(person_id or "").strip())

        if person is None:
            return 0

        target_key = book_date_end_key(target_date)
        plan = normalize_development_plan(person.get("development_plan"))
        balance = 0

        for entry in visible_ledger_entries(plan.get("ledger_entries", [])):
            calendar_year = entry.get("calendar_year")

            if calendar_year is None:
                entry_key = (-100000, 1, 1)
            else:
                entry_key = (
                    int(calendar_year),
                    int(entry.get("month") or 1),
                    int(entry.get("day") or 1),
                )

            if entry_key > target_key:
                continue

            if entry["kind"] == LEDGER_KIND_EARNED:
                balance += entry["amount_sickles"]
            elif entry["kind"] == LEDGER_KIND_BOUGHT:
                balance -= entry["amount_sickles"]

        for reading in self.readings_for_person(person_id):
            if (
                reading["source_type"] == "Purchased"
                and book_date_is_on_or_before(reading["date"], target_date)
            ):
                balance -= int(reading["price_sickles"] or 0)

        return balance

    def holding_remaining_copies(self, holding, target_date):
        normalized_holding = normalize_book_holding(holding)

        if normalized_holding["copies"] is None:
            return None

        purchases = sum(
            1
            for reading in self.list_readings()
            if reading["source_type"] == "Purchased"
            and reading["source_entry_id"]
            == normalized_holding["entry_id"]
            and book_date_is_on_or_before(reading["date"], target_date)
        )
        return max(0, normalized_holding["copies"] - purchases)

    def available_sources_for_person(self, person_id, target_date):
        normalized_person_id = str(person_id or "").strip()
        normalized_date = normalize_world_event_date(target_date)
        person = self.people_by_id().get(normalized_person_id)

        if person is None:
            return []

        slot_state = self.reading_slot_state(
            normalized_person_id,
            normalized_date,
        )

        if slot_state["remaining"] <= 0:
            return []

        money = self.available_money_sickles(
            normalized_person_id,
            normalized_date,
        )
        person_location_id = self.person_location_id_on_date(
            normalized_person_id,
            normalized_date,
        )
        person_region_id = self.location_region_id(person_location_id)
        organizations = self.organizations_by_id()
        school_name = str(person.get("school", "") or "").strip().casefold()
        available = []

        for book in self.list_books():
            if not book_date_is_on_or_before(
                book["publication_date"],
                normalized_date,
            ):
                continue

            for holding in book["holdings"]:
                option = self.available_holding_source(
                    book,
                    holding,
                    normalized_person_id,
                    normalized_date,
                    money,
                    person_region_id,
                    school_name,
                    organizations,
                )

                if option is not None:
                    available.append(option)

        available.sort(key=self.available_source_sort_key)
        return available

    def available_holding_source(
        self,
        book,
        holding,
        person_id,
        target_date,
        money,
        person_region_id,
        school_name,
        organizations,
    ):
        if not book_holding_is_active(holding, target_date):
            return None

        remaining_copies = self.holding_remaining_copies(
            holding,
            target_date,
        )

        if remaining_copies == 0:
            return None

        holder_type = holding["holder_type"]
        source_type = ""
        source_name = holding["holder_name"]
        source_organization_id = ""
        source_person_id = ""
        source_location_id = ""
        price_sickles = 0

        if holder_type in ("Library", "Shop"):
            organization_id = holding["organization_id"]
            organization = organizations.get(organization_id)

            if organization is None:
                return None

            organization_location_id = (
                self.effective_organization_location_id(organization_id)
            )
            organization_region_id = self.location_region_id(
                organization_location_id
            )
            same_region = bool(
                person_region_id
                and organization_region_id
                and person_region_id == organization_region_id
            )
            organization_name = str(
                organization.get("name", "") or ""
            ).strip()
            source_organization_id = organization_id

            if holder_type == "Library":
                if not organization.get("includes_library"):
                    return None

                is_school_library = bool(
                    school_name
                    and organization_name.casefold() == school_name
                )

                if is_school_library:
                    source_type = "School library"
                    source_name = organization_name
                elif (
                    organization.get("library_open_to_outsiders")
                    and same_region
                ):
                    source_type = "Library"
                    source_name = organization_name
                else:
                    return None
            else:
                if not organization.get("has_shop") or not same_region:
                    return None

                price_sickles = int(holding["price_sickles"] or 0)

                if price_sickles > money:
                    return None

                source_type = "Purchased"
                source_name = organization_name
        elif holder_type == "Private owner":
            if holding["person_id"] != person_id:
                return None

            source_type = "Owned copy"
            source_person_id = holding["person_id"]
        else:
            return None

        option = {
            "book_id": book["record_id"],
            "book_title": book["title"],
            "author_name": book["author_name"],
            "source_entry_id": holding["entry_id"],
            "source_type": source_type,
            "source_name": source_name,
            "source_organization_id": source_organization_id,
            "source_person_id": source_person_id,
            "source_location_id": source_location_id,
            "price_sickles": price_sickles,
            "remaining_copies": remaining_copies,
        }
        option["label"] = self.available_source_label(option)
        return option

    def available_source_label(self, option):
        source_text = option["source_name"]

        if option["source_type"] == "Purchased":
            price = int(option["price_sickles"] or 0)
            source_text = f"Buy at {source_text} · {price} sickles"
        elif option["source_type"] == "School library":
            source_text = f"Read at {source_text} library"
        elif option["source_type"] == "Library":
            source_text = f"Read at {source_text} library"
        else:
            source_text = f"Read from {source_text}"

        return f"{option['book_title']} — {source_text}"

    def available_source_sort_key(self, option):
        return (
            option["book_title"].casefold(),
            option["source_type"],
            option["source_name"].casefold(),
            option["source_entry_id"],
        )
