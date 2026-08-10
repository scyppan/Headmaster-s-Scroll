import tkinter as tk
from collections import Counter
from functools import partial
from tkinter import messagebox

from mage_maker.sections.development.models import (
    DEVELOPMENT_ABILITY_OPTIONS,
    DEVELOPMENT_SKILL_OPTIONS,
    DEVELOPMENT_SKILLS_BY_ABILITY,
)
from mage_maker.sections.development.traits import (
    TRAIT_DEFINITIONS,
    trait_effect_text,
)
from mage_maker.ui.theme import (
    APP_BACKGROUND,
    BORDER,
    BORDER_SOFT,
    FIELD_BACKGROUND,
    LIST_ALTERNATE,
    PRIMARY,
    PRIMARY_HOVER,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import SoftButton


class InitialSkillBonusDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        required_count,
        selected_skills,
        save_command,
    ):
        super().__init__(parent)
        self.required_count = int(required_count)
        self.selected_skills = list(selected_skills or [])
        self.save_command = save_command
        self.skill_values = {}
        self.skill_bonus_amounts = {
            skill: 0
            for skill in DEVELOPMENT_SKILL_OPTIONS
        }
        self.skill_label_values = {}
        self.skill_checkbuttons = {}
        self.skill_adjustment_frames = {}
        self.skill_decrement_buttons = {}
        self.skill_increment_buttons = {}
        self.selection_summary_value = tk.StringVar()
        self.title("Select Initial Skill Bonuses")
        self.geometry("1120x600")
        self.minsize(980, 520)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.restore_selection()
        self.update_selection_state()
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
        card.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=20,
            pady=20,
        )
        card.grid_rowconfigure(3, weight=1)
        card.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            card,
            text=(
                f"Assign {self.required_count} initial "
                + (
                    "skill bonus point"
                    if self.required_count == 1
                    else "skill bonus points"
                )
            ),
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(15, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        explanation = tk.Label(
            card,
            text=(
                "Check one or more skills, then use −1 and +1 "
                "to distribute every point."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(10),
            anchor="w",
            justify="left",
        )
        explanation.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(4, 12),
        )
        selection_summary = tk.Label(
            card,
            textvariable=self.selection_summary_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        selection_summary.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(0, 7),
        )
        checkbox_panel = tk.Frame(
            card,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=8,
            pady=8,
        )
        checkbox_panel.grid(
            row=3,
            column=0,
            sticky="nsew",
        )
        checkbox_panel.grid_columnconfigure(
            (0, 1, 2, 3),
            weight=1,
            uniform="skill_abilities",
        )
        checkbox_panel.grid_rowconfigure(0, weight=1)

        for ability_index, ability in enumerate(
            DEVELOPMENT_ABILITY_OPTIONS
        ):
            ability_panel = tk.Frame(
                checkbox_panel,
                bg=FIELD_BACKGROUND,
                highlightbackground=BORDER_SOFT,
                highlightthickness=1,
            )
            ability_panel.grid(
                row=0,
                column=ability_index,
                sticky="nsew",
                padx=(
                    0 if ability_index == 0 else 4,
                    0
                    if ability_index
                    == len(DEVELOPMENT_ABILITY_OPTIONS) - 1
                    else 4,
                ),
            )
            ability_panel.grid_columnconfigure(0, weight=1)
            ability_heading = tk.Label(
                ability_panel,
                text=ability,
                bg=SURFACE_MUTED,
                fg=TEXT_DARK,
                font=app_font(11, "bold"),
                anchor="w",
                padx=10,
                pady=8,
            )
            ability_heading.grid(
                row=0,
                column=0,
                sticky="ew",
            )

            for skill_index, skill in enumerate(
                DEVELOPMENT_SKILLS_BY_ABILITY[ability]
            ):
                row_background = (
                    FIELD_BACKGROUND
                    if skill_index % 2 == 0
                    else LIST_ALTERNATE
                )
                skill_row = tk.Frame(
                    ability_panel,
                    bg=row_background,
                    padx=4,
                    pady=3,
                )
                skill_row.grid(
                    row=skill_index + 1,
                    column=0,
                    sticky="ew",
                )
                skill_row.grid_columnconfigure(0, weight=1)
                variable = tk.BooleanVar(value=False)
                label_value = tk.StringVar(value=skill)
                checkbutton = tk.Checkbutton(
                    skill_row,
                    textvariable=label_value,
                    variable=variable,
                    command=partial(
                        self.selection_changed,
                        skill,
                    ),
                    bg=row_background,
                    fg=TEXT_DARK,
                    activebackground=row_background,
                    activeforeground=TEXT_DARK,
                    disabledforeground=TEXT_MUTED,
                    selectcolor=FIELD_BACKGROUND,
                    font=app_font(10),
                    anchor="w",
                    borderwidth=0,
                    highlightthickness=0,
                    padx=6,
                    pady=5,
                )
                checkbutton.grid(
                    row=0,
                    column=0,
                    sticky="ew",
                )
                adjustment_frame = tk.Frame(
                    skill_row,
                    bg=row_background,
                )
                adjustment_frame.grid(
                    row=0,
                    column=1,
                    sticky="e",
                    padx=(4, 2),
                )
                decrement_button = SoftButton(
                    adjustment_frame,
                    text="−1",
                    command=partial(
                        self.adjust_skill_bonus,
                        skill,
                        -1,
                    ),
                    background=row_background,
                    width=34,
                    height=27,
                    radius=8,
                    font=app_font(9, "bold"),
                    padx=4,
                )
                decrement_button.pack(
                    side="left",
                    padx=(0, 3),
                )
                increment_button = SoftButton(
                    adjustment_frame,
                    text="+1",
                    command=partial(
                        self.adjust_skill_bonus,
                        skill,
                        1,
                    ),
                    background=row_background,
                    width=34,
                    height=27,
                    radius=8,
                    font=app_font(9, "bold"),
                    padx=4,
                )
                increment_button.pack(side="left")
                adjustment_frame.grid_remove()
                self.skill_values[skill] = variable
                self.skill_label_values[skill] = label_value
                self.skill_checkbuttons[skill] = checkbutton
                self.skill_adjustment_frames[skill] = (
                    adjustment_frame
                )
                self.skill_decrement_buttons[skill] = (
                    decrement_button
                )
                self.skill_increment_buttons[skill] = (
                    increment_button
                )
        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(
            row=4,
            column=0,
            sticky="ew",
            pady=(14, 0),
        )
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.destroy,
            background=SURFACE,
            width=88,
            height=38,
        )
        cancel_button.pack(side="right", padx=(6, 0))
        self.save_button = SoftButton(
            footer,
            text="Save selection",
            command=self.save_selection,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=132,
            height=38,
        )
        self.save_button.pack(side="right")

    def restore_selection(self):
        selected_counts = Counter(self.selected_skills)
        remaining_count = self.required_count

        for skill in DEVELOPMENT_SKILL_OPTIONS:
            restored_amount = min(
                selected_counts.get(skill, 0),
                remaining_count,
            )
            self.skill_bonus_amounts[skill] = restored_amount
            self.skill_values[skill].set(restored_amount > 0)
            remaining_count -= restored_amount

    def selection_changed(self, changed_skill=None):
        if changed_skill not in self.skill_values:
            self.update_selection_state()
            return

        is_selected = self.skill_values[changed_skill].get()
        current_amount = self.skill_bonus_amounts[changed_skill]
        selected_count = sum(self.skill_bonus_amounts.values())

        if is_selected and current_amount == 0:
            if selected_count >= self.required_count:
                self.skill_values[changed_skill].set(False)
            else:
                self.skill_bonus_amounts[changed_skill] = 1
        elif not is_selected:
            self.skill_bonus_amounts[changed_skill] = 0

        self.update_selection_state()

    def adjust_skill_bonus(self, skill, change):
        if skill not in self.skill_bonus_amounts:
            return

        current_amount = self.skill_bonus_amounts[skill]
        selected_count = sum(self.skill_bonus_amounts.values())

        if change > 0:
            if (
                selected_count >= self.required_count
                or current_amount >= self.required_count
            ):
                return

            current_amount += 1
        elif change < 0:
            if current_amount <= 0:
                return

            current_amount -= 1
        else:
            return

        self.skill_bonus_amounts[skill] = current_amount
        self.skill_values[skill].set(current_amount > 0)
        self.update_selection_state()

    def selected_skill_bonuses(self):
        selected_skills = []

        for skill in DEVELOPMENT_SKILL_OPTIONS:
            selected_skills.extend(
                [skill] * self.skill_bonus_amounts[skill]
            )

        return selected_skills

    def update_selection_state(self):
        selected_count = sum(self.skill_bonus_amounts.values())
        selection_is_full = (
            selected_count >= self.required_count
        )
        self.selection_summary_value.set(
            f"{selected_count} of {self.required_count} "
            "bonus points assigned"
        )
        self.save_button.set_enabled(
            selected_count == self.required_count
        )

        for skill, checkbutton in self.skill_checkbuttons.items():
            amount = self.skill_bonus_amounts[skill]
            self.skill_label_values[skill].set(
                f"{skill} +{amount}"
                if amount
                else skill
            )
            checkbutton.configure(
                state=(
                    "disabled"
                    if selection_is_full
                    and amount == 0
                    else "normal"
                )
            )

            if amount:
                self.skill_adjustment_frames[skill].grid()
            else:
                self.skill_adjustment_frames[skill].grid_remove()

            self.skill_decrement_buttons[skill].set_enabled(
                amount > 0
            )
            self.skill_increment_buttons[skill].set_enabled(
                not selection_is_full
                and amount < self.required_count
            )

    def save_selection(self):
        selection = self.selected_skill_bonuses()

        if len(selection) != self.required_count:
            messagebox.showinfo(
                "Select skill bonuses",
                (
                    f"Assign exactly {self.required_count} "
                    + (
                        "skill bonus point."
                        if self.required_count == 1
                        else "skill bonus points."
                    )
                ),
                parent=self,
            )
            return

        self.save_command(selection)
        self.destroy()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"


class TraitSelectionDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        required_count,
        selected_traits,
        save_command,
    ):
        super().__init__(parent)
        self.required_count = int(required_count)
        self.selected_traits = list(selected_traits or [])
        self.save_command = save_command
        self.trait_values = {}
        self.trait_checkbuttons = {}
        self.selection_summary_value = tk.StringVar()
        self.title("Select Initial Traits")
        self.geometry("1180x760")
        self.minsize(1040, 680)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.restore_selection()
        self.update_selection_state()
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
        card.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=20,
            pady=20,
        )
        card.grid_rowconfigure(2, weight=1)
        card.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            card,
            text=(
                f"Select {self.required_count} "
                + (
                    "trait"
                    if self.required_count == 1
                    else "traits"
                )
            ),
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(15, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        selection_summary = tk.Label(
            card,
            textvariable=self.selection_summary_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        selection_summary.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(5, 10),
        )
        body = tk.Frame(card, bg=SURFACE)
        body.grid(row=2, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        checkbox_panel = tk.Frame(
            body,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=8,
            pady=8,
        )
        checkbox_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        checkbox_panel.grid_columnconfigure(
            (0, 1, 2),
            weight=1,
            uniform="trait_checks",
        )
        trait_columns = 3
        trait_rows = (
            len(TRAIT_DEFINITIONS)
            + trait_columns
            - 1
        ) // trait_columns

        for row_index in range(trait_rows):
            row_background = (
                FIELD_BACKGROUND
                if row_index % 2 == 0
                else LIST_ALTERNATE
            )
            checkbox_panel.grid_rowconfigure(
                row_index,
                weight=1,
            )

            for column_index in range(trait_columns):
                option_index = (
                    row_index * trait_columns
                    + column_index
                )

                if option_index >= len(TRAIT_DEFINITIONS):
                    continue

                definition = TRAIT_DEFINITIONS[option_index]
                trait_name = definition["name"]
                variable = tk.BooleanVar(value=False)
                checkbutton = tk.Checkbutton(
                    checkbox_panel,
                    text=(
                        f"{trait_name}\n"
                        f"{trait_effect_text(definition)}"
                    ),
                    variable=variable,
                    command=partial(
                        self.selection_changed,
                        option_index,
                    ),
                    bg=row_background,
                    fg=TEXT_DARK,
                    activebackground=row_background,
                    activeforeground=TEXT_DARK,
                    disabledforeground=TEXT_MUTED,
                    selectcolor=FIELD_BACKGROUND,
                    font=app_font(10),
                    anchor="nw",
                    justify="left",
                    wraplength=310,
                    borderwidth=0,
                    highlightthickness=0,
                    padx=8,
                    pady=7,
                )
                checkbutton.grid(
                    row=row_index,
                    column=column_index,
                    sticky="nsew",
                )
                self.trait_values[trait_name] = variable
                self.trait_checkbuttons[trait_name] = checkbutton
        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(14, 0),
        )
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.destroy,
            background=SURFACE,
            width=88,
            height=38,
        )
        cancel_button.pack(side="right", padx=(6, 0))
        self.save_button = SoftButton(
            footer,
            text="Save selection",
            command=self.save_selection,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=132,
            height=38,
        )
        self.save_button.pack(side="right")

    def restore_selection(self):
        restored_count = 0

        for definition in TRAIT_DEFINITIONS:
            trait_name = definition["name"]
            should_select = (
                trait_name in self.selected_traits
                and restored_count < self.required_count
            )
            self.trait_values[trait_name].set(should_select)

            if should_select:
                restored_count += 1

    def selection_changed(self, changed_index=None):
        selection = [
            definition["name"]
            for definition in TRAIT_DEFINITIONS
            if self.trait_values[definition["name"]].get()
        ]

        if (
            len(selection) > self.required_count
            and changed_index is not None
            and 0 <= int(changed_index) < len(TRAIT_DEFINITIONS)
        ):
            changed_name = TRAIT_DEFINITIONS[
                int(changed_index)
            ]["name"]
            self.trait_values[changed_name].set(False)

        self.update_selection_state()

    def update_selection_state(self):
        selected_traits = [
            definition["name"]
            for definition in TRAIT_DEFINITIONS
            if self.trait_values[definition["name"]].get()
        ]
        selected_count = len(selected_traits)
        selection_is_full = (
            selected_count >= self.required_count
        )
        self.selection_summary_value.set(
            f"{selected_count} of {self.required_count} selected"
        )
        self.save_button.set_enabled(
            selected_count == self.required_count
        )

        for (
            trait_name,
            checkbutton,
        ) in self.trait_checkbuttons.items():
            checkbutton.configure(
                state=(
                    "disabled"
                    if selection_is_full
                    and trait_name not in selected_traits
                    else "normal"
                )
            )

    def save_selection(self):
        selection = [
            definition["name"]
            for definition in TRAIT_DEFINITIONS
            if self.trait_values[definition["name"]].get()
        ]

        if len(selection) != self.required_count:
            messagebox.showinfo(
                "Select traits",
                (
                    f"Select exactly {self.required_count} "
                    + (
                        "trait."
                        if self.required_count == 1
                        else "traits."
                    )
                ),
                parent=self,
            )
            return

        self.save_command(selection)
        self.destroy()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"
