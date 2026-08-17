import tkinter as tk
from tkinter import messagebox, ttk
from copy import deepcopy
from uuid import uuid4

from headmasters_scroll.errors import SharedDataError
from runtime_theme import bind_theme
from sections.magic.proficiencies.constants import PROFICIENCY_SKILLS
from sections.nature_and_alchemy.creatures.form_fields import BoundedNumberField
from sections.nature_and_alchemy.creatures.tag_editor import TagEditor
from sections.nature_and_alchemy.recipes.controller import RecipeController
from sections.nature_and_alchemy.recipes.requirements import (
    CatalogReferenceDialog,
    RequirementGroupEditor,
    configure_recipe_tree,
)
from shared.widgets import MultilineField, RecordToolbar, RoundedEntry, RoundedSelect
from theme import APP_BACKGROUND, BORDER, SURFACE, SURFACE_MUTED, TEXT_DARK, TEXT_MUTED, app_font


class RecipesPage(tk.Frame):
    def __init__(self, parent, database):
        super().__init__(parent, bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")
        self.database = database
        self.controller = RecipeController(database)
        self.records = []
        self.current_record_id = None
        self.formulations = []
        self.current_formulation_index = 0
        self.output_item = None
        self.form_dirty = False
        self.loading = False
        self.grid_rowconfigure(1, weight=1); self.grid_columnconfigure(0, weight=1)
        self.toolbar = RecordToolbar(
            self, title="Recipes", new_command=self.new_record,
            delete_command=self.delete_record, revert_command=self.revert_record,
            save_command=self.save_record, duplicate_command=self.duplicate_record,
        )
        self.toolbar.grid(row=0, column=0, sticky="ew")
        panes = tk.PanedWindow(self, orient="horizontal", bg=BORDER, borderwidth=0, sashwidth=6)
        panes.grid(row=1, column=0, sticky="nsew", padx=25, pady=25)
        list_card = tk.Frame(panes, bg=SURFACE)
        list_card.grid_rowconfigure(1, weight=1); list_card.grid_columnconfigure(0, weight=1)
        self.query = tk.StringVar(); self.query.trace_add("write", self.refresh_list)
        RoundedEntry(list_card, textvariable=self.query, background=SURFACE, height=38, font=app_font(10)).grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        configure_recipe_tree(self, "RecipesCatalog.Treeview")
        self.tree = ttk.Treeview(
            list_card,
            columns=("skill",),
            show="tree headings",
            style="RecipesCatalog.Treeview",
        )
        self.tree.heading("#0", text="Recipe"); self.tree.heading("skill", text="Skill")
        self.tree.column("#0", width=210); self.tree.column("skill", width=90)
        self.tree.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.tree.bind("<<TreeviewSelect>>", self.select_record)
        form = tk.Frame(panes, bg=SURFACE)
        form.grid_columnconfigure(0, weight=1); form.grid_rowconfigure(3, weight=1)
        bind_theme(form, background="SURFACE")
        identity = tk.Frame(form, bg=SURFACE)
        identity.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))
        identity.grid_columnconfigure(0, weight=3); identity.grid_columnconfigure(1, weight=2); identity.grid_columnconfigure(2, weight=1)
        self.name = tk.StringVar(); self.skill = tk.StringVar()
        self.name.trace_add("write", self.mark_dirty); self.skill.trace_add("write", self.mark_dirty)
        self._field_label(identity, "Name", 0)
        RoundedEntry(identity, textvariable=self.name, background=SURFACE, height=40, font=app_font(11)).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        self._field_label(identity, "Skill", 1)
        RoundedSelect(identity, variable=self.skill, values=PROFICIENCY_SKILLS, background=SURFACE, height=40, font=app_font(10), placeholder="Select skill").grid(row=1, column=1, sticky="ew", padx=8)
        self._field_label(identity, "Threshold", 2)
        self.threshold = BoundedNumberField(identity, "", self.mark_dirty, minimum=1, maximum=100)
        self.threshold.grid(row=1, column=2, sticky="ew", padx=(8, 0))
        description_row = tk.Frame(form, bg=SURFACE)
        description_row.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 10))
        description_row.grid_columnconfigure(0, weight=2); description_row.grid_columnconfigure(1, weight=1)
        self.description = MultilineField(description_row, "Description", self.mark_dirty, height=6)
        self.description.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.tags = TagEditor(description_row, self.mark_dirty)
        self.tags.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        formulation = tk.Frame(form, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        formulation.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 10))
        formulation.grid_columnconfigure(1, weight=2)
        formulation.grid_columnconfigure(4, weight=3)
        tk.Label(formulation, text="Variant", bg=SURFACE, fg=TEXT_DARK, font=app_font(10)).grid(row=0, column=0, sticky="w", padx=(8, 4), pady=8)
        self.formulation_choice = tk.StringVar()
        self.formulation_combo = ttk.Combobox(formulation, textvariable=self.formulation_choice, state="readonly", width=22)
        self.formulation_combo.grid(row=0, column=1, sticky="ew", padx=4, pady=8)
        self.formulation_combo.bind("<<ComboboxSelected>>", self.select_formulation)
        ttk.Button(formulation, text="+", width=3, command=self.add_formulation).grid(row=0, column=2, padx=2)
        ttk.Button(formulation, text="⧉", width=3, command=self.duplicate_formulation).grid(row=0, column=3, padx=2)
        self.formulation_name = tk.StringVar()
        self.formulation_name.trace_add("write", self.handle_formulation_name_change)
        name_box = tk.Frame(formulation, bg=SURFACE)
        name_box.grid(row=0, column=4, sticky="ew", padx=4, pady=8)
        name_box.grid_columnconfigure(1, weight=1)
        tk.Label(name_box, text="Name", bg=SURFACE, fg=TEXT_DARK, font=app_font(9)).grid(row=0, column=0, padx=(0, 5))
        RoundedEntry(name_box, textvariable=self.formulation_name, background=SURFACE, height=36, font=app_font(9)).grid(row=0, column=1, sticky="ew")
        ttk.Button(formulation, text="−", width=3, command=self.delete_formulation).grid(row=0, column=5, padx=(2, 8))
        tk.Label(formulation, text="Output item", bg=SURFACE, fg=TEXT_DARK, font=app_font(9)).grid(row=1, column=0, sticky="w", padx=(8, 4), pady=(0, 8))
        self.output_button = tk.Button(
            formulation, text="Choose output item…", command=self.choose_output,
            anchor="w", relief="solid", bd=1, bg=APP_BACKGROUND,
            fg=TEXT_DARK, font=app_font(9),
        )
        self.output_button.grid(row=1, column=1, columnspan=3, sticky="ew", padx=4, pady=(0, 8))
        tk.Label(formulation, text="Output quantity", bg=SURFACE, fg=TEXT_DARK, font=app_font(9)).grid(row=1, column=4, sticky="e", padx=4, pady=(0, 8))
        self.output_quantity = tk.StringVar(value="1")
        self.output_quantity.trace_add("write", self.mark_dirty)
        ttk.Spinbox(formulation, textvariable=self.output_quantity, from_=1, to=100000, width=9).grid(row=1, column=5, sticky="w", padx=(2, 8), pady=(0, 8))

        requirements = tk.Frame(form, bg=SURFACE)
        requirements.grid(row=3, column=0, sticky="nsew", padx=18, pady=(0, 10))
        for column in range(4): requirements.grid_columnconfigure(column, weight=1)
        requirements.grid_rowconfigure(0, weight=1)
        self.ingredients = RequirementGroupEditor(requirements, "Required ingredients", database, "ingredient", self.mark_dirty)
        self.ingredients.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.vessels = RequirementGroupEditor(requirements, "Required vessels", database, "vessel", self.mark_dirty)
        self.vessels.grid(row=0, column=1, sticky="nsew", padx=5)
        self.proficiencies = RequirementGroupEditor(requirements, "Required Proficiencies", database, "proficiency", self.mark_dirty)
        self.proficiencies.grid(row=0, column=2, sticky="nsew", padx=5)
        self.spells = RequirementGroupEditor(requirements, "Required spells", database, "spell", self.mark_dirty)
        self.spells.grid(row=0, column=3, sticky="nsew", padx=(5, 0))
        self.notes = MultilineField(form, "DB Notes", self.mark_dirty, height=4)
        self.notes.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 18))
        panes.add(list_card, minsize=250, width=315); panes.add(form, minsize=760)
        self.status = tk.StringVar(value="Ready")
        tk.Label(self, textvariable=self.status, bg=SURFACE_MUTED, fg=TEXT_MUTED, font=app_font(9), anchor="w", padx=12, pady=7).grid(row=2, column=0, sticky="ew")
        self.refresh_records()
        self.load_record(self.records[0]["record_id"]) if self.records else self.new_record()

    def _field_label(self, parent, text, column):
        tk.Label(parent, text=text, bg=SURFACE, fg=TEXT_DARK, font=app_font(10), anchor="w").grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0), pady=(0, 4))

    def refresh_records(self, selected_id=None):
        self.records = self.controller.list_records(); self.refresh_list()
        if selected_id and self.tree.exists(selected_id): self.tree.selection_set(selected_id)

    def refresh_list(self, *_args):
        query = self.query.get().strip().casefold(); self.tree.delete(*self.tree.get_children())
        for record in self.records:
            searchable = f"{record.get('name', '')} {record.get('skill', '')} {' '.join(record.get('tags', []) or [])}".casefold()
            if query and query not in searchable: continue
            self.tree.insert("", "end", iid=str(record["record_id"]), text=str(record.get("name") or "Unnamed recipe"), values=(record.get("skill", ""),))

    def select_record(self, *_args):
        selected = self.tree.selection()
        if not selected or selected[0] == self.current_record_id: return
        if not self.confirm_unsaved_changes():
            if self.current_record_id: self.tree.selection_set(self.current_record_id)
            return
        self.load_record(selected[0])

    def load_record(self, record_id):
        record = self.controller.get_record(record_id)
        if record is None: return False
        self.loading = True; self.current_record_id = record_id
        self.name.set(record.get("name", "")); self.skill.set(record.get("skill", "")); self.threshold.set_value(record.get("threshold", 1))
        self.description.set_value(record.get("description", "")); self.tags.set_tags(record.get("tags", [])); self.notes.set_value(record.get("dbnotes", ""))
        self.formulations = deepcopy(record.get("formulations") or [{
            "record_id": str(uuid4()), "name": "Default",
            "output_item": record.get("output_item"),
            "output_quantity": record.get("output_quantity", 1),
            "ingredient_requirements": record.get("ingredient_requirements", []),
            "vessel_requirements": record.get("vessel_requirements", []),
            "proficiency_requirements": record.get("proficiency_requirements", []),
            "spell_requirements": record.get("spell_requirements", []),
        }])
        self.current_formulation_index = 0
        self.refresh_formulation_choices()
        self.load_formulation(0)
        self.loading = False; self.form_dirty = False
        self.toolbar.set_record_state(dirty=False, has_record=True); self.tree.selection_set(record_id); self.status.set(f"Loaded {record.get('name', 'recipe')}")
        return True

    def values(self):
        self.commit_current_formulation()
        return {
            "name": self.name.get(), "skill": self.skill.get(),
            "threshold": self.threshold.get_value(),
            "description": self.description.get_value(), "tags": self.tags.get_tags(),
            "dbnotes": self.notes.get_value(), "formulations": deepcopy(self.formulations),
        }

    def new_record(self):
        if not self.confirm_unsaved_changes(): return False
        self.loading = True; self.current_record_id = None
        self.name.set(""); self.skill.set(""); self.threshold.set_value(1); self.description.set_value(""); self.tags.set_tags([]); self.notes.set_value("")
        self.formulations = [self.blank_formulation("Default")]
        self.current_formulation_index = 0
        self.refresh_formulation_choices(); self.load_formulation(0)
        self.loading = False; self.form_dirty = False; self.toolbar.set_record_state(dirty=False, has_record=False); self.tree.selection_remove(self.tree.selection()); self.status.set("Creating a recipe")
        return True

    def save_record(self):
        try:
            values = self.values(); record = self.controller.create_record(values) if self.current_record_id is None else self.controller.update_record(self.current_record_id, values)
        except (
            TypeError, ValueError, KeyError, OSError, RuntimeError, SharedDataError
        ) as error:
            messagebox.showerror(
                "Cannot save recipe",
                f"{error}\n\nYour entries are still in the form. Please try Save again.",
                parent=self,
            )
            return False
        self.current_record_id = record["record_id"]; self.refresh_records(self.current_record_id); self.load_record(self.current_record_id); return True

    def delete_record(self):
        if self.current_record_id is None: return self.new_record()
        record = self.controller.get_record(self.current_record_id) or {}
        if not messagebox.askyesno("Delete recipe", f"Permanently delete {record.get('name', 'this recipe')}?", parent=self): return
        self.controller.delete_record(self.current_record_id); self.current_record_id = None; self.refresh_records(); self.load_record(self.records[0]["record_id"]) if self.records else self.new_record()

    def duplicate_record(self):
        if self.current_record_id is None:
            return False
        if not self.confirm_unsaved_changes():
            return False
        try:
            record = self.controller.duplicate_record(self.current_record_id)
        except (TypeError, ValueError, KeyError, OSError, RuntimeError, SharedDataError) as error:
            messagebox.showerror("Cannot duplicate recipe", str(error), parent=self)
            return False
        self.refresh_records(record["record_id"])
        self.load_record(record["record_id"])
        return True

    def blank_formulation(self, name):
        return {
            "record_id": str(uuid4()), "name": name, "output_item": None,
            "output_quantity": 1, "ingredient_requirements": [],
            "vessel_requirements": [], "proficiency_requirements": [],
            "spell_requirements": [],
        }

    def refresh_formulation_choices(self):
        names = [str(item.get("name") or f"Formulation {index + 1}") for index, item in enumerate(self.formulations)]
        self.formulation_combo.configure(values=names)
        if names:
            self.formulation_choice.set(names[min(self.current_formulation_index, len(names) - 1)])

    def handle_formulation_name_change(self, *_args):
        if self.loading or not self.formulations:
            return
        index = min(self.current_formulation_index, len(self.formulations) - 1)
        name = self.formulation_name.get().strip() or f"Formulation {index + 1}"
        self.formulations[index]["name"] = name
        self.refresh_formulation_choices()
        self.mark_dirty()

    def commit_current_formulation(self):
        if self.loading or not self.formulations:
            return
        index = min(self.current_formulation_index, len(self.formulations) - 1)
        try:
            quantity = int(self.output_quantity.get() or 1)
        except ValueError:
            quantity = self.output_quantity.get()
        self.formulations[index].update({
            "name": self.formulation_name.get().strip() or f"Formulation {index + 1}",
            "output_item": deepcopy(self.output_item),
            "output_quantity": quantity,
            "ingredient_requirements": self.ingredients.get_groups(),
            "vessel_requirements": self.vessels.get_groups(),
            "proficiency_requirements": self.proficiencies.get_groups(),
            "spell_requirements": self.spells.get_groups(),
        })

    def load_formulation(self, index):
        if not self.formulations:
            return
        self.loading = True
        self.current_formulation_index = max(0, min(index, len(self.formulations) - 1))
        item = self.formulations[self.current_formulation_index]
        self.formulation_name.set(item.get("name", ""))
        self.output_item = deepcopy(item.get("output_item"))
        self.output_quantity.set(str(item.get("output_quantity", 1) or 1))
        self.ingredients.set_groups(item.get("ingredient_requirements", []))
        self.vessels.set_groups(item.get("vessel_requirements", []))
        self.proficiencies.set_groups(item.get("proficiency_requirements", []))
        self.spells.set_groups(item.get("spell_requirements", []))
        self.refresh_output_button(); self.refresh_formulation_choices()
        self.loading = False

    def select_formulation(self, _event=None):
        selected = self.formulation_combo.current()
        if selected < 0 or selected == self.current_formulation_index:
            return
        self.commit_current_formulation(); self.load_formulation(selected)

    def add_formulation(self):
        self.commit_current_formulation()
        self.formulations.append(self.blank_formulation(f"Formulation {len(self.formulations) + 1}"))
        self.load_formulation(len(self.formulations) - 1); self.mark_dirty()

    def duplicate_formulation(self):
        if not self.formulations:
            return
        self.commit_current_formulation()
        copy = deepcopy(self.formulations[self.current_formulation_index])
        copy["record_id"] = str(uuid4())
        copy["name"] = f"{copy.get('name', 'Formulation')} (Copy)"
        self.formulations.insert(self.current_formulation_index + 1, copy)
        self.load_formulation(self.current_formulation_index + 1); self.mark_dirty()

    def delete_formulation(self):
        if len(self.formulations) <= 1:
            messagebox.showinfo("Formulation required", "A recipe must keep at least one formulation.", parent=self)
            return
        del self.formulations[self.current_formulation_index]
        self.load_formulation(min(self.current_formulation_index, len(self.formulations) - 1)); self.mark_dirty()

    def choose_output(self):
        dialog = CatalogReferenceDialog(self, self.database, "Choose formulation output")
        self.wait_window(dialog)
        if dialog.result:
            self.output_item = dialog.result
            self.refresh_output_button(); self.mark_dirty()

    def refresh_output_button(self):
        self.output_button.configure(text=(self.output_item or {}).get("name", "Choose output item…"))

    def revert_record(self):
        return self.load_record(self.current_record_id) if self.current_record_id else self.new_record()

    def mark_dirty(self, *_args):
        if self.loading: return
        self.form_dirty = True; self.toolbar.set_record_state(dirty=True, has_record=self.current_record_id is not None); self.status.set("Unsaved changes")

    def confirm_unsaved_changes(self):
        if not self.form_dirty: return True
        choice = messagebox.askyesnocancel("Unsaved recipe", "Save changes before continuing?", parent=self)
        if choice is None: return False
        if choice: return self.save_record()
        self.form_dirty = False; return True

    def can_leave(self):
        return self.confirm_unsaved_changes()
