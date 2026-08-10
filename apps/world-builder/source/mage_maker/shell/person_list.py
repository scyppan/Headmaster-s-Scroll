import tkinter as tk
from datetime import date
from functools import partial

from mage_maker.sections.development.characteristics import (
    initial_values_are_complete,
)
from mage_maker.sections.settings.mage_groups import (
    mage_group_definition,
    normalize_mage_groups,
)
from mage_maker.ui.theme import (
    BORDER_SOFT,
    BUTTON_SOFT,
    FIELD_BACKGROUND,
    LIST_ALTERNATE,
    LIST_HOVER,
    LIST_SELECTED,
    LOCKED_BORDER,
    PRIMARY,
    PRIMARY_HOVER,
    SURFACE,
    TEXT_DARK,
    TEXT_LIGHT,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import RoundedEntry, RoundedSelect, SoftButton


FILTER_SHOW_ALL = "Show all"
AGE_FILTER_OPTIONS = (
    FILTER_SHOW_ALL,
    "0–10",
    "11–17",
    "18–29",
    "30–49",
    "50–69",
    "70+",
    "Unknown age",
)
AGE_FILTER_BOUNDS = {
    "0–10": (0, 10),
    "11–17": (11, 17),
    "18–29": (18, 29),
    "30–49": (30, 49),
    "50–69": (50, 69),
    "70+": (70, None),
}
SORT_BIRTH_YEAR = "Birth year"
SORT_BIRTH_YEAR_NEWEST = "Birth year (newest)"
SORT_NAME = "Name"
SORT_GROUP = "Group"
SORT_AGE = "Age"
SORT_OPTIONS = (
    SORT_BIRTH_YEAR,
    SORT_BIRTH_YEAR_NEWEST,
    SORT_NAME,
    SORT_GROUP,
    SORT_AGE,
)
GENERATION_MAX_SPAN_YEARS = 20
GENERATION_FILTER_PREFIX = "Generation "
AGE_FILTER_PREFIX = "The "
AGE_FILTER_SUFFIX = " Age"
AGE_ORDINAL_WORDS = (
    "First",
    "Second",
    "Third",
    "Fourth",
    "Fifth",
    "Sixth",
    "Seventh",
    "Eighth",
    "Ninth",
    "Tenth",
    "Eleventh",
    "Twelfth",
    "Thirteenth",
    "Fourteenth",
    "Fifteenth",
    "Sixteenth",
    "Seventeenth",
    "Eighteenth",
    "Nineteenth",
    "Twentieth",
)


def approximate_generation_map(people):
    people_by_id = {
        str(person.get("record_id", "") or "").strip(): person
        for person in people or []
        if isinstance(person, dict)
        and str(person.get("record_id", "") or "").strip()
    }
    generations = {}
    dated_people = []

    for record_id, person in people_by_id.items():
        value = person.get("birth_year")

        if isinstance(value, bool) or value in (None, ""):
            continue

        try:
            birth_year = int(value)
        except (TypeError, ValueError):
            continue

        birth_month = person.get("birth_month")
        birth_day = person.get("birth_day")

        try:
            birth_month = int(birth_month)
        except (TypeError, ValueError):
            birth_month = 13

        try:
            birth_day = int(birth_day)
        except (TypeError, ValueError):
            birth_day = 32

        dated_people.append(
            (
                birth_year,
                birth_month,
                birth_day,
                record_id,
                person,
            )
        )

    dated_people.sort()
    current_generation = 0
    oldest_birth_year_in_generation = None

    for birth_year, _, _, record_id, person in dated_people:
        parent_ids = {
            str(person.get(field_name, "") or "").strip()
            for field_name in (
                "biological_mother_id",
                "biological_father_id",
            )
            if str(person.get(field_name, "") or "").strip()
        }
        parent_in_last_generation = any(
            generations.get(parent_id) == current_generation
            for parent_id in parent_ids
        )
        exceeds_last_generation_span = bool(
            oldest_birth_year_in_generation is not None
            and birth_year - oldest_birth_year_in_generation
            > GENERATION_MAX_SPAN_YEARS
        )

        if (
            current_generation == 0
            or parent_in_last_generation
            or exceeds_last_generation_span
        ):
            current_generation += 1
            oldest_birth_year_in_generation = birth_year

        generations[record_id] = current_generation

    return generations


def person_generation_sort_key(person):
    values = []

    for field_name, fallback in (
        ("birth_year", 100000),
        ("birth_month", 13),
        ("birth_day", 32),
    ):
        value = person.get(field_name)

        try:
            values.append(int(value))
        except (TypeError, ValueError):
            values.append(fallback)

    values.append(
        str(person.get("displayed_name", "") or "").casefold()
    )
    values.append(str(person.get("record_id", "") or ""))
    return tuple(values)


def apply_generation_overrides(
    people,
    generation_by_id,
    generation_overrides,
):
    people_by_id = {
        str(person.get("record_id", "") or "").strip(): person
        for person in people or []
        if isinstance(person, dict)
        and str(person.get("record_id", "") or "").strip()
    }
    updated_generations = {}

    for record_id, generation_number in dict(
        generation_by_id or {}
    ).items():
        normalized_record_id = str(record_id or "").strip()

        if (
            normalized_record_id not in people_by_id
            or isinstance(generation_number, bool)
        ):
            continue

        try:
            normalized_generation_number = int(generation_number)
        except (TypeError, ValueError):
            continue

        if normalized_generation_number <= 0:
            continue

        updated_generations[normalized_record_id] = (
            normalized_generation_number
        )
    normalized_overrides = {
        str(record_id or "").strip(): str(
            target_record_id or ""
        ).strip()
        for record_id, target_record_id in dict(
            generation_overrides or {}
        ).items()
        if str(record_id or "").strip() in updated_generations
        and str(target_record_id or "").strip()
        in updated_generations
        and str(record_id or "").strip()
        != str(target_record_id or "").strip()
    }

    for _ in range(len(updated_generations)):
        changed = False

        for record_id, target_record_id in normalized_overrides.items():
            target_generation = updated_generations.get(
                target_record_id
            )

            if (
                target_generation is not None
                and updated_generations.get(record_id)
                != target_generation
            ):
                updated_generations[record_id] = target_generation
                changed = True

        if not changed:
            break

    group_sort_keys = {}

    for record_id, generation_number in updated_generations.items():
        person = people_by_id[record_id]
        person_sort_key = person_generation_sort_key(person)
        existing_sort_key = group_sort_keys.get(generation_number)

        if (
            existing_sort_key is None
            or person_sort_key < existing_sort_key
        ):
            group_sort_keys[generation_number] = person_sort_key

    ordered_generation_numbers = [
        generation_number
        for _, generation_number in sorted(
            (
                person_sort_key,
                generation_number,
            )
            for generation_number, person_sort_key
            in group_sort_keys.items()
        )
    ]
    renumbered_generations = {
        generation_number: index
        for index, generation_number in enumerate(
            ordered_generation_numbers,
            start=1,
        )
    }
    return {
        record_id: renumbered_generations[generation_number]
        for record_id, generation_number in updated_generations.items()
    }


def age_ordinal_text(age_number):
    normalized_age_number = max(1, int(age_number))

    if normalized_age_number <= len(AGE_ORDINAL_WORDS):
        return AGE_ORDINAL_WORDS[normalized_age_number - 1]

    last_two_digits = normalized_age_number % 100

    if 11 <= last_two_digits <= 13:
        suffix = "th"
    elif normalized_age_number % 10 == 1:
        suffix = "st"
    elif normalized_age_number % 10 == 2:
        suffix = "nd"
    elif normalized_age_number % 10 == 3:
        suffix = "rd"
    else:
        suffix = "th"

    return f"{normalized_age_number}{suffix}"


def generation_group_labels(people, generation_by_id):
    people_by_id = {
        str(person.get("record_id", "") or "").strip(): person
        for person in people or []
        if isinstance(person, dict)
        and str(person.get("record_id", "") or "").strip()
    }
    birth_years_by_generation = {}

    for record_id, generation_number in dict(
        generation_by_id or {}
    ).items():
        person = people_by_id.get(str(record_id or "").strip())

        if person is None:
            continue

        birth_year = person.get("birth_year")

        if isinstance(birth_year, bool):
            continue

        try:
            normalized_birth_year = int(birth_year)
        except (TypeError, ValueError):
            continue

        birth_years_by_generation.setdefault(
            int(generation_number),
            [],
        ).append(normalized_birth_year)

    labels_by_generation = {}
    age_number = 0
    generation_number = 0

    for group_number in sorted(set(generation_by_id.values())):
        birth_years = birth_years_by_generation.get(group_number, [])
        spans_more_than_twenty_years = bool(
            birth_years
            and max(birth_years) - min(birth_years)
            > GENERATION_MAX_SPAN_YEARS
        )

        if spans_more_than_twenty_years:
            age_number += 1
            labels_by_generation[group_number] = (
                f"{AGE_FILTER_PREFIX}{age_ordinal_text(age_number)}"
                f"{AGE_FILTER_SUFFIX}"
            )
        else:
            generation_number += 1
            labels_by_generation[group_number] = (
                f"{GENERATION_FILTER_PREFIX}{generation_number}"
            )

    return labels_by_generation


class PeopleList(tk.Frame):
    def __init__(
        self,
        parent,
        selection_command,
        create_command,
        period_provider=None,
        initial_period_filter="",
        period_filter_change_command=None,
        initial_generation_filter="",
        generation_filter_change_command=None,
        generation_override_provider=None,
        generation_move_command=None,
    ):
        super().__init__(parent, bg=SURFACE)
        self.selection_command = selection_command
        self.create_command = create_command
        self.period_provider = period_provider
        self.period_filter_change_command = (
            period_filter_change_command
        )
        self.generation_filter_change_command = (
            generation_filter_change_command
        )
        self.generation_override_provider = (
            generation_override_provider
        )
        self.generation_move_command = generation_move_command
        self.people = []
        self.periods = []
        self.periods_by_name = {}
        self.period_names_by_filter_label = {}
        self.period_filter_options = [FILTER_SHOW_ALL]
        self.visible_record_ids = []
        self.labels_by_id = {}
        self.search_text_by_id = {}
        self.rows_by_id = {}
        self.row_labels_by_id = {}
        self.group_colors_by_id = {}
        self.group_names_by_id = {}
        self.initial_values_complete_by_id = {}
        self.unfinished_by_id = {}
        self.generation_by_id = {}
        self.generation_labels_by_number = {}
        self.generation_numbers_by_filter_label = {}
        self.generation_group_members = {}
        self.generation_overrides = {}
        self.generation_scope_name = None
        self.generation_filter_options = [FILTER_SHOW_ALL]
        self.selected_record_id = None
        self.hovered_record_id = None
        self.filter_updates_paused = False
        self.refresh_periods(rebuild=False)

        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.heading = tk.Label(
            self,
            text="All People",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(15, "bold"),
            anchor="w",
        )
        self.heading.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 10))

        self.search_value = tk.StringVar()
        self.search_value.trace_add("write", self.filter_people)
        self.search_entry = RoundedEntry(
            self,
            textvariable=self.search_value,
            background=SURFACE,
            height=40,
            font=app_font(11),
        )
        self.search_entry.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=16,
            pady=(0, 12),
        )

        filters = tk.Frame(self, bg=SURFACE)
        filters.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=16,
            pady=(0, 8),
        )
        filters.grid_columnconfigure(1, weight=1)
        self.group_filter_value = tk.StringVar(
            value=FILTER_SHOW_ALL
        )
        self.age_filter_value = tk.StringVar(
            value=FILTER_SHOW_ALL
        )
        requested_initial_period = str(
            initial_period_filter or ""
        ).strip()
        initial_period_label = FILTER_SHOW_ALL

        if requested_initial_period in self.periods_by_name:
            initial_period_label = self.period_filter_label(
                requested_initial_period
            )
        elif requested_initial_period in self.period_names_by_filter_label:
            initial_period_label = requested_initial_period

        self.period_filter_value = tk.StringVar(
            value=initial_period_label
        )
        self.generation_filter_value = tk.StringVar(
            value=(
                str(initial_generation_filter or "").strip()
                or FILTER_SHOW_ALL
            )
        )
        self.unfinished_only_value = tk.BooleanVar(value=False)
        self.sort_value = tk.StringVar(
            value=SORT_BIRTH_YEAR
        )
        self.filter_summary_value = tk.StringVar(
            value="All people · Birth year"
        )
        self.filter_button = SoftButton(
            filters,
            text="Filters ▾",
            command=self.show_filter_menu,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=82,
            height=30,
            font=app_font(9, "bold"),
        )
        self.filter_button.grid(
            row=0,
            column=0,
            sticky="w",
        )
        filter_summary = tk.Label(
            filters,
            textvariable=self.filter_summary_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
        )
        filter_summary.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=8,
        )
        self.show_all_button = SoftButton(
            filters,
            text=FILTER_SHOW_ALL,
            command=self.show_all_people,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=70,
            height=30,
            font=app_font(8, "bold"),
        )
        self.show_all_button.grid(
            row=0,
            column=2,
            sticky="e",
        )
        self.group_filter_options = [FILTER_SHOW_ALL]
        self.filter_menu = tk.Menu(
            self,
            tearoff=False,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            activebackground=LIST_HOVER,
            activeforeground=TEXT_DARK,
            relief="solid",
            borderwidth=1,
            font=app_font(10),
        )
        self.rebuild_filter_menu()
        self.group_filter_value.trace_add(
            "write",
            self.filter_people,
        )
        self.age_filter_value.trace_add(
            "write",
            self.filter_people,
        )
        self.period_filter_value.trace_add(
            "write",
            self.period_filter_changed,
        )
        self.generation_filter_value.trace_add(
            "write",
            self.generation_filter_changed,
        )
        self.unfinished_only_value.trace_add(
            "write",
            self.filter_people,
        )
        self.sort_value.trace_add(
            "write",
            self.filter_people,
        )

        period_filter = tk.Frame(self, bg=SURFACE)
        period_filter.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=16,
            pady=(0, 10),
        )
        period_filter.grid_columnconfigure(1, weight=1)
        period_filter_label = tk.Label(
            period_filter,
            text="Born in",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        period_filter_label.grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 8),
        )
        self.period_filter_select = RoundedSelect(
            period_filter,
            self.period_filter_value,
            self.period_filter_options,
            background=SURFACE,
            height=34,
            font=app_font(9),
        )
        self.period_filter_select.grid(
            row=0,
            column=1,
            columnspan=2,
            sticky="ew",
        )
        generation_filter_label = tk.Label(
            period_filter,
            text="Generation / Age",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        generation_filter_label.grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=(7, 0),
        )
        self.generation_filter_select = RoundedSelect(
            period_filter,
            self.generation_filter_value,
            self.generation_filter_options,
            background=SURFACE,
            height=34,
            font=app_font(9),
        )
        self.generation_filter_select.grid(
            row=1,
            column=1,
            sticky="ew",
            pady=(7, 0),
        )
        self.generation_move_button = SoftButton(
            period_filter,
            text="Move person",
            command=self.show_generation_move_menu,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=92,
            height=34,
            font=app_font(8, "bold"),
        )
        self.generation_move_button.grid(
            row=1,
            column=2,
            sticky="e",
            padx=(6, 0),
            pady=(7, 0),
        )
        self.generation_move_button.set_enabled(False)
        self.unfinished_only_check = tk.Checkbutton(
            period_filter,
            text="Only show unfinished",
            variable=self.unfinished_only_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
            borderwidth=0,
            highlightthickness=0,
        )
        self.unfinished_only_check.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(7, 0),
        )

        list_container = tk.Frame(self, bg=SURFACE)
        list_container.grid(row=4, column=0, sticky="nsew", padx=16)
        list_container.grid_rowconfigure(0, weight=1)
        list_container.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            list_container,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightcolor=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", self.resize_rows)
        self.canvas.bind("<MouseWheel>", self.scroll_people)

        scrollbar = tk.Scrollbar(
            list_container,
            orient="vertical",
            command=self.canvas.yview,
            relief="flat",
            borderwidth=0,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.row_container = tk.Frame(self.canvas, bg=FIELD_BACKGROUND)
        self.row_container.grid_columnconfigure(0, weight=1)
        self.row_container.bind("<Configure>", self.update_scroll_region)
        self.row_window = self.canvas.create_window(
            (0, 0),
            window=self.row_container,
            anchor="nw",
        )

        footer = tk.Frame(self, bg=SURFACE)
        footer.grid(row=5, column=0, sticky="ew", padx=16, pady=14)
        footer.grid_columnconfigure(0, weight=1)

        self.count_label = tk.Label(
            footer,
            text="0 people",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        self.count_label.grid(row=0, column=0, sticky="w")

        self.create_button = SoftButton(
            footer,
            text="Create Magician",
            command=self.create_command,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=148,
            height=38,
        )
        self.create_button.grid(row=0, column=1, sticky="e")

    def set_people(
        self,
        people,
        selected_record_id=None,
        mage_groups=None,
    ):
        self.people = list(people or [])

        if hasattr(self, "period_provider"):
            self.refresh_periods(rebuild=False)

        self.labels_by_id = {}
        self.search_text_by_id = {}
        self.group_colors_by_id = {}
        self.group_names_by_id = {}
        self.initial_values_complete_by_id = {}
        self.unfinished_by_id = {}
        groups = normalize_mage_groups(mage_groups)
        group_filter_options = [
            FILTER_SHOW_ALL,
            *[group["name"] for group in groups],
        ]

        self.group_filter_options = group_filter_options

        if hasattr(self, "filter_menu"):
            self.rebuild_filter_menu()

        for person in self.people:
            record_id = person["record_id"]
            name = str(person.get("displayed_name", "")).strip() or "Unnamed magician"
            birth_text = self.format_birth_date(person)
            self.labels_by_id[record_id] = f"{name}\n{birth_text}"
            group = mage_group_definition(
                person.get("mage_group_id"),
                groups,
            )
            self.group_colors_by_id[record_id] = group["color"]
            self.group_names_by_id[record_id] = group["name"]
            self.initial_values_complete_by_id[record_id] = (
                initial_values_are_complete(person)
            )
            self.unfinished_by_id[record_id] = bool(
                person.get("unfinished", False)
            )
            name_details = person.get("name_details", {})
            name_entries = (
                name_details.get("entries", [])
                if isinstance(name_details, dict)
                else []
            )
            name_detail_text = " ".join(
                " ".join(
                    str(entry.get(field_name, "") or "")
                    for field_name in ("name_type", "name_entry", "date", "note")
                )
                for entry in name_entries
                if isinstance(entry, dict)
            )

            self.search_text_by_id[record_id] = " ".join(
                str(value or "")
                for value in (
                    person.get("displayed_name"),
                    name_detail_text,
                    person.get("school"),
                    group["name"],
                    person.get("birth_year"),
                    person.get("death_year"),
                )
            ).casefold()

        if (
            hasattr(self, "group_filter_value")
            and self.group_filter_value.get()
            not in group_filter_options
        ):
            previous_filter_pause = self.filter_updates_paused
            self.filter_updates_paused = True
            self.group_filter_value.set(FILTER_SHOW_ALL)
            self.filter_updates_paused = previous_filter_pause

        self.selected_record_id = selected_record_id
        self.refresh_generation_assignments()
        self.rebuild_rows()

    def refresh_periods(self, rebuild=True):
        periods = []

        if callable(self.period_provider):
            try:
                periods = self.period_provider()
            except (OSError, TypeError, ValueError):
                periods = []

        return self.set_periods(periods, rebuild=rebuild)

    def set_periods(self, periods, rebuild=True):
        normalized_periods = []

        for period in periods or []:
            if not isinstance(period, dict):
                continue

            period_name = str(period.get("name", "") or "").strip()

            try:
                start_year = int(
                    period.get("calculation_start_year")
                )
                end_year = int(
                    period.get("calculation_end_year")
                )
            except (TypeError, ValueError):
                continue

            if not period_name or end_year < start_year:
                continue

            normalized_periods.append(
                {
                    **period,
                    "name": period_name,
                    "calculation_start_year": start_year,
                    "calculation_end_year": end_year,
                }
            )

        self.periods = normalized_periods
        self.periods_by_name = {
            period["name"]: period
            for period in self.periods
        }
        self.period_names_by_filter_label = {
            self.period_filter_label(period["name"]): period["name"]
            for period in self.periods
        }
        self.period_filter_options = [
            FILTER_SHOW_ALL,
            *[
                self.period_filter_label(period["name"])
                for period in self.periods
            ],
        ]

        if (
            hasattr(self, "period_filter_value")
            and self.period_filter_value.get()
            not in self.period_filter_options
        ):
            previous_filter_pause = self.filter_updates_paused
            self.filter_updates_paused = True
            self.period_filter_value.set(FILTER_SHOW_ALL)
            self.filter_updates_paused = previous_filter_pause

        if hasattr(self, "filter_menu"):
            self.rebuild_filter_menu()

        if hasattr(self, "period_filter_select"):
            self.period_filter_select.set_values(
                self.period_filter_options
            )

        if hasattr(self, "generation_filter_value"):
            self.refresh_generation_assignments()

        if rebuild and hasattr(self, "canvas"):
            self.rebuild_rows()

        return list(self.periods)

    def rebuild_filter_menu(self):
        if not hasattr(self, "filter_menu"):
            return

        self.filter_menu.delete(0, "end")
        group_menu = tk.Menu(
            self.filter_menu,
            tearoff=False,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            activebackground=LIST_HOVER,
            activeforeground=TEXT_DARK,
            relief="solid",
            borderwidth=1,
            font=app_font(10),
        )

        for group_name in self.group_filter_options:
            group_menu.add_radiobutton(
                label=group_name,
                variable=self.group_filter_value,
                value=group_name,
            )

        age_menu = tk.Menu(
            self.filter_menu,
            tearoff=False,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            activebackground=LIST_HOVER,
            activeforeground=TEXT_DARK,
            relief="solid",
            borderwidth=1,
            font=app_font(10),
        )

        for age_option in AGE_FILTER_OPTIONS:
            age_menu.add_radiobutton(
                label=age_option,
                variable=self.age_filter_value,
                value=age_option,
            )

        period_menu = tk.Menu(
            self.filter_menu,
            tearoff=False,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            activebackground=LIST_HOVER,
            activeforeground=TEXT_DARK,
            relief="solid",
            borderwidth=1,
            font=app_font(10),
        )

        for period_label in self.period_filter_options:
            period_menu.add_radiobutton(
                label=period_label,
                variable=self.period_filter_value,
                value=period_label,
            )

        generation_menu = tk.Menu(
            self.filter_menu,
            tearoff=False,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            activebackground=LIST_HOVER,
            activeforeground=TEXT_DARK,
            relief="solid",
            borderwidth=1,
            font=app_font(10),
        )

        for generation_label in self.generation_filter_options:
            generation_menu.add_radiobutton(
                label=generation_label,
                variable=self.generation_filter_value,
                value=generation_label,
            )

        sort_menu = tk.Menu(
            self.filter_menu,
            tearoff=False,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            activebackground=LIST_HOVER,
            activeforeground=TEXT_DARK,
            relief="solid",
            borderwidth=1,
            font=app_font(10),
        )

        for sort_option in SORT_OPTIONS:
            sort_menu.add_radiobutton(
                label=sort_option,
                variable=self.sort_value,
                value=sort_option,
            )

        self.filter_menu.add_cascade(
            label="Group",
            menu=group_menu,
        )
        self.filter_menu.add_cascade(
            label="Age",
            menu=age_menu,
        )
        self.filter_menu.add_cascade(
            label="Period",
            menu=period_menu,
        )
        self.filter_menu.add_cascade(
            label="Generation / Age",
            menu=generation_menu,
        )
        self.filter_menu.add_cascade(
            label="Sort by",
            menu=sort_menu,
        )
        self.filter_menu.add_separator()
        self.filter_menu.add_command(
            label=FILTER_SHOW_ALL,
            command=self.show_all_people,
        )

    def show_filter_menu(self):
        self.filter_button.update_idletasks()

        try:
            self.filter_menu.tk_popup(
                self.filter_button.winfo_rootx(),
                (
                    self.filter_button.winfo_rooty()
                    + self.filter_button.winfo_height()
                ),
            )
        finally:
            self.filter_menu.grab_release()

    def update_filter_summary(self):
        selected_parts = []
        selected_group = self.group_filter_value.get()
        selected_age = self.age_filter_value.get()
        selected_period = self.period_filter_value.get()
        selected_generation = self.generation_filter_value.get()

        if selected_group != FILTER_SHOW_ALL:
            selected_parts.append(selected_group)

        if selected_age != FILTER_SHOW_ALL:
            selected_parts.append(selected_age)

        if selected_period != FILTER_SHOW_ALL:
            selected_parts.append(selected_period)

        if selected_generation != FILTER_SHOW_ALL:
            selected_parts.append(selected_generation)

        if self.unfinished_only_value.get():
            selected_parts.append("Unfinished only")

        if not selected_parts:
            selected_parts.append("All people")

        selected_parts.append(self.sort_value.get())
        self.filter_summary_value.set(" · ".join(selected_parts))

    def period_filter_changed(self, *arguments):
        if self.filter_updates_paused:
            return

        self.remember_period_filter()
        self.refresh_generation_assignments()
        self.filter_people()

    def generation_filter_changed(self, *arguments):
        if self.filter_updates_paused:
            return

        self.remember_generation_filter()
        self.filter_people()

    def remember_period_filter(self):
        period_filter_change_command = getattr(
            self,
            "period_filter_change_command",
            None,
        )

        if not callable(period_filter_change_command):
            return False

        selected_label = self.period_filter_value.get()
        selected_period_name = self.period_names_by_filter_label.get(
            selected_label,
            selected_label,
        )

        if selected_period_name == FILTER_SHOW_ALL:
            selected_period_name = ""

        return bool(
            period_filter_change_command(selected_period_name)
        )

    def remember_generation_filter(self):
        generation_filter_change_command = getattr(
            self,
            "generation_filter_change_command",
            None,
        )

        if not callable(generation_filter_change_command):
            return False

        selected_generation = str(
            self.generation_filter_value.get() or ""
        ).strip()

        if selected_generation == FILTER_SHOW_ALL:
            selected_generation = ""

        return bool(
            generation_filter_change_command(selected_generation)
        )

    def selected_period_scope_name(self):
        selected_period = (
            self.period_filter_value.get()
            if hasattr(self, "period_filter_value")
            else FILTER_SHOW_ALL
        )

        if selected_period == FILTER_SHOW_ALL:
            return ""

        return self.period_names_by_filter_label.get(
            selected_period,
            selected_period,
        )

    def generation_override_values(self):
        generation_override_provider = getattr(
            self,
            "generation_override_provider",
            None,
        )

        if not callable(generation_override_provider):
            return {}

        try:
            overrides = generation_override_provider(
                self.selected_period_scope_name()
            )
        except (KeyError, OSError, TypeError, ValueError):
            return {}

        if not isinstance(overrides, dict):
            return {}

        return {
            str(record_id or "").strip(): str(
                target_record_id or ""
            ).strip()
            for record_id, target_record_id in overrides.items()
            if str(record_id or "").strip()
            and str(target_record_id or "").strip()
        }

    def refresh_generation_assignments(self):
        generation_scope_name = self.selected_period_scope_name()
        previous_scope_name = getattr(
            self,
            "generation_scope_name",
            None,
        )
        previous_selected_label = (
            self.generation_filter_value.get()
            if hasattr(self, "generation_filter_value")
            else FILTER_SHOW_ALL
        )
        previous_selected_group = getattr(
            self,
            "generation_numbers_by_filter_label",
            {},
        ).get(previous_selected_label)
        selected_period = (
            self.period_filter_value.get()
            if hasattr(self, "period_filter_value")
            else FILTER_SHOW_ALL
        )
        generation_people = [
            person
            for person in getattr(self, "people", [])
            if self.matches_period_filter(person, selected_period)
        ]
        automatic_generation_by_id = approximate_generation_map(
            generation_people,
        )
        self.generation_overrides = self.generation_override_values()
        self.generation_by_id = apply_generation_overrides(
            generation_people,
            automatic_generation_by_id,
            self.generation_overrides,
        )
        self.generation_labels_by_number = generation_group_labels(
            generation_people,
            self.generation_by_id,
        )
        self.generation_numbers_by_filter_label = {
            label: generation_number
            for generation_number, label
            in self.generation_labels_by_number.items()
        }
        self.generation_group_members = {}

        for record_id, generation_number in self.generation_by_id.items():
            self.generation_group_members.setdefault(
                generation_number,
                [],
            ).append(record_id)

        for generation_number in self.generation_group_members:
            self.generation_group_members[generation_number].sort(
                key=self.record_generation_sort_key
            )

        self.generation_filter_options = [
            FILTER_SHOW_ALL,
            *[
                self.generation_labels_by_number[generation_number]
                for generation_number
                in sorted(self.generation_labels_by_number)
            ],
        ]

        if (
            previous_scope_name == generation_scope_name
            and previous_selected_group
            in self.generation_labels_by_number
        ):
            selected_generation_label = (
                self.generation_labels_by_number[
                    previous_selected_group
                ]
            )
        elif previous_selected_label in self.generation_filter_options:
            selected_generation_label = previous_selected_label
        else:
            selected_generation_label = FILTER_SHOW_ALL

        self.generation_scope_name = generation_scope_name

        if (
            hasattr(self, "generation_filter_value")
            and self.generation_filter_value.get()
            != selected_generation_label
        ):
            previous_filter_pause = self.filter_updates_paused
            self.filter_updates_paused = True
            self.generation_filter_value.set(selected_generation_label)
            self.filter_updates_paused = previous_filter_pause
            self.remember_generation_filter()

        if hasattr(self, "generation_filter_select"):
            self.generation_filter_select.set_values(
                self.generation_filter_options
            )

        if hasattr(self, "filter_menu"):
            self.rebuild_filter_menu()

        self.update_generation_move_button()

        return dict(self.generation_by_id)

    def record_generation_sort_key(self, record_id):
        for person in self.people:
            if str(person.get("record_id", "") or "") == str(
                record_id or ""
            ):
                return person_generation_sort_key(person)

        return 100000, 13, 32, "", str(record_id or "")

    def update_generation_move_button(self):
        if not hasattr(self, "generation_move_button"):
            return False

        selected_record_id = str(
            self.selected_record_id or ""
        ).strip()
        can_move = bool(
            callable(getattr(self, "generation_move_command", None))
            and selected_record_id in self.generation_by_id
            and (
                len(self.generation_group_members) > 1
                or selected_record_id in self.generation_overrides
            )
        )
        self.generation_move_button.set_enabled(can_move)
        return can_move

    def show_generation_move_menu(self):
        if not self.update_generation_move_button():
            return False

        selected_record_id = str(
            self.selected_record_id or ""
        ).strip()
        current_generation = self.generation_by_id.get(
            selected_record_id
        )
        person_name = self.labels_by_id.get(
            selected_record_id,
            "Selected person",
        ).split("\n", 1)[0]
        current_label = self.generation_labels_by_number.get(
            current_generation,
            "Current group",
        )
        move_menu = tk.Menu(
            self,
            tearoff=False,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            activebackground=LIST_HOVER,
            activeforeground=TEXT_DARK,
            relief="solid",
            borderwidth=1,
            font=app_font(10),
        )
        move_menu.add_command(
            label=f"{person_name} · {current_label}",
            state="disabled",
        )
        move_menu.add_separator()

        for generation_number in sorted(
            self.generation_labels_by_number
        ):
            if generation_number == current_generation:
                continue

            move_menu.add_command(
                label=(
                    "Move to "
                    + self.generation_labels_by_number[
                        generation_number
                    ]
                ),
                command=partial(
                    self.move_selected_person_to_group,
                    generation_number,
                ),
            )

        if selected_record_id in self.generation_overrides:
            move_menu.add_separator()
            move_menu.add_command(
                label="Use automatic assignment",
                command=self.use_automatic_generation_assignment,
            )

        self.generation_move_button.update_idletasks()

        try:
            move_menu.tk_popup(
                self.generation_move_button.winfo_rootx(),
                self.generation_move_button.winfo_rooty()
                + self.generation_move_button.winfo_height(),
            )
        finally:
            move_menu.grab_release()

        return True

    def move_selected_person_to_group(self, generation_number):
        generation_move_command = getattr(
            self,
            "generation_move_command",
            None,
        )
        selected_record_id = str(
            self.selected_record_id or ""
        ).strip()
        target_members = list(
            self.generation_group_members.get(generation_number, [])
        )
        target_record_id = next(
            (
                record_id
                for record_id in target_members
                if record_id != selected_record_id
            ),
            "",
        )

        if (
            not callable(generation_move_command)
            or not selected_record_id
            or not target_record_id
        ):
            return False

        changed = generation_move_command(
            self.selected_period_scope_name(),
            selected_record_id,
            target_record_id,
        )
        self.refresh_after_generation_move()
        return changed is not False

    def use_automatic_generation_assignment(self):
        generation_move_command = getattr(
            self,
            "generation_move_command",
            None,
        )
        selected_record_id = str(
            self.selected_record_id or ""
        ).strip()

        if not callable(generation_move_command) or not selected_record_id:
            return False

        changed = generation_move_command(
            self.selected_period_scope_name(),
            selected_record_id,
            "",
        )
        self.refresh_after_generation_move()
        return changed is not False

    def refresh_after_generation_move(self):
        selected_generation_label = self.generation_filter_value.get()
        self.refresh_generation_assignments()

        if selected_generation_label != FILTER_SHOW_ALL:
            selected_generation = self.generation_by_id.get(
                str(self.selected_record_id or "").strip()
            )
            replacement_label = self.generation_labels_by_number.get(
                selected_generation,
                FILTER_SHOW_ALL,
            )

            if self.generation_filter_value.get() != replacement_label:
                previous_filter_pause = self.filter_updates_paused
                self.filter_updates_paused = True
                self.generation_filter_value.set(replacement_label)
                self.filter_updates_paused = previous_filter_pause
                self.remember_generation_filter()

        self.filter_people()
        return True

    def format_birth_date(self, person):
        birth_year = person.get("birth_year")
        death_year = person.get("death_year")
        birth_year_text = (
            str(birth_year)
            if birth_year not in (None, "")
            else "Birth year unknown"
        )

        if bool(person.get("deceased")) or death_year not in (None, ""):
            death_year_text = (
                str(death_year)
                if death_year not in (None, "")
                else "Death year unknown"
            )
            return f"({birth_year_text} - {death_year_text})"

        return f"Born: {birth_year_text}"

    def set_selected_record(self, record_id):
        self.selected_record_id = record_id
        self.refresh_row_colors()
        self.scroll_selected_into_view()
        self.update_generation_move_button()

    def set_initial_values_status(
        self,
        record_id,
        complete,
        unfinished=None,
    ):
        normalized_record_id = str(record_id or "").strip()

        if normalized_record_id not in self.labels_by_id:
            return

        self.initial_values_complete_by_id[
            normalized_record_id
        ] = bool(complete)

        if unfinished is not None:
            self.unfinished_by_id[normalized_record_id] = bool(
                unfinished
            )

        show_red_border = self.unfinished_by_id.get(
            normalized_record_id,
            False,
        )
        label = self.row_labels_by_id.get(
            normalized_record_id
        )

        if label is None:
            return

        label.configure(
            highlightbackground=(
                LOCKED_BORDER if show_red_border else FIELD_BACKGROUND
            ),
            highlightcolor=(
                LOCKED_BORDER if show_red_border else FIELD_BACKGROUND
            ),
            highlightthickness=2 if show_red_border else 0,
        )

    def filter_people(self, *arguments):
        if self.filter_updates_paused:
            return

        if hasattr(self, "filter_summary_value"):
            self.update_filter_summary()

        self.rebuild_rows()

    def show_all_people(self):
        self.filter_updates_paused = True
        self.search_value.set("")
        self.group_filter_value.set(FILTER_SHOW_ALL)
        self.age_filter_value.set(FILTER_SHOW_ALL)

        if hasattr(self, "period_filter_value"):
            self.period_filter_value.set(FILTER_SHOW_ALL)

        if hasattr(self, "generation_filter_value"):
            self.generation_filter_value.set(FILTER_SHOW_ALL)

        if hasattr(self, "unfinished_only_value"):
            self.unfinished_only_value.set(False)

        self.filter_updates_paused = False

        if hasattr(self, "period_filter_value"):
            self.remember_period_filter()

        if hasattr(self, "generation_filter_value"):
            self.refresh_generation_assignments()

        if hasattr(self, "generation_filter_value"):
            self.remember_generation_filter()

        if hasattr(self, "filter_summary_value"):
            self.update_filter_summary()

        self.rebuild_rows()

    def person_age(self, person):
        birth_year = self.integer_value(person.get("birth_year"))

        if birth_year is None:
            return None

        death_year = self.integer_value(person.get("death_year"))
        has_death_date = bool(person.get("deceased")) or death_year is not None
        today = date.today()
        end_year = death_year if has_death_date else today.year

        if end_year is None:
            return None

        age = end_year - birth_year
        birth_month = self.integer_value(person.get("birth_month"))
        birth_day = self.integer_value(person.get("birth_day"))

        if has_death_date:
            end_month = self.integer_value(person.get("death_month"))
            end_day = self.integer_value(person.get("death_day"))
        else:
            end_month = today.month
            end_day = today.day

        if (
            birth_month is not None
            and birth_day is not None
            and end_month is not None
            and end_day is not None
            and (end_month, end_day) < (birth_month, birth_day)
        ):
            age -= 1

        if age < 0:
            return None

        return age

    def integer_value(self, value):
        if isinstance(value, bool):
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def matches_age_filter(self, person, selected_filter):
        if selected_filter == FILTER_SHOW_ALL:
            return True

        age = self.person_age(person)

        if selected_filter == "Unknown age":
            return age is None

        bounds = AGE_FILTER_BOUNDS.get(selected_filter)

        if bounds is None:
            return True

        minimum_age, maximum_age = bounds

        if age is None or age < minimum_age:
            return False

        return maximum_age is None or age <= maximum_age

    def period_filter_label(self, period_name):
        if period_name == FILTER_SHOW_ALL:
            return FILTER_SHOW_ALL

        period = self.periods_by_name.get(period_name, {})
        start_year = period.get("start_year")
        end_year = period.get("end_year")

        if start_year in (None, "") or end_year in (None, ""):
            return period_name

        return f"{period_name} ({start_year} to {end_year})"

    def matches_period_filter(self, person, selected_period_name):
        if selected_period_name == FILTER_SHOW_ALL:
            return True

        selected_period_name = getattr(
            self,
            "period_names_by_filter_label",
            {},
        ).get(selected_period_name, selected_period_name)
        period = getattr(self, "periods_by_name", {}).get(
            selected_period_name
        )

        if period is None:
            return True

        birth_year = self.integer_value(person.get("birth_year"))

        if birth_year is None:
            return False

        period_start = int(period["calculation_start_year"])
        period_end = int(period["calculation_end_year"])

        return period_start <= birth_year <= period_end

    def matches_generation_filter(
        self,
        person,
        selected_generation,
    ):
        if selected_generation == FILTER_SHOW_ALL:
            return True

        generation_text = str(selected_generation or "").strip()
        requested_generation = getattr(
            self,
            "generation_numbers_by_filter_label",
            {},
        ).get(generation_text)

        if requested_generation is None:
            return True

        record_id = str(person.get("record_id", "") or "").strip()
        return (
            getattr(self, "generation_by_id", {}).get(record_id)
            == requested_generation
        )

    def person_sort_key(self, person):
        selected_sort = (
            self.sort_value.get()
            if hasattr(self, "sort_value")
            else SORT_BIRTH_YEAR
        )
        record_id = person.get("record_id")
        name = str(
            person.get("displayed_name", "") or ""
        ).casefold()
        group_name = str(
            self.group_names_by_id.get(record_id, "") or ""
        ).casefold()
        birth_year = self.integer_value(person.get("birth_year"))
        birth_month = self.integer_value(person.get("birth_month"))
        birth_day = self.integer_value(person.get("birth_day"))
        birth_is_dated = birth_year is not None
        oldest_birth_key = (
            birth_is_dated,
            birth_year if birth_year is not None else 0,
            birth_month if birth_month is not None else 13,
            birth_day if birth_day is not None else 32,
            name,
        )

        if selected_sort == SORT_BIRTH_YEAR_NEWEST:
            return (
                birth_is_dated,
                -birth_year if birth_year is not None else 0,
                -birth_month if birth_month is not None else 0,
                -birth_day if birth_day is not None else 0,
                name,
            )

        if selected_sort == SORT_NAME:
            return name, *oldest_birth_key

        if selected_sort == SORT_GROUP:
            return group_name, *oldest_birth_key

        if selected_sort == SORT_AGE:
            age = self.person_age(person)
            return (
                age is None,
                -age if age is not None else 0,
                *oldest_birth_key,
            )

        return oldest_birth_key

    def filtered_people(self):
        query = self.search_value.get().strip().casefold()
        selected_group = self.group_filter_value.get()
        selected_age = self.age_filter_value.get()
        selected_period = (
            self.period_filter_value.get()
            if hasattr(self, "period_filter_value")
            else FILTER_SHOW_ALL
        )
        selected_generation = (
            self.generation_filter_value.get()
            if hasattr(self, "generation_filter_value")
            else FILTER_SHOW_ALL
        )
        unfinished_only = (
            self.unfinished_only_value.get()
            if hasattr(self, "unfinished_only_value")
            else False
        )
        matched_people = []

        for person in self.people:
            record_id = person["record_id"]

            if (
                query
                and query not in self.search_text_by_id[record_id]
            ):
                continue

            if (
                selected_group != FILTER_SHOW_ALL
                and self.group_names_by_id.get(record_id)
                != selected_group
            ):
                continue

            if not self.matches_age_filter(person, selected_age):
                continue

            if not self.matches_period_filter(person, selected_period):
                continue

            if not self.matches_generation_filter(
                person,
                selected_generation,
            ):
                continue

            if unfinished_only and not getattr(
                self,
                "unfinished_by_id",
                {},
            ).get(record_id, False):
                continue

            matched_people.append(person)

        return sorted(
            matched_people,
            key=self.person_sort_key,
        )

    def rebuild_rows(self):
        if hasattr(self, "filter_summary_value"):
            self.update_filter_summary()

        self.visible_record_ids = [
            person["record_id"]
            for person in self.filtered_people()
        ]

        for row in self.rows_by_id.values():
            row.destroy()

        self.rows_by_id = {}
        self.row_labels_by_id = {}
        wrap_length = max(140, self.canvas.winfo_width() - 31)

        for row_index, record_id in enumerate(self.visible_record_ids):
            row = tk.Frame(
                self.row_container,
                bg=FIELD_BACKGROUND,
                cursor="hand2",
            )
            row.grid(row=row_index, column=0, sticky="ew")
            row.grid_columnconfigure(1, weight=1)
            group_bar = tk.Frame(
                row,
                bg=self.group_colors_by_id[record_id],
                width=5,
                cursor="hand2",
            )
            group_bar.grid(row=0, column=0, sticky="ns")
            group_bar.grid_propagate(False)
            label = tk.Label(
                row,
                text=self.labels_by_id[record_id],
                bg=FIELD_BACKGROUND,
                fg=TEXT_DARK,
                font=app_font(10),
                anchor="nw",
                justify="left",
                wraplength=wrap_length,
                padx=10,
                pady=8,
                cursor="hand2",
                highlightbackground=(
                    LOCKED_BORDER
                    if self.unfinished_by_id.get(record_id, False)
                    else FIELD_BACKGROUND
                ),
                highlightcolor=(
                    LOCKED_BORDER
                    if self.unfinished_by_id.get(record_id, False)
                    else FIELD_BACKGROUND
                ),
                highlightthickness=(
                    2
                    if self.unfinished_by_id.get(record_id, False)
                    else 0
                ),
            )
            label.grid(row=0, column=1, sticky="ew")

            for widget in (row, group_bar, label):
                widget.bind(
                    "<Button-1>",
                    partial(self.select_row, record_id),
                )
                widget.bind(
                    "<Enter>",
                    partial(self.enter_row, record_id),
                )
                widget.bind(
                    "<Leave>",
                    partial(self.leave_row, record_id),
                )
                widget.bind("<MouseWheel>", self.scroll_people)

            self.rows_by_id[record_id] = row
            self.row_labels_by_id[record_id] = label

        visible_count = len(self.visible_record_ids)
        total_count = len(self.people)

        if visible_count == total_count:
            self.count_label.configure(text=f"{total_count} people")
        else:
            self.count_label.configure(text=f"{visible_count} of {total_count} people")

        self.refresh_row_colors()
        self.update_scroll_region()
        self.scroll_selected_into_view()

    def select_row(self, record_id, event=None):
        if self.selection_command(record_id) is not False:
            self.selected_record_id = record_id

        self.refresh_row_colors()
        self.update_generation_move_button()

    def enter_row(self, record_id, event=None):
        self.hovered_record_id = record_id
        self.refresh_row_colors()

    def leave_row(self, record_id, event=None):
        if self.hovered_record_id == record_id:
            self.hovered_record_id = None

        self.refresh_row_colors()

    def refresh_row_colors(self):
        for row_index, record_id in enumerate(self.visible_record_ids):
            if record_id == self.selected_record_id:
                background = LIST_SELECTED
            elif record_id == self.hovered_record_id:
                background = LIST_HOVER
            elif row_index % 2:
                background = LIST_ALTERNATE
            else:
                background = FIELD_BACKGROUND

            row = self.rows_by_id.get(record_id)

            if row is not None:
                row.configure(bg=background)

            label = self.row_labels_by_id.get(record_id)

            if label is not None:
                label.configure(bg=background)

    def resize_rows(self, event):
        self.canvas.itemconfigure(self.row_window, width=max(1, event.width - 2))
        wrap_length = max(140, event.width - 31)

        for label in self.row_labels_by_id.values():
            label.configure(wraplength=wrap_length)

        self.update_scroll_region()

    def update_scroll_region(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def scroll_people(self, event):
        if event.delta:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        return "break"

    def scroll_selected_into_view(self):
        row = self.rows_by_id.get(self.selected_record_id)

        if row is None:
            return

        self.update_idletasks()
        content_height = max(1, self.row_container.winfo_height())
        viewport_top = self.canvas.canvasy(0)
        viewport_bottom = viewport_top + self.canvas.winfo_height()
        row_top = row.winfo_y()
        row_bottom = row_top + row.winfo_height()

        if row_top < viewport_top:
            self.canvas.yview_moveto(row_top / content_height)
        elif row_bottom > viewport_bottom:
            target_top = row_bottom - self.canvas.winfo_height()
            self.canvas.yview_moveto(target_top / content_height)
