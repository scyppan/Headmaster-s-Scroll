import tkinter as tk
from tkinter import messagebox

from mage_maker.sections.family_tree.relationships import format_person_date
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
        card.grid_rowconfigure(5, weight=1)
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

        list_frame = tk.Frame(card, bg=SURFACE)
        list_frame.grid(row=5, column=0, sticky="nsew")
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
        footer.grid(row=6, column=0, sticky="ew", pady=(14, 0))
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
        available_people = list(self.primary_people)

        if self.show_alternate_value.get():
            available_people.extend(self.alternate_people)

        self.visible_people = [
            person
            for person in available_people
            if not query
            or query in str(person.get("displayed_name", "")).casefold()
        ]
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
        )

    def create_basic_person(self, displayed_name):
        created_person = self.create_command(displayed_name)
        self.after_idle(self.destroy)
        return created_person

    def close_dialog(self, event=None):
        self.destroy()
        return "break"

    def focus_search(self):
        self.search_entry.focus_set()


class BasicRelationshipDialog(tk.Toplevel):
    def __init__(self, parent, heading, explanation, save_command):
        super().__init__(parent)
        self.save_command = save_command
        self.displayed_name_value = tk.StringVar()

        self.title("Enter new character")
        self.geometry("470x250")
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

        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(row=3, column=0, sticky="e", pady=(14, 0))
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

        try:
            created_person = self.save_command(displayed_name)
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror("Cannot add character", str(error), parent=self)
            return

        if created_person is not None:
            self.destroy()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"
