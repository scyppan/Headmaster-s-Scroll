from __future__ import annotations

from copy import deepcopy
from difflib import SequenceMatcher
import tkinter as tk
from tkinter import messagebox, ttk
from uuid import uuid4

from runtime_theme import bind_theme
from shared.widgets import RoundedEntry, RoundedSelect, SoftButton, StripedListbox
from theme import (
    APP_BACKGROUND,
    BORDER_SOFT,
    FIELD_BACKGROUND,
    SIDEBAR_TILE_SELECTED,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    app_font,
)


ITEM_COLLECTIONS = (
    ("Raw Material", "raw_materials"),
    ("General Item", "general_items"),
    ("Holdable Item", "holdable_items"),
    ("Accessory", "accessories"),
    ("Potion", "potions"),
    ("Preparation", "preparations"),
    ("Food/Drink", "foods_and_drinks"),
    ("Book", "books"),
)


def configure_recipe_tree(widget, style_name):
    """Give recipe catalog trees the same parchment treatment as DBM lists."""
    style = ttk.Style(widget)
    style.configure(
        style_name,
        background=FIELD_BACKGROUND,
        fieldbackground=FIELD_BACKGROUND,
        foreground=TEXT_DARK,
        bordercolor=BORDER_SOFT,
        lightcolor=BORDER_SOFT,
        darkcolor=BORDER_SOFT,
        rowheight=25,
        font=app_font(9),
    )
    style.map(
        style_name,
        background=[("selected", SIDEBAR_TILE_SELECTED)],
        foreground=[("selected", TEXT_DARK)],
    )
    heading_style = f"{style_name}.Heading"
    style.configure(
        heading_style,
        background=SURFACE_MUTED,
        foreground=TEXT_DARK,
        bordercolor=BORDER_SOFT,
        lightcolor=BORDER_SOFT,
        darkcolor=BORDER_SOFT,
        font=app_font(9),
    )
    style.map(heading_style, background=[("active", SIDEBAR_TILE_SELECTED)])


def requirement_catalog(database, kind):
    if kind == "proficiency":
        sources = (("Proficiency", "proficiencies"),)
    elif kind == "spell":
        sources = (("Spell", "spells"),)
    else:
        sources = ITEM_COLLECTIONS
    tag_names_by_id = {
        str(tag.get("record_id", "")): str(tag.get("name", ""))
        for tag in (
            database.get_collection("tag_catalog")
            if database.has_container("tag_catalog") else []
        )
        if isinstance(tag, dict)
    }
    rows = []
    for label, collection in sources:
        if not database.has_container(collection):
            continue
        for record in database.get_collection(collection):
            record_id = str(record.get("record_id", "") or "").strip()
            name = str(record.get("name") or record.get("title") or "").strip()
            if record_id and name:
                display_catalog = (
                    "Raw Material"
                    if collection == "general_items"
                    and str(record.get("type", "")) == "Raw Material"
                    else label
                )
                rows.append({
                    "collection": collection,
                    "record_id": record_id,
                    "name": name,
                    "catalog": display_catalog,
                    "tags": sorted({
                        *[str(value).strip() for value in record.get("tags", []) or [] if str(value).strip()],
                        *[
                            tag_names_by_id.get(str(value), "").strip()
                            for value in record.get("tag_ids", []) or []
                            if tag_names_by_id.get(str(value), "").strip()
                        ],
                    }, key=str.casefold),
                })
    for parent_collection, label, child_collection in (
        ("plants", "Plant Part", "plant_parts"),
        ("creatures", "Creature Part", "creature_parts"),
    ):
        if kind in {"proficiency", "spell"} or not database.has_container(parent_collection):
            continue
        for parent in database.get_collection(parent_collection):
            for part in parent.get("parts", []) or []:
                record_id = str(part.get("record_id", "") or "").strip()
                name = str(part.get("name", "") or "").strip()
                if record_id and name:
                    rows.append({
                        "collection": child_collection,
                        "record_id": record_id,
                        "parent_record_id": str(parent.get("record_id", "")),
                        "name": name,
                        "catalog": label,
                        "tags": [str(value).strip() for value in part.get("tags", []) or [] if str(value).strip()],
                    })
    return sorted(rows, key=lambda row: (row["name"].casefold(), row["catalog"]))


def clean_catalog_reference(row):
    result = deepcopy(row)
    result.pop("catalog", None)
    result.pop("tags", None)
    return result


