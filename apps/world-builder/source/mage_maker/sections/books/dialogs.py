import tkinter as tk
from copy import deepcopy
from tkinter import messagebox

from mage_maker.sections.books.models import BOOK_HOLDER_TYPES
from mage_maker.sections.development.organization_dialogs import (
    OrganizationSelectionDialog,
)
from mage_maker.sections.events.dialog import (
    EventLocationPickerDialog,
    EventPersonPickerDialog,
)
from mage_maker.sections.events.models import split_world_event_date
from mage_maker.ui.theme import (
    ADD_GREEN,
    ADD_GREEN_HOVER,
    APP_BACKGROUND,
    BORDER,
    BORDER_SOFT,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    FIELD_BACKGROUND,
    LIST_SELECTED,
    PRIMARY,
    PRIMARY_DARK,
    PRIMARY_HOVER,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_LIGHT,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import (
    LabeledEntry,
    MultilineField,
    RoundedEntry,
    RoundedSelect,
    SoftButton,
)


class BookDialog(tk.Toplevel):
    def __init__(self, parent, controller, book, save_command):
        super().__init__(parent)
        self.controller = controller
        self.book = deepcopy(book) if isinstance(book, dict) else {}
        self.save_command = save_command
        self.author_person_id = str(
            self.book.get("author_person_id", "") or ""
        ).strip()
        self.publication_location_id = str(
            self.book.get("publication_location_id", "") or ""
        ).strip()
        publication_year, publication_month, publication_day = (
            split_world_event_date(self.book.get("publication_date", ""))
        )
        self.title_value = tk.StringVar(value=self.book.get("title", ""))
        self.author_value = tk.StringVar(
            value=self.book.get("author_name", "")
        )
        self.publication_year_value = tk.StringVar(value=publication_year)
        self.publication_month_value = tk.StringVar(value=publication_month)
        self.publication_day_value = tk.StringVar(value=publication_day)
        self.publication_location_value = tk.StringVar(
            value=(
                self.book.get("publication_location_name", "")
                or "No publication location selected"
            )
        )
        self.mass_printed_value = tk.BooleanVar(
            value=bool(self.book.get("mass_printed", False))
        )
        self.title("Edit Book" if self.book else "New Book")
        self.geometry("780x680")
        self.minsize(680, 600)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.load_text_values()
        self.grab_set()
        self.after_idle(self.focus_title)

    def build_dialog(self):
        heading = tk.Label(
            self,
            text="Edit book" if self.book else "Create book",
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(15, "bold"),
            anchor="w",
            padx=20,
            pady=13,
        )
        heading.grid(row=0, column=0, sticky="ew")
        body = tk.Frame(self, bg=SURFACE, padx=22, pady=18)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(5, weight=1)
        self.title_field = LabeledEntry(
            body,
            "Title",
            self.title_value,
            background=SURFACE,
        )
        self.title_field.grid(row=0, column=0, sticky="ew")
        author_row = tk.Frame(body, bg=SURFACE)
        author_row.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        author_row.grid_columnconfigure(0, weight=1)
        self.author_field = LabeledEntry(
            author_row,
            "Author",
            self.author_value,
            background=SURFACE,
        )
        self.author_field.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        choose_author = SoftButton(
            author_row,
            text="Choose mage…",
            command=self.open_author_picker,
            background=SURFACE,
            width=126,
            height=40,
        )
        choose_author.grid(row=0, column=1, sticky="s")
        date_row = tk.Frame(body, bg=SURFACE)
        date_row.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        date_row.grid_columnconfigure(0, weight=1)
        date_fields = tk.Frame(date_row, bg=SURFACE)
        date_fields.grid(row=0, column=0, sticky="w")
        self.publication_year_field = LabeledEntry(
            date_fields,
            "Publication year",
            self.publication_year_value,
            background=SURFACE,
        )
        self.publication_year_field.grid(row=0, column=0, sticky="w")
        self.publication_month_field = LabeledEntry(
            date_fields,
            "Month",
            self.publication_month_value,
            background=SURFACE,
        )
        self.publication_month_field.grid(
            row=0,
            column=1,
            sticky="w",
            padx=(8, 0),
        )
        self.publication_day_field = LabeledEntry(
            date_fields,
            "Day",
            self.publication_day_value,
            background=SURFACE,
        )
        self.publication_day_field.grid(
            row=0,
            column=2,
            sticky="w",
            padx=(8, 0),
        )
        self.publication_year_field.configure(width=150)
        self.publication_month_field.configure(width=90)
        self.publication_day_field.configure(width=90)
        location_panel = tk.Frame(body, bg=SURFACE_MUTED, padx=12, pady=10)
        location_panel.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        location_panel.grid_columnconfigure(0, weight=1)
        location_heading = tk.Label(
            location_panel,
            text="Publication location / first known location",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        location_heading.grid(row=0, column=0, columnspan=3, sticky="ew")
        location_value = tk.Label(
            location_panel,
            textvariable=self.publication_location_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        location_value.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        choose_location = SoftButton(
            location_panel,
            text="Choose…",
            command=self.open_location_picker,
            background=SURFACE_MUTED,
            width=88,
            height=34,
            font=app_font(9, "bold"),
        )
        choose_location.grid(row=1, column=1, padx=(8, 0), pady=(5, 0))
        clear_location = SoftButton(
            location_panel,
            text="Clear",
            command=self.clear_location,
            background=SURFACE_MUTED,
            width=70,
            height=34,
            font=app_font(9, "bold"),
        )
        clear_location.grid(row=1, column=2, padx=(6, 0), pady=(5, 0))
        mass_printed = tk.Checkbutton(
            body,
            text="Mass printed / widely distributed",
            variable=self.mass_printed_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(10),
            anchor="w",
            borderwidth=0,
            highlightthickness=0,
        )
        mass_printed.grid(row=4, column=0, sticky="w", pady=(12, 0))
        text_row = tk.Frame(body, bg=SURFACE)
        text_row.grid(row=5, column=0, sticky="nsew", pady=(12, 0))
        text_row.grid_columnconfigure(0, weight=1)
        text_row.grid_columnconfigure(1, weight=1)
        text_row.grid_rowconfigure(0, weight=1)
        self.description_field = MultilineField(
            text_row,
            "Description",
            115,
            background=SURFACE,
        )
        self.description_field.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 6),
        )
        self.notes_field = MultilineField(
            text_row,
            "Notes",
            115,
            background=SURFACE,
        )
        self.notes_field.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(6, 0),
        )
        footer = tk.Frame(self, bg=APP_BACKGROUND)
        footer.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 16))
        footer.grid_columnconfigure(0, weight=1)
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=APP_BACKGROUND,
            width=88,
            height=38,
        )
        cancel_button.grid(row=0, column=1, padx=(0, 7))
        save_button = SoftButton(
            footer,
            text="Save book",
            command=self.save_book,
            background=APP_BACKGROUND,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=112,
            height=38,
        )
        save_button.grid(row=0, column=2)

    def load_text_values(self):
        self.description_field.text.insert(
            "1.0",
            str(self.book.get("description", "") or ""),
        )
        self.notes_field.text.insert(
            "1.0",
            str(self.book.get("notes", "") or ""),
        )

    def focus_title(self):
        self.title_field.control.focus_set()

    def open_author_picker(self):
        EventPersonPickerDialog(
            self,
            self.controller.people_options(),
            self.controller.recent_people_options(),
            self.author_person_id,
            self.author_selected,
            mage_groups=self.controller.mage_groups(),
            dialog_title="Choose book author",
            heading_text="Choose the author",
            selection_prompt="Select the book's author.",
            action_text="Use author",
        )

    def author_selected(self, person_id):
        normalized_person_id = str(person_id or "").strip()
        person = self.controller.people_by_id().get(normalized_person_id)

        if person is None:
            return

        self.author_person_id = normalized_person_id
        self.author_value.set(
            str(person.get("displayed_name", "") or "Unknown author").strip()
        )

    def open_location_picker(self):
        EventLocationPickerDialog(
            self,
            list(self.controller.locations_by_id().values()),
            self.publication_location_id,
            self.location_selected,
            dialog_title="Choose publication location",
            action_text="Use location",
        )

    def location_selected(self, location_id):
        normalized_location_id = str(location_id or "").strip()
        locations = list(self.controller.locations_by_id().values())
        location = self.controller.locations_by_id().get(
            normalized_location_id
        )

        if location is None:
            return

        self.publication_location_id = normalized_location_id
        self.publication_location_value.set(
            self.controller.holding_name(
                {
                    "holder_type": "Location archive",
                    "location_id": normalized_location_id,
                    "holder_name": location.get("name", ""),
                }
            )
        )

    def clear_location(self):
        self.publication_location_id = ""
        self.publication_location_value.set(
            "No publication location selected"
        )

    def publication_date_value(self):
        year = self.publication_year_value.get().strip()
        month = self.publication_month_value.get().strip()
        day = self.publication_day_value.get().strip()

        if not year:
            raise ValueError("Publication year is required.")

        if month and not year:
            raise ValueError("Publication month requires a year.")

        if day and not month:
            raise ValueError("Publication day requires a month.")

        return year + (f"-{month}" if month else "") + (
            f"-{day}" if day else ""
        )

    def values(self):
        author_name = self.author_value.get().strip()
        selected_author = self.controller.people_by_id().get(
            self.author_person_id
        )

        if (
            selected_author is not None
            and str(selected_author.get("displayed_name", "") or "").strip()
            != author_name
        ):
            self.author_person_id = ""

        return {
            **deepcopy(self.book),
            "title": self.title_value.get(),
            "author_person_id": self.author_person_id,
            "author_name": author_name,
            "publication_date": self.publication_date_value(),
            "publication_location_id": self.publication_location_id,
            "publication_location_name": (
                self.publication_location_value.get()
                if self.publication_location_id
                else ""
            ),
            "mass_printed": self.mass_printed_value.get(),
            "description": self.description_field.text.get("1.0", "end-1c"),
            "notes": self.notes_field.text.get("1.0", "end-1c"),
            "contents": deepcopy(self.book.get("contents", [])),
            "holdings": deepcopy(self.book.get("holdings", [])),
        }

    def save_book(self):
        try:
            saved = self.save_command(self.values())
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot save book",
                str(error),
                parent=self,
            )
            return

        if saved is not False:
            self.close_dialog()

    def close_dialog(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass

        self.destroy()


class BookContentPickerDialog(tk.Toplevel):
    def __init__(self, parent, controller, save_command):
        super().__init__(parent)
        self.controller = controller
        self.save_command = save_command
        self.options = controller.content_options()
        self.visible_options = []
        self.search_value = tk.StringVar()
        self.type_value = tk.StringVar(value="All types")
        self.result_value = tk.StringVar()
        self.title("Add Book Content")
        self.geometry("680x650")
        self.minsize(540, 500)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.search_value.trace_add("write", self.refresh_results)
        self.type_value.trace_add("write", self.refresh_results)
        self.refresh_results()
        self.grab_set()
        self.after_idle(self.focus_search)

    def build_dialog(self):
        heading = tk.Label(
            self,
            text="Add spell, proficiency, or recipe",
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(15, "bold"),
            anchor="w",
            padx=20,
            pady=13,
        )
        heading.grid(row=0, column=0, sticky="ew")
        body = tk.Frame(self, bg=SURFACE, padx=20, pady=18)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(3, weight=1)
        body.grid_columnconfigure(0, weight=1)
        filters = tk.Frame(body, bg=SURFACE)
        filters.grid(row=0, column=0, sticky="ew")
        filters.grid_columnconfigure(0, weight=1)
        self.search_control = RoundedEntry(
            filters,
            textvariable=self.search_value,
            background=SURFACE,
            height=40,
        )
        self.search_control.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        type_select = RoundedSelect(
            filters,
            self.type_value,
            ("All types", "Spell", "Proficiency", "Recipe"),
            background=SURFACE,
            width=150,
            height=40,
        )
        type_select.grid(row=0, column=1)
        result_label = tk.Label(
            body,
            textvariable=self.result_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        result_label.grid(row=1, column=0, sticky="ew", pady=(9, 5))
        list_frame = tk.Frame(
            body,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        list_frame.grid(row=3, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.results_list = tk.Listbox(
            list_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            font=app_font(10),
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            activestyle="none",
            exportselection=False,
        )
        self.results_list.grid(row=0, column=0, sticky="nsew")
        self.results_list.bind("<Double-Button-1>", self.choose_content)
        scrollbar = tk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.results_list.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.results_list.configure(yscrollcommand=scrollbar.set)
        footer = tk.Frame(self, bg=APP_BACKGROUND)
        footer.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 16))
        footer.grid_columnconfigure(0, weight=1)
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=APP_BACKGROUND,
            width=88,
            height=38,
        )
        cancel_button.grid(row=0, column=1, padx=(0, 7))
        add_button = SoftButton(
            footer,
            text="Add content",
            command=self.choose_content,
            background=APP_BACKGROUND,
            fill=ADD_GREEN,
            hover_fill=ADD_GREEN_HOVER,
            foreground=TEXT_DARK,
            width=116,
            height=38,
        )
        add_button.grid(row=0, column=2)

    def refresh_results(self, *arguments):
        query_terms = [
            term
            for term in self.search_value.get().strip().casefold().split()
            if term
        ]
        selected_type = self.type_value.get()
        self.visible_options = [
            option
            for option in self.options
            if (
                selected_type == "All types"
                or option["content_type"] == selected_type
            )
            and all(term in option["search_text"] for term in query_terms)
        ]
        self.results_list.delete(0, "end")

        for option in self.visible_options:
            self.results_list.insert(
                "end",
                f"{option['name']}  ·  {option['content_type']}",
            )

        count = len(self.visible_options)
        self.result_value.set(
            f"{count} result" if count == 1 else f"{count} results"
        )

    def choose_content(self, event=None):
        selection = self.results_list.curselection()

        if not selection:
            return

        try:
            self.save_command(deepcopy(self.visible_options[int(selection[0])]))
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot add book content",
                str(error),
                parent=self,
            )
            return

        self.close_dialog()

    def focus_search(self):
        self.search_control.focus_set()

    def close_dialog(self):
        self.destroy()


