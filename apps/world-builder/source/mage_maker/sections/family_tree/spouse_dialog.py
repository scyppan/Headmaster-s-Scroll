import tkinter as tk
from tkinter import messagebox

from mage_maker.sections.family_tree.relationships import (
    format_person_date,
    person_can_give_birth,
)
from mage_maker.sections.family_tree.spouse_relationships import (
    empty_spouse_relationship,
    normalize_spouse_relationships,
)
from mage_maker.sections.family_tree.spouse_defaults import (
    prepare_new_spouse_values,
)
from mage_maker.ui.theme import (
    APP_BACKGROUND,
    BORDER,
    BORDER_SOFT,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    FIELD_BACKGROUND,
    LIST_ALTERNATE,
    LIST_SELECTED,
    PRIMARY,
    PRIMARY_HOVER,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import (
    CalendarAdoptionNotice,
    LabeledEntry,
    RoundedEntry,
    SoftButton,
)


class SpousePickerDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        focus_person,
        candidates,
        save_command,
        create_person_command,
        children=None,
        close_command=None,
    ):
        super().__init__(parent)
        self.focus_person = dict(focus_person or {})
        self.candidates = list(candidates or [])
        self.visible_candidates = []
        self.save_command = save_command
        self.create_person_command = create_person_command
        self.close_command = close_command
        self.closed = False
        self.new_person_dialog = None
        self.existing_children = [
            dict(child)
            for child in children or []
            if isinstance(child, dict)
        ]
        self.search_value = tk.StringVar()
        self.married_value = tk.BooleanVar(value=False)
        self.divorced_value = tk.BooleanVar(value=False)
        self.marriage_year_value = tk.StringVar()
        self.marriage_month_value = tk.StringVar()
        self.marriage_day_value = tk.StringVar()
        self.divorce_year_value = tk.StringVar()
        self.divorce_month_value = tk.StringVar()
        self.divorce_day_value = tk.StringVar()
        self.match_value = tk.StringVar(value="Select a person to see location evidence.")
        self.search_value.trace_add("write", self.filter_candidates)
        self.divorced_value.trace_add("write", self.divorce_changed)

        self.title("Add spouse")
        self.geometry("860x650")
        self.minsize(760, 590)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)

        card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        card.grid_rowconfigure(2, weight=1)
        card.grid_columnconfigure(0, weight=1)

        heading = tk.Label(
            card,
            text="Add spouse",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(14, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        explanation = tk.Label(
            card,
            text=(
                "Showing people with the opposite Can give birth assignment within seven birth years. "
                "People living in the same location during overlapping years are listed first."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=680,
        )
        explanation.grid(row=1, column=0, sticky="ew", pady=(4, 12))

        workspace = tk.Frame(card, bg=SURFACE)
        workspace.grid(row=2, column=0, sticky="nsew")
        workspace.grid_rowconfigure(0, weight=1)
        workspace.grid_columnconfigure(0, weight=5, uniform="spouse")
        workspace.grid_columnconfigure(1, weight=4, uniform="spouse")

        self.build_candidate_panel(workspace)
        self.build_relationship_panel(workspace)

        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        enter_new_button = SoftButton(
            footer,
            text="Enter new",
            command=self.open_new_person_dialog,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=104,
            height=36,
        )
        enter_new_button.pack(side="left")
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=SURFACE,
            width=88,
            height=36,
        )
        cancel_button.pack(side="right", padx=(6, 0))
        okay_button = SoftButton(
            footer,
            text="Okay",
            command=self.save_spouse,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=104,
            height=36,
        )
        okay_button.pack(side="right")

        self.bind("<Escape>", self.close_dialog)
        self.bind("<Return>", self.save_spouse)
        self.filter_candidates()
        self.after_idle(self.focus_search)

    def build_candidate_panel(self, parent):
        panel = tk.Frame(
            parent,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=12,
            pady=12,
        )
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        search = RoundedEntry(
            panel,
            textvariable=self.search_value,
            background=SURFACE_MUTED,
            height=38,
        )
        search.grid(row=0, column=0, sticky="ew")
        self.search_entry = search

        count_text = (
            "No matching people. Enter a Birth year on the profile, or use Enter new."
            if not self.candidates
            else f"{len(self.candidates)} matching candidate(s)"
        )
        count_label = tk.Label(
            panel,
            text=count_text,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
            justify="left",
            wraplength=390,
        )
        count_label.grid(row=1, column=0, sticky="ew", pady=(5, 8))

        list_frame = tk.Frame(panel, bg=SURFACE_MUTED)
        list_frame.grid(row=2, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.listbox = tk.Listbox(
            list_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
            font=app_font(9),
            activestyle="none",
            exportselection=False,
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", self.candidate_selected)
        self.listbox.bind("<Double-Button-1>", self.save_spouse)
        scrollbar = tk.Scrollbar(list_frame, command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scrollbar.set)

    def build_relationship_panel(self, parent):
        panel = tk.Frame(
            parent,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=14,
            pady=12,
        )
        panel.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        panel.grid_columnconfigure(0, weight=1)

        match_label = tk.Label(
            panel,
            textvariable=self.match_value,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
            justify="left",
            wraplength=310,
            padx=10,
            pady=9,
        )
        match_label.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        married_check = tk.Checkbutton(
            panel,
            text="They were married",
            variable=self.married_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            activebackground=SURFACE_MUTED,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(10, "bold"),
            anchor="w",
            borderwidth=0,
            highlightthickness=0,
        )
        married_check.grid(row=1, column=0, sticky="w")
        marriage_date = self.build_date_row(panel, "Marriage date", "marriage")
        marriage_date.grid(row=2, column=0, sticky="ew", pady=(5, 14))

        divorced_check = tk.Checkbutton(
            panel,
            text="They divorced",
            variable=self.divorced_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            activebackground=SURFACE_MUTED,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(10, "bold"),
            anchor="w",
            borderwidth=0,
            highlightthickness=0,
        )
        divorced_check.grid(row=3, column=0, sticky="w")
        divorce_date = self.build_date_row(panel, "Divorce date", "divorce")
        divorce_date.grid(row=4, column=0, sticky="ew", pady=(5, 0))
        calendar_notice = CalendarAdoptionNotice(
            panel,
            background=SURFACE_MUTED,
            wraplength=500,
            date_variables=(
                (
                    self.marriage_year_value,
                    self.marriage_month_value,
                    self.marriage_day_value,
                ),
                (
                    self.divorce_year_value,
                    self.divorce_month_value,
                    self.divorce_day_value,
                ),
            ),
        )
        calendar_notice.grid(
            row=5,
            column=0,
            sticky="w",
            pady=(6, 0),
        )

    def build_date_row(self, parent, label_text, prefix):
        frame = tk.Frame(parent, bg=SURFACE_MUTED)
        frame.grid_columnconfigure((0, 1, 2), weight=1)
        heading = tk.Label(
            frame,
            text=label_text,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(8, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        year_field = LabeledEntry(
            frame,
            "Year",
            getattr(self, f"{prefix}_year_value"),
            background=SURFACE_MUTED,
        )
        year_field.grid(row=1, column=0, sticky="ew", padx=(0, 5))
        month_field = LabeledEntry(
            frame,
            "Month",
            getattr(self, f"{prefix}_month_value"),
            background=SURFACE_MUTED,
        )
        month_field.grid(row=1, column=1, sticky="ew", padx=5)
        day_field = LabeledEntry(
            frame,
            "Day",
            getattr(self, f"{prefix}_day_value"),
            background=SURFACE_MUTED,
        )
        day_field.grid(row=1, column=2, sticky="ew", padx=(5, 0))
        return frame

    def filter_candidates(self, *arguments):
        query = self.search_value.get().strip().casefold()
        self.visible_candidates = [
            person
            for person in self.candidates
            if not query
            or query in str(person.get("displayed_name", "")).casefold()
            or query in str(person.get("_spouse_match", "")).casefold()
            or query in str(person.get("_spouse_recent_location", "")).casefold()
        ]
        self.listbox.delete(0, "end")

        for index, person in enumerate(self.visible_candidates):
            recent_location = str(
                person.get("_spouse_recent_location", "") or ""
            ).strip()
            location_text = f" ({recent_location})" if recent_location else ""
            self.listbox.insert(
                "end",
                f"{format_person_date(person)}: "
                f"{person.get('displayed_name', 'Unnamed')}{location_text}",
            )
            self.listbox.itemconfigure(
                index,
                background=FIELD_BACKGROUND if index % 2 == 0 else LIST_ALTERNATE,
            )

    def candidate_selected(self, event=None):
        selected = self.listbox.curselection()

        if not selected:
            return

        person = self.visible_candidates[selected[0]]
        gap = person.get("_spouse_age_gap", 0)
        self.match_value.set(
            f"{person.get('_spouse_match', '')}\nBirth-year difference: {gap}"
        )

    def divorce_changed(self, *arguments):
        if self.divorced_value.get():
            self.married_value.set(True)

    def relationship_values(self, person_id):
        relationship = empty_spouse_relationship(person_id)
        relationship.update(
            {
                "married": self.married_value.get(),
                "marriage_year": self.marriage_year_value.get(),
                "marriage_month": self.marriage_month_value.get(),
                "marriage_day": self.marriage_day_value.get(),
                "divorced": self.divorced_value.get(),
                "divorce_year": self.divorce_year_value.get(),
                "divorce_month": self.divorce_month_value.get(),
                "divorce_day": self.divorce_day_value.get(),
            }
        )
        return normalize_spouse_relationships([relationship])[0]

    def save_spouse(self, event=None):
        selected = self.listbox.curselection()

        if not selected:
            messagebox.showinfo("Select a spouse", "Select a person first.", parent=self)
            return

        person = self.visible_candidates[selected[0]]
        person_id = str(person.get("record_id", "") or "")

        try:
            relationship = self.relationship_values(person_id)
            self.save_command(relationship)
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror("Cannot add spouse", str(error), parent=self)
            return

        self.close_dialog()

    def open_new_person_dialog(self):
        if self.new_person_dialog is not None:
            try:
                if self.new_person_dialog.winfo_exists():
                    self.new_person_dialog.deiconify()
                    self.new_person_dialog.lift()
                    self.new_person_dialog.after_idle(
                        self.new_person_dialog.focus_name
                    )
                    return
            except tk.TclError:
                pass

            self.new_person_dialog = None

        self.new_person_dialog = NewSpousePersonDialog(
            self,
            self.focus_person,
            self.create_new_person,
            self.existing_children,
        )

    def new_person_dialog_closed(self):
        self.new_person_dialog = None

        if not self.closed and self.winfo_exists():
            self.deiconify()
            self.lift()
            self.after_idle(self.focus_search)

    def create_new_person(self, values):
        try:
            created_person = self.create_person_command(values)
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror("Cannot add character", str(error), parent=self)
            return None

        candidate = dict(created_person)
        candidate["_spouse_age_gap"] = self.new_person_age_gap(candidate)
        candidate["_spouse_location_match"] = False
        candidate["_spouse_match"] = "New character entry"
        self.candidates.append(candidate)
        self.filter_candidates()
        self.search_value.set(str(created_person.get("displayed_name", "")))
        self.filter_candidates()

        if self.visible_candidates:
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(0)
            self.listbox.see(0)
            self.candidate_selected()

        return created_person

    def new_person_age_gap(self, person):
        try:
            focus_year = int(self.focus_person.get("birth_year"))
            person_year = int(person.get("birth_year"))
        except (TypeError, ValueError):
            return 0

        return abs(person_year - focus_year)

    def close_dialog(self, event=None):
        if self.closed:
            return "break"

        self.closed = True
        nested_dialog = self.new_person_dialog
        self.new_person_dialog = None

        if nested_dialog is not None:
            try:
                if nested_dialog.winfo_exists():
                    nested_dialog.destroy()
            except tk.TclError:
                pass

        self.destroy()

        if self.close_command is not None:
            self.close_command()

        return "break"

    def focus_search(self):
        self.search_entry.focus_set()


class NewSpousePersonDialog(tk.Toplevel):
    def __init__(self, parent, focus_person, save_command, children=None):
        super().__init__(parent)
        self.owner_dialog = parent
        self.focus_person = dict(focus_person or {})
        self.save_command = save_command
        self.existing_children = [
            dict(child)
            for child in children or []
            if isinstance(child, dict)
        ]
        self.displayed_name_value = tk.StringVar()
        self.can_give_birth_value = tk.BooleanVar(
            value=not person_can_give_birth(self.focus_person)
        )
        self.birth_year_value = tk.StringVar()
        self.birth_month_value = tk.StringVar()
        self.birth_day_value = tk.StringVar()
        self.deceased_value = tk.BooleanVar(value=False)
        self.death_year_value = tk.StringVar()
        self.death_month_value = tk.StringVar()
        self.death_day_value = tk.StringVar()
        self.deceased_value.trace_add("write", self.deceased_changed)

        self.title("Enter new spouse")
        self.geometry("560x590")
        self.resizable(False, False)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)

        card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        card.grid_columnconfigure(0, weight=1)

        heading = tk.Label(
            card,
            text="Enter a new spouse",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(13, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        name_field = LabeledEntry(
            card,
            "Displayed name",
            self.displayed_name_value,
            background=SURFACE,
        )
        self.name_field = name_field
        name_field.grid(row=1, column=0, sticky="ew", pady=(12, 10))

        can_give_birth_check = tk.Checkbutton(
            card,
            text="Can give birth",
            variable=self.can_give_birth_value,
            state="disabled",
            disabledforeground=TEXT_DARK,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
            anchor="w",
            borderwidth=0,
            highlightthickness=0,
        )
        can_give_birth_check.grid(row=2, column=0, sticky="w", pady=(0, 10))

        birth_frame = tk.Frame(card, bg=SURFACE)
        birth_frame.grid(row=3, column=0, sticky="ew")
        birth_frame.grid_columnconfigure((0, 1, 2), weight=1)
        year_field = LabeledEntry(
            birth_frame,
            "Birth year",
            self.birth_year_value,
            background=SURFACE,
        )
        year_field.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        month_field = LabeledEntry(
            birth_frame,
            "Month",
            self.birth_month_value,
            background=SURFACE,
        )
        month_field.grid(row=0, column=1, sticky="ew", padx=5)
        day_field = LabeledEntry(
            birth_frame,
            "Day",
            self.birth_day_value,
            background=SURFACE,
        )
        day_field.grid(row=0, column=2, sticky="ew", padx=(5, 0))
        calendar_notice = CalendarAdoptionNotice(
            birth_frame,
            background=SURFACE,
            wraplength=480,
            date_variables=(
                self.birth_year_value,
                self.birth_month_value,
                self.birth_day_value,
            ),
        )
        calendar_notice.grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(5, 0),
        )

        deceased_check = tk.Checkbutton(
            card,
            text="Dead",
            variable=self.deceased_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
            anchor="w",
            borderwidth=0,
            highlightthickness=0,
        )
        deceased_check.grid(row=4, column=0, sticky="w", pady=(12, 0))

        self.death_frame = tk.Frame(card, bg=SURFACE)
        self.death_frame.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        self.death_frame.grid_columnconfigure((0, 1, 2), weight=1)
        death_heading = tk.Label(
            self.death_frame,
            text="Date of death",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        death_heading.grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(0, 5),
        )
        death_year_field = LabeledEntry(
            self.death_frame,
            "Year",
            self.death_year_value,
            background=SURFACE,
        )
        death_year_field.grid(row=1, column=0, sticky="ew", padx=(0, 5))
        death_month_field = LabeledEntry(
            self.death_frame,
            "Month",
            self.death_month_value,
            background=SURFACE,
        )
        death_month_field.grid(row=1, column=1, sticky="ew", padx=5)
        death_day_field = LabeledEntry(
            self.death_frame,
            "Day",
            self.death_day_value,
            background=SURFACE,
        )
        death_day_field.grid(row=1, column=2, sticky="ew", padx=(5, 0))
        self.death_frame.grid_remove()

        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(row=6, column=0, sticky="e", pady=(18, 0))
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=SURFACE,
            width=88,
            height=36,
        )
        cancel_button.pack(side="left", padx=(0, 6))
        okay_button = SoftButton(
            footer,
            text="Okay",
            command=self.save_person,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=104,
            height=36,
        )
        okay_button.pack(side="left")

        self.bind("<Escape>", self.close_dialog)
        self.bind("<Return>", self.save_person)
        self.after_idle(self.focus_name)

    def save_person(self, event=None):
        displayed_name = self.displayed_name_value.get().strip()

        if not displayed_name:
            messagebox.showerror(
                "Displayed name required",
                "Enter a displayed name for the character.",
                parent=self,
            )
            return

        values = {
            "displayed_name": displayed_name,
            "birth_year": self.birth_year_value.get(),
            "birth_month": self.birth_month_value.get(),
            "birth_day": self.birth_day_value.get(),
            "can_give_birth": self.can_give_birth_value.get(),
            "deceased": self.deceased_value.get(),
            "death_year": (
                self.death_year_value.get() if self.deceased_value.get() else ""
            ),
            "death_month": (
                self.death_month_value.get() if self.deceased_value.get() else ""
            ),
            "death_day": (
                self.death_day_value.get() if self.deceased_value.get() else ""
            ),
        }

        try:
            values = prepare_new_spouse_values(
                self.focus_person,
                self.existing_children,
                values,
            )
        except (TypeError, ValueError) as error:
            messagebox.showerror("Cannot add spouse", str(error), parent=self)
            return

        created_person = self.save_command(values)

        if created_person is not None:
            self.close_dialog()

    def deceased_changed(self, *arguments):
        if self.deceased_value.get():
            self.death_frame.grid()
        else:
            self.death_frame.grid_remove()

    def focus_name(self):
        self.name_field.control.focus_set()

    def close_dialog(self, event=None):
        self.destroy()

        try:
            if self.owner_dialog.winfo_exists():
                self.owner_dialog.new_person_dialog_closed()
        except tk.TclError:
            pass

        return "break"