class CatalogReferenceDialog(tk.Toplevel):
    """Search the complete item catalog and return one stable typed reference."""

    def __init__(self, parent, database, title="Choose output item"):
        super().__init__(parent)
        self.result = None
        self.catalog = requirement_catalog(database, "item")
        self.visible_rows = []
        self.title(title)
        self.geometry("650x470")
        self.minsize(520, 360)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.configure(bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.query = tk.StringVar()
        self.query.trace_add("write", self.refresh)
        RoundedEntry(
            self, textvariable=self.query, background=APP_BACKGROUND,
            height=40, font=app_font(10),
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=14)
        style_name = f"RecipeCatalogReference{id(self)}.Treeview"
        configure_recipe_tree(self, style_name)
        self.results = ttk.Treeview(
            self, columns=("catalog",), show="tree headings",
            selectmode="browse", style=style_name,
        )
        self.results.heading("#0", text="Name")
        self.results.heading("catalog", text="Catalog")
        self.results.column("#0", width=390)
        self.results.column("catalog", width=150)
        self.results.grid(row=1, column=0, sticky="nsew", padx=14)
        self.results.bind("<Double-1>", lambda _event: self.choose())
        actions = tk.Frame(self, bg=APP_BACKGROUND)
        actions.grid(row=2, column=0, sticky="ew", padx=14, pady=14)
        SoftButton(actions, text="Cancel", command=self.destroy, width=100, height=36).pack(side="right")
        SoftButton(actions, text="Choose", command=self.choose, width=100, height=36).pack(side="right", padx=8)
        self.refresh()

    def refresh(self, *_args):
        self.visible_rows = fuzzy_rows(self.catalog, self.query.get())
        self.results.delete(*self.results.get_children())
        for index, row in enumerate(self.visible_rows):
            self.results.insert(
                "", "end", iid=str(index), text=row["name"],
                values=(row["catalog"],),
            )

    def choose(self):
        selected = self.results.selection()
        if not selected:
            return
        self.result = clean_catalog_reference(self.visible_rows[int(selected[0])])
        self.destroy()


class OutputEffectDialog(tk.Toplevel):
    def __init__(self, parent, database, alternative):
        super().__init__(parent)
        self.database = database
        self.result = None
        self.output_item = deepcopy(alternative.get("output_item"))
        self.quantity_modifier = tk.StringVar(
            value=str(alternative.get("output_quantity_modifier", 0) or 0)
        )
        self.title("Replacement output effect")
        self.geometry("560x210")
        self.resizable(True, False)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.configure(bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")
        self.grid_columnconfigure(1, weight=1)
        tk.Label(self, text="Output item", bg=APP_BACKGROUND, fg=TEXT_DARK).grid(row=0, column=0, sticky="w", padx=14, pady=(18, 8))
        self.output_label = tk.Button(
            self, command=self.choose_output, anchor="w", relief="solid",
            bd=1, bg=FIELD_BACKGROUND, fg=TEXT_DARK, font=app_font(9),
        )
        self.output_label.grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=(18, 8))
        tk.Label(self, text="Quantity shift", bg=APP_BACKGROUND, fg=TEXT_DARK).grid(row=1, column=0, sticky="w", padx=14, pady=8)
        ttk.Spinbox(self, textvariable=self.quantity_modifier, from_=-100000, to=100000, width=10).grid(row=1, column=1, sticky="w", pady=8)
        tk.Label(
            self, text="Leave the item blank to keep the formulation's base output. Use −1 to make one fewer.",
            bg=APP_BACKGROUND, fg=TEXT_DARK, anchor="w",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=14)
        actions = tk.Frame(self, bg=APP_BACKGROUND)
        actions.grid(row=3, column=0, columnspan=2, sticky="e", padx=14, pady=14)
        ttk.Button(actions, text="Clear item", command=self.clear_output).pack(side="left", padx=4)
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side="left", padx=4)
        ttk.Button(actions, text="Save effect", command=self.save).pack(side="left", padx=4)
        self.refresh_output_label()

    def choose_output(self):
        dialog = CatalogReferenceDialog(self, self.database, "Choose replacement output")
        self.wait_window(dialog)
        if dialog.result:
            self.output_item = dialog.result
            self.refresh_output_label()

    def clear_output(self):
        self.output_item = None
        self.refresh_output_label()

    def refresh_output_label(self):
        self.output_label.configure(text=(self.output_item or {}).get("name", "Keep base output"))

    def save(self):
        try:
            modifier = int(self.quantity_modifier.get() or 0)
        except ValueError:
            messagebox.showerror("Invalid quantity", "Quantity shift must be a whole number.", parent=self)
            return
        self.result = {
            "output_item": deepcopy(self.output_item),
            "output_quantity_modifier": modifier,
        }
        self.destroy()


