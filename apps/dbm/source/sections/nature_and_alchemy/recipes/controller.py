from copy import deepcopy
from uuid import uuid4

from database.name_links import ensure_unique_record_name
from sections.magic.proficiencies.constants import PROFICIENCY_SKILLS


class RecipeController:
    collection_name = "recipes"

    def __init__(self, database):
        self.database = database

    def list_records(self):
        return sorted(self.database.get_collection(self.collection_name), key=lambda row: (str(row.get("name", "")).casefold(), str(row.get("record_id", ""))))

    def get_record(self, record_id):
        return self.database.read(self.collection_name, record_id)

    def create_record(self, values):
        normalized = self.normalize(values)
        self.validate(normalized)
        ensure_unique_record_name(self.database.get_collection(self.collection_name), normalized["name"], record_label="recipe")
        record = self.database.create(self.collection_name, normalized)
        try:
            self.database.save()
        except Exception:
            self.database.discard_unsaved_changes()
            raise
        return record

    def update_record(self, record_id, values):
        normalized = self.normalize(values)
        current = self.get_record(record_id)
        if current is None:
            raise KeyError(f"Unknown recipe record ID: {record_id}")
        prospective = deepcopy(current); prospective.update(normalized)
        self.validate(prospective)
        ensure_unique_record_name(self.database.get_collection(self.collection_name), prospective["name"], record_id=record_id, record_label="recipe")
        record = self.database.update(self.collection_name, record_id, normalized)
        try:
            self.database.save()
        except Exception:
            self.database.discard_unsaved_changes()
            raise
        return record

    def delete_record(self, record_id):
        record = self.database.delete(self.collection_name, record_id)
        try:
            self.database.save()
        except Exception:
            self.database.discard_unsaved_changes()
            raise
        return record

    def duplicate_record(self, record_id):
        current = self.get_record(record_id)
        if current is None:
            raise KeyError(f"Unknown recipe record ID: {record_id}")
        values = deepcopy(current)
        values.pop("record_id", None)
        values.pop("last_updated", None)
        for formulation in values.get("formulations", []) or []:
            formulation["record_id"] = str(uuid4())
            for field in (
                "ingredient_requirements", "vessel_requirements",
                "proficiency_requirements", "spell_requirements",
            ):
                for group in formulation.get(field, []) or []:
                    group["record_id"] = str(uuid4())
        base_name = str(current.get("name", "Recipe") or "Recipe").strip()
        existing = {
            str(record.get("name", "")).casefold()
            for record in self.database.get_collection(self.collection_name)
        }
        candidate = f"{base_name} (Copy)"
        number = 2
        while candidate.casefold() in existing:
            candidate = f"{base_name} (Copy {number})"
            number += 1
        values["name"] = candidate
        return self.create_record(values)

    def normalize(self, values):
        result = deepcopy(values)
        result["name"] = " ".join(str(result.get("name", "") or "").split())
        result["skill"] = " ".join(str(result.get("skill", "") or "").split())
        result["threshold"] = int(result.get("threshold", 1))
        for field in ("description", "dbnotes"):
            result[field] = str(result.get(field, "") or "").strip()
        result["tags"] = [" ".join(str(tag).split()) for tag in result.get("tags", []) or [] if str(tag).strip()]
        raw_formulations = result.get("formulations")
        if not isinstance(raw_formulations, list) or not raw_formulations:
            raw_formulations = [{
                "record_id": str(uuid4()),
                "name": "Default",
                "output_item": result.get("output_item"),
                "output_quantity": result.get("output_quantity", 1),
                "ingredient_requirements": result.get("ingredient_requirements", []),
                "vessel_requirements": result.get("vessel_requirements", []),
                "proficiency_requirements": result.get("proficiency_requirements", []),
                "spell_requirements": result.get("spell_requirements", []),
            }]
        result["formulations"] = [
            self.normalize_formulation(formulation, index)
            for index, formulation in enumerate(raw_formulations)
        ]
        # Keep the first formulation mirrored for older Game Board readers.
        primary = result["formulations"][0]
        for field in ("output_item", "output_quantity", "ingredient_requirements", "vessel_requirements", "proficiency_requirements", "spell_requirements"):
            result[field] = deepcopy(primary.get(field))
        return result

    def normalize_reference(self, raw):
        if not isinstance(raw, dict):
            return None
        reference = {
            "collection": str(raw.get("collection", "") or "").strip(),
            "record_id": str(raw.get("record_id", "") or "").strip(),
            "name": str(raw.get("name", "") or "").strip(),
        }
        if raw.get("parent_record_id"):
            reference["parent_record_id"] = str(raw.get("parent_record_id"))
        return reference if all(reference.get(field) for field in ("collection", "record_id", "name")) else None

    def normalize_formulation(self, raw, index):
        if not isinstance(raw, dict):
            raise TypeError("Every formulation must be an object.")
        formulation = {
            "record_id": str(raw.get("record_id", "") or uuid4()),
            "name": " ".join(str(raw.get("name", "") or f"Formulation {index + 1}").split()),
            "output_item": self.normalize_reference(raw.get("output_item")),
            "output_quantity": int(raw.get("output_quantity", 1) or 1),
        }
        for field in ("ingredient_requirements", "vessel_requirements", "proficiency_requirements", "spell_requirements"):
            formulation[field] = self.normalize_groups(raw.get(field, []), field)
        return formulation

    def normalize_groups(self, groups, label):
        if not isinstance(groups, list):
            raise TypeError(f"{label} must be a list.")
        normalized = []
        for group in groups:
            if not isinstance(group, dict):
                raise TypeError("Every requirement line must be an object.")
            alternatives = []
            for raw in group.get("alternatives", []) or []:
                item = deepcopy(raw)
                item["collection"] = str(item.get("collection", "") or "").strip()
                item["record_id"] = str(item.get("record_id", "") or "").strip()
                item["name"] = str(item.get("name", "") or "").strip()
                if label == "ingredient_requirements":
                    item["quantity"] = int(item.get("quantity", 1) or 1)
                output_item = self.normalize_reference(item.get("output_item"))
                if output_item:
                    item["output_item"] = output_item
                else:
                    item.pop("output_item", None)
                modifier = int(item.get("output_quantity_modifier", 0) or 0)
                if modifier:
                    item["output_quantity_modifier"] = modifier
                else:
                    item.pop("output_quantity_modifier", None)
                alternatives.append(item)
            normalized.append({"record_id": str(group.get("record_id", "") or uuid4()), "alternatives": alternatives})
        return normalized

    def validate(self, values):
        if not values.get("name"):
            raise ValueError("A recipe must have a name.")
        if values.get("skill") not in PROFICIENCY_SKILLS:
            raise ValueError("A recipe must use a defined skill.")
        if not 1 <= values.get("threshold", 0) <= 100:
            raise ValueError("Recipe threshold must be between 1 and 100.")
        valid_collections = {"raw_materials", "general_items", "holdable_items", "accessories", "potions", "preparations", "foods_and_drinks", "books", "plant_parts", "creature_parts"}
        formulations = values.get("formulations", [])
        if not formulations:
            raise ValueError("A recipe needs at least one formulation.")
        formulation_ids = set()
        for formulation in formulations:
            formulation_id = formulation.get("record_id")
            if not formulation_id or formulation_id in formulation_ids:
                raise ValueError("Every formulation needs a unique stable ID.")
            formulation_ids.add(formulation_id)
            if not formulation.get("name"):
                raise ValueError("Every formulation needs a name.")
            self.validate_output(formulation.get("output_item"), formulation.get("output_quantity"), valid_collections)
            for field in ("ingredient_requirements", "vessel_requirements", "proficiency_requirements", "spell_requirements"):
                self.validate_groups(formulation.get(field, []), field, valid_collections)

    def validate_output(self, output_item, quantity, valid_collections):
        if not isinstance(output_item, dict):
            raise ValueError("Every formulation needs an output item.")
        if output_item.get("collection") not in valid_collections or not output_item.get("record_id") or not output_item.get("name"):
            raise ValueError("A formulation references an invalid output item.")
        if not isinstance(quantity, int) or quantity < 1:
            raise ValueError("Output quantity must be at least one.")

    def validate_groups(self, groups, field, valid_collections):
        seen_groups = set()
        for group in groups:
            group_id = group.get("record_id")
            if not group_id or group_id in seen_groups or not group.get("alternatives"):
                raise ValueError("Every requirement line needs a stable ID and at least one alternative.")
            seen_groups.add(group_id)
            seen_alternatives = set()
            for item in group["alternatives"]:
                identity = (item.get("collection"), item.get("record_id"), item.get("parent_record_id", ""))
                if identity in seen_alternatives:
                    raise ValueError("A requirement line cannot repeat an alternative.")
                seen_alternatives.add(identity)
                if field == "proficiency_requirements":
                    expected = {"proficiencies"}
                elif field == "spell_requirements":
                    expected = {"spells"}
                else:
                    expected = valid_collections
                if item.get("collection") not in expected or not item.get("record_id") or not item.get("name"):
                    raise ValueError("A requirement references an invalid catalog record.")
                if field == "ingredient_requirements" and item.get("quantity", 0) < 1:
                    raise ValueError("Ingredient quantities must be at least one.")
                output_item = item.get("output_item")
                if output_item is not None:
                    self.validate_output(output_item, 1, valid_collections)
                modifier = item.get("output_quantity_modifier", 0)
                if isinstance(modifier, bool) or not isinstance(modifier, int):
                    raise ValueError("Replacement quantity shifts must be whole numbers.")