class BookHoldingDialog(tk.Toplevel):
    def __init__(self, parent, controller, holding, save_command):
        super().__init__(parent)
        self.controller = controller
        self.holding = deepcopy(holding) if isinstance(holding, dict) else {}
        self.save_command = save_command
        self.organization_id = str(
            self.holding.get("organization_id", "") or ""
        ).strip()
        self.person_id = str(self.holding.get("person_id", "") or "").strip()
        self.location_id = str(
            self.holding.get("location_id", "") or ""
        ).strip()
        start_year, start_month, start_day = split_world_event_date(
            self.holding.get("available_from", "")
        )
        end_year, end_month, end_day = split_world_event_date(
            self.holding.get("available_until", "")
        )
        sold_year, sold_month, sold_day = split_world_event_date(
            self.holding.get("sold_out_date", "")
        )
        self.holder_type_value = tk.StringVar(
            value=self.holding.get("holder_type", BOOK_HOLDER_TYPES[0])
        )
        self.holder_value = tk.StringVar(
            value=self.holding.get("holder_name", "No holder selected")
            or "No holder selected"
        )
        self.start_year_value = tk.StringVar(value=start_year)
        self.start_month_value = tk.StringVar(value=start_month)
        self.start_day_value = tk.StringVar(value=start_day)
        self.end_year_value = tk.StringVar(value=end_year)
        self.end_month_value = tk.StringVar(value=end_month)
        self.end_day_value = tk.StringVar(value=end_day)
        self.sold_year_value = tk.StringVar(value=sold_year)
        self.sold_month_value = tk.StringVar(value=sold_month)
        self.sold_day_value = tk.StringVar(value=sold_day)
        self.copies_value = tk.StringVar(
            value=(
                ""
                if self.holding.get("copies") is None
                else str(self.holding.get("copies"))
            )
        )
        self.price_value = tk.StringVar(
            value=(
                ""
                if self.holding.get("price_sickles") is None
                else str(self.holding.get("price_sickles"))
            )
        )
        self.title("Edit Book Holding" if self.holding else "Add Book Holding")
        self.geometry("740x680")
        self.minsize(650, 600)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.notes_field.text.insert(
            "1.0",
            str(self.holding.get("notes", "") or ""),
        )
        self.holder_type_value.trace_add("write", self.holder_type_changed)
        self.grab_set()

    def build_dialog(self):
        heading = tk.Label(
            self,
            text="Edit holding" if self.holding else "Add holding",
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(15, "bold"),
            anchor="w",
            padx=20,
            pady=13,
        )
        heading.grid(row=0, column=0, sticky="ew")
        body = tk.Frame(self, bg=SURFACE, padx=22, pady=18)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(5, weight=1)
        holder_row = tk.Frame(body, bg=SURFACE)
        holder_row.grid(row=0, column=0, sticky="ew")
        holder_row.grid_columnconfigure(1, weight=1)
        type_select = RoundedSelect(
            holder_row,
            self.holder_type_value,
            BOOK_HOLDER_TYPES,
            background=SURFACE,
            width=160,
            height=40,
        )
        type_select.grid(row=0, column=0, padx=(0, 8))
        holder_label = tk.Label(
            holder_row,
            textvariable=self.holder_value,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
            padx=12,
            pady=10,
        )
        holder_label.grid(row=0, column=1, sticky="ew")
        choose_button = SoftButton(
            holder_row,
            text="Choose…",
            command=self.open_holder_picker,
            background=SURFACE,
            width=88,
            height=40,
        )
        choose_button.grid(row=0, column=2, padx=(8, 0))
        self.build_date_row(
            body,
            1,
            "Available from",
            self.start_year_value,
            self.start_month_value,
            self.start_day_value,
        )
        self.build_date_row(
            body,
            2,
            "Available until",
            self.end_year_value,
            self.end_month_value,
            self.end_day_value,
        )
        self.build_date_row(
            body,
            3,
            "Sold out on",
            self.sold_year_value,
            self.sold_month_value,
            self.sold_day_value,
        )
        numbers_row = tk.Frame(body, bg=SURFACE)
        numbers_row.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        numbers_row.grid_columnconfigure(0, weight=1)
        numbers_row.grid_columnconfigure(1, weight=1)
        copies_field = LabeledEntry(
            numbers_row,
            "Copies (blank means unlimited)",
            self.copies_value,
            background=SURFACE,
        )
        copies_field.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        price_field = LabeledEntry(
            numbers_row,
            "Price in sickles (shops)",
            self.price_value,
            background=SURFACE,
        )
        price_field.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.notes_field = MultilineField(
            body,
            "Holding notes",
            120,
            background=SURFACE,
        )
        self.notes_field.grid(row=5, column=0, sticky="nsew", pady=(12, 0))
        footer = tk.Frame(self, bg=APP_BACKGROUND)
        footer.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 16))
        footer.grid_columnconfigure(0, weight=1)
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=APP_BACKGROUND,
            width=88,
            height=38,
        )
        cancel_button.grid(row=0, column=1, padx=(0, 7))
        save_button = SoftButton(
            footer,
            text="Save holding",
            command=self.save_holding,
            background=APP_BACKGROUND,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=122,
            height=38,
        )
        save_button.grid(row=0, column=2)

    def build_date_row(self, parent, row, label_text, year, month, day):
        date_row = tk.Frame(parent, bg=SURFACE)
        date_row.grid(row=row, column=0, sticky="ew", pady=(12, 0))
        date_row.grid_columnconfigure(0, minsize=150)
        label = tk.Label(
            date_row,
            text=label_text,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        label.grid(row=0, column=0, sticky="w")
        year_control = RoundedEntry(
            date_row,
            textvariable=year,
            background=SURFACE,
            width=110,
            height=36,
        )
        year_control.grid(row=0, column=1, padx=(0, 7))
        month_control = RoundedEntry(
            date_row,
            textvariable=month,
            background=SURFACE,
            width=74,
            height=36,
        )
        month_control.grid(row=0, column=2, padx=(0, 7))
        day_control = RoundedEntry(
            date_row,
            textvariable=day,
            background=SURFACE,
            width=74,
            height=36,
        )
        day_control.grid(row=0, column=3)

    def holder_type_changed(self, *arguments):
        self.organization_id = ""
        self.person_id = ""
        self.location_id = ""
        self.holder_value.set("No holder selected")

    def open_holder_picker(self):
        holder_type = self.holder_type_value.get()

        if holder_type in ("Library", "Shop"):
            OrganizationSelectionDialog(
                self,
                list(self.controller.organizations_by_id().values()),
                self.organization_selected,
                location_provider=self.controller.location_provider,
            )
        elif holder_type == "Private owner":
            EventPersonPickerDialog(
                self,
                self.controller.people_options(),
                self.controller.recent_people_options(),
                self.person_id,
                self.person_selected,
                mage_groups=self.controller.mage_groups(),
                dialog_title="Choose book owner",
                heading_text="Choose the private owner",
                selection_prompt="Select the person who owns this copy.",
                action_text="Use owner",
            )
        else:
            EventLocationPickerDialog(
                self,
                list(self.controller.locations_by_id().values()),
                self.location_id,
                self.location_selected,
                dialog_title="Choose archive location",
                action_text="Use location",
            )

    def organization_selected(self, organization):
        self.organization_id = str(
            organization.get("record_id", "") or ""
        ).strip()
        self.person_id = ""
        self.location_id = ""
        self.holder_value.set(
            self.controller.holding_name(
                {
                    "holder_type": self.holder_type_value.get(),
                    "organization_id": self.organization_id,
                    "holder_name": organization.get("name", ""),
                }
            )
        )

    def person_selected(self, person_id):
        self.person_id = str(person_id or "").strip()
        self.organization_id = ""
        self.location_id = ""
        self.holder_value.set(
            self.controller.holding_name(
                {
                    "holder_type": "Private owner",
                    "person_id": self.person_id,
                    "holder_name": "",
                }
            )
        )

    def location_selected(self, location_id):
        self.location_id = str(location_id or "").strip()
        self.organization_id = ""
        self.person_id = ""
        self.holder_value.set(
            self.controller.holding_name(
                {
                    "holder_type": "Location archive",
                    "location_id": self.location_id,
                    "holder_name": "",
                }
            )
        )

    def optional_date_value(self, year_value, month_value, day_value, label):
        year = year_value.get().strip()
        month = month_value.get().strip()
        day = day_value.get().strip()

        if not year:
            if month or day:
                raise ValueError(f"{label} month and day require a year.")

            return ""

        if day and not month:
            raise ValueError(f"{label} day requires a month.")

        return year + (f"-{month}" if month else "") + (
            f"-{day}" if day else ""
        )

    def values(self):
        return {
            **deepcopy(self.holding),
            "holder_type": self.holder_type_value.get(),
            "organization_id": self.organization_id,
            "person_id": self.person_id,
            "location_id": self.location_id,
            "holder_name": self.holder_value.get(),
            "available_from": self.optional_date_value(
                self.start_year_value,
                self.start_month_value,
                self.start_day_value,
                "Available from",
            ),
            "available_until": self.optional_date_value(
                self.end_year_value,
                self.end_month_value,
                self.end_day_value,
                "Available until",
            ),
            "sold_out_date": self.optional_date_value(
                self.sold_year_value,
                self.sold_month_value,
                self.sold_day_value,
                "Sold out",
            ),
            "copies": self.copies_value.get().strip(),
            "price_sickles": self.price_value.get().strip(),
            "notes": self.notes_field.text.get("1.0", "end-1c"),
        }

    def save_holding(self):
        try:
            saved = self.save_command(self.values())
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot save holding",
                str(error),
                parent=self,
            )
            return

        if saved is not False:
            self.close_dialog()

    def close_dialog(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass

        self.destroy()


class BookReadingDialog(tk.Toplevel):
    def __init__(self, parent, controller, person_id, save_command):
        super().__init__(parent)
        self.controller = controller
        self.person_id = str(person_id or "").strip()
        self.save_command = save_command
        self.options = []
        self.year_value = tk.StringVar()
        self.month_value = tk.StringVar()
        self.day_value = tk.StringVar()
        self.search_value = tk.StringVar()
        self.result_value = tk.StringVar(
            value="Enter a reading date, then find available books."
        )
        self.title("Record Book Reading")
        self.geometry("720x620")
        self.minsize(580, 500)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.search_value.trace_add("write", self.filter_results)
        self.grab_set()

    def build_dialog(self):
        heading = tk.Label(
            self,
            text="Record reading",
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(15, "bold"),
            anchor="w",
            padx=20,
            pady=13,
        )
        heading.grid(row=0, column=0, sticky="ew")
        body = tk.Frame(self, bg=SURFACE, padx=20, pady=18)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(4, weight=1)
        body.grid_columnconfigure(0, weight=1)
        date_row = tk.Frame(body, bg=SURFACE)
        date_row.grid(row=0, column=0, sticky="ew")
        year_control = RoundedEntry(
            date_row,
            textvariable=self.year_value,
            background=SURFACE,
            width=112,
            height=38,
        )
        year_control.grid(row=0, column=0, padx=(0, 7))
        month_control = RoundedEntry(
            date_row,
            textvariable=self.month_value,
            background=SURFACE,
            width=78,
            height=38,
        )
        month_control.grid(row=0, column=1, padx=(0, 7))
        day_control = RoundedEntry(
            date_row,
            textvariable=self.day_value,
            background=SURFACE,
            width=78,
            height=38,
        )
        day_control.grid(row=0, column=2, padx=(0, 8))
        find_button = SoftButton(
            date_row,
            text="Find available books",
            command=self.find_available_books,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=170,
            height=38,
        )
        find_button.grid(row=0, column=3)
        hint = tk.Label(
            body,
            text="Date: year, optional month, optional day",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        hint.grid(row=1, column=0, sticky="ew", pady=(5, 10))
        self.search_control = RoundedEntry(
            body,
            textvariable=self.search_value,
            background=SURFACE,
            height=38,
        )
        self.search_control.grid(row=2, column=0, sticky="ew")
        result_label = tk.Label(
            body,
            textvariable=self.result_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=650,
        )
        result_label.grid(row=3, column=0, sticky="ew", pady=(8, 5))
        list_frame = tk.Frame(
            body,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        list_frame.grid(row=4, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.results_list = tk.Listbox(
            list_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            font=app_font(10),
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            activestyle="none",
            exportselection=False,
        )
        self.results_list.grid(row=0, column=0, sticky="nsew")
        self.results_list.bind("<Double-Button-1>", self.save_reading)
        scrollbar = tk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.results_list.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.results_list.configure(yscrollcommand=scrollbar.set)
        footer = tk.Frame(self, bg=APP_BACKGROUND)
        footer.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 16))
        footer.grid_columnconfigure(0, weight=1)
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=APP_BACKGROUND,
            width=88,
            height=38,
        )
        cancel_button.grid(row=0, column=1, padx=(0, 7))
        record_button = SoftButton(
            footer,
            text="Record reading",
            command=self.save_reading,
            background=APP_BACKGROUND,
            fill=ADD_GREEN,
            hover_fill=ADD_GREEN_HOVER,
            foreground=TEXT_DARK,
            width=128,
            height=38,
        )
        record_button.grid(row=0, column=2)

    def reading_date_value(self):
        year = self.year_value.get().strip()
        month = self.month_value.get().strip()
        day = self.day_value.get().strip()

        if not year:
            raise ValueError("Reading year is required.")

        if day and not month:
            raise ValueError("Reading day requires a month.")

        return year + (f"-{month}" if month else "") + (
            f"-{day}" if day else ""
        )

    def find_available_books(self):
        try:
            reading_date = self.reading_date_value()
            self.options = self.controller.available_sources_for_person(
                self.person_id,
                reading_date,
            )
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot find available books",
                str(error),
                parent=self,
            )
            return

        self.filter_results()

    def filter_results(self, *arguments):
        query_terms = [
            term
            for term in self.search_value.get().strip().casefold().split()
            if term
        ]
        visible_options = [
            option
            for option in self.options
            if all(term in option["label"].casefold() for term in query_terms)
        ]
        self.visible_options = visible_options
        self.results_list.delete(0, "end")

        for option in visible_options:
            self.results_list.insert("end", option["label"])

        if not self.options:
            slot_state = None

            try:
                slot_state = self.controller.reading_slot_state(
                    self.person_id,
                    self.reading_date_value(),
                )
            except (TypeError, ValueError):
                pass

            if slot_state is not None and slot_state["remaining"] <= 0:
                self.result_value.set(
                    "No reading slot remains for this year. No book will "
                    "be recorded."
                )
            else:
                self.result_value.set(
                    "No eligible book is available on this date. The "
                    "catalog checks publication, dated holdings, regional "
                    "access, school access, stock, money, and annual slots."
                )
            return

        count = len(visible_options)
        self.result_value.set(
            f"{count} available source"
            if count == 1
            else f"{count} available sources"
        )

    def save_reading(self, event=None):
        selection = self.results_list.curselection()

        if not selection:
            return

        option = self.visible_options[int(selection[0])]

        try:
            reading = self.controller.record_reading(
                self.person_id,
                option["book_id"],
                self.reading_date_value(),
                option["source_entry_id"],
            )
            self.save_command(reading)
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot record reading",
                str(error),
                parent=self,
            )
            return

        self.close_dialog()

    def close_dialog(self):
        self.destroy()