class TagAlternativesDialog(tk.Toplevel):
    def __init__(self, parent, catalog):
        super().__init__(parent)
        self.result = None
        self.catalog = catalog
        self.tags = sorted({tag for row in catalog for tag in row.get("tags", [])}, key=str.casefold)
        self.visible_tags = []
        self.title("Add all items with tag")
        self.geometry("480x430")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.configure(bg=APP_BACKGROUND)
        self.grid_rowconfigure(1, weight=1); self.grid_columnconfigure(0, weight=1)
        self.query = tk.StringVar(); self.query.trace_add("write", self.refresh)
        RoundedEntry(self, textvariable=self.query, background=APP_BACKGROUND, height=40, font=app_font(10)).grid(row=0, column=0, sticky="ew", padx=14, pady=14)
        self.listbox = StripedListbox(self, exportselection=False, bg=FIELD_BACKGROUND, fg=TEXT_DARK, selectbackground=SIDEBAR_TILE_SELECTED, selectforeground=TEXT_DARK)
        self.listbox.grid(row=1, column=0, sticky="nsew", padx=14)
        self.listbox.bind("<Double-1>", lambda _event: self.choose())
        actions = tk.Frame(self, bg=APP_BACKGROUND); actions.grid(row=2, column=0, sticky="e", padx=14, pady=14)
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side="left", padx=4)
        ttk.Button(actions, text="Add matching items", command=self.choose).pack(side="left", padx=4)
        self.refresh()

    def refresh(self, *_args):
        query = self.query.get().strip().casefold()
        self.visible_tags = [tag for tag in self.tags if not query or query in tag.casefold()]
        self.listbox.delete(0, "end")
        for tag in self.visible_tags:
            count = sum(tag in row.get("tags", []) for row in self.catalog)
            self.listbox.insert("end", f"{tag}  ({count})")

    def choose(self):
        selected = self.listbox.curselection()
        if not selected:
            return
        tag = self.visible_tags[selected[0]]
        self.result = [clean_catalog_reference(row) for row in self.catalog if tag in row.get("tags", [])]
        self.destroy()


class QuickProficiencyDialog(tk.Toplevel):
    """Create a minimum valid proficiency without leaving the recipe chooser."""

    def __init__(self, parent, database):
        super().__init__(parent)
        from sections.magic.proficiencies.constants import PROFICIENCY_SKILLS

        self.database = database
        self.result = None
        self.title("New proficiency")
        self.geometry("560x260")
        self.resizable(True, False)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.configure(bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")
        self.grid_columnconfigure(1, weight=1)
        self.name = tk.StringVar()
        self.skill = tk.StringVar()
        self.threshold = tk.StringVar(value="1")
        for row, label in enumerate(("Name", "Skill", "Threshold")):
            tk.Label(self, text=label, bg=APP_BACKGROUND, fg=TEXT_DARK, anchor="w").grid(row=row, column=0, sticky="w", padx=14, pady=8)
        RoundedEntry(self, textvariable=self.name, background=APP_BACKGROUND, height=38, font=app_font(10)).grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=(14, 6))
        RoundedSelect(self, variable=self.skill, values=PROFICIENCY_SKILLS, background=APP_BACKGROUND, height=38, font=app_font(9), placeholder="Select skill").grid(row=1, column=1, sticky="ew", padx=(0, 14), pady=6)
        ttk.Spinbox(self, textvariable=self.threshold, from_=1, to=100, width=10).grid(row=2, column=1, sticky="w", pady=6)
        tk.Label(
            self,
            text="You can add its description, tags, materials, and other details later in Proficiencies.",
            bg=APP_BACKGROUND, fg=TEXT_DARK, anchor="w",
        ).grid(row=3, column=0, columnspan=2, sticky="ew", padx=14, pady=6)
        actions = tk.Frame(self, bg=APP_BACKGROUND)
        actions.grid(row=4, column=0, columnspan=2, sticky="e", padx=14, pady=14)
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side="left", padx=4)
        ttk.Button(actions, text="Create proficiency", command=self.create).pack(side="left", padx=4)

    def create(self):
        from sections.magic.proficiencies.controller import ProficiencyController

        try:
            self.result = ProficiencyController(self.database).create_record({
                "name": self.name.get(),
                "skill": self.skill.get(),
                "threshold": int(self.threshold.get()),
                "target_scope": "none",
                "tags": [],
            })
        except (TypeError, ValueError, KeyError, OSError, RuntimeError) as error:
            messagebox.showerror("Cannot create proficiency", str(error), parent=self)
            self.result = None
            return
        self.destroy()


