from __future__ import annotations

import tkinter as tk

from headmasters_scroll.effects import TARGET_SCOPE_LABELS, TARGET_SCOPES
from runtime_theme import bind_theme
from shared.item_actions import (
    ITEM_EFFECT_COLLECTIONS,
    ITEM_EFFECT_TYPES,
    normalize_item_action,
)
from shared.widgets.controls import RoundedEntry, RoundedSelect, SoftButton
from shared.widgets.fields import MultilineField
from shared.widgets.striped_listbox import StripedListbox
from theme import BORDER, PRIMARY, SURFACE, TEXT_DARK, TEXT_MUTED, app_font


class EffectPicker(tk.Toplevel):
    def __init__(self, parent, database, effect_type, selected_command):
        super().__init__(parent)
        self.database = database
        self.effect_type = effect_type
        self.selected_command = selected_command
        self.records = []
        self.visible_records = []
        self.title(f"Choose {effect_type}")
        self.geometry("720x520")
        self.minsize(520, 360)
        self.configure(bg=SURFACE)
        bind_theme(self, background="SURFACE")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.query_value = tk.StringVar()
        self.query_value.trace_add("write", self.refresh)
        self.spell_filters = None
        search_row = tk.Frame(self, bg=SURFACE)
        search_row.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        search_row.grid_columnconfigure(0, weight=1)
        search = RoundedEntry(
            search_row, textvariable=self.query_value, background=SURFACE,
            height=36, font=app_font(10),
        )
        search.grid(row=0, column=0, sticky="ew")
        if effect_type == "Spell":
            from sections.magic.spells.filter_dialog import EMPTY_SPELL_FILTERS
            self.spell_filters = dict(EMPTY_SPELL_FILTERS)
            SoftButton(
                search_row, text="Advanced filters…",
                command=self.open_spell_filters, background=SURFACE,
                width=150, height=36,
            ).grid(row=0, column=1, padx=(8, 0))
        self.listbox = StripedListbox(self, font=app_font(10))
        self.listbox.grid(row=1, column=0, sticky="nsew", padx=10)
        self.listbox.bind("<Double-Button-1>", self.choose)
        self.listbox.bind("<Return>", self.choose)
        choose = SoftButton(
            self, text="Choose", command=self.choose, background=SURFACE,
            fill=PRIMARY, fill_role="PRIMARY", hover_fill_role="PRIMARY_DARK",
            height=36,
        )
        choose.grid(row=2, column=0, sticky="e", padx=10, pady=10)

        for collection in ITEM_EFFECT_COLLECTIONS[effect_type]:
            label = "Preparation" if collection == "preparations" else effect_type
            for record in database.get_collection(collection):
                if record.get("record_id") and record.get("name"):
                    self.records.append((collection, label, record))
        self.records.sort(key=lambda value: str(value[2].get("name", "")).casefold())
        self.refresh()
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        search.focus_set()

    def refresh(self, *arguments):
        query = self.query_value.get().strip().casefold()
        terms = query.split()
        self.visible_records = [
            value for value in self.records
            if all(term in " ".join((
                str(value[2].get("name", "")),
                str(value[2].get("description", "")),
                str(value[2].get("skill", "")),
                str(value[2].get("tags", "")),
            )).casefold() for term in terms)
            and self.matches_advanced_filters(value[2])
        ]
        self.listbox.delete(0, "end")
        for _collection, label, record in self.visible_records:
            suffix = f" — {label}" if self.effect_type == "Potion" else ""
            self.listbox.insert("end", f"{record.get('name', '')}{suffix}")

    def matches_advanced_filters(self, record):
        if self.effect_type != "Spell" or not self.spell_filters:
            return True
        from sections.magic.spells.record_list import SpellList
        return SpellList.record_matches_filters(record, self.spell_filters)

    def open_spell_filters(self):
        from sections.magic.spells.filter_dialog import SpellFilterDialog
        records = [record for _collection, _label, record in self.records]
        dialog = SpellFilterDialog(self, records, self.spell_filters)
        self.wait_window(dialog)
        if dialog.result is not None:
            self.spell_filters = dialog.result
            self.refresh()

    def choose(self, event=None):
        selected = self.listbox.curselection()
        if not selected:
            return
        collection, _label, record = self.visible_records[int(selected[0])]
        self.selected_command(collection, record)
        self.destroy()


