from copy import deepcopy

from sections.magic.spells.constants import (
    SPELL_SKILLS,
    SPELL_SKILLS_BY_NORMALIZED_NAME,
    SPELL_SUBTYPES,
    SPELL_SUBTYPES_BY_NORMALIZED_NAME,
)
from sections.magic.traditions import (
    TRADITIONS,
    TRADITIONS_BY_NORMALIZED_NAME,
)


class SpellController:
    collection_name = "spells"
    text_fields = (
        "name",
        "incantation",
        "tradition",
        "skill",
        "subtype",
        "description",
        "history",
        "rationale",
        "dbnotes",
    )

    def __init__(self, database):
        self.database = database

    def list_records(self):
        records = self.database.get_collection(self.collection_name)
        records.sort(key=self.record_sort_key)

        return records

    def get_record(self, record_id):
        return self.database.read(self.collection_name, record_id)

    def create_record(self, record_values):
        complete_values = {
            "name": "",
            "incantation": "",
            "tradition": "",
            "skill": "",
            "subtype": "",
            "threshold": None,
            "description": "",
            "history": "",
            "rationale": "",
            "tags": [],
            "dbnotes": "",
        }
        complete_values.update(deepcopy(record_values))
        normalized_values = self.normalize_record_values(complete_values)
        self.validate_record_values(normalized_values)
        self.ensure_unique_spell_identity(normalized_values)
        created_record = self.database.create(
            self.collection_name,
            normalized_values,
        )
        self.database.save()

        return created_record

    def update_record(self, record_id, record_values):
        current_record = self.get_record(record_id)

        if current_record is None:
            raise KeyError(f"Unknown spell record ID: {record_id}")

        normalized_changes = self.normalize_record_values(record_values)
        prospective_record = deepcopy(current_record)
        prospective_record.update(normalized_changes)
        self.validate_record_values(prospective_record)
        self.ensure_unique_spell_identity(
            prospective_record,
            record_id=record_id,
        )
        updated_record = self.database.update(
            self.collection_name,
            record_id,
            normalized_changes,
        )
        self.database.save()

        return updated_record

    def delete_record(self, record_id):
        deleted_record = self.database.delete(
            self.collection_name,
            record_id,
        )
        self.database.save()

        return deleted_record

    def normalize_record_values(self, record_values):
        normalized_values = deepcopy(record_values)

        for field_name in self.text_fields:
            if field_name in normalized_values:
                normalized_values[field_name] = str(
                    normalized_values[field_name] or ""
                ).strip()

        if "subtype" in normalized_values:
            normalized_subtype = " ".join(
                normalized_values["subtype"].split()
            ).casefold()
            canonical_subtype = SPELL_SUBTYPES_BY_NORMALIZED_NAME.get(
                normalized_subtype
            )

            if canonical_subtype is not None:
                normalized_values["subtype"] = canonical_subtype

        if "skill" in normalized_values:
            normalized_skill = " ".join(
                normalized_values["skill"].split()
            ).casefold()
            canonical_skill = SPELL_SKILLS_BY_NORMALIZED_NAME.get(
                normalized_skill
            )

            if canonical_skill is not None:
                normalized_values["skill"] = canonical_skill

        if "tradition" in normalized_values:
            normalized_tradition = " ".join(
                normalized_values["tradition"].split()
            ).casefold()
            canonical_tradition = TRADITIONS_BY_NORMALIZED_NAME.get(
                normalized_tradition
            )

            if canonical_tradition is not None:
                normalized_values["tradition"] = canonical_tradition

        if "threshold" in normalized_values:
            threshold = normalized_values["threshold"]

            if threshold in (None, ""):
                normalized_values["threshold"] = None
            elif isinstance(threshold, bool):
                normalized_values["threshold"] = threshold
            else:
                normalized_values["threshold"] = int(threshold)

        if "tags" in normalized_values:
            tags = normalized_values["tags"]

            if not isinstance(tags, list):
                raise TypeError("Spell tags must be a list.")

            normalized_values["tags"] = [
                " ".join(str(tag).split()) for tag in tags
            ]

        return normalized_values

    def validate_record_values(self, record_values):
        if not record_values.get("name", "").strip():
            raise ValueError("A spell must have a name.")

        if not record_values.get("skill", "").strip():
            raise ValueError("A spell must have a skill.")

        if record_values["skill"] not in SPELL_SKILLS:
            raise ValueError("A spell must use a defined skill.")

        if not record_values.get("subtype", "").strip():
            raise ValueError("A spell must have a subtype.")

        if record_values["subtype"] not in SPELL_SUBTYPES:
            raise ValueError("A spell must use a defined subtype.")

        tradition = record_values.get("tradition", "")

        if tradition and tradition not in TRADITIONS:
            raise ValueError("A spell must use a defined tradition.")

        threshold = record_values.get("threshold")

        if isinstance(threshold, bool) or not isinstance(threshold, int):
            raise ValueError("A spell must have a numeric threshold.")

        if not 1 <= threshold <= 100:
            raise ValueError("Spell threshold must be between 1 and 100.")

        if "tags" in record_values:
            self.validate_tags(record_values["tags"])

        for field_name in self.text_fields:
            if field_name in record_values and not isinstance(
                record_values[field_name],
                str,
            ):
                raise TypeError(f"Spell {field_name} must be text.")

    def validate_tags(self, tags):
        if not isinstance(tags, list):
            raise TypeError("Spell tags must be a list.")

        normalized_tags = set()

        for tag in tags:
            if not isinstance(tag, str):
                raise TypeError("Every spell tag must be text.")

            tag_text = tag.strip()

            if not tag_text:
                raise ValueError("Spell tags cannot be blank.")

            normalized_tag = " ".join(tag_text.split()).casefold()

            if normalized_tag in normalized_tags:
                raise ValueError(f"Duplicate spell tag: {tag_text}")

            normalized_tags.add(normalized_tag)

    def ensure_unique_spell_identity(self, record_values, record_id=None):
        proposed_identity = self.spell_identity(record_values)

        for existing_record in self.database.get_collection(
            self.collection_name
        ):
            if existing_record.get("record_id") == record_id:
                continue

            if self.spell_identity(existing_record) == proposed_identity:
                raise ValueError(
                    "A spell with this name, incantation, skill, and subtype "
                    "already exists."
                )

    def spell_identity(self, record):
        return tuple(
            " ".join(str(record.get(field_name, "")).split()).casefold()
            for field_name in ("name", "incantation", "skill", "subtype")
        )

    def record_sort_key(self, record):
        return (
            record.get("name", "").casefold(),
            record.get("incantation", "").casefold(),
            record.get("skill", "").casefold(),
            record.get("subtype", "").casefold(),
            record.get("record_id", ""),
        )