def fuzzy_rows(rows, query):
    query = " ".join(str(query).casefold().split())
    if not query:
        return rows
    ranked = []
    for row in rows:
        name = row["name"].casefold()
        text = f"{name} {row['catalog'].casefold()}"
        if query == name:
            score = 0
        elif name.startswith(query):
            score = 1
        elif query in text:
            score = 2
        else:
            similarity = SequenceMatcher(None, query, name).ratio()
            if similarity < 0.42:
                continue
            score = 4 - similarity
        ranked.append((score, name, row))
    ranked.sort(key=lambda item: item[:2])
    return [item[2] for item in ranked]


class RequirementLineDialog(tk.Toplevel):
    def __init__(self, parent, database, kind, group=None):
        super().__init__(parent)
        self.database = database
        self.kind = kind
        self.catalog = requirement_catalog(database, kind)
        self.result = None
        self.alternatives = deepcopy((group or {}).get("alternatives", []))
        self.title(f"{kind.title()} requirement")
        self.geometry("760x520")
        self.minsize(620, 420)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.configure(bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.query = tk.StringVar()
        self.query.trace_add("write", self.refresh_results)
        RoundedEntry(self, textvariable=self.query, background=APP_BACKGROUND, height=40, font=app_font(10)).grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        subject = {
            "ingredient": "ingredient",
            "vessel": "vessel",
            "proficiency": "proficiency",
            "spell": "spell",
        }.get(kind, "requirement")
        tk.Label(
            self,
            text=(
                f"Choose the required {subject}. Add a replacement only when "
                f"either choice is acceptable."
            ),
            bg=APP_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(9),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=14)
        body = tk.PanedWindow(self, orient="horizontal", bg=APP_BACKGROUND, sashwidth=5, borderwidth=0)
        body.grid(row=2, column=0, sticky="nsew", padx=14, pady=8)
        left = tk.Frame(body, bg=SURFACE)
        left.grid_rowconfigure(0, weight=1); left.grid_columnconfigure(0, weight=1)
        result_style = f"RecipeRequirementResults{id(self)}.Treeview"
        configure_recipe_tree(self, result_style)
        self.results = ttk.Treeview(
            left,
            columns=("catalog",),
            show="tree headings",
            selectmode="browse",
            style=result_style,
        )
        self.results.heading("#0", text="Name"); self.results.heading("catalog", text="Catalog")
        self.results.column("#0", width=280); self.results.column("catalog", width=120)
        self.results.grid(row=0, column=0, sticky="nsew")
        add_row = tk.Frame(left, bg=SURFACE); add_row.grid(row=1, column=0, sticky="ew", pady=8)
        self.quantity = tk.StringVar(value="1")
        if kind == "ingredient":
            tk.Label(add_row, text="Qty", bg=SURFACE, fg=TEXT_DARK).pack(side="left", padx=(6, 2))
            ttk.Spinbox(add_row, textvariable=self.quantity, from_=1, to=100000, width=7).pack(side="left")
        self.add_button = SoftButton(
            add_row,
            text="Set required",
            command=self.add_alternative,
            background=SURFACE,
            width=125,
            height=32,
        )
        self.add_button.pack(side="right", padx=6)
        if kind == "proficiency":
            SoftButton(
                add_row,
                text="+ New proficiency",
                command=self.create_proficiency,
                background=SURFACE,
                width=145,
                height=32,
            ).pack(side="left", padx=6)
        right = tk.Frame(body, bg=SURFACE)
        right.grid_rowconfigure(1, weight=1); right.grid_columnconfigure(0, weight=1)
        tk.Label(
            right,
            text="Required choice and optional replacements",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        self.selected = StripedListbox(
            right,
            exportselection=False,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=SIDEBAR_TILE_SELECTED,
            selectforeground=TEXT_DARK,
            highlightbackground=BORDER_SOFT,
            highlightcolor=BORDER_SOFT,
            relief="flat",
            borderwidth=0,
            font=app_font(9),
        )
        self.selected.grid(row=1, column=0, sticky="nsew", padx=8)
        selected_actions = tk.Frame(right, bg=SURFACE)
        selected_actions.grid(row=2, column=0, sticky="ew", padx=8, pady=8)
        if kind not in {"proficiency", "spell"}:
            ttk.Button(
                selected_actions,
                text="Output effect…",
                command=self.edit_output_effect,
            ).pack(side="left")
        ttk.Button(selected_actions, text="Remove", command=self.remove_alternative).pack(side="right")
        body.add(left, minsize=300); body.add(right, minsize=260)
        actions = tk.Frame(self, bg=APP_BACKGROUND)
        actions.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 14))
        SoftButton(actions, text="Cancel", command=self.destroy, width=100, height=36).pack(side="right")
        SoftButton(actions, text="Save line", command=self.save, width=110, height=36).pack(side="right", padx=8)
        self.refresh_results(); self.refresh_selected()

    def refresh_results(self, *_args):
        self.results.delete(*self.results.get_children())
        for index, row in enumerate(fuzzy_rows(self.catalog, self.query.get())):
            self.results.insert("", "end", iid=str(index), text=row["name"], values=(row["catalog"],), tags=(row["record_id"], row["collection"], str(row.get("parent_record_id", ""))))
            self.results.set(str(index), "catalog", row["catalog"])
        self.visible_rows = fuzzy_rows(self.catalog, self.query.get())

    def add_alternative(self):
        selected = self.results.selection()
        if not selected:
            return
        row = deepcopy(self.visible_rows[int(selected[0])])
        if self.kind == "ingredient":
            try:
                row["quantity"] = max(1, int(self.quantity.get()))
            except ValueError:
                messagebox.showerror("Invalid quantity", "Quantity must be a whole number.", parent=self)
                return
        row = clean_catalog_reference(row)
        identity = (row["collection"], row["record_id"], row.get("parent_record_id", ""))
        if identity not in {(item.get("collection"), item.get("record_id"), item.get("parent_record_id", "")) for item in self.alternatives}:
            self.alternatives.append(row)
        self.refresh_selected()

    def refresh_selected(self):
        self.selected.delete(0, "end")
        for index, item in enumerate(self.alternatives):
            quantity = f"{item.get('quantity', 1)} × " if self.kind == "ingredient" else ""
            role = "Required" if index == 0 else "Replacement"
            effect = []
            if (item.get("output_item") or {}).get("name"):
                effect.append(f"output: {item['output_item']['name']}")
            modifier = int(item.get("output_quantity_modifier", 0) or 0)
            if modifier:
                effect.append(f"qty {modifier:+d}")
            suffix = f"  → {', '.join(effect)}" if effect else ""
            self.selected.insert("end", f"{role} · {quantity}{item.get('name', 'Unnamed')}{suffix}")
        self.add_button.set_text(
            "Add replacement" if self.alternatives else "Set required"
        )

    def remove_alternative(self):
        selected = self.selected.curselection()
        if selected:
            del self.alternatives[selected[0]]
            self.refresh_selected()

    def edit_output_effect(self):
        selected = self.selected.curselection()
        if not selected:
            return
        index = selected[0]
        dialog = OutputEffectDialog(self, self.database, self.alternatives[index])
        self.wait_window(dialog)
        if dialog.result is None:
            return
        if dialog.result["output_item"]:
            self.alternatives[index]["output_item"] = dialog.result["output_item"]
        else:
            self.alternatives[index].pop("output_item", None)
        modifier = dialog.result["output_quantity_modifier"]
        if modifier:
            self.alternatives[index]["output_quantity_modifier"] = modifier
        else:
            self.alternatives[index].pop("output_quantity_modifier", None)
        self.refresh_selected()
        self.selected.selection_set(index)

    def create_proficiency(self):
        dialog = QuickProficiencyDialog(self, self.database)
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.catalog = requirement_catalog(self.database, self.kind)
        self.query.set(dialog.result.get("name", ""))
        self.refresh_results()
        for index, row in enumerate(self.visible_rows):
            if row.get("record_id") == dialog.result.get("record_id"):
                self.results.selection_set(str(index))
                self.results.see(str(index))
                break

    def save(self):
        if not self.alternatives:
            subject = {
                "ingredient": "ingredient",
                "vessel": "vessel",
                "proficiency": "proficiency",
                "spell": "spell",
            }.get(self.kind, "requirement")
            messagebox.showerror(
                "Requirement needed",
                f"Choose the required {subject}.",
                parent=self,
            )
            return
        self.result = {"record_id": str(uuid4()), "alternatives": deepcopy(self.alternatives)}
        self.destroy()


