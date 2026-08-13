import tkinter as tk
import uuid
from tkinter import messagebox

from mage_maker.sections.items.link_dialog import RecordLinkDialog
from mage_maker.ui.theme import (
    APP_BACKGROUND, BORDER, BUTTON_SOFT, BUTTON_SOFT_HOVER, FIELD_BACKGROUND,
    LIST_SELECTED, PRIMARY_DARK, SURFACE, TEXT_DARK, TEXT_LIGHT, app_font,
)
from mage_maker.ui.widgets import RoundedEntry, SoftButton


class NamedCreaturesPage(tk.Frame):
    """Compact named-creature catalog with searchable species linking."""

    def __init__(self, parent, database, game_database, status_command, records_changed_command=None):
        super().__init__(parent, bg=APP_BACKGROUND)
        self.database = database
        self.game_database = game_database
        self.status_command = status_command
        self.records_changed_command = records_changed_command
        self.records = []
        self.visible = []
        self.selected_id = ""
        self.species_id = ""
        self.species_name = tk.StringVar(value="No species selected")
        self.search_value = tk.StringVar()
        self.name_value = tk.StringVar()
        self.build_page()
        self.search_value.trace_add("write", lambda *_: self.render_list())
        self.refresh()

    def build_page(self):
        shell = tk.Frame(self, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        shell.pack(fill="both", expand=True, padx=18, pady=18)
        shell.grid_columnconfigure(1, weight=1)
        shell.grid_rowconfigure(1, weight=1)
        tk.Label(shell, text="Named Creatures", bg=PRIMARY_DARK, fg=TEXT_LIGHT, font=app_font(16, "bold"), padx=14, pady=10, anchor="w").grid(row=0, column=0, columnspan=2, sticky="ew")
        left = tk.Frame(shell, bg=SURFACE, padx=10, pady=10)
        left.grid(row=1, column=0, sticky="nsew")
        RoundedEntry(left, textvariable=self.search_value, background=SURFACE, height=34).pack(fill="x", pady=(0, 6))
        self.listbox = tk.Listbox(left, width=32, exportselection=False, bg=FIELD_BACKGROUND, fg=TEXT_DARK, selectbackground=LIST_SELECTED)
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.choose)
        SoftButton(left, text="New", command=self.new, background=SURFACE, fill=BUTTON_SOFT, hover_fill=BUTTON_SOFT_HOVER, foreground=TEXT_DARK, height=30).pack(fill="x", pady=(7, 0))
        form = tk.Frame(shell, bg=SURFACE, padx=18, pady=18)
        form.grid(row=1, column=1, sticky="nsew")
        form.grid_columnconfigure(0, weight=1)
        tk.Label(form, text="Creature name", bg=SURFACE, fg=TEXT_DARK, font=app_font(9, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        RoundedEntry(form, textvariable=self.name_value, background=SURFACE, height=34).grid(row=1, column=0, sticky="ew", pady=(3, 12))
        species = tk.Frame(form, bg=SURFACE)
        species.grid(row=2, column=0, sticky="ew")
        species.grid_columnconfigure(0, weight=1)
        tk.Label(species, textvariable=self.species_name, bg=SURFACE, fg=TEXT_DARK, anchor="w").grid(row=0, column=0, sticky="ew")
        SoftButton(species, text="Choose species...", command=self.choose_species, background=SURFACE, fill=BUTTON_SOFT, hover_fill=BUTTON_SOFT_HOVER, foreground=TEXT_DARK, height=30).grid(row=0, column=1, padx=(7, 0))
        actions = tk.Frame(form, bg=SURFACE)
        actions.grid(row=3, column=0, sticky="ew", pady=(22, 0))
        SoftButton(actions, text="Delete", command=self.delete, background=SURFACE, fill=BUTTON_SOFT, hover_fill=BUTTON_SOFT_HOVER, foreground=TEXT_DARK, height=30).pack(side="left")
        SoftButton(actions, text="Save", command=self.save, background=SURFACE, fill=PRIMARY_DARK, hover_fill=BUTTON_SOFT_HOVER, foreground=TEXT_LIGHT, height=30).pack(side="right")

    def refresh(self):
        self.records = self.database.list_records("named_creatures")
        self.render_list()

    def render_list(self):
        query = self.search_value.get().strip().casefold()
        self.visible = [item for item in self.records if query in f"{item.get('name','')} {item.get('species_name','')}".casefold()]
        self.listbox.delete(0, "end")
        for item in self.visible:
            self.listbox.insert("end", f"{item.get('name', '')}  -  {item.get('species_name', '')}")

    def choose(self, _event=None):
        selection = self.listbox.curselection()
        if not selection:
            return
        record = self.visible[selection[0]]
        self.selected_id = str(record.get("record_id", ""))
        self.name_value.set(record.get("name", ""))
        self.species_id = str(record.get("species_record_id", ""))
        self.species_name.set(record.get("species_name", "No species selected"))

    def new(self):
        self.selected_id = ""
        self.name_value.set("")
        self.species_id = ""
        self.species_name.set("No species selected")

    def choose_species(self):
        options = []
        for record in self.game_database.collection("creatures"):
            record_id, name = str(record.get("record_id", "")), str(record.get("name", ""))
            if record_id and name:
                options.append({"value": record_id, "label": name, "group": str(record.get("creature_type", "Creature")), "search_text": f"{name} {record.get('creature_type','')} {record.get('classification','')} {record.get('description','')}"})
        self._species = {item["value"]: item for item in options}
        RecordLinkDialog(self, "Choose Species", "Choose a creature species", "Search the complete creature catalog.", options, [self.species_id] if self.species_id else [], self.species_chosen, "Choose species", group_label="Creature type", result_limit=200)

    def species_chosen(self, ids, *_unused):
        record = self._species.get(str((ids or [""])[0]))
        if record:
            self.species_id = record["value"]
            self.species_name.set(record["label"])

    def save(self):
        name = self.name_value.get().strip()
        if not name or not self.species_id:
            messagebox.showerror("Named Creature", "Enter a name and choose a species.", parent=self)
            return
        values = {"name": name, "species_record_id": self.species_id, "species_name": self.species_name.get()}
        if self.selected_id:
            self.database.update_record("named_creatures", self.selected_id, values)
        else:
            values["record_id"] = str(uuid.uuid4())
            created = self.database.create_record("named_creatures", values)
            self.selected_id = created["record_id"]
        self.database.save()
        self.refresh()
        self.status_command("Named creature saved")
        if callable(self.records_changed_command):
            self.records_changed_command()

    def delete(self):
        if not self.selected_id or not messagebox.askyesno("Delete", "Delete this named creature?", parent=self):
            return
        self.database.delete_record("named_creatures", self.selected_id)
        self.database.save()
        self.new()
        self.refresh()
        if callable(self.records_changed_command):
            self.records_changed_command()
