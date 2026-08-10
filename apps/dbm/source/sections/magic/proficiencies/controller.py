from copy import deepcopy

from sections.magic.proficiencies.constants import (
    PROFICIENCY_SKILLS,
    PROFICIENCY_SKILLS_BY_NORMALIZED_NAME,
)
from sections.magic.proficiencies.required_materials import (
    REQUIRED_MATERIAL_TYPES,
    RequiredMaterialCatalog,
)
from sections.magic.traditions import (
    TRADITIONS,
    TRADITIONS_BY_NORMALIZED_NAME,
)


class ProficiencyController:
    collection_name = "proficiencies"
    text_fields = (
        "name",
        "tradition",
        "skill",
        "description",
        "history",
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
            "tradition": "",
            "skill": "",
            "threshold": None,
            "required_materials": [],
            "description": "",
            "history": "",
            "tags": [],
            "dbnotes": "",
        }
        complete_values.update(deepcopy(record_values))
        normalized_values = self.normalize_record_values(complete_values)
        self.validate_record_values(normalized_values)
        self.ensure_unique_identity(normalized_values)
        created_record = self.database.create(
            self.collection_name,
            normalized_values,
        )
        self.database.save()

        return created_record

    def update_record(self, record_id, record_values):
        current_record = self.get_record(record_id)

        if current_record is None:
            raise KeyError(f"Unknown proficiency record ID: {record_id}")

        normalized_changes = self.normalize_record_values(record_values)
        prospective_record = deepcopy(current_record)
        prospective_record.update(normalized_changes)
        self.validate_record_values(prospective_record)
        self.ensure_unique_identity(
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

        if "skill" in normalized_values:
            normalized_skill = " ".join(
                normalized_values["skill"].split()
            ).casefold()
            canonical_skill = PROFICIENCY_SKILLS_BY_NORMALIZED_NAME.get(
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

        if "required_materials" in normalized_values:
            normalized_values["required_materials"] = (
                self.normalize_required_materials(
                    normalized_values["required_materials"]
                )
            )

        if "tags" in normalized_values:
            normalized_values["tags"] = self.normalize_name_list(
                normalized_values["tags"],
                "tags",
            )

        return normalized_values

    def normalize_name_list(self, values, field_name):
        if not isinstance(values, list):
            raise TypeError(f"Proficiency {field_name} must be a list.")

        return [" ".join(str(value).split()) for value in values]

    def normalize_required_materials(self, materials):
        if not isinstance(materials, list):
            raise TypeError("Proficiency required materials must be a list.")

        normalized_materials = []

        for material in materials:
            if not isinstance(material, dict):
                raise TypeError("Every required material must be an object.")

            quantity = material.get("quantity", 1)

            if isinstance(quantity, bool):
                normalized_quantity = quantity
            else:
                normalized_quantity = int(quantity)

            normalized_materials.append(
                {
                    "name": " ".join(str(material.get("name", "")).split()),
                    "type": " ".join(str(material.get("type", "")).split()),
                    "quantity": normalized_quantity,
                }
            )

        return normalized_materials

    def validate_record_values(self, record_values):
        if not record_values.get("name", "").strip():
            raise ValueError("A proficiency must have a name.")

        skill = record_values.get("skill", "")

        if skill not in PROFICIENCY_SKILLS:
            raise ValueError("A proficiency must use a defined skill.")

        tradition = record_values.get("tradition", "")

        if tradition and tradition not in TRADITIONS:
            raise ValueError("A proficiency must use a defined tradition.")

        threshold = record_values.get("threshold")

        if threshold is not None:
            if isinstance(threshold, bool) or not isinstance(threshold, int):
                raise ValueError("Proficiency threshold must be numeric.")

            if not 1 <= threshold <= 100:
                raise ValueError(
                    "Proficiency threshold must be between 1 and 100."
                )

        self.validate_required_materials(
            record_values.get("required_materials", [])
        )
        self.validate_tags(record_values.get("tags", []))

        for field_name in self.text_fields:
            if field_name in record_values and not isinstance(
                record_values[field_name],
                str,
            ):
                raise TypeError(f"Proficiency {field_name} must be text.")

    def validate_name_list(self, values, field_label):
        if not isinstance(values, list):
            raise TypeError(f"Proficiency {field_label} must be a list.")

        normalized_values = set()

        for value in values:
            if not isinstance(value, str):
                raise TypeError(
                    f"Every proficiency {field_label} entry must be text."
                )

            if not value.strip():
                raise ValueError(
                    f"Proficiency {field_label} entries cannot be blank."
                )

            normalized_value = " ".join(value.split()).casefold()

            if normalized_value in normalized_values:
                raise ValueError(
                    f"Duplicate proficiency {field_label} entry: {value}"
                )

            normalized_values.add(normalized_value)

    def validate_required_materials(self, materials):
        if not isinstance(materials, list):
            raise TypeError("Proficiency required materials must be a list.")

        catalog = RequiredMaterialCatalog.for_database(self.database)
        normalized_materials = set()

        for material in materials:
            if not isinstance(material, dict):
                raise TypeError("Every required material must be an object.")

            material_name = material.get("name", "")
            material_type = material.get("type", "")
            quantity = material.get("quantity")

            if not material_name:
                raise ValueError("Every required material must have a name.")

            if material_type not in REQUIRED_MATERIAL_TYPES:
                raise ValueError(
                    f"Unknown required material type: {material_type}"
                )

            if isinstance(quantity, bool) or not isinstance(quantity, int):
                raise TypeError(
                    f"Quantity for {material_name} must be a whole number."
                )

            if quantity < 1:
                raise ValueError(
                    f"Quantity for {material_name} must be at least 1."
                )

            if not catalog.contains(material_name, material_type):
                raise ValueError(
                    f"Unknown required {material_type}: {material_name}"
                )

            material_key = (
                material_type.casefold(),
                material_name.casefold(),
            )

            if material_key in normalized_materials:
                raise ValueError(
                    f"Duplicate required material: {material_name}"
                )

            normalized_materials.add(material_key)

    def validate_tags(self, tags):
        self.validate_name_list(tags, "tags")

    def ensure_unique_identity(self, record_values, record_id=None):
        proposed_identity = self.proficiency_identity(record_values)

        for existing_record in self.database.get_collection(
            self.collection_name
        ):
            if existing_record.get("record_id") == record_id:
                continue

            if self.proficiency_identity(existing_record) == proposed_identity:
                raise ValueError(
                    "A proficiency with this name, skill, tradition, and "
                    "threshold already exists."
                )

    def proficiency_identity(self, record):
        return (
            " ".join(str(record.get("name", "")).split()).casefold(),
            " ".join(str(record.get("skill", "")).split()).casefold(),
            " ".join(str(record.get("tradition", "")).split()).casefold(),
            record.get("threshold"),
        )

    def record_sort_key(self, record):
        return (
            record.get("name", "").casefold(),
            record.get("skill", "").casefold(),
            record.get("threshold")
            if record.get("threshold") is not None
            else -1,
            record.get("record_id", ""),
        )
