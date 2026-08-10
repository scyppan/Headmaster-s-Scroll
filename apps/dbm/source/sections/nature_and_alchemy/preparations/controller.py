from database.name_links import ensure_unique_record_name
from sections.nature_and_alchemy.potions.recipe_schema import (
    INGREDIENT_TYPES,
)


class PreparationController:
    def __init__(self, database, collection_name, record_label):
        self.database = database
        self.collection_name = collection_name
        self.record_label = record_label

    def list_records(self):
        records = self.database.get_collection(self.collection_name)
        records.sort(key=self.record_sort_key)

        return records

    def get_record(self, record_id):
        return self.database.read(self.collection_name, record_id)

    def create_record(self, record_values):
        complete_values = {
            "name": "",
            "skill": "",
            "brew_time": "",
            "threshold": None,
            "required_proficiencies": [],
            "additional_instructions": "",
            "description": "",
            "raw_effect": "",
            "effect_in_potions": "",
            "ingredients": [],
            "dbnotes": "",
            **record_values,
        }
        legacy_proficiency = str(
            complete_values.pop("proficiency", "")
        ).strip()

        if (
            legacy_proficiency
            and not complete_values.get("required_proficiencies")
        ):
            complete_values["required_proficiencies"] = [
                legacy_proficiency
            ]

        complete_values["ingredients"] = self.normalize_ingredients(
            complete_values.get("ingredients", [])
        )
        complete_values["required_proficiencies"] = (
            self.normalize_required_proficiencies(
                complete_values.get("required_proficiencies", [])
            )
        )
        self.validate_record_values(complete_values)
        ensure_unique_record_name(
            self.database.get_collection(self.collection_name),
            complete_values.get("name", ""),
            record_label=self.record_label,
        )
        created_record = self.database.create(
            self.collection_name,
            complete_values,
        )
        self.database.save()

        return created_record

    def update_record(self, record_id, record_values):
        normalized_values = dict(record_values)
        legacy_proficiency = str(
            normalized_values.pop("proficiency", "")
        ).strip()

        if (
            legacy_proficiency
            and "required_proficiencies" not in normalized_values
        ):
            normalized_values["required_proficiencies"] = [
                legacy_proficiency
            ]

        if "ingredients" in normalized_values:
            normalized_values["ingredients"] = self.normalize_ingredients(
                normalized_values["ingredients"]
            )

        if "required_proficiencies" in normalized_values:
            normalized_values["required_proficiencies"] = (
                self.normalize_required_proficiencies(
                    normalized_values["required_proficiencies"]
                )
            )

        self.validate_record_values(normalized_values)

        if "name" in normalized_values:
            ensure_unique_record_name(
                self.database.get_collection(self.collection_name),
                normalized_values["name"],
                record_id=record_id,
                record_label=self.record_label,
            )

        updated_record = self.database.update(
            self.collection_name,
            record_id,
            normalized_values,
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

    def validate_record_values(self, record_values):
        if not isinstance(record_values, dict):
            raise TypeError(
                f"{self.record_label.title()} values must be structured"
            )

        for field_name, field_label in (
            ("name", "Name"),
            ("skill", "Skill"),
            ("brew_time", "Brew Time"),
            ("additional_instructions", "Additional Instructions"),
            ("description", "Description"),
            ("raw_effect", "Raw Effect"),
            ("effect_in_potions", "Effect in Potions"),
            ("dbnotes", "DB Notes"),
        ):
            if field_name in record_values and not isinstance(
                record_values[field_name],
                str,
            ):
                raise TypeError(f"{field_label} must be text")

        if "threshold" in record_values:
            self.validate_threshold(record_values["threshold"])

        if "ingredients" in record_values:
            self.validate_ingredients(record_values["ingredients"])

        if "required_proficiencies" in record_values:
            self.validate_required_proficiencies(
                record_values["required_proficiencies"]
            )

    def validate_threshold(self, threshold):
        if threshold is None:
            return

        if isinstance(threshold, bool) or not isinstance(threshold, int):
            raise TypeError("Threshold must be a whole number")

        if not 1 <= threshold <= 100:
            raise ValueError("Threshold must be between 1 and 100")

    def validate_ingredients(self, ingredients):
        if not isinstance(ingredients, list):
            raise TypeError("Ingredients must be a list")

        for ingredient in ingredients:
            if not isinstance(ingredient, dict):
                raise TypeError("Every ingredient must be structured")

            ingredient_name = ingredient.get("name", "")

            if not isinstance(ingredient_name, str):
                raise TypeError("Every ingredient name must be text")

            if not ingredient_name.strip():
                raise ValueError("Every ingredient must have a name")

            ingredient_type = ingredient.get("type", "General Item")

            if not isinstance(ingredient_type, str):
                raise TypeError("Every ingredient type must be text")

            if ingredient_type not in INGREDIENT_TYPES:
                raise ValueError(
                    f"Unknown ingredient type: {ingredient_type}"
                )

            quantity = ingredient.get("quantity", 1)

            if isinstance(quantity, bool) or not isinstance(quantity, int):
                raise TypeError("Ingredient quantity must be a whole number")

            if quantity < 1:
                raise ValueError("Ingredient quantity must be at least 1")

    def validate_required_proficiencies(self, proficiencies):
        if not isinstance(proficiencies, list):
            raise TypeError("Required Proficiencies must be a list")

        normalized_names = set()

        for proficiency in proficiencies:
            if not isinstance(proficiency, str):
                raise TypeError("Every required proficiency must be text")

            proficiency_name = proficiency.strip()

            if not proficiency_name:
                raise ValueError(
                    "Every required proficiency must have a name"
                )

            normalized_name = " ".join(proficiency_name.split()).casefold()

            if normalized_name in normalized_names:
                raise ValueError(
                    f"Duplicate required proficiency: {proficiency_name}"
                )

            normalized_names.add(normalized_name)

    def normalize_ingredients(self, ingredients):
        if not isinstance(ingredients, list):
            return ingredients

        normalized_ingredients = []

        for ingredient in ingredients:
            if not isinstance(ingredient, dict):
                normalized_ingredients.append(ingredient)
                continue

            normalized_ingredient = dict(ingredient)
            normalized_ingredient["type"] = str(
                normalized_ingredient.get("type", "General Item")
            ).strip() or "General Item"
            normalized_ingredient.setdefault("quantity", 1)
            normalized_ingredients.append(normalized_ingredient)

        return normalized_ingredients

    def normalize_required_proficiencies(self, proficiencies):
        if not isinstance(proficiencies, list):
            return proficiencies

        return [str(proficiency).strip() for proficiency in proficiencies]

    def record_sort_key(self, record):
        return (
            record.get("name", "").casefold(),
            record.get("last_updated", ""),
            record.get("record_id", ""),
        )
