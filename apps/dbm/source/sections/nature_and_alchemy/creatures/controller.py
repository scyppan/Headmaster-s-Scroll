from database.name_links import ensure_unique_record_name
from sections.nature_and_alchemy.creatures.constants import (
    CLASSIFICATIONS,
    CREATURE_TYPES,
    INSTINCT_INTENTIONS,
    INSTINCT_STANCES,
    PROFICIENCY_DEFAULTS,
    UNDEFINED,
    YES_NO_ONLY,
    YES_NO_VALUES,
)
from shared.wounds import (
    WOUND_AMOUNT_LIMITS,
    WOUND_SEVERITIES,
    WOUND_TYPES,
)


class CreatureController:
    collection_name = "creatures"

    def __init__(self, database):
        self.database = database

    def list_records(self):
        records = self.database.get_collection(self.collection_name)
        records.sort(key=self.record_sort_key)

        return records

    def get_record(self, record_id):
        return self.database.read(self.collection_name, record_id)

    def create_record(self, record_values):
        self.validate_record_values(record_values)
        ensure_unique_record_name(
            self.database.get_collection(self.collection_name),
            record_values.get("name", ""),
            record_label="creature",
        )
        created_record = self.database.create(
            self.collection_name,
            record_values,
        )
        self.database.save()

        return created_record

    def update_record(self, record_id, record_values):
        self.validate_record_values(record_values)

        if "name" in record_values:
            ensure_unique_record_name(
                self.database.get_collection(self.collection_name),
                record_values["name"],
                record_id=record_id,
                record_label="creature",
            )

        updated_record = self.database.update(
            self.collection_name,
            record_id,
            record_values,
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
        creature_type = record_values.get("creature_type", UNDEFINED)
        classification = record_values.get("classification", UNDEFINED)

        if creature_type not in CREATURE_TYPES:
            raise ValueError(f"Unknown creature type: {creature_type}")

        if classification not in CLASSIFICATIONS:
            raise ValueError(f"Unknown classification: {classification}")

        magical_value = record_values.get("magical", UNDEFINED)

        if magical_value not in YES_NO_VALUES:
            raise ValueError("Magical must be Yes, No, or {undefined}")

        for field_name in (
            "sentient",
            "has_human_social_skills",
            "can_be_lured",
            "can_be_tamed",
            "can_bond",
        ):
            field_value = record_values.get(field_name, "No")

            if field_value not in YES_NO_ONLY:
                raise ValueError(
                    f"{field_name.replace('_', ' ').title()} must be "
                    "Yes or No"
                )

        self.validate_range(
            record_values.get("wound_cap", {}),
            "Wound Cap",
            1,
            30,
        )
        self.validate_range(
            record_values.get("size", {}),
            "Size",
            1,
            5,
        )
        self.validate_range(
            record_values.get("magical_resistance", {}),
            "Magical Resistance",
            1,
            50,
        )
        self.validate_range(
            record_values.get("intelligence", {}),
            "Intelligence",
            1,
            50,
        )
        self.validate_range(
            record_values.get("social_skill", {}),
            "Human Social Skill",
            1,
            50,
        )

        if record_values.get("has_human_social_skills") == "No":
            social_skill = record_values.get("social_skill", {})

            if any(
                social_skill.get(field_name) is not None
                for field_name in ("low", "high")
            ):
                raise ValueError(
                    "Human Social Skill must be empty when the creature "
                    "does not have human social skills"
                )

        movement = record_values.get("movement", {})

        if not isinstance(movement, dict):
            raise TypeError("Movement must be a structured object")

        for movement_name in ("land", "water", "air"):
            movement_value = movement.get(movement_name, {})

            if not isinstance(movement_value, dict):
                raise TypeError(
                    f"{movement_name.title()} movement must be structured"
                )

            enabled_value = movement_value.get("enabled", "No")

            if enabled_value not in YES_NO_ONLY:
                raise ValueError(
                    f"{movement_name.title()} movement must be Yes or No"
                )

            if enabled_value == "No" and any(
                movement_value.get(field_name) is not None
                for field_name in ("low", "high")
            ):
                raise ValueError(
                    f"{movement_name.title()} speed must be empty when "
                    "movement is No"
                )

            self.validate_range(
                movement_value,
                f"{movement_name.title()} Speed",
                1,
                50,
            )

        instinct = record_values.get("in_situ_instinct", {})

        if not isinstance(instinct, dict):
            raise TypeError("In-situ instinct must be structured")

        self.validate_instinct_choices(
            instinct.get("stance", []),
            "stance",
            INSTINCT_STANCES,
        )
        self.validate_instinct_choices(
            instinct.get("intention", []),
            "intention",
            INSTINCT_INTENTIONS,
        )

        attacks = record_values.get("attacks", [])
        abilities = record_values.get("abilities", [])
        parts = record_values.get("parts", [])
        tags = record_values.get("tags", [])
        self.validate_actions(attacks, "attack")
        self.validate_actions(abilities, "ability")
        self.validate_parts(parts)
        self.validate_tags(tags)

    def validate_instinct_choices(self, choices, label, allowed_choices):
        if not isinstance(choices, list):
            raise TypeError(f"Instinct {label} choices must be a list")

        seen_choices = set()

        for choice in choices:
            if choice not in allowed_choices:
                raise ValueError(f"Unknown instinct {label}: {choice}")

            if choice in seen_choices:
                raise ValueError(f"Duplicate instinct {label}: {choice}")

            seen_choices.add(choice)

    def validate_range(self, range_value, label, minimum, maximum):
        if not isinstance(range_value, dict):
            raise TypeError(f"{label} must be a structured range")

        low_value = range_value.get("low")
        high_value = range_value.get("high")

        for value_name, value in (("Low", low_value), ("High", high_value)):
            if value is None:
                continue

            if not isinstance(value, int):
                raise TypeError(f"{label} {value_name} must be a whole number")

            if not minimum <= value <= maximum:
                raise ValueError(
                    f"{label} {value_name} must be between "
                    f"{minimum} and {maximum}"
                )

        if (
            low_value is not None
            and high_value is not None
            and low_value > high_value
        ):
            raise ValueError(f"{label} Low cannot be greater than High")

    def validate_actions(self, actions, action_label):
        if not isinstance(actions, list):
            raise TypeError(f"{action_label.title()}s must be a list")

        normalized_names = set()

        for action in actions:
            if not isinstance(action, dict):
                raise TypeError(
                    f"Every {action_label} must be structured"
                )

            action_name = str(action.get("name", "")).strip()

            if not action_name:
                raise ValueError(
                    f"Every {action_label} must have a name"
                )

            normalized_name = " ".join(action_name.split()).casefold()

            if normalized_name in normalized_names:
                raise ValueError(
                    f"Duplicate {action_label}: {action_name}"
                )

            normalized_names.add(normalized_name)
            self.validate_range(
                action.get("roll", {}),
                f"{action_name} Roll",
                1,
                50,
            )
            self.validate_damage_entries(
                action.get("immediate_damage", []),
                f"{action_name} Immediate Damage",
            )
            self.validate_damage_entries(
                action.get("damage_over_time", []),
                f"{action_name} Damage over Time",
            )

    def validate_damage_entries(self, damage_entries, label):
        if not isinstance(damage_entries, list):
            raise TypeError(f"{label} must be a list")

        for damage_entry in damage_entries:
            if not isinstance(damage_entry, dict):
                raise TypeError(f"Every {label} entry must be structured")

            wound_type = damage_entry.get("type", UNDEFINED)
            severity = damage_entry.get("severity", UNDEFINED)
            amount = damage_entry.get("amount")

            if wound_type != UNDEFINED and wound_type not in WOUND_TYPES:
                raise ValueError(f"Unknown wound type: {wound_type}")

            if severity != UNDEFINED and severity not in WOUND_SEVERITIES:
                raise ValueError(f"Unknown wound severity: {severity}")

            if not isinstance(amount, int):
                raise TypeError(f"{label} amount must be a whole number")

            maximum = WOUND_AMOUNT_LIMITS.get(severity, 50)

            if not 1 <= amount <= maximum:
                raise ValueError(
                    f"{label} amount must be between 1 and {maximum} "
                    f"for {severity} wounds"
                )

    def validate_parts(self, parts):
        if not isinstance(parts, list):
            raise TypeError("Creature parts must be a list")

        proficiency_names = {
            str(record.get("name", "")).strip()
            for record in self.database.get_collection("proficiencies")
            if str(record.get("name", "")).strip()
        }
        allowed_proficiencies = {
            *PROFICIENCY_DEFAULTS,
            *proficiency_names,
        }
        normalized_part_names = set()

        for part in parts:
            if not isinstance(part, dict):
                raise TypeError("Every creature part must be structured")

            part_name = str(part.get("name", "")).strip()

            if not part_name:
                raise ValueError("Every creature part must have a name")

            normalized_name = " ".join(part_name.split()).casefold()

            if normalized_name in normalized_part_names:
                raise ValueError(f"Duplicate creature part: {part_name}")

            normalized_part_names.add(normalized_name)
            required_proficiency = part.get("required_proficiency", "No")

            if required_proficiency not in allowed_proficiencies:
                raise ValueError(
                    f"Unknown proficiency for {part_name}: "
                    f"{required_proficiency}"
                )

            for field_name, field_label in (
                ("description", "Description"),
                ("raw_effects", "Raw Effects"),
                ("effect_in_potions", "Effect in Potions"),
            ):
                field_value = part.get(field_name, "")

                if not isinstance(field_value, str):
                    raise TypeError(
                        f"{part_name} {field_label} must be text"
                    )

    def validate_tags(self, tags):
        if not isinstance(tags, list):
            raise TypeError("Tags must be a list")

        normalized_tags = set()

        for tag in tags:
            tag_text = str(tag).strip()

            if not tag_text:
                raise ValueError("Tags cannot be blank")

            normalized_tag = " ".join(tag_text.split()).casefold()

            if normalized_tag in normalized_tags:
                raise ValueError(f"Duplicate tag: {tag_text}")

            normalized_tags.add(normalized_tag)

    def record_sort_key(self, record):
        return (
            record.get("name", "").casefold(),
            record.get("last_updated", ""),
            record.get("record_id", ""),
        )
