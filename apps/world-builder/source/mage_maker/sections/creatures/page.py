import tkinter as tk
import uuid
from copy import deepcopy
from tkinter import messagebox

from mage_maker.core.dates import (
    format_date_parts,
    format_historical_display_date,
    normalize_historical_date_parts,
    split_partial_date,
)
from mage_maker.sections.creatures.models import solidify_named_creature
from mage_maker.sections.items.link_dialog import RecordLinkDialog
from mage_maker.ui.theme import (
    APP_BACKGROUND, BORDER, BUTTON_SOFT, BUTTON_SOFT_HOVER, FIELD_BACKGROUND,
    LIST_SELECTED, PRIMARY_DARK, SURFACE, TEXT_DARK, TEXT_LIGHT, app_font,
)
from mage_maker.ui.widgets import RoundedEntry, SoftButton


RELATIONSHIP_LABELS = {
    "tamed_creature": "Tamed by",
    "bonded_creature": "Bonded with",
    "irked_creature": "Irked",
}
RELATIONSHIP_TYPES_BY_LABEL = {
    label: event_type for event_type, label in RELATIONSHIP_LABELS.items()
}


class CreatureRelationshipDialog(tk.Toplevel):
    """Edit a normalized dated relationship event for a named creature."""

    def __init__(self, parent, event_controller, creature, save_command, event=None):
        super().__init__(parent)
        self.event_controller = event_controller
        self.creature = creature
        self.save_command = save_command
        self.event = deepcopy(event) if isinstance(event, dict) else {}
        self.person_ids = list(self.event.get("person_ids", []) or [])
        self.relationship_value = tk.StringVar(
            value=RELATIONSHIP_LABELS.get(
                self.event.get("event_type"), "Tamed by"
            )
        )
        year, month, day = split_partial_date(
            self.event.get("date", ""), "Relationship date"
        )
        self.year_value = tk.StringVar(value=year)
        self.month_value = tk.StringVar(value=month)
        self.day_value = tk.StringVar(value=day)
        self.people_value = tk.StringVar()
        self.title("Creature relationship")
        self.configure(bg=APP_BACKGROUND)
        self.geometry("620x420")
        self.minsize(540, 380)
        self.transient(parent.winfo_toplevel())
        self._build()
        self._refresh_people_label()
        self.grab_set()

    def _build(self):
        shell = tk.Frame(
            self, bg=SURFACE, highlightbackground=BORDER,
            highlightthickness=1, padx=16, pady=14,
        )
        shell.pack(fill="both", expand=True, padx=12, pady=12)
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(6, weight=1)
        tk.Label(
            shell, text=self.creature.get("name", "Named creature"),
            bg=SURFACE, fg=TEXT_DARK, font=app_font(14, "bold"), anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tk.Label(
            shell, text="Relationship", bg=SURFACE, fg=TEXT_DARK,
            font=app_font(9, "bold"), anchor="w",
        ).grid(row=1, column=0, sticky="ew")
        relationship = tk.OptionMenu(
            shell, self.relationship_value, *RELATIONSHIP_TYPES_BY_LABEL
        )
        relationship.configure(bg=FIELD_BACKGROUND, fg=TEXT_DARK, anchor="w")
        relationship.grid(row=2, column=0, sticky="ew", pady=(3, 10))

        date_row = tk.Frame(shell, bg=SURFACE)
        date_row.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        for column, (label, value) in enumerate((
            ("Year", self.year_value),
            ("Month", self.month_value),
            ("Day", self.day_value),
        )):
            date_row.grid_columnconfigure(column, weight=1)
            tk.Label(
                date_row, text=label, bg=SURFACE, fg=TEXT_DARK,
                font=app_font(9, "bold"), anchor="w",
            ).grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 5, 0))
            tk.Entry(
                date_row, textvariable=value, bg=FIELD_BACKGROUND,
                fg=TEXT_DARK, relief="solid", bd=1,
            ).grid(row=1, column=column, sticky="ew", padx=(0 if column == 0 else 5, 0))

        people = tk.Frame(shell, bg=SURFACE)
        people.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        people.grid_columnconfigure(0, weight=1)
        tk.Label(
            people, textvariable=self.people_value, bg=SURFACE,
            fg=TEXT_DARK, anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        SoftButton(
            people, text="Choose people...", command=self.choose_people,
            background=SURFACE, fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER, foreground=TEXT_DARK, height=30,
        ).grid(row=0, column=1, padx=(8, 0))

        tk.Label(
            shell, text="Details", bg=SURFACE, fg=TEXT_DARK,
            font=app_font(9, "bold"), anchor="w",
        ).grid(row=5, column=0, sticky="ew")
        self.description = tk.Text(
            shell, height=6, wrap="word", bg=FIELD_BACKGROUND,
            fg=TEXT_DARK, relief="solid", bd=1,
        )
        self.description.grid(row=6, column=0, sticky="nsew", pady=(3, 10))
        self.description.insert("1.0", self.event.get("description", ""))
        actions = tk.Frame(shell, bg=SURFACE)
        actions.grid(row=7, column=0, sticky="ew")
        SoftButton(
            actions, text="Cancel", command=self.destroy,
            background=SURFACE, fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER, foreground=TEXT_DARK, height=30,
        ).pack(side="right")
        SoftButton(
            actions, text="Save relationship", command=self.save,
            background=SURFACE, fill=PRIMARY_DARK,
            hover_fill=BUTTON_SOFT_HOVER, foreground=TEXT_LIGHT, height=30,
        ).pack(side="right", padx=(0, 8))

    def choose_people(self):
        options = []
        for option in self.event_controller.people_options():
            label = str(option.get("label", "") or "Unnamed person")
            group = str(option.get("group_name", "") or "People")
            options.append({
                "value": str(option.get("value", "") or ""),
                "label": label,
                "group": group,
                "search_text": f"{label} {group}",
            })
        RecordLinkDialog(
            self, "Choose People", "Choose people in this relationship",
            "Search the complete people catalog.", options, self.person_ids,
            self.people_chosen, "Choose people", group_label="Mage group",
            result_limit=200,
        )

    def people_chosen(self, ids, *_unused):
        self.person_ids = list(ids or [])
        self._refresh_people_label()

    def _refresh_people_label(self):
        labels_by_id = self.event_controller.people_option_labels(self.person_ids)
        labels = [
            labels_by_id.get(person_id, "Unknown person")
            for person_id in self.person_ids
        ]
        self.people_value.set(
            ", ".join(labels) if labels else "No people selected"
        )

    def save(self):
        if not self.person_ids:
            messagebox.showerror(
                "Creature relationship", "Choose at least one person.", parent=self
            )
            return
        try:
            year, month, day = normalize_historical_date_parts(
                self.year_value.get(), self.month_value.get(),
                self.day_value.get(), "Relationship date", required_year=True,
            )
        except ValueError as error:
            messagebox.showerror("Creature relationship", str(error), parent=self)
            return
        event_type = RELATIONSHIP_TYPES_BY_LABEL[self.relationship_value.get()]
        values = {
            "event_type": event_type,
            "title": f"{RELATIONSHIP_LABELS[event_type]} {self.creature.get('name', 'creature')}",
            "date": format_date_parts(year, month, day, unknown=""),
            "description": self.description.get("1.0", "end-1c").strip(),
            "person_ids": list(self.person_ids),
            "named_creature_id": str(self.creature.get("record_id", "")),
            "named_creature_name": str(self.creature.get("name", "")),
        }
        try:
            self.save_command(values, self.event)
        except Exception as error:
            messagebox.showerror("Creature relationship", str(error), parent=self)
            return
        self.destroy()


class NamedCreaturesPage(tk.Frame):
    """Permanent named creatures with fixed stats and dated relationships."""

    def __init__(
        self, parent, database, game_database, status_command,
        records_changed_command=None, event_controller=None,
    ):
        super().__init__(parent, bg=APP_BACKGROUND)
        self.database = database
        self.game_database = game_database
        self.event_controller = event_controller
        self.status_command = status_command
        self.records_changed_command = records_changed_command
        self.records = []
        self.visible = []
        self.selected_id = ""
        self.selected_record = {}
        self.relationships = []
        self.species_id = ""
        self.species_name = tk.StringVar(value="No species selected")
        self.search_value = tk.StringVar()
        self.name_value = tk.StringVar()
        self.birth_year = tk.StringVar()
        self.birth_month = tk.StringVar()
        self.birth_day = tk.StringVar()
        self.death_year = tk.StringVar()
        self.death_month = tk.StringVar()
        self.death_day = tk.StringVar()
        self.stat_values = {
            key: tk.StringVar(value="—")
            for key in (
                "size", "heavy_wound_cap", "magical_resistance",
                "intelligence", "social_skill", "movement",
            )
        }
        self._species_records = {
            str(record.get("record_id", "") or ""): record
            for record in self.game_database.collection("creatures")
            if isinstance(record, dict)
        }
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

        dates = tk.LabelFrame(form, text="Life dates", bg=SURFACE, fg=TEXT_DARK, padx=8, pady=7)
        dates.grid(row=3, column=0, sticky="ew", pady=(12, 8))
        date_fields = (
            ("Birth year", self.birth_year), ("Month", self.birth_month),
            ("Day", self.birth_day), ("Death year", self.death_year),
            ("Month", self.death_month), ("Day", self.death_day),
        )
        for column, (label, value) in enumerate(date_fields):
            dates.grid_columnconfigure(column, weight=1)
            tk.Label(dates, text=label, bg=SURFACE, fg=TEXT_DARK, font=app_font(8, "bold"), anchor="w").grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 4, 0))
            tk.Entry(dates, textvariable=value, bg=FIELD_BACKGROUND, fg=TEXT_DARK, relief="solid", bd=1).grid(row=1, column=column, sticky="ew", padx=(0 if column == 0 else 4, 0))

        stats = tk.LabelFrame(form, text="Permanent stats", bg=SURFACE, fg=TEXT_DARK, padx=8, pady=7)
        stats.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        for index, (label, key) in enumerate((
            ("Size", "size"), ("Heavy wounds", "heavy_wound_cap"),
            ("Resistance", "magical_resistance"),
            ("Intelligence", "intelligence"), ("Social", "social_skill"),
            ("Movement", "movement"),
        )):
            row, column = divmod(index, 3)
            stats.grid_columnconfigure(column, weight=1)
            cell = tk.Frame(stats, bg=SURFACE)
            cell.grid(row=row, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0), pady=2)
            tk.Label(cell, text=f"{label}:", bg=SURFACE, fg=TEXT_DARK, font=app_font(8, "bold")).pack(side="left")
            tk.Label(cell, textvariable=self.stat_values[key], bg=SURFACE, fg=TEXT_DARK).pack(side="left", padx=(4, 0))
        self.actions_list = tk.Listbox(stats, height=3, exportselection=False, bg=FIELD_BACKGROUND, fg=TEXT_DARK, selectbackground=LIST_SELECTED)
        self.actions_list.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(6, 0))

        relationships = tk.LabelFrame(form, text="Dated relationships", bg=SURFACE, fg=TEXT_DARK, padx=8, pady=7)
        relationships.grid(row=5, column=0, sticky="nsew", pady=(0, 8))
        relationships.grid_columnconfigure(0, weight=1)
        form.grid_rowconfigure(5, weight=1)
        self.relationship_list = tk.Listbox(relationships, height=4, exportselection=False, bg=FIELD_BACKGROUND, fg=TEXT_DARK, selectbackground=LIST_SELECTED)
        self.relationship_list.grid(row=0, column=0, sticky="nsew")
        relationship_actions = tk.Frame(relationships, bg=SURFACE)
        relationship_actions.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        for label, command in (("Add", self.add_relationship), ("Edit", self.edit_relationship), ("Delete", self.delete_relationship)):
            SoftButton(relationship_actions, text=label, command=command, background=SURFACE, fill=BUTTON_SOFT, hover_fill=BUTTON_SOFT_HOVER, foreground=TEXT_DARK, height=28).pack(side="left", padx=(0, 5))

        actions = tk.Frame(form, bg=SURFACE)
        actions.grid(row=6, column=0, sticky="ew", pady=(6, 0))
        SoftButton(actions, text="Delete", command=self.delete, background=SURFACE, fill=BUTTON_SOFT, hover_fill=BUTTON_SOFT_HOVER, foreground=TEXT_DARK, height=30).pack(side="left")
        SoftButton(actions, text="Save", command=self.save, background=SURFACE, fill=PRIMARY_DARK, hover_fill=BUTTON_SOFT_HOVER, foreground=TEXT_LIGHT, height=30).pack(side="right")

    def refresh(self):
        self.records = self.database.list_records("named_creatures")
        changed = False
        for record in self.records:
            if record.get("statistics_solidified"):
                continue
            species = self._species_records.get(
                str(record.get("species_record_id", "") or "")
            )
            if species is None:
                continue
            solidified, was_changed = solidify_named_creature(record, species)
            if was_changed:
                self.database.update_record(
                    "named_creatures", record["record_id"], solidified
                )
                changed = True
        if changed:
            self.status_command("Solidifying named-creature statistics...")
            self.database.save()
            self.records = self.database.list_records("named_creatures")
            self.status_command("Named-creature statistics are permanent")
        self.render_list()
        if self.selected_id:
            current = next((
                record for record in self.records
                if str(record.get("record_id", "")) == self.selected_id
            ), None)
            if current:
                self.load_record(current)

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
        self.load_record(self.visible[selection[0]])

    def load_record(self, record):
        self.selected_record = deepcopy(record)
        self.selected_id = str(record.get("record_id", ""))
        self.name_value.set(record.get("name", ""))
        self.species_id = str(record.get("species_record_id", ""))
        self.species_name.set(record.get("species_name", "No species selected"))
        self._set_date_values("birth", record.get("birth_date", ""))
        self._set_date_values("death", record.get("death_date", ""))
        self._render_stats(record)
        self._refresh_relationships()

    def _set_date_values(self, prefix, value):
        year, month, day = split_partial_date(value, f"{prefix.title()} date")
        getattr(self, f"{prefix}_year").set(year)
        getattr(self, f"{prefix}_month").set(month)
        getattr(self, f"{prefix}_day").set(day)

    def _render_stats(self, record):
        generated = record.get("generated") or {}
        for key in (
            "size", "heavy_wound_cap", "magical_resistance",
            "intelligence", "social_skill",
        ):
            value = generated.get(key)
            self.stat_values[key].set("—" if value is None else str(value))
        movement = generated.get("movement") or {}
        self.stat_values["movement"].set(
            ", ".join(
                f"{name}: {value}" for name, value in movement.items()
                if value is not None
            ) or "None"
        )
        self.actions_list.delete(0, "end")
        for action in record.get("actions", []) or []:
            adjusted = action.get("adjusted_range") or {}
            self.actions_list.insert(
                "end",
                f"{action.get('name', 'Action')} · {action.get('aptitude', 'typical')} · "
                f"{adjusted.get('low', 0)}–{adjusted.get('high', 0)}",
            )
        if not self.actions_list.size():
            self.actions_list.insert("end", "No attacks or abilities")

    def new(self):
        self.selected_id = ""
        self.selected_record = {}
        self.name_value.set("")
        self.species_id = ""
        self.species_name.set("No species selected")
        self._set_date_values("birth", "")
        self._set_date_values("death", "")
        self._render_stats({})
        self.relationships = []
        self.relationship_list.delete(0, "end")

    def choose_species(self):
        if self.selected_id:
            messagebox.showinfo(
                "Named Creature",
                "This creature's species and generated stats are already established.",
                parent=self,
            )
            return
        options = []
        for record in self._species_records.values():
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
        try:
            birth_date = self._date_value("birth")
            death_date = self._date_value("death")
        except ValueError as error:
            messagebox.showerror("Named Creature", str(error), parent=self)
            return
        if self.selected_id:
            values = deepcopy(self.selected_record)
            values.update({
                "name": name,
                "birth_date": birth_date,
                "death_date": death_date,
            })
            self.database.update_record("named_creatures", self.selected_id, values)
        else:
            values = {
                "record_id": str(uuid.uuid4()),
                "name": name,
                "species_record_id": self.species_id,
                "species_name": self.species_name.get(),
                "birth_date": birth_date,
                "death_date": death_date,
            }
            species = self._species_records.get(self.species_id)
            if species is None:
                messagebox.showerror(
                    "Named Creature", "That creature species no longer exists.",
                    parent=self,
                )
                return
            values, _changed = solidify_named_creature(values, species)
            created = self.database.create_record("named_creatures", values)
            self.selected_id = created["record_id"]
        self.database.save()
        self.refresh()
        self.status_command("Named creature saved")
        if callable(self.records_changed_command):
            self.records_changed_command()

    def _date_value(self, prefix):
        year, month, day = normalize_historical_date_parts(
            getattr(self, f"{prefix}_year").get(),
            getattr(self, f"{prefix}_month").get(),
            getattr(self, f"{prefix}_day").get(),
            f"{prefix.title()} date", required_year=False,
        )
        return format_date_parts(year, month, day, unknown="")

    def _refresh_relationships(self):
        self.relationship_list.delete(0, "end")
        if not self.selected_id or self.event_controller is None:
            self.relationships = []
            return
        self.relationships = [
            event
            for event in self.event_controller.events_for_named_creature(
                self.selected_id
            )
            if event.get("event_type") in RELATIONSHIP_LABELS
        ]
        person_ids = {
            person_id
            for event in self.relationships
            for person_id in event.get("person_ids", []) or []
        }
        labels = self.event_controller.people_option_labels(person_ids)
        for event in self.relationships:
            people = ", ".join(
                labels.get(person_id, "Unknown person")
                for person_id in event.get("person_ids", []) or []
            ) or "No person"
            self.relationship_list.insert(
                "end",
                f"{format_historical_display_date(event.get('date', ''))} · "
                f"{RELATIONSHIP_LABELS.get(event.get('event_type'), 'Related to')} · {people}",
            )

    def add_relationship(self):
        if not self.selected_id:
            messagebox.showinfo(
                "Creature relationship", "Save the named creature first.", parent=self
            )
            return
        if self.event_controller is not None:
            CreatureRelationshipDialog(
                self, self.event_controller, self.selected_record,
                self._save_relationship,
            )

    def edit_relationship(self):
        selection = self.relationship_list.curselection()
        if not selection or self.event_controller is None:
            return
        CreatureRelationshipDialog(
            self, self.event_controller, self.selected_record,
            self._save_relationship, self.relationships[selection[0]],
        )

    def _save_relationship(self, values, current):
        if current and current.get("record_id"):
            self.event_controller.update_event(current["record_id"], values)
        else:
            self.event_controller.create_event(values)
        self._refresh_relationships()
        if callable(self.records_changed_command):
            self.records_changed_command()

    def delete_relationship(self):
        selection = self.relationship_list.curselection()
        if not selection or self.event_controller is None:
            return
        event = self.relationships[selection[0]]
        if not messagebox.askyesno(
            "Delete relationship", "Delete this relationship event?", parent=self
        ):
            return
        self.event_controller.delete_event(event["record_id"])
        self._refresh_relationships()
        if callable(self.records_changed_command):
            self.records_changed_command()

    def delete(self):
        if not self.selected_id or not messagebox.askyesno("Delete", "Delete this named creature?", parent=self):
            return
        if self.relationships:
            messagebox.showerror(
                "Delete named creature",
                "Delete this creature's relationship events first.",
                parent=self,
            )
            return
        self.database.delete_record("named_creatures", self.selected_id)
        self.database.save()
        self.new()
        self.refresh()
        if callable(self.records_changed_command):
            self.records_changed_command()
