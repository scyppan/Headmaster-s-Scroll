import tkinter as tk
from functools import partial

from mage_maker.sections.development.models import (
    DEVELOPMENT_SKILL_OPTIONS,
)
from mage_maker.ui.theme import (
    APP_BACKGROUND,
    BORDER,
    BORDER_SOFT,
    FIELD_BACKGROUND,
    LIST_ALTERNATE,
    LIST_SELECTED,
    PRIMARY,
    PRIMARY_HOVER,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import (
    RoundedEntry,
    RoundedSelect,
    SoftButton,
)


FOLLOW_DEVELOPMENT_STRATEGY = "Follow development strategy"
INLINE_PERSON_LIMIT = 10


class EventEminencePicker(tk.Frame):
    def __init__(
        self,
        parent,
        controller,
        background,
    ):
        super().__init__(
            parent,
            bg=background,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=7,
            pady=5,
        )
        self.controller = controller
        self.background = background
        self.person_ids = []
        self.earned_person_ids = []
        self.skills_by_person_id = {}
        self.event_identity = ""
        self.variables_by_person_id = {}
        self.skill_variables_by_person_id = {}
        self.checkbuttons = []
        self.skill_selects_by_person_id = {}
        self.rendered_rows = []
        self.is_enabled = True
        self.layout_mode = "inline"
        self.loading_inline_bulk = False
        self.heading_value = tk.StringVar(value="Eminence")
        self.summary_value = tk.StringVar(
            value="No linked people can receive Eminence."
        )
        self.set_all_value = tk.BooleanVar(value=False)
        self.bulk_skill_value = tk.StringVar(
            value=FOLLOW_DEVELOPMENT_STRATEGY
        )
        self.grid_columnconfigure(0, weight=1)
        self.build_controls()
        self.bulk_skill_value.trace_add(
            "write",
            self.inline_bulk_skill_changed,
        )

    def build_controls(self):
        self.inline_panel = tk.Frame(
            self,
            bg=self.background,
        )
        self.inline_panel.grid(row=0, column=0, sticky="ew")
        self.inline_panel.grid_columnconfigure(0, weight=1)
        inline_heading = tk.Label(
            self.inline_panel,
            textvariable=self.heading_value,
            bg=self.background,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        inline_heading.grid(row=0, column=0, sticky="ew")
        inline_hint = tk.Label(
            self.inline_panel,
            text="Choose who earns one Eminence point and its skill.",
            bg=self.background,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
        )
        inline_hint.grid(row=1, column=0, sticky="ew", pady=(0, 2))
        inline_bulk = tk.Frame(
            self.inline_panel,
            bg=self.background,
        )
        inline_bulk.grid(row=2, column=0, sticky="ew", pady=(0, 3))
        inline_bulk.grid_columnconfigure(0, weight=1)
        self.inline_set_all_checkbutton = tk.Checkbutton(
            inline_bulk,
            text="Set Eminence for all in event",
            variable=self.set_all_value,
            command=self.inline_set_all_changed,
            bg=self.background,
            fg=TEXT_DARK,
            activebackground=self.background,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(8, "bold"),
            borderwidth=0,
            highlightthickness=0,
        )
        self.inline_set_all_checkbutton.grid(
            row=0,
            column=0,
            sticky="w",
        )
        self.inline_bulk_skill_select = RoundedSelect(
            inline_bulk,
            self.bulk_skill_value,
            [
                FOLLOW_DEVELOPMENT_STRATEGY,
                *DEVELOPMENT_SKILL_OPTIONS,
            ],
            background=self.background,
            width=220,
            height=24,
            font=app_font(8),
        )
        self.inline_bulk_skill_select.grid(
            row=0,
            column=1,
            sticky="e",
            padx=(8, 0),
        )
        self.rows = tk.Frame(self.inline_panel, bg=self.background)
        self.rows.grid(row=3, column=0, sticky="ew")
        self.rows.grid_columnconfigure(0, weight=1)

        self.compact_panel = tk.Frame(
            self,
            bg=self.background,
        )
        self.compact_panel.grid_columnconfigure(0, weight=1)
        heading_row = tk.Frame(
            self.compact_panel,
            bg=self.background,
        )
        heading_row.grid(row=0, column=0, sticky="ew")
        heading_row.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            heading_row,
            textvariable=self.heading_value,
            bg=self.background,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        self.edit_button = SoftButton(
            heading_row,
            text="Edit Eminence",
            command=self.open_dialog,
            background=self.background,
            fill=FIELD_BACKGROUND,
            hover_fill=LIST_SELECTED,
            foreground=TEXT_DARK,
            width=104,
            height=24,
            font=app_font(8, "bold"),
        )
        self.edit_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        summary = tk.Label(
            self.compact_panel,
            textvariable=self.summary_value,
            bg=self.background,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
            justify="left",
        )
        summary.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self.compact_panel.grid_remove()

    def set_values(
        self,
        person_ids,
        earned_person_ids=(),
        skills_by_person_id=None,
        event_identity="",
    ):
        self.person_ids = []

        for person_id in person_ids or ():
            normalized_person_id = str(person_id or "").strip()

            if (
                normalized_person_id
                and normalized_person_id not in self.person_ids
            ):
                self.person_ids.append(normalized_person_id)

        self.event_identity = str(event_identity or "").strip()
        requested_earned_ids = {
            str(person_id or "").strip()
            for person_id in earned_person_ids or ()
            if str(person_id or "").strip()
        }
        self.earned_person_ids = [
            person_id
            for person_id in self.person_ids
            if person_id in requested_earned_ids
            and self.person_can_earn(person_id)
        ]
        candidate_skills = (
            skills_by_person_id
            if isinstance(skills_by_person_id, dict)
            else {}
        )
        self.skills_by_person_id = {}

        for person_id in self.person_ids:
            if not self.person_can_earn(person_id):
                continue

            selected_skill = str(
                candidate_skills.get(person_id, "") or ""
            ).strip()

            if selected_skill not in DEVELOPMENT_SKILL_OPTIONS:
                selected_skill = self.default_skill(person_id)

            self.skills_by_person_id[person_id] = selected_skill

        self.loading_inline_bulk = True
        self.bulk_skill_value.set(self.initial_bulk_skill_option())
        self.loading_inline_bulk = False
        self.render_inline_people()
        self.select_initial_layout()
        self.refresh_summary()

    def update_people(self, person_ids):
        self.set_values(
            person_ids,
            self.get_values(),
            self.get_skill_values(include_unearned=True),
            self.event_identity,
        )

    def get_values(self):
        self.commit_inline_values()
        return [
            person_id
            for person_id in self.person_ids
            if person_id in self.earned_person_ids
            and self.person_can_earn(person_id)
        ]

    def get_skill_values(self, include_unearned=False):
        self.commit_inline_values()
        selected_person_ids = (
            self.person_ids
            if include_unearned
            else self.get_values()
        )
        return {
            person_id: self.skills_by_person_id[person_id]
            for person_id in selected_person_ids
            if self.skills_by_person_id.get(person_id)
            in DEVELOPMENT_SKILL_OPTIONS
        }

    def default_skill(self, person_id):
        if self.controller is not None and hasattr(
            self.controller,
            "suggest_event_eminence_skill",
        ):
            selected_skill = self.controller.suggest_event_eminence_skill(
                person_id,
                self.event_identity,
            )

            if selected_skill in DEVELOPMENT_SKILL_OPTIONS:
                return selected_skill

        return DEVELOPMENT_SKILL_OPTIONS[0]

    def person_can_earn(self, person_id):
        if self.controller is None or not hasattr(
            self.controller,
            "person_can_earn_eminence",
        ):
            return True

        return bool(
            self.controller.person_can_earn_eminence(person_id)
        )

    def eligible_person_count(self):
        return sum(
            1
            for person_id in self.person_ids
            if self.person_can_earn(person_id)
        )

    def eligible_person_ids(self):
        return {
            person_id
            for person_id in self.person_ids
            if self.person_can_earn(person_id)
        }

    def people_labels_by_id(self):
        if self.controller is None:
            return {}

        label_provider = getattr(
            self.controller,
            "people_option_labels",
            None,
        )

        if callable(label_provider):
            return label_provider(self.person_ids)

        return {
            str(option.get("value", "") or "").strip(): str(
                option.get("label", "") or "Unknown person"
            ).strip()
            for option in self.controller.people_options()
            if isinstance(option, dict)
            and str(option.get("value", "") or "").strip()
        }

    def initial_bulk_skill_option(self):
        eligible_ids = self.eligible_person_ids()

        if not eligible_ids:
            return FOLLOW_DEVELOPMENT_STRATEGY

        if all(
            self.skills_by_person_id.get(person_id)
            == self.default_skill(person_id)
            for person_id in eligible_ids
        ):
            return FOLLOW_DEVELOPMENT_STRATEGY

        selected_skills = {
            self.skills_by_person_id.get(person_id, "")
            for person_id in eligible_ids
        }

        if len(selected_skills) == 1:
            selected_skill = next(iter(selected_skills))

            if selected_skill in DEVELOPMENT_SKILL_OPTIONS:
                return selected_skill

        return FOLLOW_DEVELOPMENT_STRATEGY

    def render_inline_people(self):
        for row in self.rendered_rows:
            row.destroy()

        self.rendered_rows = []
        self.variables_by_person_id = {}
        self.skill_variables_by_person_id = {}
        self.checkbuttons = []
        self.skill_selects_by_person_id = {}

        if (
            not self.person_ids
            or len(self.person_ids) > INLINE_PERSON_LIMIT
        ):
            self.refresh_inline_bulk_controls()
            return

        labels_by_id = self.people_labels_by_id()
        earned_ids = set(self.earned_person_ids)

        for row_index, person_id in enumerate(self.person_ids):
            row_background = (
                FIELD_BACKGROUND
                if row_index % 2 == 0
                else self.background
            )
            row = tk.Frame(
                self.rows,
                bg=row_background,
                padx=5,
                pady=1,
            )
            self.rendered_rows.append(row)
            row.grid(row=row_index, column=0, sticky="ew")
            row.grid_columnconfigure(0, weight=1)
            person_name = tk.Label(
                row,
                text=labels_by_id.get(person_id, "Unknown person"),
                bg=row_background,
                fg=TEXT_DARK,
                font=app_font(9),
                anchor="w",
            )
            person_name.grid(row=0, column=0, sticky="ew")

            if not self.person_can_earn(person_id):
                ineligible_label = tk.Label(
                    row,
                    text="Non-magical · cannot earn Eminence",
                    bg=row_background,
                    fg=TEXT_MUTED,
                    font=app_font(8, "bold"),
                    anchor="e",
                )
                ineligible_label.grid(
                    row=0,
                    column=1,
                    columnspan=2,
                    sticky="e",
                    padx=(10, 0),
                )
                continue

            earns_value = tk.BooleanVar(
                value=person_id in earned_ids
            )
            earns_checkbutton = tk.Checkbutton(
                row,
                text="Earns Eminence",
                variable=earns_value,
                bg=row_background,
                fg=TEXT_DARK,
                activebackground=row_background,
                activeforeground=TEXT_DARK,
                selectcolor=FIELD_BACKGROUND,
                font=app_font(9, "bold"),
                borderwidth=0,
                highlightthickness=0,
                state="normal" if self.is_enabled else "disabled",
                command=partial(
                    self.inline_earning_changed,
                    person_id,
                ),
            )
            earns_checkbutton.grid(
                row=0,
                column=1,
                sticky="e",
                padx=(10, 0),
            )
            selected_skill = self.skills_by_person_id.get(
                person_id,
                self.default_skill(person_id),
            )
            skill_value = tk.StringVar(value=selected_skill)
            skill_select = RoundedSelect(
                row,
                skill_value,
                DEVELOPMENT_SKILL_OPTIONS,
                background=row_background,
                width=132,
                height=24,
                font=app_font(8),
            )
            skill_select.grid(
                row=0,
                column=2,
                sticky="e",
                padx=(8, 0),
            )
            self.variables_by_person_id[person_id] = earns_value
            self.skill_variables_by_person_id[person_id] = skill_value
            self.checkbuttons.append(earns_checkbutton)
            self.skill_selects_by_person_id[person_id] = skill_select
            self.update_skill_enabled(person_id)

        self.refresh_inline_bulk_controls()

    def commit_inline_values(self):
        if not self.variables_by_person_id:
            return

        self.earned_person_ids = [
            person_id
            for person_id in self.person_ids
            if person_id in self.variables_by_person_id
            and self.variables_by_person_id[person_id].get()
            and self.person_can_earn(person_id)
        ]

        for person_id in self.person_ids:
            skill_variable = self.skill_variables_by_person_id.get(
                person_id
            )

            if skill_variable is None:
                continue

            selected_skill = str(skill_variable.get() or "").strip()

            if selected_skill in DEVELOPMENT_SKILL_OPTIONS:
                self.skills_by_person_id[person_id] = selected_skill

    def sync_inline_controls_from_state(self):
        earned_ids = set(self.earned_person_ids)

        for person_id, earns_value in self.variables_by_person_id.items():
            earns_value.set(person_id in earned_ids)
            selected_skill = self.skills_by_person_id.get(
                person_id,
                self.default_skill(person_id),
            )
            skill_variable = self.skill_variables_by_person_id.get(
                person_id
            )

            if skill_variable is not None:
                skill_variable.set(selected_skill)

            self.update_skill_enabled(person_id)

        self.refresh_inline_bulk_controls()

    def refresh_inline_bulk_controls(self):
        eligible_ids = self.eligible_person_ids()
        all_people_awarded = bool(eligible_ids) and eligible_ids.issubset(
            self.earned_person_ids
        )
        self.loading_inline_bulk = True
        self.set_all_value.set(all_people_awarded)
        self.loading_inline_bulk = False
        self.inline_set_all_checkbutton.configure(
            state=(
                "normal"
                if self.is_enabled and eligible_ids
                else "disabled"
            )
        )
        self.inline_bulk_skill_select.set_enabled(
            self.is_enabled and bool(eligible_ids)
        )

    def inline_earning_changed(self, person_id):
        self.commit_inline_values()
        self.update_skill_enabled(person_id)
        self.refresh_summary(commit_values=False)

    def inline_set_all_changed(self):
        if self.loading_inline_bulk:
            return

        self.commit_inline_values()

        if self.set_all_value.get():
            self.earned_person_ids = [
                person_id
                for person_id in self.person_ids
                if self.person_can_earn(person_id)
            ]
            self.apply_inline_bulk_skill_to_all()
        else:
            self.earned_person_ids = []

        self.sync_inline_controls_from_state()
        self.refresh_summary(commit_values=False)

    def inline_bulk_skill_changed(self, *arguments):
        if self.loading_inline_bulk or not self.set_all_value.get():
            return

        self.commit_inline_values()
        self.apply_inline_bulk_skill_to_all()
        self.sync_inline_controls_from_state()
        self.refresh_summary(commit_values=False)

    def apply_inline_bulk_skill_to_all(self):
        selected_option = str(
            self.bulk_skill_value.get() or ""
        ).strip()

        for person_id in self.person_ids:
            if not self.person_can_earn(person_id):
                continue

            self.skills_by_person_id[person_id] = (
                self.default_skill(person_id)
                if selected_option == FOLLOW_DEVELOPMENT_STRATEGY
                else (
                    selected_option
                    if selected_option in DEVELOPMENT_SKILL_OPTIONS
                    else self.default_skill(person_id)
                )
            )

    def update_skill_enabled(self, person_id):
        skill_select = self.skill_selects_by_person_id.get(person_id)
        earns_value = self.variables_by_person_id.get(person_id)

        if skill_select is None:
            return

        skill_select.set_enabled(
            self.is_enabled
            and earns_value is not None
            and bool(earns_value.get())
        )

    def refresh_summary(self, commit_values=True):
        if commit_values:
            self.commit_inline_values()

        earned_count = len(
            [
                person_id
                for person_id in self.person_ids
                if person_id in self.earned_person_ids
                and self.person_can_earn(person_id)
            ]
        )
        eligible_count = self.eligible_person_count()
        self.heading_value.set(
            (
                "Eminence · 1 awarded"
                if earned_count == 1
                else f"Eminence · {earned_count} awarded"
            )
        )

        if not self.person_ids:
            self.summary_value.set(
                "Link people to the event before assigning Eminence."
            )
            self.edit_button.set_enabled(False)
            self.grid_remove()
            return

        if eligible_count == 0:
            self.summary_value.set(
                "None of the linked people can earn Eminence."
            )
        elif earned_count == 0:
            self.summary_value.set(
                f"0 of {eligible_count} eligible people receive Eminence."
            )
        elif earned_count == 1:
            self.summary_value.set(
                f"1 of {eligible_count} eligible people receives Eminence."
            )
        else:
            self.summary_value.set(
                f"{earned_count} of {eligible_count} eligible people "
                "receive Eminence."
            )

        self.edit_button.set_enabled(
            self.is_enabled and eligible_count > 0
        )
        self.refresh_inline_bulk_controls()
        self.grid()

    def select_initial_layout(self):
        if len(self.person_ids) > INLINE_PERSON_LIMIT:
            self.show_compact_layout()
            return

        self.show_inline_layout()

    def show_inline_layout(self):
        if self.layout_mode == "inline":
            self.compact_panel.grid_remove()
            self.inline_panel.grid(row=0, column=0, sticky="ew")
            return False

        self.compact_panel.grid_remove()
        self.inline_panel.grid(row=0, column=0, sticky="ew")
        self.layout_mode = "inline"
        return True

    def show_compact_layout(self):
        if self.layout_mode == "compact":
            self.inline_panel.grid_remove()
            self.compact_panel.grid(row=0, column=0, sticky="ew")
            return False

        self.inline_panel.grid_remove()
        self.compact_panel.grid(row=0, column=0, sticky="ew")
        self.layout_mode = "compact"
        return True

    def inline_layout_fits(
        self,
        person_count,
        projected_height,
        available_height,
        required_width,
        available_width,
    ):
        if person_count > INLINE_PERSON_LIMIT:
            return False

        if available_height <= 1 or available_width <= 1:
            return True

        return (
            projected_height <= available_height - 4
            and required_width <= available_width - 8
        )

    def fit_to_available_space(
        self,
        content_height,
        available_height,
        available_width,
    ):
        if not self.person_ids:
            return False

        self.update_idletasks()
        displayed_panel = (
            self.inline_panel
            if self.layout_mode == "inline"
            else self.compact_panel
        )
        displayed_height = max(1, displayed_panel.winfo_reqheight())
        inline_height = max(1, self.inline_panel.winfo_reqheight())
        projected_height = max(0, content_height) + (
            inline_height - displayed_height
        )
        picker_width = self.winfo_width()

        if picker_width <= 1:
            picker_width = available_width

        required_width = self.inline_panel.winfo_reqwidth() + 14
        use_inline = self.inline_layout_fits(
            len(self.person_ids),
            projected_height,
            available_height,
            required_width,
            picker_width,
        )

        if use_inline:
            return self.show_inline_layout()

        return self.show_compact_layout()

    def open_dialog(self):
        if not self.is_enabled or self.eligible_person_count() == 0:
            return False

        self.commit_inline_values()

        EventEminenceDialog(
            self,
            self.controller,
            self.person_ids,
            self.get_values(),
            self.get_skill_values(include_unearned=True),
            self.event_identity,
            self.dialog_saved,
        )
        return True

    def dialog_saved(self, earned_person_ids, skills_by_person_id):
        self.set_values(
            self.person_ids,
            earned_person_ids,
            skills_by_person_id,
            self.event_identity,
        )

    def set_enabled(self, enabled):
        self.is_enabled = bool(enabled)
        self.edit_button.set_enabled(
            self.is_enabled and self.eligible_person_count() > 0
        )
        state = "normal" if self.is_enabled else "disabled"

        for checkbutton in self.checkbuttons:
            checkbutton.configure(state=state)

        for person_id in self.person_ids:
            self.update_skill_enabled(person_id)

        self.refresh_inline_bulk_controls()


class EventEminenceDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        controller,
        person_ids,
        earned_person_ids,
        skills_by_person_id,
        event_identity,
        save_command,
    ):
        super().__init__(parent)
        self.controller = controller
        self.person_ids = []

        for person_id in person_ids or ():
            normalized_person_id = str(person_id or "").strip()

            if (
                normalized_person_id
                and normalized_person_id not in self.person_ids
            ):
                self.person_ids.append(normalized_person_id)

        self.event_identity = str(event_identity or "").strip()
        self.save_command = save_command
        self.labels_by_person_id = self.people_labels_by_id()
        self.eligible_person_ids = {
            person_id
            for person_id in self.person_ids
            if self.person_can_earn(person_id)
        }
        requested_earned_ids = {
            str(person_id or "").strip()
            for person_id in earned_person_ids or ()
            if str(person_id or "").strip()
        }
        self.earned_person_ids = [
            person_id
            for person_id in self.person_ids
            if person_id in requested_earned_ids
            and person_id in self.eligible_person_ids
        ]
        candidate_skills = (
            skills_by_person_id
            if isinstance(skills_by_person_id, dict)
            else {}
        )
        self.skills_by_person_id = {}

        for person_id in self.eligible_person_ids:
            selected_skill = str(
                candidate_skills.get(person_id, "") or ""
            ).strip()

            if selected_skill not in DEVELOPMENT_SKILL_OPTIONS:
                selected_skill = self.default_skill(person_id)

            self.skills_by_person_id[person_id] = selected_skill

        self.visible_person_ids = []
        self.selected_person_id = (
            self.earned_person_ids[0]
            if self.earned_person_ids
            else next(
                (
                    person_id
                    for person_id in self.person_ids
                    if person_id in self.eligible_person_ids
                ),
                "",
            )
        )
        self.search_value = tk.StringVar()
        self.count_value = tk.StringVar()
        self.selected_person_value = tk.StringVar(
            value="Select a person to edit their Eminence."
        )
        self.earns_eminence_value = tk.BooleanVar(value=False)
        self.skill_value = tk.StringVar(
            value=DEVELOPMENT_SKILL_OPTIONS[0]
        )
        self.loading_detail = False
        self.loading_bulk = False
        self.set_all_value = tk.BooleanVar(
            value=(
                bool(self.eligible_person_ids)
                and self.eligible_person_ids.issubset(
                    self.earned_person_ids
                )
            )
        )
        self.bulk_skill_value = tk.StringVar(
            value=self.initial_bulk_skill_option()
        )
        self.refreshing_results = False
        self.title("Event Eminence")
        self.geometry("760x680")
        self.minsize(620, 560)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.search_value.trace_add("write", self.refresh_results)
        self.skill_value.trace_add("write", self.detail_skill_changed)
        self.bulk_skill_value.trace_add(
            "write",
            self.bulk_skill_changed,
        )
        self.refresh_results()
        self.bind("<Escape>", self.close_dialog)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def build_dialog(self):
        card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        card.grid_rowconfigure(5, weight=1)
        card.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            card,
            text="Assign event Eminence",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(14, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        explanation = tk.Label(
            card,
            text=(
                "Choose who earns one Eminence point from this event. "
                "Set everyone from their development strategies or one "
                "shared skill, then adjust individuals as needed."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=680,
        )
        explanation.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        self.search_control = RoundedEntry(
            card,
            textvariable=self.search_value,
            background=SURFACE,
            height=36,
            font=app_font(10),
        )
        self.search_control.grid(row=2, column=0, sticky="ew")
        self.search_control.bind_input("<Escape>", self.clear_search)
        bulk_controls = tk.Frame(
            card,
            bg=SURFACE,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=10,
            pady=8,
        )
        bulk_controls.grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(8, 0),
        )
        bulk_controls.grid_columnconfigure(0, weight=1)
        self.set_all_checkbutton = tk.Checkbutton(
            bulk_controls,
            text="Set Eminence for all in event",
            variable=self.set_all_value,
            command=self.set_all_eminence_changed,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
            borderwidth=0,
            highlightthickness=0,
        )
        self.set_all_checkbutton.grid(
            row=0,
            column=0,
            sticky="w",
        )
        self.bulk_skill_select = RoundedSelect(
            bulk_controls,
            self.bulk_skill_value,
            [
                FOLLOW_DEVELOPMENT_STRATEGY,
                *DEVELOPMENT_SKILL_OPTIONS,
            ],
            background=SURFACE,
            width=220,
            height=28,
            font=app_font(8),
        )
        self.bulk_skill_select.grid(
            row=0,
            column=1,
            sticky="e",
            padx=(10, 0),
        )
        actions = tk.Frame(card, bg=SURFACE)
        actions.grid(row=4, column=0, sticky="ew", pady=(8, 6))
        actions.grid_columnconfigure(2, weight=1)
        award_visible_button = SoftButton(
            actions,
            text="Award visible",
            command=self.award_visible_people,
            background=SURFACE,
            fill=FIELD_BACKGROUND,
            hover_fill=LIST_SELECTED,
            foreground=TEXT_DARK,
            width=104,
            height=30,
            font=app_font(8, "bold"),
        )
        award_visible_button.grid(row=0, column=0, sticky="w")
        clear_visible_button = SoftButton(
            actions,
            text="Clear visible",
            command=self.clear_visible_people,
            background=SURFACE,
            width=98,
            height=30,
            font=app_font(8, "bold"),
        )
        clear_visible_button.grid(
            row=0,
            column=1,
            sticky="w",
            padx=(6, 0),
        )
        count_label = tk.Label(
            actions,
            textvariable=self.count_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="e",
        )
        count_label.grid(row=0, column=2, sticky="e")
        results_frame = tk.Frame(
            card,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        results_frame.grid(row=5, column=0, sticky="nsew")
        results_frame.grid_rowconfigure(0, weight=1)
        results_frame.grid_columnconfigure(0, weight=1)
        self.results_list = tk.Listbox(
            results_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=app_font(10),
            activestyle="none",
            exportselection=False,
        )
        self.results_list.grid(row=0, column=0, sticky="nsew")
        self.results_list.bind(
            "<<ListboxSelect>>",
            self.person_selected,
        )
        self.results_list.bind(
            "<Double-Button-1>",
            self.toggle_selected_person,
        )
        self.results_list.bind(
            "<space>",
            self.toggle_selected_person,
        )
        scrollbar = tk.Scrollbar(
            results_frame,
            command=self.results_list.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.results_list.configure(yscrollcommand=scrollbar.set)
        detail = tk.Frame(
            card,
            bg=SURFACE,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=10,
            pady=8,
        )
        detail.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        detail.grid_columnconfigure(0, weight=1)
        selected_person = tk.Label(
            detail,
            textvariable=self.selected_person_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        selected_person.grid(row=0, column=0, sticky="ew")
        self.earns_eminence_checkbutton = tk.Checkbutton(
            detail,
            text="Earns Eminence",
            variable=self.earns_eminence_value,
            command=self.detail_earning_changed,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
            borderwidth=0,
            highlightthickness=0,
        )
        self.earns_eminence_checkbutton.grid(
            row=0,
            column=1,
            sticky="e",
            padx=(10, 0),
        )
        self.skill_select = RoundedSelect(
            detail,
            self.skill_value,
            DEVELOPMENT_SKILL_OPTIONS,
            background=SURFACE,
            width=150,
            height=26,
            font=app_font(8),
        )
        self.skill_select.grid(
            row=0,
            column=2,
            sticky="e",
            padx=(8, 0),
        )
        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(row=7, column=0, sticky="ew", pady=(14, 0))
        footer.grid_columnconfigure(0, weight=1)
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.destroy,
            background=SURFACE,
            width=88,
            height=36,
        )
        cancel_button.grid(row=0, column=1, padx=(0, 6))
        save_button = SoftButton(
            footer,
            text="Save Eminence",
            command=self.save_dialog,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=118,
            height=36,
        )
        save_button.grid(row=0, column=2)
        self.after_idle(self.search_control.focus_set)

    def people_labels_by_id(self):
        if self.controller is None:
            return {
                person_id: "Unknown person"
                for person_id in self.person_ids
            }

        label_provider = getattr(
            self.controller,
            "people_option_labels",
            None,
        )

        if callable(label_provider):
            return label_provider(self.person_ids)

        return {
            str(option.get("value", "") or "").strip(): str(
                option.get("label", "") or "Unknown person"
            ).strip()
            for option in self.controller.people_options()
            if isinstance(option, dict)
            and str(option.get("value", "") or "").strip()
        }

    def person_can_earn(self, person_id):
        if self.controller is None or not hasattr(
            self.controller,
            "person_can_earn_eminence",
        ):
            return True

        return bool(
            self.controller.person_can_earn_eminence(person_id)
        )

    def default_skill(self, person_id):
        if self.controller is not None and hasattr(
            self.controller,
            "suggest_event_eminence_skill",
        ):
            selected_skill = self.controller.suggest_event_eminence_skill(
                person_id,
                self.event_identity,
            )

            if selected_skill in DEVELOPMENT_SKILL_OPTIONS:
                return selected_skill

        return DEVELOPMENT_SKILL_OPTIONS[0]

    def initial_bulk_skill_option(self):
        if not self.eligible_person_ids:
            return FOLLOW_DEVELOPMENT_STRATEGY

        if all(
            self.skills_by_person_id.get(person_id)
            == self.default_skill(person_id)
            for person_id in self.eligible_person_ids
        ):
            return FOLLOW_DEVELOPMENT_STRATEGY

        selected_skills = {
            self.skills_by_person_id.get(person_id, "")
            for person_id in self.eligible_person_ids
        }

        if len(selected_skills) == 1:
            selected_skill = next(iter(selected_skills))

            if selected_skill in DEVELOPMENT_SKILL_OPTIONS:
                return selected_skill

        return FOLLOW_DEVELOPMENT_STRATEGY

    def refresh_results(self, *arguments):
        query_terms = [
            term
            for term in self.search_value.get().casefold().split()
            if term
        ]
        self.visible_person_ids = [
            person_id
            for person_id in self.person_ids
            if all(
                term
                in self.labels_by_person_id.get(
                    person_id,
                    "Unknown person",
                ).casefold()
                for term in query_terms
            )
        ]
        self.refreshing_results = True
        self.results_list.delete(0, "end")

        for row_index, person_id in enumerate(self.visible_person_ids):
            person_name = self.labels_by_person_id.get(
                person_id,
                "Unknown person",
            )

            if person_id not in self.eligible_person_ids:
                display_text = (
                    f"  {person_name} · cannot earn Eminence"
                )
            elif person_id in self.earned_person_ids:
                display_text = (
                    f"✓ {person_name} · "
                    f"{self.skills_by_person_id[person_id]}"
                )
            else:
                display_text = f"  {person_name}"

            self.results_list.insert("end", display_text)
            self.results_list.itemconfigure(
                row_index,
                background=(
                    FIELD_BACKGROUND
                    if row_index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

            if person_id == self.selected_person_id:
                self.results_list.selection_set(row_index)
                self.results_list.see(row_index)

        if self.selected_person_id not in self.visible_person_ids:
            self.selected_person_id = (
                self.visible_person_ids[0]
                if self.visible_person_ids
                else ""
            )

            if self.selected_person_id:
                self.results_list.selection_set(0)

        self.refreshing_results = False
        self.refresh_count()
        self.refresh_bulk_controls()
        self.load_selected_person()

    def refresh_bulk_controls(self):
        all_people_awarded = bool(self.eligible_person_ids) and (
            self.eligible_person_ids.issubset(self.earned_person_ids)
        )
        self.loading_bulk = True
        self.set_all_value.set(all_people_awarded)
        self.loading_bulk = False
        self.set_all_checkbutton.configure(
            state=(
                "normal"
                if self.eligible_person_ids
                else "disabled"
            )
        )
        self.bulk_skill_select.set_enabled(
            bool(self.eligible_person_ids)
        )

    def refresh_count(self):
        earned_count = len(self.earned_person_ids)
        eligible_count = len(self.eligible_person_ids)
        self.count_value.set(
            f"{earned_count} of {eligible_count} selected"
        )

    def person_selected(self, event=None):
        if self.refreshing_results:
            return

        selected_rows = self.results_list.curselection()

        if not selected_rows:
            return

        self.commit_detail_values()
        self.selected_person_id = self.visible_person_ids[
            selected_rows[0]
        ]
        self.load_selected_person()

    def load_selected_person(self):
        self.loading_detail = True
        selected_person_id = self.selected_person_id

        if not selected_person_id:
            self.selected_person_value.set(
                "No people match this search."
            )
            self.earns_eminence_value.set(False)
            self.earns_eminence_checkbutton.configure(state="disabled")
            self.skill_select.set_enabled(False)
            self.loading_detail = False
            return

        self.selected_person_value.set(
            self.labels_by_person_id.get(
                selected_person_id,
                "Unknown person",
            )
        )
        person_is_eligible = (
            selected_person_id in self.eligible_person_ids
        )
        person_earns_eminence = (
            selected_person_id in self.earned_person_ids
        )
        self.earns_eminence_value.set(person_earns_eminence)
        self.earns_eminence_checkbutton.configure(
            state="normal" if person_is_eligible else "disabled"
        )
        self.skill_value.set(
            self.skills_by_person_id.get(
                selected_person_id,
                DEVELOPMENT_SKILL_OPTIONS[0],
            )
        )
        self.skill_select.set_enabled(
            person_is_eligible and person_earns_eminence
        )
        self.loading_detail = False

    def commit_detail_values(self):
        if self.loading_detail or not self.selected_person_id:
            return

        if self.selected_person_id not in self.eligible_person_ids:
            return

        selected_skill = str(self.skill_value.get() or "").strip()

        if selected_skill in DEVELOPMENT_SKILL_OPTIONS:
            self.skills_by_person_id[
                self.selected_person_id
            ] = selected_skill

    def detail_earning_changed(self):
        if self.loading_detail or not self.selected_person_id:
            return

        if self.selected_person_id not in self.eligible_person_ids:
            return

        if self.earns_eminence_value.get():
            if self.selected_person_id not in self.earned_person_ids:
                self.earned_person_ids.append(self.selected_person_id)

            self.skills_by_person_id.setdefault(
                self.selected_person_id,
                self.default_skill(self.selected_person_id),
            )
        else:
            self.earned_person_ids = [
                person_id
                for person_id in self.earned_person_ids
                if person_id != self.selected_person_id
            ]

        self.refresh_results()

    def detail_skill_changed(self, *arguments):
        self.commit_detail_values()

        if not self.loading_detail and self.selected_person_id:
            self.refresh_results()

    def toggle_selected_person(self, event=None):
        selected_rows = self.results_list.curselection()

        if selected_rows:
            self.selected_person_id = self.visible_person_ids[
                selected_rows[0]
            ]

        if self.selected_person_id not in self.eligible_person_ids:
            return "break"

        self.loading_detail = True
        self.earns_eminence_value.set(
            self.selected_person_id not in self.earned_person_ids
        )
        self.loading_detail = False
        self.detail_earning_changed()
        return "break"

    def award_visible_people(self):
        for person_id in self.visible_person_ids:
            if person_id not in self.eligible_person_ids:
                continue

            if person_id not in self.earned_person_ids:
                self.earned_person_ids.append(person_id)

            self.skills_by_person_id.setdefault(
                person_id,
                self.default_skill(person_id),
            )

        self.refresh_results()

    def clear_visible_people(self):
        visible_person_ids = set(self.visible_person_ids)
        self.earned_person_ids = [
            person_id
            for person_id in self.earned_person_ids
            if person_id not in visible_person_ids
        ]
        self.refresh_results()

    def set_all_eminence_changed(self):
        if self.loading_bulk:
            return

        if self.set_all_value.get():
            self.earned_person_ids = [
                person_id
                for person_id in self.person_ids
                if person_id in self.eligible_person_ids
            ]
            self.apply_bulk_skill_to_all()
        else:
            self.earned_person_ids = []

        self.refresh_results()

    def bulk_skill_changed(self, *arguments):
        if self.loading_bulk or not self.set_all_value.get():
            return

        self.apply_bulk_skill_to_all()
        self.refresh_results()

    def apply_bulk_skill_to_all(self):
        selected_option = str(
            self.bulk_skill_value.get() or ""
        ).strip()

        for person_id in self.person_ids:
            if person_id not in self.eligible_person_ids:
                continue

            self.skills_by_person_id[person_id] = (
                self.default_skill(person_id)
                if selected_option == FOLLOW_DEVELOPMENT_STRATEGY
                else (
                    selected_option
                    if selected_option in DEVELOPMENT_SKILL_OPTIONS
                    else self.default_skill(person_id)
                )
            )

    def save_dialog(self):
        self.commit_detail_values()
        earned_person_ids = [
            person_id
            for person_id in self.person_ids
            if person_id in self.earned_person_ids
            and person_id in self.eligible_person_ids
        ]
        selected_skills = {
            person_id: self.skills_by_person_id.get(
                person_id,
                self.default_skill(person_id),
            )
            for person_id in earned_person_ids
        }
        self.save_command(earned_person_ids, selected_skills)
        self.destroy()

    def clear_search(self, event=None):
        if self.search_value.get():
            self.search_value.set("")
            return "break"

        self.destroy()
        return "break"

    def close_dialog(self, event=None):
        self.destroy()
        return "break"
