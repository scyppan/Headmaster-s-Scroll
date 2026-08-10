import tkinter as tk
from copy import deepcopy

from runtime_theme import bind_theme
from sections.nature_and_alchemy.creatures.form_fields import (
    LabeledEntry,
)
from sections.nature_and_alchemy.potions.ingredient_picker import (
    IngredientPicker,
)
from sections.nature_and_alchemy.potions.recipe_schema import (
    INGREDIENT_TYPES,
)
from shared.widgets import SoftButton, StripedListbox
from theme import (
    BORDER_SOFT,
    FIELD_BACKGROUND,
    SIDEBAR_TILE_SELECTED,
    SURFACE,
    TEXT_DARK,
    app_font,
)

class IngredientsEditor(tk.Frame):
    def __init__(
        self,
        parent,
        database,
        change_command,
        title_text="Ingredients",
        selected_label="Selected Ingredient",
        unnamed_item_label="Unnamed ingredient",
    ):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.database = database
        self.change_command = change_command
        self.unnamed_item_label = unnamed_item_label
        self.loading_ingredient = False
        self.ingredients = []
        self.selected_index = None

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=4)
        self.grid_columnconfigure(1, weight=2)
        self.grid_columnconfigure(2, weight=1)

        self.header = tk.Frame(self, bg=SURFACE)
        self.header.grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(0, 10),
        )
        self.header.grid_columnconfigure(0, weight=1)
        bind_theme(self.header, background="SURFACE")

        self.title = tk.Label(
            self.header,
            text=title_text,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(12),
            anchor="w",
        )
        self.title.grid(row=0, column=0, sticky="ew")
        bind_theme(
            self.title,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.add_button = SoftButton(
            self.header,
            text="Add",
            command=self.add_ingredient,
            width=68,
            height=34,
        )
        self.add_button.grid(row=0, column=1, padx=(8, 3))

        self.remove_button = SoftButton(
            self.header,
            text="Remove",
            command=self.remove_ingredient,
            width=84,
            height=34,
        )
        self.remove_button.grid(row=0, column=2, padx=3)

        self.up_button = SoftButton(
            self.header,
            text="Move Up",
            command=self.move_ingredient_up,
            width=92,
            height=34,
        )
        self.up_button.grid(row=0, column=3, padx=3)

        self.down_button = SoftButton(
            self.header,
            text="Move Down",
            command=self.move_ingredient_down,
            width=104,
            height=34,
        )
        self.down_button.grid(row=0, column=4, padx=(3, 0))

        self.name_field = LabeledEntry(
            self,
            selected_label,
            self.handle_field_change,
            font_size=11,
        )
        self.name_field.grid(row=1, column=0, sticky="ew", pady=(0, 12))

        self.type_field = LabeledEntry(
            self,
            "Ingredient Type",
            self.handle_field_change,
        )
        self.type_field.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(12, 0),
            pady=(0, 12),
        )

        self.quantity_field = LabeledEntry(
            self,
            "Quantity Required",
            self.handle_field_change,
            justify="center",
            font_size=10,
        )
        self.quantity_field.grid(
            row=1,
            column=2,
            sticky="ew",
            padx=(12, 0),
            pady=(0, 12),
        )
        quantity_validation = (
            self.register(self.validate_quantity_input),
            "%P",
        )
        self.quantity_field.entry.entry.configure(
            validate="key",
            validatecommand=quantity_validation,
        )

        self.list_frame = tk.Frame(self, bg=SURFACE)
        self.list_frame.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="nsew",
        )
        self.list_frame.grid_rowconfigure(0, weight=1)
        self.list_frame.grid_columnconfigure(0, weight=1)
        bind_theme(self.list_frame, background="SURFACE")

        self.listbox = StripedListbox(
            self.list_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=SIDEBAR_TILE_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            highlightbackground=BORDER_SOFT,
            highlightcolor=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
            font=app_font(10),
            activestyle="none",
            exportselection=False,
            selectmode="browse",
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", self.select_ingredient)

        self.scrollbar = tk.Scrollbar(
            self.list_frame,
            orient="vertical",
            command=self.listbox.yview,
            relief="flat",
            borderwidth=0,
        )
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        self.listbox.configure(yscrollcommand=self.scrollbar.set)

        self.set_detail_enabled(False)

    def set_ingredients(self, ingredients):
        self.loading_ingredient = True
        self.ingredients = (
            deepcopy(ingredients) if isinstance(ingredients, list) else []
        )
        self.selected_index = 0 if self.ingredients else None
        self.refresh_list()
        self.load_selected_ingredient()
        self.loading_ingredient = False

    def get_ingredients(self):
        self.save_selected_ingredient()
        converted_ingredients = []

        for ingredient in self.ingredients:
            ingredient_name = str(ingredient.get("name", "")).strip()

            if not ingredient_name:
                raise ValueError("Every ingredient must have a name")

            ingredient_type = str(
                ingredient.get("type", "General Item")
            ).strip() or "General Item"

            if ingredient_type not in INGREDIENT_TYPES:
                raise ValueError(
                    f"Unknown ingredient type for {ingredient_name}: "
                    f"{ingredient_type}"
                )

            quantity = ingredient.get("quantity", 1)

            if isinstance(quantity, bool) or not isinstance(quantity, int):
                raise TypeError(
                    f"Quantity for {ingredient_name} must be a whole number"
                )

            if quantity < 1:
                raise ValueError(
                    f"Quantity for {ingredient_name} must be at least 1"
                )

            converted_ingredients.append(
                {
                    "name": ingredient_name,
                    "type": ingredient_type,
                    "quantity": quantity,
                }
            )

        return converted_ingredients

    def add_ingredient(self):
        self.save_selected_ingredient()
        picker = IngredientPicker(self, self.database)
        self.wait_window(picker)

        if picker.selected_ingredient is None:
            return

        self.ingredients.append(picker.selected_ingredient)
        self.selected_index = len(self.ingredients) - 1
        self.refresh_list()
        self.load_selected_ingredient()
        self.change_command()
        self.quantity_field.focus_set()

    def remove_ingredient(self):
        if self.selected_index is None:
            return

        del self.ingredients[self.selected_index]

        if self.ingredients:
            self.selected_index = min(
                self.selected_index,
                len(self.ingredients) - 1,
            )
        else:
            self.selected_index = None

        self.refresh_list()
        self.load_selected_ingredient()
        self.change_command()

    def move_ingredient_up(self):
        if self.selected_index is None or self.selected_index == 0:
            return

        self.save_selected_ingredient()
        target_index = self.selected_index - 1
        self.ingredients[target_index], self.ingredients[self.selected_index] = (
            self.ingredients[self.selected_index],
            self.ingredients[target_index],
        )
        self.selected_index = target_index
        self.refresh_list()
        self.load_selected_ingredient()
        self.change_command()

    def move_ingredient_down(self):
        if (
            self.selected_index is None
            or self.selected_index >= len(self.ingredients) - 1
        ):
            return

        self.save_selected_ingredient()
        target_index = self.selected_index + 1
        self.ingredients[target_index], self.ingredients[self.selected_index] = (
            self.ingredients[self.selected_index],
            self.ingredients[target_index],
        )
        self.selected_index = target_index
        self.refresh_list()
        self.load_selected_ingredient()
        self.change_command()

    def select_ingredient(self, event=None):
        if self.loading_ingredient:
            return

        selected_indices = self.listbox.curselection()

        if not selected_indices:
            return

        selected_index = selected_indices[0]

        if selected_index == self.selected_index:
            return

        self.save_selected_ingredient()
        self.selected_index = selected_index
        self.load_selected_ingredient()

    def refresh_list(self):
        self.loading_ingredient = True
        self.listbox.delete(0, "end")

        for ingredient in self.ingredients:
            ingredient_name = str(ingredient.get("name", "")).strip()
            display_name = ingredient_name or self.unnamed_item_label
            ingredient_type = str(
                ingredient.get("type", "General Item")
            ).strip() or "General Item"
            quantity = ingredient.get("quantity", 1)
            display_quantity = (
                quantity
                if isinstance(quantity, int)
                and not isinstance(quantity, bool)
                and quantity >= 1
                else "?"
            )
            self.listbox.insert(
                "end",
                (
                    "• "
                    f"{display_quantity} × [{ingredient_type}] {display_name}"
                ),
            )

        if self.selected_index is not None:
            self.listbox.selection_set(self.selected_index)
            self.listbox.activate(self.selected_index)
            self.listbox.see(self.selected_index)

        self.loading_ingredient = False
        self.update_button_states()

    def load_selected_ingredient(self):
        self.loading_ingredient = True

        if self.selected_index is None:
            self.name_field.set_value("")
            self.type_field.set_value("General Item")
            self.quantity_field.set_value(None)
            self.set_detail_enabled(False)
        else:
            ingredient = self.ingredients[self.selected_index]
            self.name_field.set_value(ingredient.get("name", ""))
            ingredient_type = ingredient.get("type", "General Item")
            self.type_field.set_value(ingredient_type or "General Item")
            self.quantity_field.set_value(ingredient.get("quantity", 1))
            self.set_detail_enabled(True)

        self.loading_ingredient = False
        self.update_button_states()

    def save_selected_ingredient(self):
        if self.selected_index is None:
            return

        ingredient = dict(self.ingredients[self.selected_index])
        quantity_text = self.quantity_field.get_value()
        ingredient["quantity"] = (
            int(quantity_text) if quantity_text else None
        )
        self.ingredients[self.selected_index] = ingredient

    def handle_field_change(self, *arguments):
        if self.loading_ingredient or self.selected_index is None:
            return

        self.save_selected_ingredient()
        self.refresh_list()
        self.change_command()

    def set_detail_enabled(self, enabled):
        self.name_field.entry.set_enabled(False)
        self.type_field.entry.set_enabled(False)
        self.quantity_field.entry.set_enabled(enabled)

    def validate_quantity_input(self, proposed_value):
        return proposed_value == "" or proposed_value.isdigit()

    def update_button_states(self):
        has_selection = self.selected_index is not None
        self.remove_button.set_enabled(has_selection)
        self.up_button.set_enabled(
            has_selection and self.selected_index > 0
        )
        self.down_button.set_enabled(
            has_selection
            and self.selected_index < len(self.ingredients) - 1
        )
