import tkinter as tk
from tkinter import messagebox

from mage_maker.core.dates import normalize_historical_date_parts
from mage_maker.sections.events.dialog import EventLocationPickerDialog
from mage_maker.sections.family_tree.relationships import format_person_date
from mage_maker.sections.locations.models import recent_location_label
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
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import LabeledEntry, RoundedEntry, SoftButton


class RelationshipPickerDialog(tk.Toplevel):
    VISIBLE_RESULT_LIMIT = 300

    def __init__(
        self,
        parent,
        title,
        heading,
        explanation,
        primary_people,
        alternate_people,
        alternate_label,
        alternate_note,
        select_label,
        select_command,
        create_command,
        new_profile_label,
        new_profile_explanation,
        status_options=(),
        status_command=None,
        locations=(),
        create_location_command=None,
    ):
        super().__init__(parent)
        self.primary_people = list(primary_people)
        self.alternate_people = list(alternate_people)
        self.alternate_ids = {
            str(person.get("record_id", "")) for person in self.alternate_people
        }
        self.select_command = select_command
        self.create_command = create_command
        self.new_profile_label = new_profile_label
        self.new_profile_explanation = new_profile_explanation
        self.status_options = list(status_options or ())
        self.status_command = status_command
        self.locations = [
            dict(location)
            for location in locations or ()
            if isinstance(location, dict)
        ]
        self.create_location_command = create_location_command
        self.visible_people = []
        self.search_value = tk.StringVar()
        self.show_alternate_value = tk.BooleanVar(value=False)
        self.search_value.trace_add("write", self.filter_people)
        self.show_alternate_value.trace_add("write", self.filter_people)

        self.title(title)
        self.geometry("600x600")
        self.minsize(540, 500)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        card.grid_rowconfigure(6, weight=1)
        card.grid_columnconfigure(0, weight=1)

        heading_label = tk.Label(
            card,
            text=heading,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(14, "bold"),
            anchor="w",
        )
        heading_label.grid(row=0, column=0, sticky="ew")
        explanation_label = tk.Label(
            card,
            text=explanation,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=520,
        )
        explanation_label.grid(row=1, column=0, sticky="ew", pady=(4, 10))

        search = RoundedEntry(
            card,
            textvariable=self.search_value,
            background=SURFACE,
            height=38,
        )
        search.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.search_entry = search

        alternate_check = tk.Checkbutton(
            card,
            text=alternate_label,
            variable=self.show_alternate_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            disabledforeground=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
            borderwidth=0,
            highlightthickness=0,
            state="normal" if self.alternate_people else "disabled",
        )
        alternate_check.grid(row=3, column=0, sticky="w")
        alternate_note_label = tk.Label(
            card,
            text=alternate_note,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
            justify="left",
            wraplength=520,
        )
        alternate_note_label.grid(row=4, column=0, sticky="ew", pady=(1, 9))

        status_row = tk.Frame(card, bg=SURFACE)
        status_row.grid(row=5, column=0, sticky="ew", pady=(0, 9))

        for label, status in self.status_options:
            button = SoftButton(
                status_row,
                text=label,
                command=lambda value=status: self.select_status(value),
                background=SURFACE,
                fill=BUTTON_SOFT,
                hover_fill=BUTTON_SOFT_HOVER,
                foreground=TEXT_DARK,
                width=max(96, len(label) * 8 + 24),
                height=32,
            )
            button.pack(side="left", padx=(0, 6))

        if not self.status_options:
            status_row.grid_remove()

        list_frame = tk.Frame(card, bg=SURFACE)
        list_frame.grid(row=6, column=0, sticky="nsew")
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
            font=app_font(10),
            activestyle="none",
            exportselection=False,
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind("<Double-Button-1>", self.select_person)
        scrollbar = tk.Scrollbar(list_frame, command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scrollbar.set)

        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(row=7, column=0, sticky="ew", pady=(14, 0))

        if self.create_command is not None:
            enter_new_button = SoftButton(
                footer,
                text="Enter new",
                command=self.open_basic_person_dialog,
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
            command=self.destroy,
            background=SURFACE,
            width=88,
            height=36,
        )
        cancel_button.pack(side="right", padx=(6, 0))
        select_button = SoftButton(
            footer,
            text=select_label,
            command=self.select_person,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=max(116, len(select_label) * 8 + 24),
            height=36,
        )
        select_button.pack(side="right")

        self.bind("<Escape>", self.close_dialog)
        self.bind("<Return>", self.select_person)
        self.filter_people()
        self.after_idle(self.focus_search)

    def filter_people(self, *arguments):
        query = self.search_value.get().strip().casefold()
        self.visible_people = self.matching_people(
            self.primary_people,
            self.alternate_people,
            query,
            self.show_alternate_value.get(),
        )
        self.listbox.delete(0, "end")

        for index, person in enumerate(self.visible_people):
            self.listbox.insert(
                "end",
                f"{format_person_date(person)}: {person.get('displayed_name', 'Unnamed')}",
            )
            self.listbox.itemconfigure(
                index,
                background=FIELD_BACKGROUND if index % 2 == 0 else LIST_ALTERNATE,
            )

    @classmethod
    def matching_people(
        cls,
        primary_people,
        alternate_people,
        query="",
        show_alternate=False,
    ):
        """Return displayed-name matches from either parent-role list.

        A typed name is an explicit lookup, so it must search birthing and
        non-birthing candidates together even when the optional alternate-role
        checkbox is not already enabled.  The selected record still retains
        its alternate-role flag and the existing confirmation/update rules.
        """
        normalized_query = str(query or "").strip().casefold()
        available_people = list(primary_people or ())

        if show_alternate or normalized_query:
            available_people.extend(alternate_people or ())

        unique_people = []
        seen_ids = set()
        for person in available_people:
            record_id = str(person.get("record_id", "") or "").strip()
            identity = record_id or id(person)
            if identity in seen_ids:
                continue
            seen_ids.add(identity)
            unique_people.append(person)

        if normalized_query:
            unique_people = [
                person
                for person in unique_people
                if normalized_query
                in str(person.get("displayed_name", "") or "").casefold()
            ]
            unique_people.sort(
                key=lambda person: (
                    str(person.get("displayed_name", "") or "").casefold()
                    != normalized_query,
                    str(person.get("displayed_name", "") or "").casefold(),
                )
            )

        return unique_people[: cls.VISIBLE_RESULT_LIMIT]

    def select_person(self, event=None):
        selected = self.listbox.curselection()

        if not selected:
            messagebox.showinfo("Select a person", "Select a person first.", parent=self)
            return

        person = self.visible_people[selected[0]]
        record_id = str(person.get("record_id", ""))

        try:
            self.select_command(record_id, record_id in self.alternate_ids)
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror("Cannot select person", str(error), parent=self)
            return

        self.destroy()

    def open_basic_person_dialog(self):
        BasicRelationshipDialog(
            self,
            self.new_profile_label,
            self.new_profile_explanation,
            self.create_basic_person,
            locations=self.locations,
            create_location_command=self.create_location_command,
        )

    def create_basic_person(self, profile_values):
        created_person = self.create_command(profile_values)
        self.after_idle(self.destroy)
        return created_person

    def select_status(self, status):
        if self.status_command is None:
            return

        try:
            self.status_command(str(status or "unknown"))
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot set parent status",
                str(error),
                parent=self,
            )
            return

        self.destroy()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"

    def focus_search(self):
        self.search_entry.focus_set()


