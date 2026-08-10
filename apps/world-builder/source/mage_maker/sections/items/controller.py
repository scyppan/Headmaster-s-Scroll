from copy import deepcopy

from mage_maker.sections.items.models import (
    ITEM_CATEGORIES_SETTING_KEY,
    ITEM_GROUPS_SETTING_KEY,
    item_current_holder,
    item_is_linked_to_person,
    normalize_item_categories,
    normalize_item_category,
    normalize_item_group,
    normalize_item_groups,
    normalize_item_passage,
    normalize_item_record,
    normalize_item_records,
)


class ItemController:
    def __init__(self, database, people_provider):
        self.database = database
        self.people_provider = people_provider

    def list_categories(self):
        settings = self.database.data.get(
            "_application_settings",
            {},
        )
        return normalize_item_categories(
            settings.get(ITEM_CATEGORIES_SETTING_KEY)
            if isinstance(settings, dict)
            else None
        )

    def add_category(self, category_name):
        category = normalize_item_category(category_name)
        categories = self.list_categories()

        if any(
            existing.casefold() == category.casefold()
            for existing in categories
        ):
            raise ValueError(f'An item category named "{category}" already exists.')

        categories.append(category)
        self.database.data["_application_settings"][
            ITEM_CATEGORIES_SETTING_KEY
        ] = normalize_item_categories(categories)
        self.database.dirty = True
        self.database.revision += 1
        self.database.save()
        return category

    def list_groups(self):
        settings = self.database.data.get(
            "_application_settings",
            {},
        )
        return normalize_item_groups(
            settings.get(ITEM_GROUPS_SETTING_KEY)
            if isinstance(settings, dict)
            else None
        )

    def add_group(self, group_name):
        group = normalize_item_group(group_name)

        if not group:
            raise ValueError("An item group needs a name.")

        groups = self.list_groups()

        if any(
            existing.casefold() == group.casefold()
            for existing in groups
        ):
            raise ValueError(
                f'An item group named "{group}" already exists.'
            )

        groups.append(group)
        self.database.data["_application_settings"][
            ITEM_GROUPS_SETTING_KEY
        ] = normalize_item_groups(groups)
        self.database.dirty = True
        self.database.revision += 1
        self.database.save()
        return group

    def list_items(self):
        items = normalize_item_records(
            self.database.list_records("items")
        )
        items.sort(key=self.item_sort_key)
        return items

    def item_sort_key(self, item):
        return (
            not bool(str(item.get("group", "") or "").strip()),
            str(item.get("group", "") or "").casefold(),
            str(item.get("category", "") or "").casefold(),
            str(item.get("name", "") or "").casefold(),
        )

    def get_item(self, record_id):
        item = self.database.read_record("items", record_id)
        return normalize_item_record(item) if item is not None else None

    def items_for_person(self, person_id):
        return [
            item
            for item in self.list_items()
            if item_is_linked_to_person(item, person_id)
        ]

    def current_holder(self, item):
        return item_current_holder(item)

    def create_item(self, values):
        item = self.prepare_item(values)
        self.ensure_unique_name(item["name"])
        created_item = self.database.create_record("items", item)
        self.database.save()
        return normalize_item_record(created_item)

    def update_item(self, record_id, values):
        current_item = self.get_item(record_id)

        if current_item is None:
            raise KeyError(f"Unknown item record_id: {record_id}")

        updated_values = deepcopy(values)
        updated_values["record_id"] = record_id
        updated_values.setdefault(
            "passage_history",
            current_item["passage_history"],
        )
        item = self.prepare_item(updated_values)
        self.ensure_unique_name(item["name"], excluded_record_id=record_id)
        updated_item = self.database.update_record(
            "items",
            record_id,
            item,
        )
        self.database.save()
        return normalize_item_record(updated_item)

    def delete_item(self, record_id):
        self.require_item(record_id)
        self.unlink_item_from_events(record_id)
        deleted_item = self.database.delete_record("items", record_id)
        self.database.save()
        return normalize_item_record(deleted_item)

    def unlink_item_from_events(self, item_id):
        normalized_item_id = str(item_id or "").strip()

        for event in self.database.list_records("events"):
            linked_item_ids = [
                str(linked_item_id or "").strip()
                for linked_item_id in event.get("item_ids", [])
                if str(linked_item_id or "").strip()
                != normalized_item_id
            ]
            item_link_types = dict(event.get("item_link_types", {}) or {})
            item_link_types.pop(normalized_item_id, None)
            item_new_owners = dict(
                event.get("item_new_owners", {}) or {}
            )
            item_new_owners.pop(normalized_item_id, None)

            if (
                linked_item_ids == event.get("item_ids", [])
                and item_link_types == event.get("item_link_types", {})
                and item_new_owners
                == event.get("item_new_owners", {})
            ):
                continue

            self.database.update_record(
                "events",
                event["record_id"],
                {
                    "item_ids": linked_item_ids,
                    "item_link_types": item_link_types,
                    "item_new_owners": item_new_owners,
                },
            )

        for organization in self.database.list_records("organizations"):
            organization_changed = False

            for event in organization.get("events", []):
                linked_item_ids = [
                    str(linked_item_id or "").strip()
                    for linked_item_id in event.get("item_ids", [])
                    if str(linked_item_id or "").strip()
                    != normalized_item_id
                ]
                item_link_types = dict(
                    event.get("item_link_types", {}) or {}
                )
                item_link_types.pop(normalized_item_id, None)
                item_new_owners = dict(
                    event.get("item_new_owners", {}) or {}
                )
                item_new_owners.pop(normalized_item_id, None)

                if (
                    linked_item_ids == event.get("item_ids", [])
                    and item_link_types == event.get(
                        "item_link_types",
                        {},
                    )
                    and item_new_owners == event.get(
                        "item_new_owners",
                        {},
                    )
                ):
                    continue

                event["item_ids"] = linked_item_ids
                event["item_link_types"] = item_link_types
                event["item_new_owners"] = item_new_owners
                organization_changed = True

            if organization_changed:
                self.database.update_record(
                    "organizations",
                    organization["record_id"],
                    organization,
                )

    def add_passage(self, item_id, values):
        item = self.require_item(item_id)
        passage = self.prepare_passage(values)
        current_holder = (
            item["passage_history"][-1]
            if item["passage_history"]
            else None
        )

        if current_holder is not None and (
            (
                current_holder.get("person_id")
                and current_holder.get("person_id")
                == passage["person_id"]
            )
            or (
                not current_holder.get("person_id")
                and not passage["person_id"]
                and str(
                    current_holder.get("person_name", "") or ""
                ).casefold()
                == passage["person_name"].casefold()
            )
        ):
            raise ValueError(
                (
                    f"{passage['person_name']} already holds this item."
                    if passage["person_name"]
                    else "This item is already unpossessed."
                )
            )

        item["passage_history"].append(passage)
        return self.update_item(item_id, item)

    def update_passage(self, item_id, passage_id, values):
        item = self.require_item(item_id)
        passage = self.prepare_passage(
            {
                **deepcopy(values),
                "record_id": passage_id,
            }
        )
        replacement_index = None

        for index, existing_passage in enumerate(
            item["passage_history"]
        ):
            if existing_passage["record_id"] == passage_id:
                replacement_index = index
                break

        if replacement_index is None:
            raise KeyError(f"Unknown item passage record_id: {passage_id}")

        previous_passage = (
            item["passage_history"][replacement_index - 1]
            if replacement_index > 0
            else None
        )
        next_passage = (
            item["passage_history"][replacement_index + 1]
            if replacement_index + 1 < len(item["passage_history"])
            else None
        )

        if previous_passage is not None and (
            (
                previous_passage["person_id"]
                and previous_passage["person_id"]
                == passage["person_id"]
            )
            or (
                not previous_passage["person_id"]
                and not passage["person_id"]
                and previous_passage["person_name"].casefold()
                == passage["person_name"].casefold()
            )
        ):
            raise ValueError(
                "Consecutive passage entries must have different holders."
            )

        if next_passage is not None and (
            (
                next_passage["person_id"]
                and next_passage["person_id"]
                == passage["person_id"]
            )
            or (
                not next_passage["person_id"]
                and not passage["person_id"]
                and next_passage["person_name"].casefold()
                == passage["person_name"].casefold()
            )
        ):
            raise ValueError(
                "Consecutive passage entries must have different holders."
            )

        item["passage_history"][replacement_index] = passage
        return self.update_item(item_id, item)

    def delete_passage(self, item_id, passage_id):
        item = self.require_item(item_id)
        retained_passages = [
            passage
            for passage in item["passage_history"]
            if passage["record_id"] != passage_id
        ]

        if len(retained_passages) == len(item["passage_history"]):
            raise KeyError(f"Unknown item passage record_id: {passage_id}")

        item["passage_history"] = retained_passages
        return self.update_item(item_id, item)

    def require_item(self, record_id):
        item = self.get_item(record_id)

        if item is None:
            raise KeyError(f"Unknown item record_id: {record_id}")

        return item

    def prepare_item(self, values):
        item = normalize_item_record(values)
        categories = self.list_categories()
        matching_category = next(
            (
                category
                for category in categories
                if category.casefold() == item["category"].casefold()
            ),
            None,
        )

        if matching_category is None:
            raise ValueError(
                "Choose an existing item category or add the category first."
            )

        item["category"] = matching_category
        matching_group = next(
            (
                group
                for group in self.list_groups()
                if group.casefold() == item["group"].casefold()
            ),
            None,
        )

        if item["group"] and matching_group is None:
            raise ValueError(
                "Choose an existing item group or add the group first."
            )

        item["group"] = matching_group or ""
        item["passage_history"] = [
            self.prepare_passage(passage)
            for passage in item["passage_history"]
        ]
        return normalize_item_record(item)

    def prepare_passage(self, values):
        passage = normalize_item_passage(values)
        people_by_id = {
            str(person.get("record_id", "") or "").strip(): person
            for person in self.people_provider()
            if isinstance(person, dict)
            and str(person.get("record_id", "") or "").strip()
        }

        if passage["person_id"]:
            person = people_by_id.get(passage["person_id"])

            if person is None:
                raise ValueError(
                    "The selected item holder no longer exists."
                )

            passage["person_name"] = str(
                person.get("displayed_name", "")
                or "Unnamed person"
            ).strip()

        return normalize_item_passage(passage)

    def ensure_unique_name(self, name, excluded_record_id=""):
        normalized_name = str(name or "").strip().casefold()

        for item in self.list_items():
            if item["record_id"] == excluded_record_id:
                continue

            if item["name"].casefold() == normalized_name:
                raise ValueError(
                    f'An item named "{str(name).strip()}" already exists.'
                )
