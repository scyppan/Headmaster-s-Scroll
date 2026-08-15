import tkinter as tk
from copy import deepcopy
from tkinter import messagebox

from mage_maker.dialogs.creation import CreationWizardDialog
from mage_maker.sections.development.models import (
    DEVELOPMENT_ASSIGNMENT_PROMPT,
    new_development_plan,
)
from mage_maker.sections.development.strategy_dialog import (
    DevelopmentStrategyDialog,
)
from mage_maker.sections.locations.period_definitions import (
    load_period_definitions,
)
from mage_maker.sections.profile.page import PersonForm
from mage_maker.sections.timeline.locations import ParentLocationConflict
from mage_maker.shell.person_list import PeopleList
from mage_maker.ui.theme import (
    APP_BACKGROUND,
    BORDER,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    DELETE_HOVER,
    DELETE_SOFT,
    PRIMARY,
    PRIMARY_DARK,
    PRIMARY_HOVER,
    PRIMARY_SOFT,
    SURFACE,
    TEXT_DARK,
    TEXT_LIGHT,
    app_font,
)
from mage_maker.ui.widgets import SoftButton


class MagesPage(tk.Frame):
    def __init__(
        self,
        parent,
        controller,
        game_database,
        status_command,
        records_changed_command,
        event_controller=None,
        navigate_event_command=None,
        organization_provider=None,
        settings_provider=None,
        organization_create_command=None,
        organization_location_provider=None,
        item_controller=None,
        book_controller=None,
    ):
        super().__init__(parent, bg=APP_BACKGROUND)
        self.controller = controller
        self.game_database = game_database
        self.status_command = status_command
        self.records_changed_command = records_changed_command
        self.event_controller = event_controller
        self.navigate_event_command = navigate_event_command
        self.organization_provider = organization_provider
        self.settings_provider = settings_provider
        self.organization_create_command = (
            organization_create_command
        )
        self.organization_location_provider = (
            organization_location_provider
        )
        self.item_controller = item_controller
        self.book_controller = book_controller
        self.people = []
        self.current_record_id = None
        self.form_dirty = False
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_workspace()
        self.refresh_people()

        if self.people:
            initial_record_id = (
                self.people_list.visible_record_ids[0]
                if self.people_list.visible_record_ids
                else self.people[0]["record_id"]
            )
            self.load_person(initial_record_id)

    def build_workspace(self):
        workspace = tk.PanedWindow(
            self,
            orient="horizontal",
            bg=BORDER,
            borderwidth=0,
            sashwidth=6,
            sashrelief="flat",
            showhandle=False,
        )
        workspace.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=18,
            pady=(10, 18),
        )
        list_card = tk.Frame(
            workspace,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        list_card.grid_rowconfigure(0, weight=1)
        list_card.grid_columnconfigure(0, weight=1)
        initial_period_filter = ""
        period_filter_change_command = None

        if self.settings_provider is not None:
            period_filter_provider = getattr(
                self.settings_provider,
                "people_period_filter",
                None,
            )
            stored_period_change_command = getattr(
                self.settings_provider,
                "set_people_period_filter",
                None,
            )

            if callable(period_filter_provider):
                initial_period_filter = period_filter_provider()

            if callable(stored_period_change_command):
                period_filter_change_command = (
                    stored_period_change_command
                )

        self.people_list = PeopleList(
            list_card,
            selection_command=self.select_person,
            create_command=self.open_creation_wizard,
            period_provider=load_period_definitions,
            initial_period_filter=initial_period_filter,
            period_filter_change_command=(
                period_filter_change_command
            ),
        )
        self.people_list.grid(row=0, column=0, sticky="nsew")
        editor_card = tk.Frame(
            workspace,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        editor_card.grid_rowconfigure(1, weight=1)
        editor_card.grid_columnconfigure(0, weight=1)
        self.build_editor_toolbar(editor_card)
        self.person_form = PersonForm(
            editor_card,
            self.mark_form_dirty,
            self.controller.list_people,
            self.create_related_person,
            self.update_related_person,
            self.refresh_related_people,
            self.select_person,
            self.game_database,
            self.event_controller,
            self.records_changed_command,
            self.navigate_event_command,
            mage_group_provider=self.controller.list_mage_groups,
            organization_provider=self.organization_provider,
            settings_provider=self.settings_provider,
            organization_create_command=(
                self.organization_create_command
            ),
            organization_location_provider=(
                self.organization_location_provider
            ),
            item_controller=self.item_controller,
            book_controller=self.book_controller,
            status_command=self.status_command,
            people_summary_provider=(
                self.controller.list_people_summaries
                if hasattr(
                    self.controller,
                    "list_people_summaries",
                )
                else self.controller.list_people
            ),
            save_person_command=self.save_person,
        )
        self.person_form.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=22,
            pady=18,
        )
        workspace.add(list_card, minsize=300, width=350)
        workspace.add(editor_card, minsize=690)

    def build_editor_toolbar(self, parent):
        toolbar = tk.Frame(parent, bg=PRIMARY_DARK, height=64)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.grid_propagate(False)
        toolbar.grid_columnconfigure(1, weight=1)
        self.editor_group_bar = tk.Frame(
            toolbar,
            bg=PRIMARY,
            width=10,
        )
        self.editor_group_bar.grid(
            row=0,
            column=0,
            sticky="ns",
        )
        self.editor_group_bar.grid_propagate(False)
        self.editor_title_value = tk.StringVar(
            value="Magician Profile"
        )
        label = tk.Label(
            toolbar,
            textvariable=self.editor_title_value,
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(16, "bold"),
            anchor="w",
            padx=16,
        )
        label.grid(row=0, column=1, sticky="nsew")
        self.new_button = SoftButton(
            toolbar,
            text="New",
            command=self.open_creation_wizard,
            background=PRIMARY_DARK,
            fill=PRIMARY_SOFT,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=82,
            height=38,
        )
        self.new_button.grid(row=0, column=2, padx=4, pady=13)
        self.delete_button = SoftButton(
            toolbar,
            text="Delete",
            command=self.delete_person,
            background=PRIMARY_DARK,
            fill=DELETE_SOFT,
            hover_fill=DELETE_HOVER,
            foreground=TEXT_DARK,
            width=88,
            height=38,
        )
        self.delete_button.grid(row=0, column=3, padx=4, pady=13)
        self.revert_button = SoftButton(
            toolbar,
            text="Revert",
            command=self.revert_person,
            background=PRIMARY_DARK,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=88,
            height=38,
        )
        self.revert_button.grid(row=0, column=4, padx=4, pady=13)
        self.save_button = SoftButton(
            toolbar,
            text="Save",
            command=self.save_person,
            background=PRIMARY_DARK,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=92,
            height=38,
        )
        self.save_button.grid(row=0, column=5, padx=(4, 16), pady=13)
        self.set_editor_state(False)

    def refresh_people(self, selected_record_id=None):
        summary_provider = getattr(
            self.controller,
            "list_people_list_summaries",
            None,
        )
        self.people = (
            summary_provider()
            if callable(summary_provider)
            else self.controller.list_people()
        )
        self.people_list.set_people(
            self.people,
            selected_record_id,
            self.controller.list_mage_groups(),
        )

    def load_person(self, record_id):
        person = self.controller.get_person(record_id)

        if person is None:
            return False

        self.current_record_id = record_id
        self.controller.remember_person_interaction(record_id)
        self.update_editor_identity(person)
        self.person_form.set_person(person)
        self.people_list.set_selected_record(record_id)
        self.form_dirty = False
        self.set_editor_state(True)
        self.status_command(f"Loaded {person.get('displayed_name', 'magician')}")
        return True

    def select_person(self, record_id):
        if record_id == self.current_record_id:
            return True

        if not self.confirm_unsaved_changes():
            self.people_list.set_selected_record(self.current_record_id)
            return False

        return self.load_person(record_id)

    def open_creation_wizard(self):
        if not self.confirm_unsaved_changes():
            return

        CreationWizardDialog(
            self,
            self.create_person,
            self.game_database,
            self.event_controller,
        )

    def create_person(self, values):
        creation_values = self.prepare_creation_values(values)
        created_person = self.controller.create_person(creation_values)
        self.refresh_people(created_person["record_id"])
        self.load_person(created_person["record_id"])
        self.records_changed_command()
        self.status_command(f"Created {created_person['displayed_name']}")
        return created_person

    def create_related_person(self, values):
        creation_values = self.prepare_creation_values(values)
        created_person = self.controller.create_person(creation_values)
        self.refresh_people(self.current_record_id)
        self.records_changed_command()
        self.status_command(
            f"Created {created_person['displayed_name']} as a relative"
        )
        return created_person

    def prepare_creation_values(self, values):
        creation_values = deepcopy(values)

        if creation_values.get("non_magical"):
            return creation_values

        if creation_values.get("development_plan") not in (None, ""):
            return creation_values

        if (
            self.controller.development_assignment_policy()
            != DEVELOPMENT_ASSIGNMENT_PROMPT
        ):
            return creation_values

        previous_grab = self.current_grab_widget()
        prompt_parent = (
            previous_grab
            if previous_grab is not None
            else self.development_prompt_parent()
        )
        dialog = DevelopmentStrategyDialog(
            prompt_parent,
            creation_values.get("displayed_name", ""),
        )
        self.wait_window(dialog)

        if previous_grab is not None:
            self.restore_prompt_parent_grab(previous_grab)

        if dialog.result is None:
            raise ValueError(
                "Choose a development strategy before creating this magician."
            )

        creation_values["development_plan"] = new_development_plan(
            DEVELOPMENT_ASSIGNMENT_PROMPT,
            dialog.result,
        )
        return creation_values

    def current_grab_widget(self):
        try:
            return self.grab_current()
        except tk.TclError:
            return None

    def development_prompt_parent(self):
        focused_widget = self.focus_get()

        if focused_widget is None:
            return self

        try:
            return focused_widget.winfo_toplevel()
        except (AttributeError, tk.TclError):
            return self

    def restore_prompt_parent_grab(self, prompt_parent):
        try:
            if prompt_parent.winfo_exists():
                prompt_parent.grab_set()
        except (AttributeError, tk.TclError):
            return

    def update_related_person(self, record_id, values):
        updated_person = self.controller.update_person(record_id, values)
        self.refresh_people(self.current_record_id)
        self.records_changed_command()
        self.status_command(
            f"Updated family links for {updated_person['displayed_name']}"
        )
        return updated_person

    def refresh_related_people(self):
        self.refresh_people(self.current_record_id)

    def refresh_linked_events(self):
        self.person_form.refresh_linked_events()

    def refresh_period_filters(self):
        self.people_list.refresh_periods()

    def save_person(self):
        if self.current_record_id is None:
            return False

        if self.person_form.specialty_school_is_blank():
            messagebox.showerror(
                "Specialty school required",
                "Enter the specialty school name.",
                parent=self,
            )
            return False

        values = self.person_form.get_values()

        try:
            saved_person = self.controller.update_person(
                self.current_record_id,
                values,
            )
        except ParentLocationConflict as error:
            if not self.confirm_long_distance_parent_override(error):
                return False

            values["long_distance_parent_override"] = True

            try:
                saved_person = self.controller.update_person(
                    self.current_record_id,
                    values,
                )
            except (TypeError, ValueError) as retry_error:
                messagebox.showerror(
                    "Cannot save magician",
                    str(retry_error),
                    parent=self,
                )
                return False
        except (TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot save magician",
                str(error),
                parent=self,
            )
            return False

        self.refresh_people(saved_person["record_id"])
        self.load_person(saved_person["record_id"])
        self.records_changed_command()
        self.status_command(f"Saved {saved_person['displayed_name']}")
        return True

    def confirm_long_distance_parent_override(self, error):
        return messagebox.askyesno(
            "Parents are in different locations",
            (
                f"{error}\n\n"
                "Make the parent locations match before saving, or choose Yes "
                "to use the birthing parent's location, remember that choice "
                "for these parents, and add ‘Father not present at time of "
                "birth.’ to Born.\n\n"
                "Use the birth-location override?"
            ),
            parent=self,
            icon="warning",
            default="no",
        )

    def delete_person(self):
        if self.current_record_id is None:
            return

        person = self.controller.get_person(self.current_record_id)
        person_name = person.get("displayed_name", "this magician")

        if not messagebox.askyesno(
            "Delete magician",
            f"Permanently delete {person_name}?",
            parent=self,
        ):
            return

        self.controller.delete_person(self.current_record_id)
        self.current_record_id = None
        self.form_dirty = False
        self.refresh_people()

        if self.people:
            self.load_person(self.people[0]["record_id"])
        else:
            self.set_editor_state(False)

        self.records_changed_command()
        self.status_command(f"Deleted {person_name}")

    def revert_person(self):
        if self.current_record_id is None:
            return

        self.load_person(self.current_record_id)
        self.status_command("Changes reverted")

    def mark_form_dirty(self):
        if self.current_record_id is None:
            return

        self.form_dirty = True
        self.people_list.set_initial_values_status(
            self.current_record_id,
            self.person_form.initial_values_complete(),
            self.person_form.variables["unfinished"].get(),
        )
        self.update_editor_identity_from_form()
        self.save_button.set_enabled(True)
        self.revert_button.set_enabled(True)
        self.status_command("Unsaved changes")

    def set_editor_state(self, has_person):
        self.delete_button.set_enabled(has_person)
        self.save_button.set_enabled(False)
        self.revert_button.set_enabled(False)

        if not has_person:
            self.editor_title_value.set("Magician Profile")
            self.editor_group_bar.configure(bg=PRIMARY)

    def update_editor_identity(self, person):
        person_values = person if isinstance(person, dict) else {}
        displayed_name = str(
            person_values.get("displayed_name", "") or ""
        ).strip()
        group = self.controller.mage_group(
            person_values.get("mage_group_id")
        )
        self.editor_title_value.set(
            displayed_name or "Unnamed magician"
        )
        self.editor_group_bar.configure(bg=group["color"])

    def update_editor_identity_from_form(self):
        displayed_name = self.person_form.variables[
            "displayed_name"
        ].get().strip()
        group = self.controller.mage_group(
            self.person_form.selected_mage_group_id()
        )
        self.editor_title_value.set(
            displayed_name or "Unnamed magician"
        )
        self.editor_group_bar.configure(bg=group["color"])

    def refresh_group_data(self):
        selected_record_id = self.current_record_id
        self.refresh_people(selected_record_id)

        if selected_record_id is None:
            return

        person = self.controller.get_person(selected_record_id)

        if person is None:
            return

        self.person_form.refresh_mage_groups(
            person.get("mage_group_id")
        )
        self.update_editor_identity(person)

    def confirm_unsaved_changes(self):
        if not self.person_form.confirm_unsaved_event_changes():
            return False

        if not self.form_dirty:
            return True

        save_choice = messagebox.askyesnocancel(
            "Unsaved magician changes",
            "Save changes before continuing?",
            parent=self,
        )

        if save_choice is None:
            return False

        if save_choice:
            return self.save_person()

        self.revert_person()
        return True

    def save_shortcut(self):
        if self.form_dirty:
            self.save_person()

    def create_shortcut(self):
        self.open_creation_wizard()

    def search_shortcut(self):
        self.people_list.search_entry.focus_set()
        self.people_list.search_entry.selection_range(0, "end")