class ParentCouplePickerDialog(tk.Toplevel):
    """Search existing spouse pairs and assign both parents in one action."""

    VISIBLE_RESULT_LIMIT = 300

    def __init__(self, parent, couples, select_command):
        super().__init__(parent)
        self.couples = list(couples or ())
        self.visible_couples = []
        self.select_command = select_command
        self.search_value = tk.StringVar()
        self.search_value.trace_add("write", self.filter_couples)

        self.title("Choose parent couple")
        self.geometry("640x560")
        self.minsize(540, 460)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        card.grid_rowconfigure(3, weight=1)
        card.grid_columnconfigure(0, weight=1)

        tk.Label(
            card,
            text="Choose both parents",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(14, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        tk.Label(
            card,
            text=(
                "Search either spouse's displayed name. Both parent roles "
                "will be assigned together."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 10))

        self.search_entry = RoundedEntry(
            card,
            textvariable=self.search_value,
            background=SURFACE,
            height=38,
        )
        self.search_entry.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        list_frame = tk.Frame(card, bg=SURFACE)
        list_frame.grid(row=3, column=0, sticky="nsew")
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
            font=app_font(10),
            activestyle="none",
            exportselection=False,
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind("<Double-Button-1>", self.select_couple)
        scrollbar = tk.Scrollbar(list_frame, command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scrollbar.set)

        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(row=4, column=0, sticky="e", pady=(14, 0))
        SoftButton(
            footer,
            text="Cancel",
            command=self.destroy,
            background=SURFACE,
            width=88,
            height=36,
        ).pack(side="left", padx=(0, 6))
        SoftButton(
            footer,
            text="Use couple",
            command=self.select_couple,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=112,
            height=36,
        ).pack(side="left")

        self.bind("<Escape>", self.close_dialog)
        self.bind("<Return>", self.select_couple)
        self.filter_couples()
        self.after_idle(self.search_entry.focus_set)

    @classmethod
    def matching_couples(cls, couples, query=""):
        normalized_query = str(query or "").strip().casefold()
        matches = []
        for mother, father in couples or ():
            mother_name = str(mother.get("displayed_name", "") or "")
            father_name = str(father.get("displayed_name", "") or "")
            searchable = f"{mother_name} {father_name}".casefold()
            if normalized_query and normalized_query not in searchable:
                continue
            matches.append((mother, father))
        matches.sort(
            key=lambda pair: (
                normalized_query
                not in str(pair[0].get("displayed_name", "") or "").casefold(),
                str(pair[0].get("displayed_name", "") or "").casefold(),
                str(pair[1].get("displayed_name", "") or "").casefold(),
            )
        )
        return matches[: cls.VISIBLE_RESULT_LIMIT]

    def filter_couples(self, *unused):
        self.visible_couples = self.matching_couples(
            self.couples,
            self.search_value.get(),
        )
        self.listbox.delete(0, "end")
        for index, (mother, father) in enumerate(self.visible_couples):
            self.listbox.insert(
                "end",
                f"{mother.get('displayed_name', 'Unnamed')}  +  "
                f"{father.get('displayed_name', 'Unnamed')}",
            )
            self.listbox.itemconfigure(
                index,
                background=FIELD_BACKGROUND if index % 2 == 0 else LIST_ALTERNATE,
            )

    def select_couple(self, event=None):
        selected = self.listbox.curselection()
        if not selected:
            messagebox.showinfo(
                "Choose a couple",
                "Choose a spouse pair first.",
                parent=self,
            )
            return
        mother, father = self.visible_couples[selected[0]]
        try:
            accepted = self.select_command(
                str(mother.get("record_id", "") or ""),
                str(father.get("record_id", "") or ""),
            )
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror("Cannot use couple", str(error), parent=self)
            return
        if accepted is False:
            return
        self.destroy()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"


class BasicRelationshipDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        heading,
        explanation,
        save_command,
        locations=(),
        create_location_command=None,
    ):
        super().__init__(parent)
        self.save_command = save_command
        self.displayed_name_value = tk.StringVar()
        self.birth_year_value = tk.StringVar()
        self.deceased_value = tk.BooleanVar(value=False)
        self.death_year_value = tk.StringVar()
        self.death_month_value = tk.StringVar()
        self.death_day_value = tk.StringVar()
        self.locations = [
            dict(location)
            for location in locations or ()
            if isinstance(location, dict)
        ]
        self.starting_location_id = ""
        self.create_location_command = create_location_command
        self.starting_location_value = tk.StringVar(
            value="Choose a starting location"
        )

        self.title("Enter new character")
        self.geometry("520x510")
        self.resizable(False, False)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent)
        self.grab_set()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

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

        heading_label = tk.Label(
            card,
            text=heading,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(13, "bold"),
            anchor="w",
        )
        heading_label.grid(row=0, column=0, sticky="ew")
        explanation_label = tk.Label(
            card,
            text=explanation,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=410,
        )
        explanation_label.grid(row=1, column=0, sticky="ew", pady=(4, 10))
        name_field = LabeledEntry(
            card,
            "Displayed name",
            self.displayed_name_value,
            background=SURFACE,
        )
        name_field.grid(row=2, column=0, sticky="ew")

        birth_year_field = LabeledEntry(
            card,
            "Birth year",
            self.birth_year_value,
            background=SURFACE,
        )
        birth_year_field.grid(row=3, column=0, sticky="ew", pady=(10, 0))

        death_panel = tk.Frame(card, bg=SURFACE)
        death_panel.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        death_panel.grid_columnconfigure((0, 1, 2), weight=1)
        tk.Checkbutton(
            death_panel,
            text="Dead",
            variable=self.deceased_value,
            command=self.update_death_fields,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9),
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.death_fields = tk.Frame(death_panel, bg=SURFACE)
        self.death_fields.grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="ew",
        )
        self.death_fields.grid_columnconfigure((0, 1, 2), weight=1)
        for column, label_text, variable in (
            (0, "Death year", self.death_year_value),
            (1, "Month", self.death_month_value),
            (2, "Day", self.death_day_value),
        ):
            field = LabeledEntry(
                self.death_fields,
                label_text,
                variable,
                background=SURFACE,
            )
            field.grid(
                row=0,
                column=column,
                sticky="ew",
                padx=(0 if column == 0 else 5, 0),
            )
        self.death_fields.grid_remove()

        location_panel = tk.Frame(card, bg=SURFACE)
        location_panel.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        location_panel.grid_columnconfigure(0, weight=1)
        tk.Label(
            location_panel,
            text="Starting location",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        tk.Label(
            location_panel,
            textvariable=self.starting_location_value,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(9),
            anchor="w",
            padx=9,
            pady=8,
        ).grid(row=1, column=0, sticky="ew")
        choose_location_button = SoftButton(
            location_panel,
            text="Choose…",
            command=self.choose_starting_location,
            background=SURFACE,
            width=88,
            height=34,
        )
        choose_location_button.grid(row=1, column=1, padx=(7, 0))

        if not self.locations and self.create_location_command is None:
            location_panel.grid_remove()

        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(row=6, column=0, sticky="e", pady=(14, 0))
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.destroy,
            background=SURFACE,
            width=88,
            height=36,
        )
        cancel_button.pack(side="left", padx=(0, 6))
        add_button = SoftButton(
            footer,
            text="Add character",
            command=self.save_person,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=116,
            height=36,
        )
        add_button.pack(side="left")

        self.bind("<Escape>", self.close_dialog)
        self.bind("<Return>", self.save_person)
        self.after_idle(name_field.focus_set)

    def save_person(self, event=None):
        displayed_name = self.displayed_name_value.get().strip()

        if not displayed_name:
            messagebox.showerror(
                "Displayed name required",
                "Enter a displayed name for the character.",
                parent=self,
            )
            return

        deceased_variable = getattr(self, "deceased_value", None)
        is_deceased = bool(
            deceased_variable.get()
            if deceased_variable is not None
            else False
        )

        try:
            birth_year, _, _ = normalize_historical_date_parts(
                self.birth_year_value.get(),
                "",
                "",
                "Birth",
            )
            if is_deceased:
                death_year, death_month, death_day = (
                    normalize_historical_date_parts(
                        getattr(self, "death_year_value").get(),
                        getattr(self, "death_month_value").get(),
                        getattr(self, "death_day_value").get(),
                        "Death",
                    )
                )
            else:
                death_year = death_month = death_day = None
        except ValueError as error:
            messagebox.showerror("Birth year required", str(error), parent=self)
            return

        if (
            self.locations or self.create_location_command is not None
        ) and not self.starting_location_id:
            messagebox.showerror(
                "Starting location required",
                "Choose the new parent's starting location.",
                parent=self,
            )
            return

        try:
            created_person = self.save_command(
                {
                    "displayed_name": displayed_name,
                    "birth_year": birth_year,
                    "birth_month": None,
                    "birth_day": None,
                    "deceased": is_deceased,
                    "death_year": death_year,
                    "death_month": death_month,
                    "death_day": death_day,
                    "starting_location_id": self.starting_location_id,
                    "starting_location": self.starting_location_value.get()
                    if self.starting_location_id
                    else "",
                }
            )
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror("Cannot add character", str(error), parent=self)
            return

        if created_person is not None:
            self.destroy()

    def update_death_fields(self):
        if self.deceased_value.get():
            self.death_fields.grid()
        else:
            self.death_fields.grid_remove()

    def choose_starting_location(self):
        if not self.locations and self.create_location_command is None:
            return

        EventLocationPickerDialog(
            self,
            self.locations,
            self.starting_location_id,
            self.starting_location_selected,
            dialog_title="Choose starting location",
            action_text="Use location",
            create_location_command=(
                self.create_starting_location
                if self.create_location_command is not None
                else None
            ),
        )

    def create_starting_location(self, values):
        created = self.create_location_command(values)

        if not isinstance(created, dict):
            return created

        record_id = str(created.get("record_id", "") or "").strip()

        if record_id:
            self.locations = [
                location
                for location in self.locations
                if str(location.get("record_id", "") or "").strip()
                != record_id
            ]
            self.locations.append(dict(created))

        return created

    def starting_location_selected(self, location_id):
        self.starting_location_id = str(location_id or "").strip()
        self.starting_location_value.set(
            recent_location_label(
                self.starting_location_id,
                self.locations,
            )
            if self.starting_location_id
            else "Choose a starting location"
        )

    def close_dialog(self, event=None):
        self.destroy()
        return "break"