class CustomEffectDialog(tk.Toplevel):
    def __init__(self, parent, action, selected_command):
        super().__init__(parent)
        self.selected_command = selected_command
        self.title("Custom Item Effect")
        self.geometry("560x330")
        self.configure(bg=SURFACE)
        bind_theme(self, background="SURFACE")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        tk.Label(
            self, text="Name", bg=SURFACE, fg=TEXT_DARK,
            font=app_font(9), anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 2))
        self.name_value = tk.StringVar(value=str(action.get("name", "")))
        RoundedEntry(
            self, textvariable=self.name_value, background=SURFACE,
            height=34, font=app_font(10),
        ).grid(row=1, column=0, sticky="ew", padx=10)
        self.effect_field = MultilineField(self, "Effect", lambda: None, height=8)
        self.effect_field.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        self.effect_field.set_value(action.get("description", ""))
        SoftButton(
            self, text="Apply", command=self.apply, background=SURFACE,
            fill=PRIMARY, fill_role="PRIMARY", hover_fill_role="PRIMARY_DARK",
            height=36,
        ).grid(row=3, column=0, sticky="e", padx=10, pady=(0, 10))
        self.transient(parent.winfo_toplevel())
        self.grab_set()

    def apply(self):
        name = " ".join(self.name_value.get().split())
        effect = self.effect_field.get_value().strip()
        if name and effect:
            self.selected_command(name, effect)
            self.destroy()


