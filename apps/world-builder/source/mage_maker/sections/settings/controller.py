import uuid
from copy import deepcopy

from mage_maker.sections.development.models import (
    DEVELOPMENT_ASSIGNMENT_SETTING_KEY,
    normalize_development_assignment_policy,
)
from mage_maker.sections.settings.mage_groups import (
    DEFAULT_MAGE_GROUP_ID,
    MAGE_GROUPS_SETTING_KEY,
    default_mage_group_id,
    next_mage_group_color,
    normalize_mage_group_color,
    normalize_mage_group_name,
    normalize_mage_groups,
)
from mage_maker.sections.settings.simulation import (
    DATABASE_DATE_SETTING_KEY,
    MORTALITY_TABLE_SETTING_KEY,
    normalize_database_date,
    normalize_mortality_probability,
    normalize_mortality_table,
)


PEOPLE_PERIOD_FILTER_SETTING_KEY = "people_period_filter"
PEOPLE_GENERATION_FILTER_SETTING_KEY = "people_generation_filter"
PEOPLE_GENERATION_OVERRIDES_SETTING_KEY = (
    "people_generation_overrides"
)
PEOPLE_GENERATION_ALL_SCOPE_KEY = "__all__"


class ApplicationSettingsController:
    def __init__(self, database):
        self.database = database

    def application_settings(self):
        existing_settings = self.database.data.get(
            "_application_settings",
            {},
        )
        return (
            dict(existing_settings)
            if isinstance(existing_settings, dict)
            else {}
        )

    def development_assignment_policy(self):
        settings = self.application_settings()
        return normalize_development_assignment_policy(
            settings.get(DEVELOPMENT_ASSIGNMENT_SETTING_KEY)
        )

    def people_period_filter(self):
        settings = self.application_settings()
        return str(
            settings.get(PEOPLE_PERIOD_FILTER_SETTING_KEY, "") or ""
        ).strip()

    def set_people_period_filter(self, period_name):
        normalized_period_name = str(period_name or "").strip()
        settings = self.application_settings()

        if (
            str(
                settings.get(
                    PEOPLE_PERIOD_FILTER_SETTING_KEY,
                    "",
                )
                or ""
            ).strip()
            == normalized_period_name
        ):
            return False

        settings[PEOPLE_PERIOD_FILTER_SETTING_KEY] = (
            normalized_period_name
        )
        self.database.data["_application_settings"] = settings
        self.database.dirty = True
        return True

    def people_generation_filter(self):
        settings = self.application_settings()
        return str(
            settings.get(
                PEOPLE_GENERATION_FILTER_SETTING_KEY,
                "",
            )
            or ""
        ).strip()

    def set_people_generation_filter(self, generation_label):
        normalized_generation_label = str(
            generation_label or ""
        ).strip()
        settings = self.application_settings()

        if (
            str(
                settings.get(
                    PEOPLE_GENERATION_FILTER_SETTING_KEY,
                    "",
                )
                or ""
            ).strip()
            == normalized_generation_label
        ):
            return False

        settings[PEOPLE_GENERATION_FILTER_SETTING_KEY] = (
            normalized_generation_label
        )
        self.database.data["_application_settings"] = settings
        self.database.dirty = True
        return True

    def people_generation_overrides(self, period_name=""):
        normalized_period_name = str(period_name or "").strip()
        scope_key = (
            normalized_period_name
            if normalized_period_name
            else PEOPLE_GENERATION_ALL_SCOPE_KEY
        )
        settings = self.application_settings()
        overrides_by_scope = settings.get(
            PEOPLE_GENERATION_OVERRIDES_SETTING_KEY,
            {},
        )

        if not isinstance(overrides_by_scope, dict):
            return {}

        overrides = overrides_by_scope.get(scope_key, {})

        if not isinstance(overrides, dict):
            return {}

        return {
            str(record_id or "").strip(): str(
                target_record_id or ""
            ).strip()
            for record_id, target_record_id in overrides.items()
            if str(record_id or "").strip()
            and str(target_record_id or "").strip()
            and str(record_id or "").strip()
            != str(target_record_id or "").strip()
        }

    def set_people_generation_override(
        self,
        period_name,
        record_id,
        target_record_id,
    ):
        normalized_period_name = str(period_name or "").strip()
        normalized_record_id = str(record_id or "").strip()
        normalized_target_record_id = str(
            target_record_id or ""
        ).strip()

        if not normalized_record_id:
            return False

        if normalized_record_id == normalized_target_record_id:
            return False

        scope_key = (
            normalized_period_name
            if normalized_period_name
            else PEOPLE_GENERATION_ALL_SCOPE_KEY
        )
        settings = self.application_settings()
        stored_overrides = settings.get(
            PEOPLE_GENERATION_OVERRIDES_SETTING_KEY,
            {},
        )
        overrides_by_scope = (
            deepcopy(stored_overrides)
            if isinstance(stored_overrides, dict)
            else {}
        )
        stored_scope_overrides = overrides_by_scope.get(scope_key, {})
        scope_overrides = (
            dict(stored_scope_overrides)
            if isinstance(stored_scope_overrides, dict)
            else {}
        )

        if normalized_target_record_id:
            if (
                str(scope_overrides.get(normalized_record_id, "") or "")
                == normalized_target_record_id
            ):
                return False

            scope_overrides[normalized_record_id] = (
                normalized_target_record_id
            )
        else:
            if normalized_record_id not in scope_overrides:
                return False

            scope_overrides.pop(normalized_record_id, None)

        if scope_overrides:
            overrides_by_scope[scope_key] = scope_overrides
        else:
            overrides_by_scope.pop(scope_key, None)

        settings[PEOPLE_GENERATION_OVERRIDES_SETTING_KEY] = (
            overrides_by_scope
        )
        self.database.data["_application_settings"] = settings
        self.database.dirty = True
        return True

    def set_development_assignment_policy(self, policy):
        normalized_policy = normalize_development_assignment_policy(
            policy
        )
        settings = self.application_settings()

        if (
            settings.get(DEVELOPMENT_ASSIGNMENT_SETTING_KEY)
            == normalized_policy
        ):
            return False

        settings[DEVELOPMENT_ASSIGNMENT_SETTING_KEY] = normalized_policy
        self.database.data["_application_settings"] = settings
        self.database.dirty = True
        return True

    def database_date(self):
        settings = self.application_settings()
        return normalize_database_date(
            settings.get(DATABASE_DATE_SETTING_KEY)
        )

    def set_database_date(self, year, month, day):
        normalized_date = normalize_database_date(
            {
                "year": year,
                "month": month,
                "day": day,
            }
        )
        settings = self.application_settings()

        if settings.get(DATABASE_DATE_SETTING_KEY) == normalized_date:
            return False

        settings[DATABASE_DATE_SETTING_KEY] = normalized_date
        self.database.data["_application_settings"] = settings
        self.database.dirty = True
        return True

    def mortality_table(self):
        settings = self.application_settings()
        return normalize_mortality_table(
            settings.get(MORTALITY_TABLE_SETTING_KEY)
        )

    def set_mortality_probability(self, age_label, probability):
        normalized_label = str(age_label or "").strip()
        table = self.mortality_table()

        if normalized_label not in table:
            raise ValueError("Choose a valid mortality-table age.")

        normalized_probability = normalize_mortality_probability(
            probability
        )

        if table[normalized_label] == normalized_probability:
            return False

        table[normalized_label] = normalized_probability
        settings = self.application_settings()
        settings[MORTALITY_TABLE_SETTING_KEY] = table
        self.database.data["_application_settings"] = settings
        self.database.dirty = True
        return True

    def mage_groups(self):
        settings = self.application_settings()
        return normalize_mage_groups(
            settings.get(MAGE_GROUPS_SETTING_KEY)
        )

    def default_mage_group_id(self):
        return default_mage_group_id(self.mage_groups())

    def next_mage_group_color(self):
        return next_mage_group_color(self.mage_groups())

    def mage_group_usage_counts(self):
        counts = {
            group["group_id"]: 0
            for group in self.mage_groups()
        }

        for person in self.database.list_people():
            group_id = str(
                person.get("mage_group_id", "") or ""
            ).strip()

            if group_id in counts:
                counts[group_id] += 1

        return counts

    def create_mage_group(self, name, color):
        groups = self.mage_groups()
        groups.append(
            {
                "group_id": str(uuid.uuid4()),
                "name": normalize_mage_group_name(name),
                "color": normalize_mage_group_color(color),
            }
        )
        normalized_groups = normalize_mage_groups(groups)
        created_group = deepcopy(normalized_groups[-1])
        self.store_mage_groups(normalized_groups)
        return created_group

    def update_mage_group(self, group_id, name, color):
        normalized_group_id = str(group_id or "").strip()
        groups = self.mage_groups()
        updated_group = None

        for group in groups:
            if group["group_id"] != normalized_group_id:
                continue

            group["name"] = normalize_mage_group_name(name)
            group["color"] = normalize_mage_group_color(color)
            updated_group = deepcopy(group)
            break

        if updated_group is None:
            raise KeyError("The selected mage group no longer exists.")

        normalized_groups = normalize_mage_groups(groups)
        self.store_mage_groups(normalized_groups)

        for group in normalized_groups:
            if group["group_id"] == normalized_group_id:
                return deepcopy(group)

        raise KeyError("The selected mage group no longer exists.")

    def delete_mage_group(self, group_id):
        normalized_group_id = str(group_id or "").strip()

        if normalized_group_id == DEFAULT_MAGE_GROUP_ID:
            raise ValueError(
                "The default mage group cannot be removed. "
                "You can rename it or change its color."
            )

        groups = self.mage_groups()
        retained_groups = [
            group
            for group in groups
            if group["group_id"] != normalized_group_id
        ]

        if len(retained_groups) == len(groups):
            raise KeyError("The selected mage group no longer exists.")

        normalized_groups = normalize_mage_groups(retained_groups)
        fallback_group_id = default_mage_group_id(normalized_groups)
        self.store_mage_groups(normalized_groups)
        reassigned_count = 0

        for person in self.database.list_people():
            if person.get("mage_group_id") != normalized_group_id:
                continue

            self.database.update_person(
                person["record_id"],
                {"mage_group_id": fallback_group_id},
            )
            reassigned_count += 1

        return reassigned_count

    def store_mage_groups(self, groups):
        normalized_groups = normalize_mage_groups(groups)
        settings = self.application_settings()

        if settings.get(MAGE_GROUPS_SETTING_KEY) == normalized_groups:
            return False

        settings[MAGE_GROUPS_SETTING_KEY] = normalized_groups
        self.database.data["_application_settings"] = settings
        self.database.dirty = True
        return True