class RequirementGroupEditor(tk.Frame):
    def __init__(self, parent, title, database, kind, change_command):
        super().__init__(parent, bg=SURFACE, highlightthickness=1)
        self.database = database
        self.kind = kind
        self.change_command = change_command
        self.groups = []
        self.grid_rowconfigure(1, weight=1); self.grid_columnconfigure(0, weight=1)
        header = tk.Frame(self, bg=SURFACE); header.grid(row=0, column=0, sticky="ew", padx=6, pady=5)
        tk.Label(header, text=title, bg=SURFACE, fg=TEXT_DARK, font=app_font(10)).pack(side="left")
        ttk.Button(header, text="+", width=3, command=self.add_group).pack(side="right")
        ttk.Button(header, text="✎", width=3, command=self.edit_group).pack(side="right", padx=3)
        ttk.Button(header, text="−", width=3, command=self.delete_group).pack(side="right")
        if kind not in {"proficiency", "spell"}:
            ttk.Button(
                header,
                text="# +",
                width=4,
                command=self.add_group_by_tag,
            ).pack(side="right", padx=3)
        self.tree = ttk.Treeview(self, show="tree", selectmode="browse")
        tree_style = f"RecipeRequirementGroups{id(self)}.Treeview"
        configure_recipe_tree(self, tree_style)
        self.tree.configure(style=tree_style)
        self.tree.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self.tree.bind("<Double-1>", lambda _event: self.edit_group())

    def set_groups(self, groups):
        self.groups = deepcopy(groups if isinstance(groups, list) else [])
        self.refresh()

    def get_groups(self):
        return deepcopy(self.groups)

    def display_group(self, group):
        labels = []
        for item in group.get("alternatives", []) or []:
            prefix = f"{item.get('quantity', 1)} × " if self.kind == "ingredient" else ""
            labels.append(f"{prefix}{item.get('name', 'Unnamed')}")
        if not labels:
            return "Empty requirement"
        required, *replacements = labels
        if not replacements:
            return required
        return f"{required}  (or {' / '.join(replacements)})"

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for index, group in enumerate(self.groups):
            self.tree.insert("", "end", iid=str(index), text=self.display_group(group))

    def add_group(self):
        dialog = RequirementLineDialog(self, self.database, self.kind)
        self.wait_window(dialog)
        if dialog.result:
            self.groups.append(dialog.result); self.refresh(); self.change_command()

    def edit_group(self):
        selected = self.tree.selection()
        if not selected:
            return
        index = int(selected[0])
        dialog = RequirementLineDialog(self, self.database, self.kind, self.groups[index])
        self.wait_window(dialog)
        if dialog.result:
            dialog.result["record_id"] = self.groups[index].get("record_id", dialog.result["record_id"])
            self.groups[index] = dialog.result; self.refresh(); self.tree.selection_set(str(index)); self.change_command()

    def delete_group(self):
        selected = self.tree.selection()
        if not selected:
            return
        del self.groups[int(selected[0])]
        self.refresh(); self.change_command()

    def add_group_by_tag(self):
        catalog = requirement_catalog(self.database, self.kind)
        dialog = TagAlternativesDialog(self, catalog)
        self.wait_window(dialog)
        if not dialog.result:
            return
        alternatives = []
        seen = set()
        for raw in dialog.result:
            row = deepcopy(raw)
            if self.kind == "ingredient":
                row["quantity"] = 1
            identity = (
                row.get("collection"), row.get("record_id"),
                row.get("parent_record_id", ""),
            )
            if identity in seen:
                continue
            seen.add(identity)
            alternatives.append(row)
        if alternatives:
            self.groups.append({"record_id": str(uuid4()), "alternatives": alternatives})
            self.refresh()
            self.tree.selection_set(str(len(self.groups) - 1))
            self.change_command()