class ItemEffectRow(tk.Frame):
    def __init__(self, parent, database, change_command, remove_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")
        self.database = database
        self.change_command = change_command
        self.remove_command = remove_command
        self.loading = False
        self.action = normalize_item_action({"effect_type": "Custom"})
        self.grid_columnconfigure(1, weight=1)

        self.type_value = tk.StringVar(value="Custom")
        self.type_value.trace_add("write", self.change_type)
        self.type_select = RoundedSelect(
            self, variable=self.type_value, values=ITEM_EFFECT_TYPES,
            background=SURFACE, width=110, height=30, font=app_font(8),
        )
        self.type_select.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self.choose_button = SoftButton(
            self, text="Define effect…", command=self.choose_target,
            background=SURFACE, height=30,
        )
        self.choose_button.grid(row=0, column=1, sticky="ew", padx=3)
        self.mode_value = tk.StringVar(value="Clickable")
        self.mode_value.trace_add("write", self.changed)
        self.mode_select = RoundedSelect(
            self, variable=self.mode_value, values=("Passive", "Clickable"),
            background=SURFACE, width=82, height=30, font=app_font(8),
        )
        self.mode_select.grid(row=0, column=2, padx=3)
        self.scope_value = tk.StringVar(value="Self")
        self.scope_value.trace_add("write", self.changed)
        self.scope_select = RoundedSelect(
            self, variable=self.scope_value,
            values=tuple(TARGET_SCOPE_LABELS[value] for value in TARGET_SCOPES),
            background=SURFACE, width=76, height=30, font=app_font(8),
        )
        self.scope_select.grid(row=0, column=3, padx=3)
        self.depletable_value = tk.BooleanVar(value=False)
        self.depletable_button = tk.Checkbutton(
            self, text="Deplete", variable=self.depletable_value,
            command=self.changed, bg=SURFACE, fg=TEXT_DARK,
            activebackground=SURFACE, selectcolor=SURFACE, font=app_font(7),
        )
        self.depletable_button.grid(row=0, column=4, padx=3)
        bind_theme(
            self.depletable_button, background="SURFACE",
            foreground="TEXT_DARK", activebackground="SURFACE",
            selectcolor="SURFACE",
        )
        SoftButton(
            self, text="×", command=lambda: remove_command(self),
            background=SURFACE, width=28, height=30, padx=0,
        ).grid(row=0, column=5, padx=(3, 0))

    def set_action(self, action):
        self.loading = True
        self.action = normalize_item_action(action)
        self.type_value.set(self.action.get("effect_type", "Custom"))
        self.mode_value.set(
            "Clickable" if self.action.get("activation_mode") == "click" else "Passive"
        )
        self.scope_value.set(
            TARGET_SCOPE_LABELS.get(self.action.get("target_scope", "self"), "Self")
        )
        self.depletable_value.set(bool(self.action.get("depletable", False)))
        self.refresh_label()
        self.refresh_controls()
        self.loading = False

    def refresh_label(self):
        text = self.action.get("name") or (
            "Define effect…" if self.type_value.get() == "Custom"
            else f"Choose {self.type_value.get().lower()}…"
        )
        self.choose_button.button_text = text
        self.choose_button.itemconfigure(self.choose_button.label, text=text)

    def refresh_controls(self):
        linked = self.type_value.get() != "Custom"
        if linked:
            self.mode_value.set("Clickable")
        self.depletable_button.configure(
            state="normal" if self.mode_value.get() == "Clickable" else "disabled"
        )
        if self.mode_value.get() != "Clickable":
            self.depletable_value.set(False)

    def change_type(self, *arguments):
        if self.loading:
            return
        self.action = normalize_item_action({"effect_type": self.type_value.get()})
        self.refresh_label()
        self.refresh_controls()
        self.change_command()

    def choose_target(self):
        if self.type_value.get() == "Custom":
            CustomEffectDialog(self, self.action, self.set_custom)
        else:
            EffectPicker(
                self, self.database, self.type_value.get(), self.set_linked
            )

    def set_linked(self, collection, record):
        self.action.update({
            "target_collection": collection,
            "target_id": str(record.get("record_id", "")),
            "name": str(record.get("name", "")),
            "description": str(record.get("description", "") or ""),
        })
        self.refresh_label()
        self.change_command()

    def set_custom(self, name, effect):
        self.action.update({"name": name, "description": effect})
        self.refresh_label()
        self.change_command()

    def changed(self, *arguments):
        if not self.loading:
            self.refresh_controls()
            self.change_command()

    def get_action(self):
        scope = next(
            (value for value, label in TARGET_SCOPE_LABELS.items()
             if label == self.scope_value.get()),
            "self",
        )
        value = dict(self.action)
        value.update({
            "effect_type": self.type_value.get(),
            "activation_mode": (
                "click" if self.mode_value.get() == "Clickable" else "passive"
            ),
            "target_scope": scope,
            "depletable": bool(self.depletable_value.get()),
        })
        return normalize_item_action(value)


class ItemEffectEditor(tk.Frame):
    def __init__(self, parent, database, change_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")
        self.database = database
        self.change_command = change_command
        self.rows = []
        self.grid_columnconfigure(0, weight=1)
        heading = tk.Frame(self, bg=SURFACE)
        heading.grid(row=0, column=0, sticky="ew")
        heading.grid_columnconfigure(0, weight=1)
        bind_theme(heading, background="SURFACE")
        tk.Label(
            heading, text="Item Effects", bg=SURFACE, fg=TEXT_DARK,
            font=app_font(10), anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        SoftButton(
            heading, text="+", command=self.add_effect, background=SURFACE,
            fill=PRIMARY, fill_role="PRIMARY", hover_fill_role="PRIMARY_DARK",
            width=36, height=34, padx=0,
        ).grid(row=0, column=1)
        self.rows_frame = tk.Frame(
            self, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1,
        )
        self.rows_frame.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        self.rows_frame.grid_columnconfigure(0, weight=1)
        bind_theme(
            self.rows_frame, background="SURFACE", highlightbackground="BORDER"
        )

    def set_actions(self, actions):
        for row in self.rows:
            row.destroy()
        self.rows = []
        for action in actions or []:
            self.add_effect_row(action, notify=False)

    def get_actions(self):
        return [row.get_action() for row in self.rows]

    def add_effect(self):
        self.add_effect_row({}, notify=True)

    def add_effect_row(self, action, notify):
        row = ItemEffectRow(
            self.rows_frame, self.database, self.change_command, self.remove_effect
        )
        row.set_action(action)
        row.grid(row=len(self.rows), column=0, sticky="ew", padx=3, pady=2)
        self.rows.append(row)
        if notify:
            self.change_command()

    def remove_effect(self, row):
        if row not in self.rows:
            return
        self.rows.remove(row)
        row.destroy()
        for index, current in enumerate(self.rows):
            current.grid_configure(row=index)
        self.change_command()
