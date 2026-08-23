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
from mage_maker.sections.events.types import canonical_event_type


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
    def __init__(self, people, current_person=None, foster_events=()):
        # Family-tree providers already return compact, disposable summaries.
        # Shallow copies protect the provider without recursively copying every
        # nested field for thousands of people.
        self.people_by_id = {
            str(person.get("record_id")): dict(person)
            for person in people
            if isinstance(person, dict) and person.get("record_id")
        }

        if isinstance(current_person, dict) and current_person.get("record_id"):
            current_id = str(current_person["record_id"])
            merged_person = self.people_by_id.get(current_id, {})
            merged_person.update(deepcopy(current_person))
            self.people_by_id[current_id] = merged_person

        self.children_by_parent = {}
        self.foster_children_by_parent = {}
        self.foster_parents_by_child = {}
        self._assigned_parent_ids = {"mother": [], "father": []}
        self._mate_ids_by_person = {
            record_id: [] for record_id in self.people_by_id
        }

        def remember_mate(first_id, second_id):
            first_id = str(first_id or "").strip()
            second_id = str(second_id or "").strip()
            if (
                not first_id
                or not second_id
                or first_id == second_id
                or first_id not in self.people_by_id
                or second_id not in self.people_by_id
            ):
                return
            mates = self._mate_ids_by_person.setdefault(first_id, [])
            if second_id not in mates:
                mates.append(second_id)

        for person_id, person in self.people_by_id.items():
            for mate_id in person.get("mate_ids", []) or []:
                remember_mate(person_id, mate_id)
                remember_mate(mate_id, person_id)

        for person in self.people_by_id.values():
            for field_name in ("biological_mother_id", "biological_father_id"):
                parent_id = str(person.get(field_name, "") or "").strip()

                if parent_id:
                    self.children_by_parent.setdefault(parent_id, []).append(
                        person["record_id"]
                    )
                    role = (
                        "mother"
                        if field_name == "biological_mother_id"
                        else "father"
                    )
                    if parent_id not in self._assigned_parent_ids[role]:
                        self._assigned_parent_ids[role].append(parent_id)

            parent_ids = self.unique_ids(
                (
                    person.get("biological_mother_id"),
                    person.get("biological_father_id"),
                )
            )
            if len(parent_ids) == 2:
                remember_mate(parent_ids[0], parent_ids[1])
                remember_mate(parent_ids[1], parent_ids[0])

        for event in foster_events or ():
            if (
                not isinstance(event, dict)
                or canonical_event_type(event.get("event_type"))
                != "foster_child"
            ):
                continue

            parent_ids = self.unique_ids(
                event.get("foster_parent_person_ids", [])
            )
            child_ids = self.unique_ids(
                event.get("foster_child_person_ids", [])
            )

            for parent_id in parent_ids:
                if parent_id not in self.people_by_id:
                    continue

                for child_id in child_ids:
                    if (
                        child_id not in self.people_by_id
                        or child_id == parent_id
                    ):
                        continue

                    children = self.foster_children_by_parent.setdefault(
                        parent_id,
                        [],
                    )
                    parents = self.foster_parents_by_child.setdefault(
                        child_id,
                        [],
                    )

                    if child_id not in children:
                        children.append(child_id)

                    if parent_id not in parents:
                        parents.append(parent_id)

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

    def foster_children_of(self, record_id):
        return self.unique_ids(
            self.foster_children_by_parent.get(str(record_id or ""), [])
        )

    def foster_parents_of(self, record_id):
        return self.unique_ids(
            self.foster_parents_by_child.get(str(record_id or ""), [])
        )

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
        return list(
            self._mate_ids_by_person.get(str(record_id or ""), [])
        )

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

        return list(self._assigned_parent_ids[parent_role])

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
            self.people_by_id,
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

    def parent_couple_candidates(self, focus_id):
        """Return existing spouse pairs that can jointly parent ``focus_id``.

        Choosing a couple replaces both biological-parent fields at once, so
        the current parent links must not exclude either half of an otherwise
        valid pair. Keep the ancestry, age and fertility rules used by the
        individual parent pickers. Do not pre-filter a complete couple using
        the child's current blood status: assigning both parents at once is
        what determines the child's resulting blood status.
        """
        focus = self.person(focus_id)
        if focus is None:
            return []

        excluded_ids = {str(focus_id), *self.descendants_of(focus_id)}
        eligible_by_role = {"mother": {}, "father": {}}

        for parent_role in ("mother", "father"):
            required_birth_capability = parent_role == "mother"
            for person in self.people_by_id.values():
                record_id = str(person.get("record_id", "") or "").strip()
                if not record_id or record_id in excluded_ids:
                    continue
                if bool(person.get("does_not_have_children")):
                    continue
                if person_can_give_birth(person) != required_birth_capability:
                    continue
                if is_at_least_age(person, focus, 18) is False:
                    continue
                eligible_by_role[parent_role][record_id] = person

        couples = []
        seen_pairs = set()
        for mother_id, mother in eligible_by_role["mother"].items():
            for father_id in self.mates_of(mother_id):
                father = eligible_by_role["father"].get(father_id)
                pair_key = (mother_id, father_id)
                if father is None or pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                couples.append((mother, father))

        couples.sort(
            key=lambda pair: (
                person_name_sort_key(pair[0]),
                person_name_sort_key(pair[1]),
            )
        )
        return couples

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
        children.sort(key=person_birth_sort_key)
        return children

    def child_candidates(
        self,
        focus_id,
        other_parent_id="",
        minimum_age_gap=18,
        maximum_age_gap=41,
        ignore_age_limits=False,
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
        maximum_child_birth_year = self.maximum_child_birth_year(
            focus_id,
            other_parent_id,
            maximum_age_gap,
        )

        if (
            not ignore_age_limits
            and (
                minimum_child_birth_year is None
                or maximum_child_birth_year is None
            )
        ):
            return []

        if self.person(focus_id) is None:
            return []

        candidates = []

        for person in self.people_by_id.values():
            record_id = str(person.get("record_id", ""))

            if record_id in excluded_ids:
                continue

            if str(person.get("biological_mother_id", "") or "").strip():
                continue

            if str(person.get("biological_father_id", "") or "").strip():
                continue

            birth_year = self.integer_year(person.get("birth_year"))

            if not ignore_age_limits:
                if birth_year is None:
                    continue

                if birth_year < minimum_child_birth_year:
                    continue

                if birth_year > maximum_child_birth_year:
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

    def maximum_child_birth_year(
        self,
        focus_id,
        other_parent_id="",
        maximum_age_gap=41,
    ):
        """Return the latest default birth year for a selected parent pair.

        The chooser's ordinary family-planning window treats every selected
        parent as no older than ``maximum_age_gap`` when the child is born.
        An explicit all-ages search bypasses this limit.
        """
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

        return min(birth_years) + int(maximum_age_gap)

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
        seen = set()
        pending = list(self.children_of(record_id))

        while pending:
            descendant_id = pending.pop(0)

            if descendant_id in seen:
                continue

            seen.add(descendant_id)
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
        siblings = self.sort_ids_by_birth(self.siblings_of(focus_id))
        maternal_cousins = []
        paternal_cousins = []

        for relative_id in maternal_aunts_uncles:
            maternal_cousins.extend(self.children_of(relative_id))

        for relative_id in paternal_aunts_uncles:
            paternal_cousins.extend(self.children_of(relative_id))

        children = self.sort_ids_by_birth(self.children_of(focus_id))
        foster_children = [
            child_id
            for child_id in self.foster_children_of(focus_id)
            if child_id not in children
        ]
        foster_parents = [
            parent_id
            for parent_id in self.foster_parents_of(focus_id)
            if parent_id not in (mother_id, father_id)
        ]
        nieces_nephews = []
        grandchildren = []

        for sibling_id in siblings:
            nieces_nephews.extend(self.children_of(sibling_id))

        for child_id in children:
            grandchildren.extend(self.children_of(child_id))

        grandparents = self.sort_ids_by_birth(self.unique_ids(
            self.parents_of(mother_id) + self.parents_of(father_id)
        ))
        parent_generation = self.unique_ids(
            maternal_aunts_uncles
            + [mother_id, father_id]
            + paternal_aunts_uncles
            + foster_parents
        )
        focus_generation = self.sort_ids_by_birth(self.unique_ids(
            maternal_cousins + siblings + [focus_id] + paternal_cousins
        ))
        child_generation = self.sort_ids_by_birth(self.unique_ids(
            nieces_nephews + children + foster_children
        ))
        grandchild_generation = self.sort_ids_by_birth(
            self.unique_ids(grandchildren)
        )

        return [
            self.nodes_for(grandparents, "Grandparent"),
            self.nodes_for_parent_generation(
                parent_generation,
                mother_id,
                father_id,
                maternal_aunts_uncles,
                paternal_aunts_uncles,
                foster_parents,
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
                foster_children,
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
        foster_parents=(),
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
            elif record_id in foster_parents:
                relation = "Foster parent"
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

    def nodes_for_child_generation(
        self,
        record_ids,
        children,
        nieces_nephews,
        foster_children=(),
    ):
        nodes = []

        for record_id in record_ids:
            if record_id in children:
                relation = "Child"
            elif record_id in foster_children:
                relation = "Foster child"
            else:
                relation = "Nibbling"
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

    def sort_ids_by_birth(self, record_ids):
        return sorted(
            self.unique_ids(record_ids),
            key=lambda record_id: person_birth_sort_key(
                self.person(record_id) or {}
            ),
        )


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
        return 10000, 13, 32, person_name_sort_key(person)

    try:
        birth_month = int(person.get("birth_month"))
    except (TypeError, ValueError):
        birth_month = 0

    try:
        birth_day = int(person.get("birth_day"))
    except (TypeError, ValueError):
        birth_day = 0

    return (
        birth_year,
        birth_month,
        birth_day,
        person_name_sort_key(person),
    )


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
