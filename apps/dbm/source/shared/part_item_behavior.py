from __future__ import annotations

from copy import deepcopy
import tkinter as tk
from tkinter import messagebox, ttk

from runtime_theme import bind_theme
from shared.bonus_records import (
    normalize_bonus_record_values,
    validate_bonus_record_values,
)
from shared.item_actions import normalize_item_actions, validate_item_actions
from shared.item_assets import normalize_item_image_reference
from shared.widgets import (
    BonusEditor,
    ItemEffectEditor,
    ItemImageAssetField,
    RoundedEntry,
    SoftButton,
)
from theme import APP_BACKGROUND, SURFACE, TEXT_DARK, TEXT_MUTED, app_font


def normalize_part_item_behavior(part):
    """Apply the reusable item contract without turning a part into a duplicate item."""
    value = normalize_bonus_record_values(deepcopy(part))
    value["image_asset"] = normalize_item_image_reference(
        value.get("image_asset", "")
    )
    try:
        value["base_knuts"] = int(value.get("base_knuts", 0) or 0)
    except (TypeError, ValueError) as error:
        raise ValueError("Base Knuts must be a whole number.") from error
    value["tags"] = sorted({
        " ".join(str(tag).split())
        for tag in value.get("tags", []) or []
        if str(tag).strip()
    }, key=str.casefold)
    value["actions"] = normalize_item_actions(value.get("actions", []) or [])
    value.setdefault("activation_mode", "passive")
    return value


def validate_part_item_behavior(part, database):
    value = normalize_part_item_behavior(part)
    if value["base_knuts"] < 0:
        raise ValueError("Base Knuts cannot be negative.")
    validate_bonus_record_values(value)
    validate_item_actions(value.get("actions", []), database)
    if any(not isinstance(tag, str) or not tag.strip() for tag in value["tags"]):
        raise ValueError("Part tags must be non-blank text values.")


class PartItemBehaviorDialog(tk.Toplevel):
    """Edit the item-like fields stored directly on a plant or creature part."""

    def __init__(self, parent, database, part, title="Part item properties"):
        super().__init__(parent)
        self.database = database
        self.result = None
        self.original = normalize_part_item_behavior(part)
        self.title(title)
        self.geometry("980x650")
        self.minsize(760, 560)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.configure(bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        heading = tk.Frame(self, bg=SURFACE)
        heading.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        heading.grid_columnconfigure(2, weight=1)
        bind_theme(heading, background="SURFACE")
        self.image = ItemImageAssetField(heading, lambda: None)
        self.image.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 12))
        self.image.set_value(self.original.get("image_asset", ""))
        tk.Label(
            heading, text="Base Knuts", bg=SURFACE, fg=TEXT_DARK,
            font=app_font(9), anchor="w",
        ).grid(row=0, column=1, sticky="sw", padx=(0, 8))
        self.base_knuts = tk.StringVar(value=str(self.original.get("base_knuts", 0)))
        ttk.Spinbox(
            heading, textvariable=self.base_knuts, from_=0, to=999999999,
            width=12,
        ).grid(row=1, column=1, sticky="nw", padx=(0, 18))
        tk.Label(
            heading, text="Tags (comma separated)", bg=SURFACE,
            fg=TEXT_DARK, font=app_font(9), anchor="w",
        ).grid(row=0, column=2, sticky="sw")
        self.tags = tk.StringVar(value=", ".join(self.original.get("tags", [])))
        RoundedEntry(
            heading, textvariable=self.tags, background=SURFACE,
            height=36, font=app_font(9),
        ).grid(row=1, column=2, sticky="ew")
        tk.Label(
            heading,
            text=(
                "This remains a part of its plant or creature. Loot, recipes, "
                "inventory, images, and effects all reference this same stable part."
            ),
            bg=SURFACE, fg=TEXT_MUTED, font=app_font(8), anchor="w",
        ).grid(row=2, column=1, columnspan=2, sticky="ew", pady=(8, 0))

        self.bonuses = BonusEditor(self, lambda: None)
        self.bonuses.grid(row=1, column=0, sticky="ew", padx=14, pady=8)
        self.bonuses.set_bonuses(self.original.get("bonuses", []))

        self.actions = ItemEffectEditor(self, database, lambda: None)
        self.actions.grid(row=2, column=0, sticky="nsew", padx=14, pady=8)
        self.actions.set_actions(self.original.get("actions", []))

        actions = tk.Frame(self, bg=APP_BACKGROUND)
        actions.grid(row=3, column=0, sticky="e", padx=14, pady=(8, 14))
        SoftButton(
            actions, text="Cancel", command=self.destroy,
            background=APP_BACKGROUND, width=100, height=36,
        ).pack(side="left", padx=4)
        SoftButton(
            actions, text="Apply", command=self.apply,
            background=APP_BACKGROUND, width=110, height=36,
        ).pack(side="left", padx=4)

    def apply(self):
        value = deepcopy(self.original)
        value.update({
            "image_asset": self.image.get_value(),
            "base_knuts": self.base_knuts.get(),
            "tags": [tag.strip() for tag in self.tags.get().split(",") if tag.strip()],
            "bonuses": self.bonuses.get_bonuses(),
            "actions": self.actions.get_actions(),
        })
        try:
            value = normalize_part_item_behavior(value)
            validate_part_item_behavior(value, self.database)
        except (TypeError, ValueError) as error:
            messagebox.showerror("Cannot apply item properties", str(error), parent=self)
            return
        self.result = value
        self.destroy()
