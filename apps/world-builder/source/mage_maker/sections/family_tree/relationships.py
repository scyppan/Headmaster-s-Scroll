from copy import deepcopy

from mage_maker.core.dates import (
    format_date_parts,
    format_line_item_date,
    is_at_least_age,
)
from mage_maker.sections.development.initial_values import (
    allowed_parent_magic_states,
    person_magic_state,
)


def person_can_give_birth(person):
    if not isinstance(person, dict):
        return False

    value = person.get("can_give_birth", False)

    if isinstance(value, bool):
        return value

    return str(value or "").strip().casefold() in (
        "yes",
        "true",
        "1",
        "on",
        "checked",
    )


class FamilyRelationshipMap:
    def __init__(self, people, current_person=None):
        self.people_by_id = {
            str(person.get("record_id")): deepcopy(person)
            for person in people
            if isinstance(person, dict) and person.get("record_id")
        }

        if isinstance(current_person, dict) and current_person.get("record_id"):
            current_id = str(current_person["record_id"])
            merged_person = self.people_by_id.get(current_id, {})
            merged_person.update(deepcopy(current_person))
            self.people_by_id[current_id] = merged_person

        self.children_by_parent = {}

        for person in self.people_by_id.values():
            for field_name in ("biological_mother_id", "biological_father_id"):
                parent_id = str(person.get(field_name, "") or "").strip()

                if parent_id:
                    self.children_by_parent.setdefault(parent_id, []).append(
                        person["record_id"]
                    )

    def person(self, record_id):
        return self.people_by_id.get(str(record_id or ""))

    def parents_of(self, record_id):
        person = self.person(record_id)

        if person is None:
            return []

        return self.unique_ids(
            (
                person.get("biological_mother_id"),
                person.get("biological_father_id"),
            )
        )

    def children_of(self, record_id):
        return self.unique_ids(self.children_by_parent.get(str(record_id or ""), []))

    def siblings_of(self, record_id):
        sibling_ids = []

        for parent_id in self.parents_of(record_id):
            sibling_ids.extend(self.children_of(parent_id))

        return [
            sibling_id
            for sibling_id in self.unique_ids(sibling_ids)
            if sibling_id != record_id
        ]

    def sibling_relation(self, first_record_id, second_record_id):
        first_parent_ids = set(self.parents_of(first_record_id))
        second_parent_ids = set(self.parents_of(second_record_id))
        shared_parent_ids = first_parent_ids.intersection(second_parent_ids)

        if not shared_parent_ids:
            return ""

        first_other_parent_ids = first_parent_ids.difference(shared_parent_ids)
        second_other_parent_ids = second_parent_ids.difference(shared_parent_ids)

        if (
            len(shared_parent_ids) == 1
            and len(first_other_parent_ids) == 1
            and len(second_other_parent_ids) == 1
            and first_other_parent_ids != second_other_parent_ids
        ):
            return "1/2 Sibling"

        return "Sibling"

    def mates_of(self, record_id):
        person = self.person(record_id)

        if person is None:
            return []

        mate_ids = list(person.get("mate_ids", []) or [])

        for possible_mate in self.people_by_id.values():
            if record_id in (possible_mate.get("mate_ids", []) or []):
                mate_ids.append(possible_mate["record_id"])

        for child in self.people_by_id.values():
            parent_ids = self.unique_ids(
                (
                    child.get("biological_mother_id"),
                    child.get("biological_father_id"),
                )
            )

            if record_id in parent_ids:
                mate_ids.extend(
                    parent_id for parent_id in parent_ids if parent_id != record_id
                )

        return [
            mate_id
            for mate_id in self.unique_ids(mate_ids)
            if mate_id != record_id and self.person(mate_id) is not None
        ]

    def step_parent_mates_of(self, focus_id):
        parent_ids = self.parents_of(focus_id)
        parent_id_set = set(parent_ids)
        step_parent_mates = {}

        for parent_id in parent_ids:
            mate_ids = [
                mate_id
                for mate_id in self.mates_of(parent_id)
                if mate_id not in parent_id_set
            ]

            if mate_ids:
                step_parent_mates[parent_id] = mate_ids

        return step_parent_mates

    def assigned_parent_ids(self, parent_role):
        if parent_role not in ("mother", "father"):
            raise ValueError(
                "Parent role must be birthing parent or non-birthing parent."
            )

        field_name = f"biological_{parent_role}_id"
        return self.unique_ids(
            person.get(field_name)
            for person in self.people_by_id.values()
        )

    def parent_candidates(self, focus_id, parent_role, alternate_role=False):
        if parent_role not in ("mother", "father"):
            raise ValueError(
                "Parent role must be birthing parent or non-birthing parent."
            )

        focus = self.person(focus_id)

        if focus is None:
            return []

        required_birth_capability = parent_role == "mother"
        excluded_ids = {str(focus_id)}
        excluded_ids.update(self.descendants_of(focus_id))
        other_parent_role = "father" if parent_role == "mother" else "mother"
        other_parent_id = str(
            focus.get(f"biological_{other_parent_role}_id", "") or ""
        ).strip()

        if other_parent_id:
            excluded_ids.add(other_parent_id)

        if alternate_role:
            required_birth_capability = not required_birth_capability
            excluded_ids.update(self.assigned_parent_ids(other_parent_role))

        allowed_magic_states = allowed_parent_magic_states(
            focus,
            self.people_by_id.values(),
            parent_role,
        )
        candidates = []

        for person in self.people_by_id.values():
            record_id = str(person.get("record_id", ""))

            if record_id in excluded_ids:
                continue

            if bool(person.get("does_not_have_children")):
                continue

            if person_can_give_birth(person) != required_birth_capability:
                continue

            if person_magic_state(person) not in allowed_magic_states:
                continue

            if alternate_role and self.mates_of(record_id):
                continue

            if is_at_least_age(person, focus, 18) is False:
                continue

            candidates.append(person)

        candidates.sort(key=person_name_sort_key)
        return candidates

    def partner_candidates(
        self,
        focus_id,
        alternate_role=False,
        include_existing_mates=False,
        extra_excluded_ids=None,
    ):
        focus = self.person(focus_id)

        if focus is None:
            return []

        focus_can_give_birth = person_can_give_birth(focus)
        required_birth_capability = not focus_can_give_birth
        excluded_ids = {str(focus_id)}
        excluded_ids.update(self.ancestors_of(focus_id))
        excluded_ids.update(self.descendants_of(focus_id))
        excluded_ids.update(
            str(record_id or "") for record_id in (extra_excluded_ids or [])
        )

        if not include_existing_mates:
            excluded_ids.update(self.mates_of(focus_id))

        if alternate_role:
            required_birth_capability = focus_can_give_birth
            current_parent_role = "mother" if focus_can_give_birth else "father"
            excluded_ids.update(self.assigned_parent_ids(current_parent_role))

        candidates = []

        for person in self.people_by_id.values():
            record_id = str(person.get("record_id", ""))

            if record_id in excluded_ids:
                continue

            if bool(person.get("does_not_have_children")):
                continue

            if person_can_give_birth(person) != required_birth_capability:
                continue

            if alternate_role and self.mates_of(record_id):
                continue

            candidates.append(person)

        candidates.sort(key=person_name_sort_key)
        return candidates

    def children_for_parent_role(self, record_id, parent_role):
        if parent_role not in ("mother", "father"):
            raise ValueError(
                "Parent role must be birthing parent or non-birthing parent."
            )

        field_name = f"biological_{parent_role}_id"
        normalized_id = str(record_id or "")
        children = [
            person
            for person in self.people_by_id.values()
            if str(person.get(field_name, "") or "") == normalized_id
        ]
        children.sort(key=person_name_sort_key)
        return children

    def child_candidates(
        self,
        focus_id,
        other_parent_id="",
        minimum_age_gap=18,
        other_parent_status="unknown",
    ):
        focus_id = str(focus_id or "")
        other_parent_id = str(other_parent_id or "")
        parent_ids = self.unique_ids((focus_id, other_parent_id))
        excluded_ids = set(parent_ids)

        for parent_id in parent_ids:
            parent = self.person(parent_id)

            if parent is not None and bool(
                parent.get("does_not_have_children")
            ):
                return []

        for parent_id in parent_ids:
            excluded_ids.update(self.ancestors_of(parent_id))

        minimum_child_birth_year = self.minimum_child_birth_year(
            focus_id,
            other_parent_id,
            minimum_age_gap,
        )

        if minimum_child_birth_year is None:
            return []

        if self.person(focus_id) is None:
            return []

        candidates = []

        for person in self.people_by_id.values():
            record_id = str(person.get("record_id", ""))

            if record_id in excluded_ids:
                continue

            birth_year = self.integer_year(person.get("birth_year"))

            if birth_year is None or birth_year < minimum_child_birth_year:
                continue

            candidates.append(person)

        candidates.sort(key=person_birth_sort_key)
        return candidates

    def minimum_child_birth_year(
        self,
        focus_id,
        other_parent_id="",
        minimum_age_gap=18,
    ):
        parent_ids = self.unique_ids((focus_id, other_parent_id))

        if not parent_ids:
            return None

        birth_years = []

        for parent_id in parent_ids:
            person = self.person(parent_id)

            if person is None:
                return None

            birth_year = self.integer_year(person.get("birth_year"))

            if birth_year is None:
                return None

            birth_years.append(birth_year)

        return max(birth_years) + int(minimum_age_gap)

    def youngest_known_parent_birth_year(self, focus_id, other_parent_id=""):
        birth_years = []

        for parent_id in self.unique_ids((focus_id, other_parent_id)):
            person = self.person(parent_id)

            if person is None:
                continue

            birth_year = self.integer_year(person.get("birth_year"))

            if birth_year is not None:
                birth_years.append(birth_year)

        return max(birth_years) if birth_years else None

    def integer_year(self, value):
        if isinstance(value, bool) or value in (None, ""):
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def ancestors_of(self, record_id):
        ancestors = []
        pending = list(self.parents_of(record_id))

        while pending:
            ancestor_id = pending.pop(0)

            if ancestor_id in ancestors:
                continue

            ancestors.append(ancestor_id)
            pending.extend(self.parents_of(ancestor_id))

        return ancestors

    def descendants_of(self, record_id):
        descendants = []
        pending = list(self.children_of(record_id))

        while pending:
            descendant_id = pending.pop(0)

            if descendant_id in descendants:
                continue

            descendants.append(descendant_id)
            pending.extend(self.children_of(descendant_id))

        return descendants

    def build_generations(self, focus_id):
        focus = self.person(focus_id)

        if focus is None:
            return [[], [], [], [], []]

        mother_id = str(focus.get("biological_mother_id", "") or "")
        father_id = str(focus.get("biological_father_id", "") or "")
        maternal_aunts_uncles = self.siblings_of(mother_id)
        paternal_aunts_uncles = self.siblings_of(father_id)
        siblings = self.siblings_of(focus_id)
        maternal_cousins = []
        paternal_cousins = []

        for relative_id in maternal_aunts_uncles:
            maternal_cousins.extend(self.children_of(relative_id))

        for relative_id in paternal_aunts_uncles:
            paternal_cousins.extend(self.children_of(relative_id))

        children = self.children_of(focus_id)
        nieces_nephews = []
        grandchildren = []

        for sibling_id in siblings:
            nieces_nephews.extend(self.children_of(sibling_id))

        for child_id in children:
            grandchildren.extend(self.children_of(child_id))

        grandparents = self.unique_ids(
            self.parents_of(mother_id) + self.parents_of(father_id)
        )
        parent_generation = self.unique_ids(
            maternal_aunts_uncles
            + [mother_id, father_id]
            + paternal_aunts_uncles
        )
        focus_generation = self.unique_ids(
            maternal_cousins + siblings + [focus_id] + paternal_cousins
        )
        child_generation = self.unique_ids(nieces_nephews + children)
        grandchild_generation = self.unique_ids(grandchildren)

        return [
            self.nodes_for(grandparents, "Grandparent"),
            self.nodes_for_parent_generation(
                parent_generation,
                mother_id,
                father_id,
                maternal_aunts_uncles,
                paternal_aunts_uncles,
            ),
            self.nodes_for_focus_generation(
                focus_generation,
                focus_id,
                siblings,
                maternal_cousins,
                paternal_cousins,
            ),
            self.nodes_for_child_generation(
                child_generation,
                children,
                nieces_nephews,
            ),
            self.nodes_for(grandchild_generation, "Grandchild"),
        ]

    def nodes_for(self, record_ids, relation):
        return [
            {"person": self.person(record_id), "relation": relation}
            for record_id in record_ids
            if self.person(record_id) is not None
        ]

    def nodes_for_parent_generation(
        self,
        record_ids,
        mother_id,
        father_id,
        maternal_aunts_uncles,
        paternal_aunts_uncles,
    ):
        nodes = []

        for record_id in record_ids:
            if record_id == mother_id:
                relation = "Birthing parent"
            elif record_id == father_id:
                relation = "Non-birthing parent"
            elif record_id in maternal_aunts_uncles:
                relation = "Birthing parent's pibbling"
            elif record_id in paternal_aunts_uncles:
                relation = "Non-birthing parent's pibbling"
            else:
                relation = "Pibbling"

            nodes.append({"person": self.person(record_id), "relation": relation})

        return nodes

    def nodes_for_focus_generation(
        self,
        record_ids,
        focus_id,
        siblings,
        maternal_cousins,
        paternal_cousins,
    ):
        nodes = []

        for record_id in record_ids:
            if record_id == focus_id:
                relation = "Selected person"
            elif record_id in siblings:
                relation = self.sibling_relation(focus_id, record_id)
            elif record_id in maternal_cousins:
                relation = "Birthing parent's cousin"
            elif record_id in paternal_cousins:
                relation = "Non-birthing parent's cousin"
            else:
                relation = "Cousin"

            nodes.append({"person": self.person(record_id), "relation": relation})

        return nodes

    def nodes_for_child_generation(self, record_ids, children, nieces_nephews):
        nodes = []

        for record_id in record_ids:
            relation = "Child" if record_id in children else "Nibbling"
            nodes.append({"person": self.person(record_id), "relation": relation})

        return nodes

    def visible_parent_child_edges(self, visible_ids):
        edges = []
        visible = set(visible_ids)

        for child_id in visible:
            for parent_id in self.parents_of(child_id):
                if parent_id in visible:
                    edges.append((parent_id, child_id))

        return edges

    def unique_ids(self, record_ids):
        unique = []
        seen = set()

        for record_id in record_ids:
            normalized_id = str(record_id or "").strip()

            if not normalized_id or normalized_id in seen:
                continue

            seen.add(normalized_id)
            unique.append(normalized_id)

        return unique


def format_person_date(person):
    if not isinstance(person, dict):
        return "nd."

    year = person.get("birth_year")
    month = person.get("birth_month")
    day = person.get("birth_day")

    if year in (None, ""):
        return "nd."

    return format_line_item_date(
        format_date_parts(year, month, day)
    )


def person_name_sort_key(person):
    return str(person.get("displayed_name", "")).casefold()


def person_birth_sort_key(person):
    try:
        birth_year = int(person.get("birth_year"))
    except (TypeError, ValueError):
        birth_year = 10000

    return birth_year, person_name_sort_key(person)


def maiden_name_for(person):
    if not isinstance(person, dict):
        return ""

    name_details = person.get("name_details", {})
    entries = name_details.get("entries", []) if isinstance(name_details, dict) else []

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        if str(entry.get("name_type", "")).strip().casefold() == "maiden name":
            return str(entry.get("name_entry", "") or "").strip()

    return ""
