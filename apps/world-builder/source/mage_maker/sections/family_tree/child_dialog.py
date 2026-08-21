import tkinter as tk
from tkinter import messagebox, simpledialog

from mage_maker.core.dates import normalize_date_parts
from mage_maker.sections.family_tree.relationships import FamilyRelationshipMap, format_person_date
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
    PRIMARY_SOFT,
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


class AddChildDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        current_person,
        people,
        people_provider,
        save_command,
        open_other_parent_command,
        existing_mates=None,
        active_other_parent_id=None,
    ):
        super().__init__(parent)
        self.current_person = current_person
        self.people = list(people)
        self.people_provider = people_provider
        self.save_command = save_command
        self.open_other_parent_command = open_other_parent_command
        self.existing_mates = [
            person
            for person in existing_mates or []
            if isinstance(person, dict)
            and not bool(person.get("does_not_have_children"))
        ]
        self.visible_children = []
        self.eligible_children = []
        self.new_child_name = ""
        self.new_child_can_give_birth = False
        self.new_child_profile = {}
        self.other_parent_id = ""
        self.other_parent_kind = "unknown"
        self.other_parent_is_alternate = False
        self.parent_tab_name = None
        self.other_parent_picker_dialog = None
        self.new_child_dialog = None
        self.search_value = tk.StringVar()
        self.partner_summary_value = tk.StringVar(value="Other parent: Unknown")
        self.new_parent_value = tk.StringVar(value="No new person selected.")
        self.new_child_value = tk.StringVar(value="No new child entered")
        self.age_rule_value = tk.StringVar()
        self.search_value.trace_add("write", self.filter_children)

        self.title("Add child")
        self.geometry("760x700")
        self.minsize(690, 620)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        self.card.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.card.grid_rowconfigure(0, weight=1)
        self.card.grid_columnconfigure(0, weight=1)

        self.build_partner_screen()
        self.build_child_screen()
        self.populate_existing_mates()

        if active_other_parent_id:
            self.set_other_parent(active_other_parent_id)

        self.show_partner_screen()
        self.bind("<Escape>", self.close_dialog)

    def build_partner_screen(self):
        self.partner_screen = tk.Frame(self.card, bg=SURFACE)
        self.partner_screen.grid(row=0, column=0, sticky="nsew")
        self.partner_screen.grid_rowconfigure(6, weight=1)
        self.partner_screen.grid_columnconfigure(0, weight=1)

        step_label = tk.Label(
            self.partner_screen,
            text="STEP 1 OF 2",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(8, "bold"),
            anchor="w",
        )
        step_label.grid(row=0, column=0, sticky="ew")

        heading = tk.Label(
            self.partner_screen,
            text="Choose the child's other parent",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(14, "bold"),
            anchor="w",
        )
        heading.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        explanation = tk.Label(
            self.partner_screen,
            text=(
                "Choose an existing mate first, choose a different person, or mark "
                "the other parent as Unknown or Unknown Muggle."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=650,
        )
        explanation.grid(row=2, column=0, sticky="ew", pady=(4, 10))

        quick_row = tk.Frame(self.partner_screen, bg=SURFACE)
        quick_row.grid(row=3, column=0, sticky="ew")

        self.unknown_button = SoftButton(
            quick_row,
            text="Unknown",
            command=self.choose_unknown_parent,
            background=SURFACE,
            width=102,
            height=36,
        )
        self.unknown_button.pack(side="left")

        self.muggle_button = SoftButton(
            quick_row,
            text="Unknown Muggle",
            command=self.choose_muggle_parent,
            background=SURFACE,
            width=142,
            height=36,
        )
        self.muggle_button.pack(side="left", padx=(6, 0))

        partner_summary = tk.Label(
            quick_row,
            textvariable=self.partner_summary_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="e",
            padx=10,
            pady=8,
        )
        partner_summary.pack(side="right", fill="x", expand=True, padx=(12, 0))

        tab_row = tk.Frame(self.partner_screen, bg=SURFACE)
        tab_row.grid(row=4, column=0, sticky="ew", pady=(12, 7))

        self.existing_mate_tab_button = SoftButton(
            tab_row,
            text="Existing mate",
            command=self.show_existing_mates_tab,
            background=SURFACE,
            width=132,
            height=34,
        )
        self.existing_mate_tab_button.pack(side="left")

        self.new_person_tab_button = SoftButton(
            tab_row,
            text="New person",
            command=self.show_new_person_tab,
            background=SURFACE,
            width=112,
            height=34,
        )
        self.new_person_tab_button.pack(side="left", padx=(6, 0))

        self.parent_tab_content = tk.Frame(
            self.partner_screen,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        self.parent_tab_content.grid(row=6, column=0, sticky="nsew")
        self.parent_tab_content.grid_rowconfigure(0, weight=1)
        self.parent_tab_content.grid_columnconfigure(0, weight=1)

        self.build_existing_mate_panel()
        self.build_new_person_panel()

        footer = tk.Frame(self.partner_screen, bg=SURFACE)
        footer.grid(row=7, column=0, sticky="ew", pady=(14, 0))

        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=SURFACE,
            width=88,
            height=36,
        )
        cancel_button.pack(side="right", padx=(6, 0))

        next_button = SoftButton(
            footer,
            text="Next · Choose child",
            command=self.show_child_screen,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=154,
            height=36,
        )
        next_button.pack(side="right")

    def build_existing_mate_panel(self):
        self.existing_mate_panel = tk.Frame(
            self.parent_tab_content,
            bg=SURFACE_MUTED,
        )
        self.existing_mate_panel.grid(row=0, column=0, sticky="nsew")
        self.existing_mate_panel.grid_rowconfigure(1, weight=1)
        self.existing_mate_panel.grid_columnconfigure(0, weight=1)

        note = tk.Label(
            self.existing_mate_panel,
            text="Select the existing mate who is this child's other parent.",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        note.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 7))

        self.existing_mate_listbox = tk.Listbox(
            self.existing_mate_panel,
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
        self.existing_mate_listbox.grid(row=1, column=0, sticky="nsew")
        self.existing_mate_listbox.bind(
            "<<ListboxSelect>>",
            self.existing_mate_selected,
        )
        self.existing_mate_listbox.bind(
            "<Double-Button-1>",
            self.existing_mate_double_clicked,
        )

        scrollbar = tk.Scrollbar(
            self.existing_mate_panel,
            command=self.existing_mate_listbox.yview,
        )
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.existing_mate_listbox.configure(yscrollcommand=scrollbar.set)

    def build_new_person_panel(self):
        self.new_person_panel = tk.Frame(
            self.parent_tab_content,
            bg=SURFACE_MUTED,
        )
        self.new_person_panel.grid(row=0, column=0, sticky="nsew")
        self.new_person_panel.grid_rowconfigure(2, weight=1)
        self.new_person_panel.grid_columnconfigure(0, weight=1)

        note = tk.Label(
            self.new_person_panel,
            text=(
                "Choose someone who is not yet listed as a mate, or enter a new "
                "name-only character. They will become a reciprocal mate when the "
                "child is added."
            ),
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=620,
        )
        note.grid(row=0, column=0, sticky="ew")

        selection_summary = tk.Label(
            self.new_person_panel,
            textvariable=self.new_parent_value,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
            padx=12,
            pady=10,
        )
        selection_summary.grid(row=1, column=0, sticky="ew", pady=(12, 8))

        choose_button = SoftButton(
            self.new_person_panel,
            text="Choose or enter person",
            command=self.open_other_parent_picker,
            background=SURFACE_MUTED,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=184,
            height=38,
        )
        choose_button.grid(row=2, column=0, sticky="n", pady=(30, 0))

    def build_child_screen(self):
        self.child_screen = tk.Frame(self.card, bg=SURFACE)
        self.child_screen.grid(row=0, column=0, sticky="nsew")
        self.child_screen.grid_rowconfigure(6, weight=1)
        self.child_screen.grid_columnconfigure(0, weight=1)

        step_label = tk.Label(
            self.child_screen,
            text="STEP 2 OF 2",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(8, "bold"),
            anchor="w",
        )
        step_label.grid(row=0, column=0, sticky="ew")

        heading = tk.Label(
            self.child_screen,
            text="Choose the child",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(14, "bold"),
            anchor="w",
        )
        heading.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        parent_row = tk.Frame(self.child_screen, bg=SURFACE_MUTED)
        parent_row.grid(row=2, column=0, sticky="ew", pady=(10, 8))
        parent_row.grid_columnconfigure(0, weight=1)

        selected_parent = tk.Label(
            parent_row,
            textvariable=self.partner_summary_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
            padx=10,
            pady=8,
        )
        selected_parent.grid(row=0, column=0, sticky="ew")

        change_parent_button = SoftButton(
            parent_row,
            text="Change",
            command=self.show_partner_screen,
            background=SURFACE_MUTED,
            width=82,
            height=30,
        )
        change_parent_button.grid(row=0, column=1, padx=(8, 8))

        age_rule = tk.Label(
            self.child_screen,
            textvariable=self.age_rule_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=650,
        )
        age_rule.grid(row=3, column=0, sticky="ew", pady=(0, 9))

        search = RoundedEntry(
            self.child_screen,
            textvariable=self.search_value,
            background=SURFACE,
            height=38,
        )
        search.grid(row=4, column=0, sticky="ew")
        self.search_entry = search

        new_child_summary = tk.Label(
            self.child_screen,
            textvariable=self.new_child_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            padx=10,
            pady=7,
        )
        new_child_summary.grid(row=5, column=0, sticky="ew", pady=(7, 8))

        list_frame = tk.Frame(self.child_screen, bg=SURFACE)
        list_frame.grid(row=6, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        self.child_listbox = tk.Listbox(
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
        self.child_listbox.grid(row=0, column=0, sticky="nsew")
        self.child_listbox.bind("<<ListboxSelect>>", self.existing_child_selected)
        self.child_listbox.bind("<Double-Button-1>", self.save_child)

        scrollbar = tk.Scrollbar(list_frame, command=self.child_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.child_listbox.configure(yscrollcommand=scrollbar.set)

        footer = tk.Frame(self.child_screen, bg=SURFACE)
        footer.grid(row=7, column=0, sticky="ew", pady=(14, 0))

        enter_new_button = SoftButton(
            footer,
            text="Enter new",
            command=self.open_new_child_dialog,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=104,
            height=36,
        )
        enter_new_button.pack(side="left")
        quick_add_button = SoftButton(
            footer,
            text="Quick add person",
            command=self.quick_add_child,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=128,
            height=36,
        )
        quick_add_button.pack(side="left", padx=(6, 0))

        back_button = SoftButton(
            footer,
            text="Back",
            command=self.show_partner_screen,
            background=SURFACE,
            width=82,
            height=36,
        )
        back_button.pack(side="right", padx=(6, 0))

        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=SURFACE,
            width=88,
            height=36,
        )
        cancel_button.pack(side="right", padx=(6, 0))

        add_button = SoftButton(
            footer,
            text="Add child",
            command=self.save_child,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=102,
            height=36,
        )
        add_button.pack(side="right")

    def populate_existing_mates(self):
        self.existing_mate_listbox.delete(0, "end")

        for index, person in enumerate(self.existing_mates):
            self.existing_mate_listbox.insert(
                "end",
                f"{format_person_date(person)}: "
                f"{person.get('displayed_name', 'Unnamed')}",
            )
            self.existing_mate_listbox.itemconfigure(
                index,
                background=FIELD_BACKGROUND if index % 2 == 0 else LIST_ALTERNATE,
            )

        self.existing_mate_tab_button.set_text(
            f"Existing mate ({len(self.existing_mates)})"
        )
        self.existing_mate_tab_button.set_enabled(bool(self.existing_mates))

        if self.existing_mates:
            self.show_existing_mates_tab()
        else:
            self.show_new_person_tab()

    def show_existing_mates_tab(self):
        if not self.existing_mates:
            return

        self.new_person_panel.grid_remove()
        self.existing_mate_panel.grid()
        self.parent_tab_name = "existing"
        self.existing_mate_tab_button.set_colors(
            PRIMARY_SOFT,
            PRIMARY_HOVER,
            TEXT_DARK,
        )
        self.new_person_tab_button.set_colors(
            BUTTON_SOFT,
            BUTTON_SOFT_HOVER,
            TEXT_DARK,
        )

    def show_new_person_tab(self):
        self.existing_mate_panel.grid_remove()
        self.new_person_panel.grid()
        self.parent_tab_name = "new"
        self.existing_mate_tab_button.set_colors(
            BUTTON_SOFT,
            BUTTON_SOFT_HOVER,
            TEXT_DARK,
        )
        self.new_person_tab_button.set_colors(
            PRIMARY_SOFT,
            PRIMARY_HOVER,
            TEXT_DARK,
        )

    def choose_unknown_parent(self):
        self.other_parent_id = ""
        self.other_parent_kind = "unknown"
        self.other_parent_is_alternate = False
        self.existing_mate_listbox.selection_clear(0, "end")
        self.new_parent_value.set("No new person selected.")
        self.update_partner_summary()

    def choose_muggle_parent(self):
        self.other_parent_id = ""
        self.other_parent_kind = "muggle"
        self.other_parent_is_alternate = False
        self.existing_mate_listbox.selection_clear(0, "end")
        self.new_parent_value.set("No new person selected.")
        self.update_partner_summary()

    def existing_mate_selected(self, event=None):
        selected_indexes = self.existing_mate_listbox.curselection()

        if not selected_indexes:
            return

        person = self.existing_mates[selected_indexes[0]]
        self.set_other_parent(person.get("record_id"), False)

    def existing_mate_double_clicked(self, event=None):
        self.existing_mate_selected()
        self.show_child_screen()

    def open_other_parent_picker(self):
        if self.other_parent_picker_dialog is not None:
            try:
                if self.other_parent_picker_dialog.winfo_exists():
                    self.other_parent_picker_dialog.deiconify()
                    self.other_parent_picker_dialog.lift()
                    return self.other_parent_picker_dialog
            except tk.TclError:
                pass

            self.other_parent_picker_dialog = None

        self.other_parent_picker_dialog = self.open_other_parent_command(
            self,
            self.set_other_parent,
            "",
        )

        if self.other_parent_picker_dialog is not None:
            self.other_parent_picker_dialog.lift()

        return self.other_parent_picker_dialog

    def set_other_parent(self, record_id, is_alternate=False):
        selected_person = None

        for person in self.people_provider():
            if str(person.get("record_id", "")) == str(record_id or ""):
                selected_person = person
                break

        if selected_person is None:
            self.choose_unknown_parent()
            return

        if bool(selected_person.get("does_not_have_children")):
            raise ValueError(
                "The selected person is marked Does not have children "
                "and cannot be added as a parent."
            )

        self.other_parent_id = str(record_id)
        self.other_parent_kind = "person"
        self.other_parent_is_alternate = bool(is_alternate)
        change_note = " · assignment will change" if is_alternate else ""
        self.new_parent_value.set(
            f"Selected: {selected_person.get('displayed_name', 'Unnamed')}"
            f"{change_note}"
        )
        self.update_partner_summary()

        for index, person in enumerate(self.existing_mates):
            if str(person.get("record_id", "")) == self.other_parent_id:
                self.existing_mate_listbox.selection_clear(0, "end")
                self.existing_mate_listbox.selection_set(index)
                self.existing_mate_listbox.see(index)
                return

        self.existing_mate_listbox.selection_clear(0, "end")
        self.show_new_person_tab()

    def update_partner_summary(self):
        if self.other_parent_kind == "unknown":
            self.partner_summary_value.set("Other parent: Unknown")
            self.unknown_button.set_colors(PRIMARY_SOFT, PRIMARY_HOVER, TEXT_DARK)
            self.muggle_button.set_colors(
                BUTTON_SOFT,
                BUTTON_SOFT_HOVER,
                TEXT_DARK,
            )
            return

        if self.other_parent_kind == "muggle":
            self.partner_summary_value.set("Other parent: Unknown Muggle")
            self.unknown_button.set_colors(
                BUTTON_SOFT,
                BUTTON_SOFT_HOVER,
                TEXT_DARK,
            )
            self.muggle_button.set_colors(PRIMARY_SOFT, PRIMARY_HOVER, TEXT_DARK)
            return

        selected_person = None

        for person in self.people_provider():
            if str(person.get("record_id", "")) == self.other_parent_id:
                selected_person = person
                break

        selected_name = (
            selected_person.get("displayed_name", "Unknown")
            if selected_person
            else "Unknown"
        )
        self.partner_summary_value.set(f"Other parent: {selected_name}")
        self.unknown_button.set_colors(
            BUTTON_SOFT,
            BUTTON_SOFT_HOVER,
            TEXT_DARK,
        )
        self.muggle_button.set_colors(
            BUTTON_SOFT,
            BUTTON_SOFT_HOVER,
            TEXT_DARK,
        )

    def show_partner_screen(self):
        self.child_screen.grid_remove()
        self.partner_screen.grid()
        self.partner_screen.tkraise()
        self.update_partner_summary()

        if self.existing_mates and self.parent_tab_name != "new":
            self.show_existing_mates_tab()
        elif not self.existing_mates:
            self.show_new_person_tab()

    def show_child_screen(self):
        self.partner_screen.grid_remove()
        self.child_screen.grid()
        self.child_screen.tkraise()
        self.refresh_child_candidates()
        self.after_idle(self.search_entry.focus_set)

    def refresh_child_candidates(self):
        current_id = str(self.current_person.get("record_id", "") or "")
        other_parent_id = (
            self.other_parent_id if self.other_parent_kind == "person" else ""
        )
        relationship_map = FamilyRelationshipMap(
            self.people_provider(),
            self.current_person,
        )
        self.eligible_children = relationship_map.child_candidates(
            current_id,
            other_parent_id,
            minimum_age_gap=18,
            other_parent_status=self.other_parent_kind,
        )
        minimum_child_year = relationship_map.minimum_child_birth_year(
            current_id,
            other_parent_id,
            minimum_age_gap=18,
        )

        if minimum_child_year is None:
            self.age_rule_value.set(
                "No existing people are shown because a selected parent's birth "
                "year is unknown. Enter a new child or add that birth year first."
            )
        else:
            self.age_rule_value.set(
                f"Showing only people born in {minimum_child_year} or later · at least "
                "18 years younger than the youngest selected parent."
            )

        self.filter_children()

    def filter_children(self, *arguments):
        if not hasattr(self, "child_listbox"):
            return

        query = self.search_value.get().strip().casefold()
        selected_child_id = self.selected_child_record_id()
        self.visible_children = [
            person
            for person in self.eligible_children
            if (
                not query
                or query in str(person.get("displayed_name", "")).casefold()
            )
        ]
        self.child_listbox.delete(0, "end")

        for index, person in enumerate(self.visible_children):
            self.child_listbox.insert(
                "end",
                f"{format_person_date(person)}: "
                f"{person.get('displayed_name', 'Unnamed')}",
            )
            self.child_listbox.itemconfigure(
                index,
                background=FIELD_BACKGROUND if index % 2 == 0 else LIST_ALTERNATE,
            )

            if str(person.get("record_id", "")) == selected_child_id:
                self.child_listbox.selection_set(index)

    def existing_child_selected(self, event=None):
        if not self.child_listbox.curselection():
            return

        self.new_child_name = ""
        self.new_child_can_give_birth = False
        self.new_child_profile = {}
        self.new_child_value.set("Using the selected existing child")

    def open_new_child_dialog(self):
        if self.new_child_dialog is not None:
            try:
                if self.new_child_dialog.winfo_exists():
                    self.new_child_dialog.deiconify()
                    self.new_child_dialog.lift()
                    return self.new_child_dialog
            except tk.TclError:
                pass

            self.new_child_dialog = None

        self.new_child_dialog = BasicChildDialog(
            self,
            self.set_new_child,
        )
        self.new_child_dialog.lift()
        return self.new_child_dialog

    def quick_add_child(self):
        displayed_name = simpledialog.askstring(
            "Quick add person",
            "Displayed name for the new child:",
            parent=self,
        )

        if displayed_name is None or not displayed_name.strip():
            return False

        return self.set_new_child(
            {
                "displayed_name": displayed_name.strip(),
                "can_give_birth": False,
                "birth_year": None,
                "birth_month": None,
                "birth_day": None,
                "deceased": False,
                "death_year": None,
                "death_month": None,
                "death_day": None,
            }
        )

    def set_new_child(self, profile_values):
        values = dict(profile_values or {})
        self.new_child_name = str(values.get("displayed_name", "") or "").strip()
        self.new_child_can_give_birth = bool(values.get("can_give_birth"))
        self.new_child_profile = {
            "birth_year": values.get("birth_year"),
            "birth_month": values.get("birth_month"),
            "birth_day": values.get("birth_day"),
            "deceased": bool(values.get("deceased")),
            "death_year": values.get("death_year"),
            "death_month": values.get("death_month"),
            "death_day": values.get("death_day"),
        }
        birth_capability_text = (
            "can give birth"
            if self.new_child_can_give_birth
            else "cannot give birth"
        )
        date_text = format_person_date(self.new_child_profile)
        date_suffix = f" · {date_text}" if date_text != "nd." else ""
        death_suffix = " · dead" if self.new_child_profile["deceased"] else ""
        self.new_child_value.set(
            f"New child: {self.new_child_name} ({birth_capability_text})"
            f"{date_suffix}{death_suffix}"
        )
        self.child_listbox.selection_clear(0, "end")
        # Completing the basic profile selects the new child; it must not
        # submit the outer dialog on an idle callback.  The old callback raced
        # the nested dialog/grab teardown and made Add child appear unreliable.
        # Keep the explicit Add child action as the single commit point.
        return True

    def selected_child_record_id(self):
        if not hasattr(self, "child_listbox"):
            return ""

        selected_indexes = self.child_listbox.curselection()

        if not selected_indexes:
            return ""

        selected_index = selected_indexes[0]

        if selected_index >= len(self.visible_children):
            return ""

        return str(self.visible_children[selected_index].get("record_id", ""))

    def save_child(self, event=None):
        child_record_id = self.selected_child_record_id()

        if child_record_id and self.new_child_name:
            messagebox.showerror(
                "Choose one child",
                "Choose an existing child or enter a new child, not both.",
                parent=self,
            )
            return

        if not child_record_id and not self.new_child_name:
            messagebox.showerror(
                "Child required",
                "Choose an existing child or use Enter new.",
                parent=self,
            )
            return

        try:
            saved_child = self.save_command(
                child_record_id,
                self.new_child_name,
                self.new_child_can_give_birth,
                self.other_parent_id,
                self.other_parent_is_alternate,
                self.other_parent_kind,
                self.new_child_profile,
            )
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror("Cannot add child", str(error), parent=self)
            return

        if saved_child is not None:
            self.close_dialog()

    def close_dialog(self, event=None):
        nested_dialogs = (
            self.other_parent_picker_dialog,
            self.new_child_dialog,
        )
        self.other_parent_picker_dialog = None
        self.new_child_dialog = None

        for nested_dialog in nested_dialogs:
            if nested_dialog is None:
                continue

            try:
                if nested_dialog.winfo_exists():
                    nested_dialog.destroy()
            except tk.TclError:
                pass

        self.destroy()
        return "break"


class BasicChildDialog(tk.Toplevel):
    def __init__(self, parent, save_command):
        super().__init__(parent)
        try:
            self.previous_grab = parent.grab_current()
        except tk.TclError:
            self.previous_grab = None

        self.save_command = save_command
        self.displayed_name_value = tk.StringVar()
        self.can_give_birth_value = tk.BooleanVar(value=False)
        self.birth_year_value = tk.StringVar()
        self.birth_month_value = tk.StringVar()
        self.birth_day_value = tk.StringVar()
        self.deceased_value = tk.BooleanVar(value=False)
        self.death_year_value = tk.StringVar()
        self.death_month_value = tk.StringVar()
        self.death_day_value = tk.StringVar()
        self.deceased_value.trace_add("write", self.deceased_changed)

        self.title("Enter new child")
        self.geometry("560x550")
        self.resizable(False, False)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent)
        self.grab_set()
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
            text="Enter a basic child profile",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(13, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")

        explanation = tk.Label(
            card,
            text=(
                "Enter the basic identity and any known birth or death date. "
                "Date parts may be left blank when they are unknown."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=480,
        )
        explanation.grid(row=1, column=0, sticky="ew", pady=(4, 10))

        name_field = LabeledEntry(
            card,
            "Displayed name",
            self.displayed_name_value,
            background=SURFACE,
        )
        name_field.grid(row=2, column=0, sticky="ew")

        birth_frame = tk.Frame(card, bg=SURFACE)
        birth_frame.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        birth_frame.grid_columnconfigure((0, 1, 2), weight=1)
        birth_heading = tk.Label(
            birth_frame,
            text="Date of birth",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        birth_heading.grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(0, 5),
        )
        birth_year_field = LabeledEntry(
            birth_frame,
            "Year",
            self.birth_year_value,
            background=SURFACE,
        )
        birth_year_field.grid(row=1, column=0, sticky="ew", padx=(0, 5))
        birth_month_field = LabeledEntry(
            birth_frame,
            "Month",
            self.birth_month_value,
            background=SURFACE,
        )
        birth_month_field.grid(row=1, column=1, sticky="ew", padx=5)
        birth_day_field = LabeledEntry(
            birth_frame,
            "Day",
            self.birth_day_value,
            background=SURFACE,
        )
        birth_day_field.grid(row=1, column=2, sticky="ew", padx=(5, 0))
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
            row=2,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(5, 0),
        )

        can_give_birth_check = tk.Checkbutton(
            card,
            text="Can give birth",
            variable=self.can_give_birth_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
            borderwidth=0,
            highlightthickness=0,
        )
        can_give_birth_check.grid(row=4, column=0, sticky="w", pady=(12, 0))

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
            borderwidth=0,
            highlightthickness=0,
        )
        deceased_check.grid(row=5, column=0, sticky="w", pady=(8, 0))

        self.death_frame = tk.Frame(card, bg=SURFACE)
        self.death_frame.grid(row=6, column=0, sticky="ew", pady=(10, 0))
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
        footer.grid(row=7, column=0, sticky="e", pady=(16, 0))

        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=SURFACE,
            width=88,
            height=36,
        )
        cancel_button.pack(side="left", padx=(0, 6))

        add_button = SoftButton(
            footer,
            text="Use child",
            command=self.save_child,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=102,
            height=36,
        )
        add_button.pack(side="left")

        self.bind("<Escape>", self.close_dialog)
        self.bind("<Return>", self.save_child)
        self.after_idle(name_field.control.focus_set)

    def save_child(self, event=None):
        displayed_name = self.displayed_name_value.get().strip()

        if not displayed_name:
            messagebox.showerror(
                "Displayed name required",
                "Enter a displayed name for the child.",
                parent=self,
            )
            return

        try:
            birth_year, birth_month, birth_day = normalize_date_parts(
                self.birth_year_value.get(),
                self.birth_month_value.get(),
                self.birth_day_value.get(),
                "Birth",
            )

            if self.deceased_value.get():
                death_year, death_month, death_day = normalize_date_parts(
                    self.death_year_value.get(),
                    self.death_month_value.get(),
                    self.death_day_value.get(),
                    "Death",
                )
            else:
                death_year, death_month, death_day = None, None, None
        except ValueError as error:
            messagebox.showerror("Cannot use child", str(error), parent=self)
            return

        profile_values = {
            "displayed_name": displayed_name,
            "can_give_birth": self.can_give_birth_value.get(),
            "birth_year": birth_year,
            "birth_month": birth_month,
            "birth_day": birth_day,
            "deceased": self.deceased_value.get(),
            "death_year": death_year,
            "death_month": death_month,
            "death_day": death_day,
        }

        if self.save_command(profile_values):
            self.close_dialog()

    def deceased_changed(self, *arguments):
        if self.deceased_value.get():
            self.death_frame.grid()
        else:
            self.death_frame.grid_remove()

    def close_dialog(self, event=None):
        self.destroy()

        if self.previous_grab is not None:
            try:
                if self.previous_grab.winfo_exists():
                    self.previous_grab.grab_set()
            except tk.TclError:
                pass

        return "break"
