import tkinter as tk
from copy import deepcopy
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox

from headmasters_scroll.assets import AssetStore
from headmasters_scroll.board import normalize_person_board

from mage_maker.core.dates import (
    format_date_parts,
    format_historical_display_date,
    person_age_at_death,
    person_death_age_text,
    split_partial_date,
)
from mage_maker.sections.development.characteristics import (
    initial_values_are_complete,
)
from mage_maker.sections.development.models import (
    calculate_development_start_year,
    development_year_pages,
    non_magical_development_plan,
    normalize_development_plan,
    school_progress_text,
)
from mage_maker.sections.development.page import DevelopmentView
from mage_maker.sections.family_tree.page import FamilyTreeView
from mage_maker.sections.events.models import death_event_person_ids
from mage_maker.sections.events.types import canonical_event_type
from mage_maker.sections.names.details import NameDetailsDialog, NameEntryDialog
from mage_maker.sections.names.history import (
    new_name_entry,
    normalize_name_details,
    normalize_name_entry,
)
from mage_maker.sections.names.timeline import (
    name_entry_for_timeline_event,
    synchronize_name_change_events,
)
from mage_maker.sections.profile.famous_connections import (
    FamousConnectionMap,
    FamousConnectionsView,
)
from mage_maker.sections.profile.books import BooksView
from mage_maker.sections.profile.jobs import NonMagicalJobsView
from mage_maker.sections.profile.portrait import choose_square_crop
from mage_maker.sections.items.page import ItemsView
from mage_maker.sections.relationships.page import RelationshipsView
from mage_maker.sections.ledger.page import LedgerView
from mage_maker.sections.settings.mage_groups import (
    default_mage_groups,
    normalize_mage_group_id,
    normalize_mage_groups,
)
from mage_maker.sections.timeline.page import TimelineView
from mage_maker.sections.timeline.events import (
    normalize_timeline_event,
    normalize_timeline_events,
    synchronize_profile_timeline_events,
)
from mage_maker.sections.timeline.locations import (
    born_long_distance_parent_ids,
    ensure_life_start_events,
)
from mage_maker.ui.theme import (
    BORDER,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    FIELD_BACKGROUND,
    PRIMARY,
    PRIMARY_HOVER,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import (
    HoverTooltip,
    LabeledEntry,
    MultilineField,
    RoundedSelect,
    SectionPanel,
    SoftButton,
)
from mage_maker.ui.colored_tags import ColoredTagsEditor


LAST_TIMELINE_PERSON_STORAGE_KEY = "last_timeline_person_id"
LAST_TIMELINE_EVENT_STORAGE_KEY = "last_timeline_event_id"


class PersonForm(tk.Frame):
    status_fields = (
        ("canon", "Canon"),
        ("player_character", "Player character"),
        ("non_magical", "Non-magical"),
        ("can_give_birth", "Can give birth"),
        ("does_not_have_children", "Does not have children"),
        ("famous_person", "This is a famous person"),
        ("animagus", "Animagus"),
        ("parseltongue", "Parseltongue"),
        ("unfinished", "Mark as unfinished"),
    )

    def __init__(
        self,
        parent,
        change_command,
        people_provider,
        create_person_command,
        update_person_command,
        refresh_people_command,
        navigate_command,
        game_database=None,
        event_controller=None,
        events_changed_command=None,
        navigate_event_command=None,
        mage_group_provider=None,
        organization_provider=None,
        settings_provider=None,
        organization_create_command=None,
        organization_location_provider=None,
        item_controller=None,
        book_controller=None,
        status_command=None,
        people_summary_provider=None,
        people_summary_by_ids_provider=None,
        save_person_command=None,
        person_record_provider=None,
    ):
        super().__init__(parent, bg=SURFACE)
        self.change_command = change_command
        self.people_provider = people_provider
        self.people_summary_provider = (
            people_summary_provider
            if callable(people_summary_provider)
            else people_provider
        )
        self.people_summary_by_ids_provider = (
            people_summary_by_ids_provider
            if callable(people_summary_by_ids_provider)
            else None
        )
        self.game_database = game_database
        self.event_controller = event_controller
        self.events_changed_command = events_changed_command
        self.navigate_event_command = navigate_event_command
        self.mage_group_provider = mage_group_provider
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
        self.status_command = status_command
        self.save_person_command = save_person_command
        self.person_record_provider = person_record_provider
        self.create_person_command = create_person_command
        self.update_person_command = update_person_command
        self.refresh_people_command = refresh_people_command
        self.navigate_command = navigate_command
        self.autosave_job = None
        self.loading = False
        self.variables = {}
        self.boolean_widgets = {}
        self.tooltips = {}
        self.text_widgets = {}
        self.name_details = {}
        self.pages = {}
        self.navigation_buttons = {}
        self.active_page_name = "profile"
        self.current_record_id = None
        self.person_snapshot = {}
        self.board_state = normalize_person_board(None)
        self.asset_store = AssetStore()
        self.portrait_photo = None
        self.loaded_section_record_ids = {}
        self.deferred_load_job = None
        self.load_generation = 0
        self.linked_events_snapshot = []
        self.timeline_selection_by_person_id = {}
        application_settings = (
            self.game_database.data.get("_application_settings", {})
            if self.game_database is not None
            and isinstance(getattr(self.game_database, "data", None), dict)
            else {}
        )
        remembered_timeline_person_id = str(
            application_settings.get(
                LAST_TIMELINE_PERSON_STORAGE_KEY,
                "",
            )
            or ""
        ).strip()
        remembered_timeline_event_id = str(
            application_settings.get(
                LAST_TIMELINE_EVENT_STORAGE_KEY,
                "",
            )
            or ""
        ).strip()

        if remembered_timeline_person_id and remembered_timeline_event_id:
            self.timeline_selection_by_person_id[
                remembered_timeline_person_id
            ] = remembered_timeline_event_id
        self.mage_groups = default_mage_groups()
        self.mage_group_value = tk.StringVar(
            value=self.mage_groups[0]["name"]
        )
        self.mage_group_value.trace_add(
            "write",
            self.mage_group_changed,
        )

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.build_navigation()

        self.content = tk.Frame(self, bg=SURFACE)
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.build_profile_page()
        self.update_person_navigation()
        self.show_page("profile")

    def ensure_page_built(self, page_name):
        """Construct a secondary profile page only when it is first opened."""
        if page_name in self.pages:
            return True
        if page_name == "family_tree":
            self.build_family_tree_page(
                self.create_person_command,
                self.update_person_command,
                self.refresh_people_command,
                self.navigate_command,
            )
        elif page_name == "relationships":
            self.build_relationships_page()
        elif page_name == "timeline":
            self.build_timeline_page(self.navigate_command)
        elif page_name == "jobs":
            self.build_jobs_page()
        elif page_name == "development":
            self.build_development_page()
        elif page_name == "items":
            self.build_items_page()
        elif page_name == "books":
            self.build_books_page()
        elif page_name == "ledger":
            self.build_ledger_page()
        else:
            return False
        return page_name in self.pages

    def build_navigation(self):
        navigation = tk.Frame(self, bg=SURFACE)
        navigation.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))

        page_definitions = (
            ("profile", "Profile", 84),
            ("family_tree", "Family Tree", 108),
            ("relationships", "Relationships", 116),
            ("timeline", "Timeline", 90),
            ("jobs", "Jobs", 76),
            ("development", "Development", 112),
            ("items", "Items", 76),
            ("books", "Books", 76),
            ("ledger", "Ledger", 78),
        )

        for page_name, button_text, width in page_definitions:
            button = SoftButton(
                navigation,
                text=button_text,
                command=partial(self.show_page, page_name),
                background=SURFACE,
                width=width,
                height=36,
            )
            button.pack(side="left", padx=(0, 6))
            self.navigation_buttons[page_name] = button

        self.current_name_value = tk.StringVar(value="Select a magician")
        current_name = tk.Label(
            navigation,
            textvariable=self.current_name_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="e",
        )
        current_name.pack(side="right", fill="x", expand=True)

    def build_profile_page(self):
        page = tk.Frame(self.content, bg=SURFACE)
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_columnconfigure(0, weight=5, uniform="profile")
        page.grid_columnconfigure(1, weight=3, uniform="profile")
        page.grid_columnconfigure(2, weight=2, uniform="profile")
        page.grid_rowconfigure(0, weight=4, uniform="profile_rows")
        page.grid_rowconfigure(1, weight=2, uniform="profile_rows")
        self.pages["profile"] = page

        identity_panel = SectionPanel(
            page,
            "Identity",
            "The displayed name is the unique name used throughout Mage Maker.",
        )
        identity_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 7),
            pady=(0, 7),
        )
        identity_panel.content.grid_columnconfigure(0, weight=1)

        name_row = tk.Frame(identity_panel.content, bg=SURFACE_MUTED)
        name_row.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        name_row.grid_columnconfigure(0, weight=3, minsize=300)
        name_row.grid_columnconfigure(2, weight=2, minsize=235)

        displayed_name_value = tk.StringVar()
        displayed_name_value.trace_add("write", self.variable_changed)
        self.variables["displayed_name"] = displayed_name_value
        displayed_name_field = LabeledEntry(
            name_row,
            "Displayed name",
            displayed_name_value,
            background=SURFACE_MUTED,
            font_size=12,
        )
        displayed_name_field.grid(row=0, column=0, sticky="new")

        self.name_details_button = SoftButton(
            name_row,
            text="Name Details",
            command=self.open_name_details,
            background=SURFACE_MUTED,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=122,
            height=40,
        )
        self.name_details_button.grid(
            row=0,
            column=1,
            sticky="n",
            padx=(7, 10),
            pady=(22, 0),
        )

        school_summary = tk.Frame(
            name_row,
            bg=SURFACE_MUTED,
        )
        school_summary.grid(
            row=0,
            column=2,
            sticky="new",
        )
        school_summary.grid_columnconfigure(0, weight=1)
        school_label = tk.Label(
            school_summary,
            text="School",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        school_label.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 5),
        )
        school_value_controls = tk.Frame(
            school_summary,
            bg=SURFACE_MUTED,
        )
        school_value_controls.grid(
            row=1,
            column=0,
            sticky="ew",
        )
        self.school_summary_value = tk.StringVar(
            value="none"
        )
        school_value = tk.Label(
            school_value_controls,
            textvariable=self.school_summary_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        school_value.pack(side="left")
        self.change_school_button = SoftButton(
            school_value_controls,
            text="Change school",
            command=self.open_school_editor,
            background=SURFACE_MUTED,
            width=116,
            height=36,
        )
        self.change_school_button.pack(
            side="left",
            padx=(8, 0),
        )

        development_summary = tk.Frame(
            identity_panel.content,
            bg=SURFACE_MUTED,
        )
        development_summary.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )
        development_summary.grid_columnconfigure(
            (0, 1),
            weight=1,
            uniform="development_summary",
        )
        school_year_block = tk.Frame(
            development_summary,
            bg=SURFACE_MUTED,
        )
        school_year_block.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 8),
        )
        school_year_label = tk.Label(
            school_year_block,
            text="School year",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        school_year_label.grid(
            row=0,
            column=0,
            sticky="ew",
        )
        self.school_year_summary_value = tk.StringVar(
            value="Not yet started school"
        )
        school_year_value = tk.Label(
            school_year_block,
            textvariable=self.school_year_summary_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        school_year_value.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(4, 0),
        )
        eminence_block = tk.Frame(
            development_summary,
            bg=SURFACE_MUTED,
        )
        eminence_block.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(8, 0),
        )
        eminence_label = tk.Label(
            eminence_block,
            text="Total eminence points",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        eminence_label.grid(
            row=0,
            column=0,
            sticky="ew",
        )
        self.total_eminence_summary_value = tk.StringVar(
            value="0 points"
        )
        eminence_value = tk.Label(
            eminence_block,
            textvariable=self.total_eminence_summary_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
            justify="left",
            wraplength=300,
        )
        eminence_value.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(4, 0),
        )

        for field_name in ("birth_year", "birth_month", "birth_day"):
            self.variables[field_name] = tk.StringVar()

        self.birth_date_display_value = tk.StringVar(
            value="Not recorded"
        )
        deceased_value = tk.BooleanVar(value=False)
        self.variables["deceased"] = deceased_value
        self.death_status_value = tk.StringVar(value="Alive")
        self.death_overview_value = tk.StringVar(value="")
        self.death_date_display_value = tk.StringVar(
            value="Not recorded"
        )
        self.life_dates_display_value = tk.StringVar(
            value="Born: Not recorded"
        )
        life_dates_frame = tk.Frame(
            identity_panel.content,
            bg=SURFACE_MUTED,
        )
        life_dates_frame.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(0, 9),
        )
        life_dates_frame.grid_columnconfigure(0, weight=1)
        self.death_date_frame = life_dates_frame
        life_dates_heading = tk.Label(
            life_dates_frame,
            text="Birth and death",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        life_dates_heading.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 5),
        )
        for field_name in ("death_year", "death_month", "death_day"):
            self.variables[field_name] = tk.StringVar()

        life_dates_value = tk.Label(
            life_dates_frame,
            textvariable=self.life_dates_display_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
            justify="left",
        )
        life_dates_value.grid(row=1, column=0, sticky="ew")
        overview = tk.Frame(page, bg=SURFACE)
        overview.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(0, 7),
            pady=(7, 0),
        )
        overview.grid_rowconfigure(0, weight=1)
        overview.grid_columnconfigure((0, 1), weight=1, uniform="overview")

        classifications_panel = SectionPanel(
            overview,
            "Classifications",
            "Quick classifications used to identify this magician's role and state.",
        )
        classifications_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 7),
        )
        classifications_panel.content.grid_columnconfigure((0, 1), weight=1)

        group_block = tk.Frame(
            classifications_panel.content,
            bg=SURFACE_MUTED,
        )
        group_block.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 8),
        )
        group_block.grid_columnconfigure(1, weight=1)
        group_label = tk.Label(
            group_block,
            text="Group",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        group_label.grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 7),
        )
        self.mage_group_select = RoundedSelect(
            group_block,
            self.mage_group_value,
            [group["name"] for group in self.mage_groups],
            background=SURFACE_MUTED,
            width=150,
            height=32,
            font=app_font(10),
        )
        self.mage_group_select.grid(
            row=0,
            column=1,
            sticky="ew",
        )

        self.add_boolean_fields(
            classifications_panel.content,
            self.status_fields,
            2,
            SURFACE_MUTED,
            start_row=1,
        )

        connections_panel = SectionPanel(
            overview,
            "Connections",
            "Family and relationship links to people marked as famous.",
        )
        connections_panel.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(7, 0),
        )
        self.famous_connections = FamousConnectionsView(
            connections_panel.content,
            SURFACE_MUTED,
        )
        self.famous_connections.grid(row=0, column=0, sticky="ew")

        narrative_field = MultilineField(
            page,
            "Narrative",
            6,
            background=SURFACE,
            hint_text="The person's story, background, and important context.",
        )
        narrative_field.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(7, 0),
            pady=(0, 7),
        )
        narrative_field.text.bind("<<Modified>>", self.text_changed)
        self.text_widgets["narrative"] = narrative_field.text

        notes_field = MultilineField(
            page,
            "Notes",
            5,
            background=SURFACE,
            hint_text="Database notes and reminders that do not belong in the narrative.",
        )
        notes_field.grid(
            row=1,
            column=1,
            sticky="nsew",
            padx=(7, 0),
            pady=(7, 0),
        )
        notes_field.text.bind("<<Modified>>", self.text_changed)
        self.text_widgets["notes"] = notes_field.text
        portrait_panel = SectionPanel(
            page,
            "Game Board portrait",
            "Square-cropped and stored locally as a private 512×512 WebP.",
        )
        portrait_panel.grid(
            row=0,
            column=2,
            sticky="nsew",
            padx=(14, 0),
            pady=(0, 7),
        )
        self.portrait_preview = tk.Label(
            portrait_panel.content,
            text="No portrait",
            bg=FIELD_BACKGROUND,
            fg=TEXT_MUTED,
            relief="solid",
            borderwidth=1,
        )
        self.portrait_preview.pack(fill="both", expand=True, pady=(0, 8))
        portrait_actions = tk.Frame(portrait_panel.content, bg=SURFACE_MUTED)
        portrait_actions.pack(fill="x")
        self.import_portrait_button = SoftButton(
            portrait_actions,
            text="Import / Replace",
            command=self.import_portrait,
            background=SURFACE_MUTED,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=126,
            height=34,
        )
        self.import_portrait_button.pack(side="left")
        self.remove_portrait_button = SoftButton(
            portrait_actions,
            text="Remove",
            command=self.remove_portrait,
            background=SURFACE_MUTED,
            width=80,
            height=34,
        )
        self.remove_portrait_button.pack(side="left", padx=(7, 0))

        self.tags_editor = ColoredTagsEditor(
            page,
            title="Tags",
            background=SURFACE,
            change_command=self.tags_changed,
            height=9,
        )
        self.tags_editor.grid(
            row=1,
            column=2,
            sticky="nsew",
            padx=(14, 0),
            pady=(7, 0),
        )

    def import_portrait(self):
        if not self.current_record_id:
            messagebox.showinfo(
                "Portrait",
                "Save this character before importing a portrait.",
                parent=self,
            )
            return
        filename = filedialog.askopenfilename(
            parent=self,
            title="Choose character portrait",
            filetypes=(
                ("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                ("All files", "*.*"),
            ),
        )
        if not filename:
            return
        try:
            crop = choose_square_crop(self, Path(filename))
            if crop is None:
                return
            metadata = self.asset_store.import_portrait(
                self.current_record_id,
                Path(filename),
                crop,
            )
            self.board_state["portrait"] = metadata
            self.render_portrait()
            if not self.loading:
                self.change_command()
        except Exception as error:
            messagebox.showerror(
                "Cannot import portrait",
                str(error),
                parent=self,
            )

    def remove_portrait(self):
        if not self.board_state.get("portrait"):
            return
        if not messagebox.askyesno(
            "Remove portrait",
            "Remove this portrait from the character record? A recoverable local asset backup will remain.",
            parent=self,
        ):
            return
        self.board_state["portrait"] = None
        if (
            self.board_state.get("display_mode") == "token"
            and not self.person_snapshot.get("player_character")
        ):
            self.board_state["display_mode"] = "dot"
        self.render_portrait()
        if not self.loading:
            self.change_command()

    def render_portrait(self):
        metadata = self.board_state.get("portrait")
        self.remove_portrait_button.set_enabled(bool(metadata))
        if not metadata:
            self.portrait_photo = None
            self.portrait_preview.configure(image="", text="No portrait")
            return
        try:
            from PIL import Image, ImageTk

            path = self.asset_store.resolve(
                str(metadata.get("asset_id")),
                metadata,
            )
            with Image.open(path) as opened:
                image = opened.copy()
            image.thumbnail((220, 220))
            self.portrait_photo = ImageTk.PhotoImage(image)
            self.portrait_preview.configure(
                image=self.portrait_photo,
                text="",
            )
        except Exception:
            self.portrait_photo = None
            self.portrait_preview.configure(
                image="",
                text="Portrait file unavailable",
            )

    def build_family_tree_page(
        self,
        create_person_command,
        update_person_command,
        refresh_people_command,
        navigate_command,
    ):
        page = tk.Frame(self.content, bg=SURFACE)
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)
        self.pages["family_tree"] = page

        self.family_tree = FamilyTreeView(
            page,
            change_command=self.family_tree_changed,
            people_provider=self.people_summary_provider,
            create_person_command=create_person_command,
            update_person_command=update_person_command,
            refresh_people_command=refresh_people_command,
            navigate_command=navigate_command,
            locations_provider=(
                self.event_controller.location_records
                if self.event_controller is not None
                else None
            ),
            event_provider=(
                self.event_controller.events_for_person
                if self.event_controller is not None
                else None
            ),
        )
        self.family_tree.grid(row=0, column=0, sticky="nsew")

    def build_development_page(self):
        page = DevelopmentView(
            self.content,
            self.game_database,
            self.development_changed,
            self.people_summary_provider,
            self.organization_provider,
            self.settings_provider,
            self.apply_development_mortality,
            self.organization_create_command,
            self.organization_location_provider,
            event_provider=(
                self.event_controller.events_for_person
                if self.event_controller is not None
                else None
            ),
        )
        page.grid(row=0, column=0, sticky="nsew")
        self.development = page
        self.school_field = page.school_field
        self.pages["development"] = page

    def build_jobs_page(self):
        page = NonMagicalJobsView(
            self.content,
            self.jobs_changed,
            self.people_provider,
            self.organization_provider,
            self.organization_create_command,
            self.organization_location_provider,
        )
        page.grid(row=0, column=0, sticky="nsew")
        self.jobs = page
        self.pages["jobs"] = page

    def build_books_page(self):
        page = BooksView(
            self.content,
            self.book_controller,
            self.status_command,
            self.events_changed_command,
        )
        page.grid(row=0, column=0, sticky="nsew")
        self.books = page
        self.pages["books"] = page

    def build_items_page(self):
        page = ItemsView(
            self.content,
            self.item_controller,
            self.people_summary_provider,
            self.status_command,
            event_controller=self.event_controller,
            events_changed_command=self.events_changed_command,
        )
        page.grid(row=0, column=0, sticky="nsew")
        self.items = page
        self.pages["items"] = page

    def build_ledger_page(self):
        page = LedgerView(
            self.content,
            self.ledger_changed,
        )
        page.grid(row=0, column=0, sticky="nsew")
        self.ledger = page
        self.pages["ledger"] = page

    def build_relationships_page(self):
        page = RelationshipsView(
            self.content,
            people_provider=self.people_summary_provider,
            event_controller=self.event_controller,
            navigate_command=self.navigate_command,
            event_saved_command=self.shared_event_saved,
        )
        page.grid(row=0, column=0, sticky="nsew")
        self.relationships = page
        self.pages["relationships"] = page

    def build_timeline_page(self, navigate_command):
        page = tk.Frame(self.content, bg=SURFACE)
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)
        self.pages["timeline"] = page

        self.timeline = TimelineView(
            page,
            self.timeline_changed,
            people_provider=self.people_summary_provider,
            people_by_ids_provider=self.people_summary_by_ids_provider,
            navigate_command=navigate_command,
            name_change_command=self.open_timeline_name_change,
            event_controller=self.event_controller,
            person_id_provider=self.current_person_identifier,
            linked_events_changed_command=self.shared_event_saved,
            life_start_save_command=self.save_life_start_event,
            death_event_save_command=self.save_death_timeline_event,
            death_event_delete_command=self.remove_death_timeline_event,
            name_details_command=self.open_name_details,
            selection_changed_command=self.timeline_event_selected,
        )
        self.timeline.grid(row=0, column=0, sticky="nsew")

    def add_entry_field(
        self,
        parent,
        row,
        column,
        field_name,
        label_text,
        background=SURFACE,
        horizontal_padding=0,
    ):
        variable = tk.StringVar()
        variable.trace_add("write", self.variable_changed)
        self.variables[field_name] = variable
        field = LabeledEntry(parent, label_text, variable, background=background)
        field.grid(
            row=row,
            column=column,
            sticky="ew",
            padx=horizontal_padding,
        )

    def add_boolean_fields(
        self,
        parent,
        fields,
        column_count,
        background=SURFACE,
        start_row=0,
    ):
        for index, (field_name, label_text) in enumerate(fields):
            variable = tk.BooleanVar(value=False)

            if field_name != "non_magical":
                variable.trace_add("write", self.variable_changed)

            self.variables[field_name] = variable
            checkbutton_values = {
                "text": label_text,
                "variable": variable,
                "bg": background,
                "fg": TEXT_DARK,
                "activebackground": background,
                "activeforeground": TEXT_DARK,
                "selectcolor": FIELD_BACKGROUND,
                "font": app_font(9),
                "anchor": "w",
                "borderwidth": 0,
                "highlightthickness": 0,
            }

            if field_name == "non_magical":
                checkbutton_values["command"] = self.non_magical_changed

            checkbutton = tk.Checkbutton(parent, **checkbutton_values)
            checkbutton.grid(
                row=start_row + (index // column_count),
                column=index % column_count,
                sticky="w",
                padx=(0, 4),
                pady=2,
            )
            self.boolean_widgets[field_name] = checkbutton

            if field_name in (
                "can_give_birth",
                "does_not_have_children",
            ):
                self.tooltips[field_name] = HoverTooltip(checkbutton)

    def section_is_current(self, section_name):
        return (
            self.loaded_section_record_ids.get(section_name)
            == self.current_record_id
        )

    def current_development_values(self):
        non_magical_variable = getattr(
            self,
            "variables",
            {},
        ).get("non_magical")

        if (
            non_magical_variable is not None
            and non_magical_variable.get()
        ):
            person = self.person_snapshot
            development_plan = (
                self.jobs.get_development_plan()
                if self.section_is_current("jobs")
                else non_magical_development_plan(
                    person.get("development_plan")
                )
            )
            return {
                "school": "",
                "blood_status": person.get("blood_status"),
                "developmental_environment": person.get(
                    "developmental_environment"
                ),
                "parental_values": deepcopy(
                    person.get("parental_values")
                ),
                "initial_bonuses": deepcopy(
                    person.get("initial_bonuses")
                ),
                "characteristics": deepcopy(
                    person.get("characteristics")
                ),
                "development_plan": development_plan,
            }

        if self.section_is_current("development"):
            return self.development.get_values()

        person = self.person_snapshot
        return {
            "school": str(person.get("school", "") or ""),
            "blood_status": person.get("blood_status"),
            "developmental_environment": person.get(
                "developmental_environment"
            ),
            "parental_values": deepcopy(person.get("parental_values")),
            "initial_bonuses": deepcopy(person.get("initial_bonuses")),
            "characteristics": deepcopy(person.get("characteristics")),
            "development_plan": deepcopy(person.get("development_plan")),
        }

    def current_development_plan(self):
        development_values = self.current_development_values()
        return normalize_development_plan(
            development_values.get("development_plan"),
            default_schema="Scattershot",
        )

    def current_timeline_events(self):
        if self.section_is_current("timeline"):
            return self.timeline.get_events()

        return deepcopy(
            self.person_snapshot.get("timeline_events", [])
        )

    def current_relationship_values(self):
        if self.section_is_current("family_tree"):
            return self.family_tree.get_relationship_values()

        return {
            "biological_mother_id": str(
                self.person_snapshot.get("biological_mother_id", "") or ""
            ),
            "biological_father_id": str(
                self.person_snapshot.get("biological_father_id", "") or ""
            ),
            "biological_mother_status": str(
                self.person_snapshot.get(
                    "biological_mother_status",
                    "unknown",
                )
                or "unknown"
            ),
            "biological_father_status": str(
                self.person_snapshot.get(
                    "biological_father_status",
                    "unknown",
                )
                or "unknown"
            ),
            "mate_ids": deepcopy(
                self.person_snapshot.get("mate_ids", [])
            ),
            "spouse_relationships": deepcopy(
                self.person_snapshot.get("spouse_relationships", [])
            ),
        }

    def person_for_deferred_load(self):
        person = deepcopy(self.person_snapshot)
        person.update(self.current_profile_values())
        person.update(self.current_relationship_values())
        return person

    def person_for_timeline_load(self):
        """Return only the fields used to synchronize Timeline events.

        A development plan can contain years of assignments, books, and
        calculations. Timeline only needs school attendance boundaries, so it
        must not deep-copy the complete profile merely to draw an event list.
        """
        person = self.person_snapshot

        if self.section_is_current("development"):
            development_values = self.development.get_values()
        elif (
            self.variables["non_magical"].get()
            and self.section_is_current("jobs")
        ):
            development_values = {
                "school": "",
                "development_plan": self.jobs.get_development_plan(),
            }
        else:
            development_values = {
                "school": person.get("school", ""),
                "development_plan": person.get("development_plan", {}),
            }

        development_plan = development_values.get(
            "development_plan",
            {},
        )
        development_plan = (
            development_plan
            if isinstance(development_plan, dict)
            else {}
        )
        school_years = development_plan.get("school_years", [])
        compact_school_years = [
            {
                "year": school_year.get("year"),
                "skipped": bool(school_year.get("skipped", False)),
            }
            for school_year in school_years
            if isinstance(school_year, dict)
        ]

        return {
            "record_id": self.current_record_id,
            "displayed_name": self.variables["displayed_name"].get(),
            "birth_year": self.variables["birth_year"].get(),
            "birth_month": self.variables["birth_month"].get(),
            "birth_day": self.variables["birth_day"].get(),
            "deceased": self.variables["deceased"].get(),
            "death_year": self.variables["death_year"].get(),
            "death_month": self.variables["death_month"].get(),
            "death_day": self.variables["death_day"].get(),
            "non_magical": self.variables["non_magical"].get(),
            "school": str(development_values.get("school", "") or ""),
            "development_plan": {
                "school_started": bool(
                    development_plan.get("school_started", False)
                ),
                "school_years": compact_school_years,
            },
            "name_details": deepcopy(self.name_details),
            "timeline_events": self.current_timeline_events(),
        }

    def cancel_deferred_load(self):
        if self.deferred_load_job is None:
            return

        try:
            self.after_cancel(self.deferred_load_job)
        except tk.TclError:
            pass

        self.deferred_load_job = None

    def schedule_deferred_active_page(self):
        self.cancel_deferred_load()
        self.deferred_load_job = self.after_idle(
            partial(
                self.load_deferred_active_page,
                self.load_generation,
                self.current_record_id,
            )
        )

    def load_deferred_active_page(self, load_generation, record_id):
        self.deferred_load_job = None

        if (
            load_generation != self.load_generation
            or record_id != self.current_record_id
        ):
            return

        self.show_page(self.active_page_name)

    def ensure_family_context(self, draw_graph=False):
        if not self.current_record_id:
            return

        if not self.section_is_current("family_tree"):
            self.family_tree.set_person(
                self.person_for_deferred_load(),
                redraw=draw_graph,
            )
            self.loaded_section_record_ids[
                "family_tree"
            ] = self.current_record_id
            return

        if draw_graph:
            self.family_tree.redraw_graph()

    def ensure_development_loaded(self):
        if (
            not getattr(self, "current_record_id", None)
            or self.variables["non_magical"].get()
            or self.section_is_current("development")
        ):
            return

        self.development.set_person(self.person_for_deferred_load())
        self.loaded_section_record_ids[
            "development"
        ] = self.current_record_id

    def ensure_jobs_loaded(self):
        if (
            not getattr(self, "current_record_id", None)
            or not self.variables["non_magical"].get()
            or self.section_is_current("jobs")
        ):
            return

        self.jobs.set_person(self.person_for_deferred_load())
        self.loaded_section_record_ids["jobs"] = self.current_record_id

    def ensure_timeline_loaded(self):
        if (
            not self.current_record_id
            or self.section_is_current("timeline")
        ):
            return

        timeline_person = self.person_for_timeline_load()
        synchronized_events = synchronize_name_change_events(
            self.name_details,
            ensure_life_start_events(timeline_person),
        )
        self.linked_events_snapshot = (
            self.event_controller.events_for_person(
                self.current_record_id
            )
            if self.event_controller is not None
            else []
        )
        shared_death_exists = any(
            self.current_record_id in death_event_person_ids(event)
            for event in self.linked_events_snapshot
        )
        self.timeline.set_linked_events(
            self.linked_events_snapshot,
            refresh=False,
        )
        self.timeline.selected_event_id = (
            self.timeline_selection_by_person_id.get(
                self.current_record_id
            )
        )
        self.timeline.set_events(
            synchronize_profile_timeline_events(
                timeline_person,
                synchronized_events,
                create_death_event=not shared_death_exists,
                organizations=(
                    self.event_controller.organization_records()
                    if self.event_controller is not None
                    else []
                ),
            ),
            refresh=False,
        )
        self.timeline.filter_events()
        self.loaded_section_record_ids["timeline"] = self.current_record_id

    def show_page(self, page_name, defer_loading=False):
        if self.variables["non_magical"].get() and page_name in (
            "development",
            "books",
            "ledger",
        ):
            page_name = "jobs"

        if not self.variables["non_magical"].get() and page_name == "jobs":
            page_name = "profile"

        if page_name not in self.pages and not defer_loading:
            self.ensure_page_built(page_name)

        if page_name not in self.pages:
            return False

        if (
            self.active_page_name == "timeline"
            and page_name != "timeline"
            and not self.timeline.confirm_unsaved_event_changes()
        ):
            return False

        self.active_page_name = page_name
        self.pages[page_name].tkraise()

        for name, button in self.navigation_buttons.items():
            if name == page_name:
                button.set_colors(PRIMARY, PRIMARY_HOVER, TEXT_DARK)
            else:
                button.set_colors(BUTTON_SOFT, BUTTON_SOFT_HOVER, TEXT_DARK)

        if defer_loading:
            return True

        if page_name == "profile":
            # The top-level profile intentionally contains only the selected
            # record. Family-wide scans wait until Family Tree is requested.
            self.update_birth_date_display()
            self.update_death_overview()

        if page_name == "family_tree":
            self.ensure_family_context(draw_graph=True)

        if page_name == "timeline":
            self.ensure_timeline_loaded()

        if page_name == "relationships":
            self.relationships.set_person(self.person_snapshot)

        if page_name == "jobs":
            self.ensure_jobs_loaded()

        if page_name == "development":
            self.ensure_development_loaded()
            self.development.set_birth_date(
                self.variables["birth_year"].get(),
                self.variables["birth_month"].get(),
                self.variables["birth_day"].get(),
            )
            parental_values_initialized = self.development.activate()

            if parental_values_initialized:
                self.development_changed()

                if self.loading:
                    self.after_idle(self.change_command)

        if page_name == "items":
            self.items.set_person(self.person_for_deferred_load())

        if page_name in ("books", "ledger"):
            self.refresh_books_and_ledger()

        return True

    def confirm_unsaved_event_changes(self):
        if not hasattr(self, "timeline"):
            return True

        confirmation_command = getattr(
            self.timeline,
            "confirm_unsaved_event_changes",
            None,
        )

        if not callable(confirmation_command):
            return True

        return confirmation_command()

    def open_school_editor(self):
        non_magical_variable = getattr(
            self,
            "variables",
            {},
        ).get("non_magical")

        if (
            non_magical_variable is not None
            and non_magical_variable.get()
        ):
            return

        self.ensure_development_loaded()
        self.development.focus_school()

    def update_school_summary(self):
        if self.variables["non_magical"].get():
            self.update_school_summary_from_person(self.person_snapshot)
            return

        if not self.section_is_current("development"):
            self.update_school_summary_from_person(self.person_snapshot)
            return

        self.school_summary_value.set(
            self.development.school_display_text()
        )
        self.school_year_summary_value.set(
            self.development.school_progress_display_text()
        )
        point_count = self.event_eminence_point_count(
            self.person_snapshot
        )
        self.total_eminence_summary_value.set(
            "1 point" if point_count == 1 else f"{point_count} points"
        )

    def event_eminence_point_count(self, person):
        person_values = person if isinstance(person, dict) else {}

        if bool(person_values.get("non_magical")):
            return 0

        event_controller = getattr(self, "event_controller", None)
        point_counter = getattr(
            event_controller,
            "eminence_points_for_person",
            None,
        )

        if not callable(point_counter):
            return 0

        person_id = str(
            person_values.get("record_id", "")
            or getattr(self, "current_record_id", "")
            or ""
        ).strip()
        return int(point_counter(person_id)) if person_id else 0

    def update_school_summary_from_person(self, person):
        person_values = person if isinstance(person, dict) else {}

        if bool(person_values.get("non_magical")) or (
            hasattr(self, "variables")
            and "non_magical" in self.variables
            and self.variables["non_magical"].get()
        ):
            self.school_summary_value.set("none")
            self.school_year_summary_value.set(
                "Not applicable · non-magical"
            )
            self.total_eminence_summary_value.set("Not eligible")
            return

        plan = (
            person_values.get("development_plan")
            if isinstance(person_values.get("development_plan"), dict)
            else {}
        )
        school_name = str(person_values.get("school", "") or "").strip()
        self.school_summary_value.set(school_name or "none")
        self.school_year_summary_value.set(
            school_progress_text(
                plan.get("school_started", False),
                plan.get("academic_years_advanced", 0),
            )
        )
        point_count = self.event_eminence_point_count(person_values)

        self.total_eminence_summary_value.set(
            "1 point" if point_count == 1 else f"{point_count} points"
        )

    def refresh_books_and_ledger(self):
        if not hasattr(self, "books") and not hasattr(self, "ledger"):
            return

        if self.variables["non_magical"].get():
            return

        plan = self.current_development_plan()
        development_values = self.current_development_values()
        school_attended = bool(
            str(development_values.get("school", "") or "").strip()
        )
        academic_start_year = calculate_development_start_year(
            self.variables["birth_year"].get(),
            self.variables["birth_month"].get(),
            self.variables["birth_day"].get(),
            school_attended=school_attended,
        )
        if hasattr(self, "books"):
            self.books.set_person(self.current_record_id)
            self.books.set_development_records(
                plan.get("school_years", []),
                plan.get("adult_years", []),
                academic_start_year,
                school_attended=school_attended,
            )
        if hasattr(self, "ledger"):
            self.ledger.set_context(
                plan.get("ledger_entries", []),
                development_year_pages(
                    plan,
                    academic_start_year,
                    self.variables["birth_year"].get(),
                    self.variables["birth_month"].get(),
                    self.variables["birth_day"].get(),
                    school_attended=school_attended,
                ),
                academic_start_year,
                self.current_record_id,
            )

    def open_name_details(self):
        NameDetailsDialog(
            self,
            self.name_details,
            self.save_name_details,
            self.variables["displayed_name"].get(),
            format_date_parts(
                self.variables["birth_year"].get(),
                self.variables["birth_month"].get(),
                self.variables["birth_day"].get(),
                unknown="",
            ),
        )

    def save_name_details(self, name_details):
        normalized_details = normalize_name_details(name_details)
        birth_date = format_date_parts(
            self.variables["birth_year"].get(),
            self.variables["birth_month"].get(),
            self.variables["birth_day"].get(),
            unknown="",
        )

        for entry in normalized_details["entries"]:
            name_type = " ".join(
                entry["name_type"].strip().casefold().split()
            )

            if name_type in ("birth name", "birthname"):
                entry["date"] = birth_date

        normalized_details = normalize_name_details(normalized_details)
        # Applying a name must not force the Timeline section to hydrate every
        # linked event.  The selected person's compact snapshot already owns
        # the embedded profile events needed for name synchronization.
        timeline_person = self.person_for_timeline_load()
        timeline_person["name_details"] = deepcopy(normalized_details)
        existing_events = self.current_timeline_events()
        timeline_person["timeline_events"] = existing_events
        synchronized_events = synchronize_name_change_events(
            normalized_details,
            ensure_life_start_events(timeline_person),
        )

        if (
            normalized_details == self.name_details
            and synchronized_events == existing_events
        ):
            return True

        self.name_details = deepcopy(normalized_details)
        if self.section_is_current("timeline"):
            self.timeline.set_events(synchronized_events)
        self.person_snapshot["name_details"] = deepcopy(
            self.name_details
        )
        self.person_snapshot["timeline_events"] = deepcopy(
            synchronized_events
        )

        if self.section_is_current("family_tree"):
            self.family_tree.update_current_person(self.current_profile_values())

        if not self.loading:
            self.change_command()
        return True

    def save_life_start_event(self, values, original_event):
        event_type = str(
            original_event.get("event_type", "") or ""
        ).strip()

        if event_type != "born":
            raise ValueError("Only the Birth event can be edited here.")

        location_ids = [
            str(location_id or "").strip()
            for location_id in values.get("location_ids", [])
            if str(location_id or "").strip()
        ]

        if len(location_ids) != 1:
            raise ValueError("Select one birth location.")

        location_id = location_ids[0]
        location_record = next(
            (
                location
                for location in self.event_controller.location_records()
                if str(location.get("record_id", "") or "").strip()
                == location_id
            ),
            None,
        )

        if location_record is None:
            raise ValueError("The selected birth location no longer exists.")

        location_name = str(
            location_record.get("name", "") or ""
        ).strip()

        if not location_name:
            raise ValueError("The selected birth location needs a name.")

        events = deepcopy(self.timeline.get_events())
        born_event = next(
            (
                event
                for event in events
                if event.get("event_type") == "born"
            ),
            None,
        )

        if born_event is None:
            raise ValueError("The required Birth event could not be found.")

        born_event["detail"] = location_name
        born_event["location_ids"] = [location_id]
        born_event["locked_location_ids"] = []
        born_event["birth_location_source"] = "manual"
        born_event["time"] = str(values.get("time", "") or "").strip()
        birth_year, birth_month, birth_day = split_partial_date(
            values.get("date", ""),
            "Birth date",
        )
        previous_loading = self.loading
        self.loading = True
        self.variables["birth_year"].set(
            str(int(birth_year)) if birth_year else ""
        )
        self.variables["birth_month"].set(
            str(int(birth_month)) if birth_month else ""
        )
        self.variables["birth_day"].set(
            str(int(birth_day)) if birth_day else ""
        )
        self.loading = previous_loading
        if hasattr(self, "person_snapshot"):
            self.person_snapshot.update(
                {
                    "birth_year": self.variables["birth_year"].get(),
                    "birth_month": self.variables["birth_month"].get(),
                    "birth_day": self.variables["birth_day"].get(),
                }
            )
        PersonForm.update_birth_date_display(self)
        PersonForm.update_death_overview(self)
        born_event["note"] = str(
            values.get("description", "") or ""
        ).strip()
        updated_name_details = deepcopy(self.name_details)

        for entry in updated_name_details.get("entries", []):
            name_type = " ".join(
                str(entry.get("name_type", "") or "")
                .strip()
                .casefold()
                .split()
            )

            if name_type in ("birth name", "birthname"):
                entry["date"] = (
                    ""
                    if not birth_year
                    else "-".join(
                        date_part
                        for date_part in (
                            birth_year,
                            birth_month,
                            birth_day,
                        )
                        if date_part
                    )
                )

        self.name_details = normalize_name_details(updated_name_details)

        timeline_person = self.current_profile_values()
        timeline_person["name_details"] = deepcopy(self.name_details)
        timeline_person["timeline_events"] = events
        synchronized_events = ensure_life_start_events(
            timeline_person,
            starting_location=location_name,
            starting_location_id=location_id,
            born_note=str(born_event.get("note", "") or "").strip(),
            long_distance_parent_ids=born_long_distance_parent_ids(
                events
            ),
        )
        return synchronize_name_change_events(
            self.name_details,
            synchronized_events,
        )

    def save_death_timeline_event(self, values, original_event):
        death_year, death_month, death_day = split_partial_date(
            values.get("date", ""),
            "Death date",
        )

        if not death_year:
            raise ValueError("A Death event requires a year.")

        location_ids = [
            str(location_id or "").strip()
            for location_id in values.get("location_ids", [])
            if str(location_id or "").strip()
        ]

        if len(location_ids) > 1:
            raise ValueError(
                "A Death event can have no more than one location."
            )

        previous_loading = self.loading
        self.loading = True
        self.variables["deceased"].set(True)
        self.variables["death_year"].set(death_year)
        self.variables["death_month"].set(death_month)
        self.variables["death_day"].set(death_day)
        self.loading = previous_loading
        mortality_values = {
            "deceased": True,
            "death_year": death_year,
            "death_month": death_month,
            "death_day": death_day,
        }
        self.person_snapshot.update(mortality_values)
        self.update_death_date_visibility()
        self.update_death_overview()

        updated_event = deepcopy(original_event)
        updated_event.update(
            {
                "event_type": "died",
                "detail": str(values.get("title", "") or "").strip(),
                "date": format_date_parts(
                    death_year,
                    death_month,
                    death_day,
                    unknown="",
                ),
                "time": str(values.get("time", "") or "").strip(),
                "note": str(
                    values.get("description", "") or ""
                ).strip(),
                "person_ids": [self.current_person_identifier()],
                "location_ids": location_ids,
                "locked_location_ids": [],
                "related_person_id": "",
                "automatic_source": "death_date",
            }
        )
        normalized_event = normalize_timeline_event(updated_event)
        event_id = normalized_event["event_id"]
        events = [
            normalized_event
            if event.get("event_id") == event_id
            else deepcopy(event)
            for event in self.timeline.get_events()
        ]

        if not any(
            event.get("event_id") == event_id
            for event in events
        ):
            events.append(normalized_event)

        self.person_snapshot["timeline_events"] = deepcopy(events)
        return normalize_timeline_events(events)

    def remove_death_timeline_event(self, death_event):
        event_id = str(death_event.get("event_id", "") or "").strip()
        previous_loading = self.loading
        self.loading = True
        self.variables["deceased"].set(False)
        self.variables["death_year"].set("")
        self.variables["death_month"].set("")
        self.variables["death_day"].set("")
        self.loading = previous_loading
        self.person_snapshot.update(
            {
                "deceased": False,
                "death_year": "",
                "death_month": "",
                "death_day": "",
            }
        )
        events = [
            deepcopy(event)
            for event in self.timeline.get_events()
            if event.get("event_id") != event_id
        ]
        self.person_snapshot["timeline_events"] = deepcopy(events)
        self.update_death_date_visibility()
        self.update_death_overview()
        return normalize_timeline_events(events)

    def open_timeline_name_change(self, event=None):
        event_values = event if isinstance(event, dict) else {}
        entry = name_entry_for_timeline_event(self.name_details, event_values)

        if entry is None:
            entry = new_name_entry()
            entry.update(
                {
                    "name_type": (
                        "birth name"
                        if event_values.get("event_type") == "birth_name"
                        else ""
                    ),
                    "name_entry": str(event_values.get("detail", "") or ""),
                    "date": str(event_values.get("date", "") or ""),
                    "note": str(event_values.get("note", "") or ""),
                }
            )

        source_event_id = str(event_values.get("event_id", "") or "")
        NameEntryDialog(
            self,
            entry,
            partial(self.save_timeline_name_change, source_event_id),
            "Edit Name" if event_values else "Add Name",
            format_date_parts(
                self.variables["birth_year"].get(),
                self.variables["birth_month"].get(),
                self.variables["birth_day"].get(),
                unknown="",
            ),
        )

    def save_timeline_name_change(self, source_event_id, entry):
        normalized_entry = normalize_name_entry(entry)
        name_type = " ".join(
            normalized_entry["name_type"].strip().casefold().split()
        )

        if name_type in ("birth name", "birthname"):
            normalized_entry["date"] = format_date_parts(
                self.variables["birth_year"].get(),
                self.variables["birth_month"].get(),
                self.variables["birth_day"].get(),
                unknown="",
            )

        entries = deepcopy(self.name_details.get("entries", []))
        replacement_index = None

        for index, existing_entry in enumerate(entries):
            if existing_entry.get("entry_id") == normalized_entry["entry_id"]:
                replacement_index = index
                break

        if replacement_index is None:
            entries.append(normalized_entry)
        else:
            entries[replacement_index] = normalized_entry

        events = [
            event
            for event in self.timeline.get_events()
            if not source_event_id or event.get("event_id") != source_event_id
        ]
        self.name_details = normalize_name_details({"entries": entries})
        timeline_person = self.current_profile_values()
        timeline_person["name_details"] = deepcopy(self.name_details)
        timeline_person["timeline_events"] = events
        synchronized_events = synchronize_name_change_events(
            self.name_details,
            ensure_life_start_events(timeline_person),
        )
        self.timeline.selected_event_id = (
            "life-start:birth-name"
            if normalized_entry["name_type"].strip().casefold() == "birth name"
            else f"name-change:{normalized_entry['entry_id']}"
        )
        self.timeline.set_events(synchronized_events)
        self.person_snapshot["name_details"] = deepcopy(
            self.name_details
        )
        self.person_snapshot["timeline_events"] = deepcopy(
            synchronized_events
        )

        if self.section_is_current("family_tree"):
            self.family_tree.update_current_person(self.current_profile_values())

        if not self.loading:
            self.change_command()

    def set_person(self, person):
        person_values = dict(person) if isinstance(person, dict) else {}

        if self.current_record_id and hasattr(self, "timeline"):
            selected_timeline_event_id = str(
                self.timeline.selected_event_id or ""
            ).strip()

            if (
                selected_timeline_event_id
                and hasattr(self, "timeline_selection_by_person_id")
            ):
                self.timeline_selection_by_person_id[
                    self.current_record_id
                ] = selected_timeline_event_id

        self.cancel_deferred_load()
        self.load_generation += 1
        self.loading = True
        self.current_record_id = person_values.get("record_id")
        if hasattr(self, "timeline"):
            self.timeline.reset_for_person_change()
        self.person_snapshot = person_values
        self.board_state = normalize_person_board(
            person_values.get("board")
        )
        self.loaded_section_record_ids = {}
        self.linked_events_snapshot = []
        displayed_name = person_values.get("displayed_name", "")
        self.current_name_value.set(displayed_name or "Unnamed magician")

        for field_name, variable in self.variables.items():
            value = person_values.get(field_name)

            if isinstance(variable, tk.BooleanVar):
                variable.set(bool(value))
            else:
                variable.set("" if value is None else str(value))

        self.refresh_mage_groups(person_values.get("mage_group_id"))
        if hasattr(self, "navigation_buttons"):
            self.update_person_navigation()
        self.update_school_summary_from_person(person_values)
        self.update_birth_date_display()
        self.update_death_date_visibility()
        self.update_death_overview()

        for field_name, text_widget in self.text_widgets.items():
            text_widget.delete("1.0", "end")
            text_widget.insert(
                "1.0",
                str(person_values.get(field_name, "") or ""),
            )
            text_widget.edit_modified(False)

        if hasattr(self, "tags_editor"):
            self.tags_editor.set_tags(person_values.get("tags", []))
        if hasattr(self, "portrait_preview"):
            self.render_portrait()

        name_details = person_values.get("name_details", {})
        self.name_details = (
            deepcopy(name_details)
            if isinstance(name_details, dict)
            else {"entries": []}
        )
        self.famous_connections.set_connections([])
        can_give_birth_control = self.boolean_widgets.get(
            "can_give_birth"
        )
        can_give_birth_tooltip = self.tooltips.get("can_give_birth")
        childlessness_control = self.boolean_widgets.get(
            "does_not_have_children"
        )
        childlessness_tooltip = self.tooltips.get(
            "does_not_have_children"
        )

        if can_give_birth_control is not None:
            can_give_birth_control.configure(state="disabled")

        if can_give_birth_tooltip is not None:
            can_give_birth_tooltip.set_text("Loading family links.")

        if childlessness_control is not None:
            childlessness_control.configure(state="disabled")

        if childlessness_tooltip is not None:
            childlessness_tooltip.set_text("Loading family links.")

        self.show_page(self.active_page_name, defer_loading=True)
        self.loading = False
        self.update_idletasks()
        self.schedule_deferred_active_page()

    def current_profile_values(self):
        development_values = self.current_development_values()
        return {
            "record_id": self.current_record_id,
            "displayed_name": self.variables["displayed_name"].get(),
            "birth_year": self.variables["birth_year"].get(),
            "birth_month": self.variables["birth_month"].get(),
            "birth_day": self.variables["birth_day"].get(),
            "deceased": self.variables["deceased"].get(),
            "death_year": self.variables["death_year"].get(),
            "death_month": self.variables["death_month"].get(),
            "death_day": self.variables["death_day"].get(),
            "non_magical": self.variables["non_magical"].get(),
            "can_give_birth": self.variables["can_give_birth"].get(),
            "does_not_have_children": self.variables[
                "does_not_have_children"
            ].get(),
            "famous_person": self.variables["famous_person"].get(),
            "animagus": self.variables["animagus"].get(),
            "parseltongue": self.variables["parseltongue"].get(),
            "unfinished": self.variables["unfinished"].get(),
            "mage_group_id": self.selected_mage_group_id(),
            "school": development_values["school"],
            "blood_status": development_values["blood_status"],
            "developmental_environment": development_values[
                "developmental_environment"
            ],
            "parental_values": deepcopy(
                development_values["parental_values"]
            ),
            "initial_bonuses": deepcopy(
                development_values["initial_bonuses"]
            ),
            "characteristics": deepcopy(
                development_values["characteristics"]
            ),
            "development_plan": development_values[
                "development_plan"
            ],
            "timeline_events": self.current_timeline_events(),
            "name_details": deepcopy(self.name_details),
            "tags": self.tags_editor.get_tags(),
            "board": deepcopy(self.board_state),
        }

    def get_values(self):
        values = {}

        for field_name, variable in self.variables.items():
            values[field_name] = variable.get()

        for field_name, text_widget in self.text_widgets.items():
            values[field_name] = text_widget.get("1.0", "end-1c")

        values.update(self.current_development_values())
        values["mage_group_id"] = self.selected_mage_group_id()
        values["name_details"] = deepcopy(self.name_details)
        values["timeline_events"] = self.current_timeline_events()
        values["tags"] = self.tags_editor.get_tags()
        values["board"] = deepcopy(self.board_state)
        values.update(self.current_relationship_values())

        return values

    def specialty_school_is_blank(self):
        if self.variables["non_magical"].get():
            return False

        if not self.section_is_current("development"):
            return False

        return self.school_field.specialty_is_blank()

    def initial_values_complete(self):
        if self.variables["non_magical"].get():
            return True

        if self.section_is_current("development"):
            return self.development.initial_values_complete()

        return initial_values_are_complete(self.person_snapshot)

    def family_tree_changed(self):
        relationship_values = self.family_tree.get_relationship_values()
        self.person_snapshot.update(deepcopy(relationship_values))

        if self.section_is_current("development"):
            self.development.set_parentage(relationship_values)

        self.update_can_give_birth_control()
        self.update_does_not_have_children_control()
        self.update_famous_connections()

        if self.active_page_name == "relationships":
            self.relationships.set_person(self.person_snapshot)

        if not self.loading:
            self.change_command()
            # Family links are part of the ordinary profile edit session.
            # A full canonical save here used to run immediately after the
            # picker closed, freezing the UI for large worlds.  Navigation,
            # explicit Save, and application close already commit dirty forms.

    def timeline_changed(self):
        if not self.loading:
            self.timeline_event_selected(self.timeline.selected_event_id)
            self.change_command()
            self.schedule_person_autosave()

    def timeline_event_selected(self, event_id):
        selected_event_id = str(event_id or "").strip()

        if not self.current_record_id or not selected_event_id:
            return

        self.timeline_selection_by_person_id[
            self.current_record_id
        ] = selected_event_id

        if self.game_database is None or not isinstance(
            getattr(self.game_database, "data", None),
            dict,
        ):
            return

        settings = self.game_database.data.setdefault(
            "_application_settings",
            {},
        )
        settings[LAST_TIMELINE_PERSON_STORAGE_KEY] = (
            self.current_record_id
        )
        settings[LAST_TIMELINE_EVENT_STORAGE_KEY] = selected_event_id
        self.game_database.dirty = True

    def tags_changed(self):
        if not self.loading:
            self.change_command()

    def schedule_person_autosave(self):
        if self.save_person_command is None or not self.current_record_id:
            return

        if self.autosave_job is not None:
            try:
                self.after_cancel(self.autosave_job)
            except tk.TclError:
                pass

        self.autosave_job = self.after_idle(self.run_person_autosave)

    def run_person_autosave(self):
        self.autosave_job = None

        if self.loading or self.save_person_command is None:
            return False

        return bool(self.save_person_command())

    def development_changed(self):
        development_values = self.current_development_values()
        self.person_snapshot.update(deepcopy(development_values))
        self.update_school_summary()
        self.refresh_books_and_ledger()
        self.loaded_section_record_ids.pop("family_tree", None)

        if not self.loading:
            self.change_command()

    def jobs_changed(self):
        if not self.variables["non_magical"].get():
            return

        self.person_snapshot["school"] = ""
        self.person_snapshot["development_plan"] = (
            self.jobs.get_development_plan()
        )

        if not self.loading:
            self.change_command()

    def apply_development_mortality(self, mortality_values):
        if self.variables["non_magical"].get():
            return

        if not isinstance(mortality_values, dict):
            return

        previous_loading = self.loading
        self.loading = True
        self.variables["deceased"].set(
            bool(mortality_values.get("deceased"))
        )
        self.variables["death_year"].set(
            str(mortality_values.get("death_year", "") or "")
        )
        self.variables["death_month"].set(
            str(mortality_values.get("death_month", "") or "")
        )
        self.variables["death_day"].set(
            str(mortality_values.get("death_day", "") or "")
        )
        self.loading = previous_loading
        self.update_death_date_visibility()
        self.update_death_overview()

    def ledger_changed(self, entries):
        if self.variables["non_magical"].get():
            return

        if self.section_is_current("development"):
            self.development.set_ledger_entries(entries)
            return

        plan = self.current_development_plan()
        plan["ledger_entries"] = deepcopy(entries)
        self.person_snapshot["development_plan"] = plan

        if not self.loading:
            self.change_command()

    def available_mage_groups(self):
        if self.mage_group_provider is None:
            return default_mage_groups()

        return normalize_mage_groups(self.mage_group_provider())

    def refresh_mage_groups(self, selected_group_id=None):
        previous_loading = self.loading
        self.loading = True
        groups = self.available_mage_groups()
        normalized_group_id = normalize_mage_group_id(
            selected_group_id,
            groups,
        )
        selected_group = next(
            (
                group
                for group in groups
                if group["group_id"] == normalized_group_id
            ),
            groups[0],
        )
        self.mage_groups = groups
        self.mage_group_select.set_values(
            [group["name"] for group in groups]
        )
        self.mage_group_value.set(selected_group["name"])
        self.loading = previous_loading

    def selected_mage_group_id(self):
        selected_name = self.mage_group_value.get()

        for group in self.mage_groups:
            if group["name"] == selected_name:
                return group["group_id"]

        return self.mage_groups[0]["group_id"]

    def mage_group_changed(self, *arguments):
        if not self.loading:
            self.change_command()

    def refresh_linked_events(self, refresh_timeline=True):
        if not self.current_record_id:
            return

        self.linked_events_snapshot = (
            self.event_controller.events_for_person(
                self.current_record_id
            )
            if self.event_controller is not None
            else []
        )

        if refresh_timeline and self.section_is_current("timeline"):
            self.timeline.set_linked_events(
                self.linked_events_snapshot
            )

        current_person = (
            self.person_record_provider(self.current_record_id)
            if callable(self.person_record_provider)
            else next(
                (
                    person
                    for person in self.people_provider()
                    if str(person.get("record_id", "") or "")
                    == str(self.current_record_id or "")
                ),
                None,
            )
        )

        if current_person is not None:
            event_owned_fields = (
                "birth_year",
                "birth_month",
                "birth_day",
                "deceased",
                "death_year",
                "death_month",
                "death_day",
                "biological_mother_id",
                "biological_father_id",
                "biological_mother_status",
                "biological_father_status",
                "mate_ids",
                "spouse_relationships",
            )

            for field_name in event_owned_fields:
                self.person_snapshot[field_name] = deepcopy(
                    current_person.get(field_name)
                )

            previous_loading = self.loading
            self.loading = True

            for field_name in (
                "birth_year",
                "birth_month",
                "birth_day",
                "death_year",
                "death_month",
                "death_day",
            ):
                self.variables[field_name].set(
                    ""
                    if current_person.get(field_name) in (None, "")
                    else str(current_person.get(field_name))
                )

            self.variables["deceased"].set(
                bool(current_person.get("deceased"))
            )
            self.loading = previous_loading
            self.update_birth_date_display()
            self.update_death_date_visibility()
            self.update_death_overview()

            if self.section_is_current("family_tree"):
                family_person = deepcopy(current_person)
                family_person.update(self.current_profile_values())
                self.family_tree.set_person(
                    family_person,
                    redraw=self.active_page_name == "family_tree",
                )

            if self.active_page_name == "relationships":
                self.relationships.set_person(self.person_snapshot)

        if self.variables["non_magical"].get():
            self.person_snapshot["development_plan"] = (
                non_magical_development_plan(
                    self.person_snapshot.get("development_plan")
                )
            )
            self.update_school_summary_from_person(
                self.person_snapshot
            )
            return

        if self.section_is_current("development") and (
            self.development.reconcile_linked_event_eminence(
                self.linked_events_snapshot
            )
        ):
            self.update_school_summary()
            self.refresh_books_and_ledger()
            return

        if current_person is not None:
            self.person_snapshot["development_plan"] = deepcopy(
                current_person.get("development_plan")
            )
            self.update_school_summary_from_person(self.person_snapshot)

    def current_person_identifier(self):
        return str(self.current_record_id or "")

    def shared_event_saved(self, event):
        # TimelineView has already replaced its linked-event collection and
        # rendered the saved row before invoking this callback.  Reapplying
        # the same collection here used to clear and rebuild the entire Events
        # list a second time, which produced a very visible flash on every
        # save.  Refresh the dependent person fields without repainting the
        # open Timeline.
        self.refresh_linked_events(refresh_timeline=False)
        self.timeline_event_selected(
            event.get("record_id", "")
            if isinstance(event, dict)
            else ""
        )

        if (
            isinstance(event, dict)
            and canonical_event_type(event.get("event_type"))
            == "foster_child"
            and getattr(self, "family_tree", None) is not None
        ):
            self.family_tree.reload_people(
                redraw=self.active_page_name == "family_tree",
                refresh_provider=False,
            )

        if self.events_changed_command is not None:
            event_id = (
                str(event.get("record_id", "") or "").strip()
                if isinstance(event, dict)
                else ""
            )
            self.events_changed_command(
                "events",
                (event_id,) if event_id else (),
            )

        # Shared events are already committed by EventController, including
        # any synchronized person fields.  Marking the whole person form dirty
        # here scheduled a second canonical save, reloaded the selected person,
        # and blanked/rebuilt the Events page.  The freshly read person snapshot
        # above is sufficient and keeps the editor stable.

    def accept_saved_person(self, person):
        """Adopt a successful save without reconstructing the open section."""
        person_values = dict(person) if isinstance(person, dict) else {}
        record_id = str(person_values.get("record_id", "") or "").strip()

        if not record_id or record_id != str(self.current_record_id or ""):
            return False

        self.person_snapshot = person_values
        self.board_state = normalize_person_board(person_values.get("board"))
        name_details = person_values.get("name_details", {})
        self.name_details = (
            deepcopy(name_details)
            if isinstance(name_details, dict)
            else {"entries": []}
        )
        self.update_school_summary_from_person(person_values)
        self.update_birth_date_display()
        self.update_death_date_visibility()
        self.update_death_overview()
        return True

    def deceased_changed(self, *arguments):
        if self.loading:
            return

        self.update_death_date_visibility()
        self.update_death_overview()
        self.change_command()

    def update_death_date_visibility(self):
        deceased = bool(self.variables["deceased"].get())

        if hasattr(self, "death_status_value"):
            self.death_status_value.set("Dead" if deceased else "Alive")

        if not hasattr(self, "death_date_display_value"):
            return

        death_date = (
            format_date_parts(
                self.variables["death_year"].get(),
                self.variables["death_month"].get(),
                self.variables["death_day"].get(),
                unknown="",
            )
            if deceased
            else ""
        )
        self.death_date_display_value.set(
            format_historical_display_date(
                death_date,
                unknown="Not recorded",
            )
        )
        PersonForm.update_life_dates_display(self)

    def update_birth_date_display(self):
        if not hasattr(self, "birth_date_display_value"):
            return

        birth_date = format_date_parts(
            self.variables["birth_year"].get(),
            self.variables["birth_month"].get(),
            self.variables["birth_day"].get(),
            unknown="",
        )
        self.birth_date_display_value.set(
            format_historical_display_date(
                birth_date,
                unknown="Not recorded",
            )
        )
        PersonForm.update_life_dates_display(self)

    def update_life_dates_display(self):
        if not hasattr(self, "life_dates_display_value"):
            return

        birth_date = format_date_parts(
            self.variables["birth_year"].get(),
            self.variables["birth_month"].get(),
            self.variables["birth_day"].get(),
            unknown="",
        )
        death_date = format_date_parts(
            self.variables["death_year"].get(),
            self.variables["death_month"].get(),
            self.variables["death_day"].get(),
            unknown="",
        )
        birth_display = format_historical_display_date(
            birth_date,
            unknown="Not recorded",
        )
        age_at_death, _exact_age = person_age_at_death(
            {
                "birth_year": self.variables["birth_year"].get(),
                "birth_month": self.variables["birth_month"].get(),
                "birth_day": self.variables["birth_day"].get(),
                "death_year": self.variables["death_year"].get(),
                "death_month": self.variables["death_month"].get(),
                "death_day": self.variables["death_day"].get(),
            }
        )
        age_display = (
            f" (Age {age_at_death})"
            if death_date and age_at_death is not None
            else ""
        )
        life_dates_text = f"Born: {birth_display}"

        if death_date:
            life_dates_text += (
                "\nDied: "
                f"{format_historical_display_date(death_date)}"
                f"{age_display}"
            )

        self.life_dates_display_value.set(life_dates_text)

    def update_death_overview(self):
        if not hasattr(self, "death_overview_value"):
            return

        if not self.variables["deceased"].get():
            self.death_overview_value.set("")
            return

        age_text = person_death_age_text(
            {
                "birth_year": self.variables["birth_year"].get(),
                "birth_month": self.variables["birth_month"].get(),
                "birth_day": self.variables["birth_day"].get(),
                "death_year": self.variables["death_year"].get(),
                "death_month": self.variables["death_month"].get(),
                "death_day": self.variables["death_day"].get(),
            }
        )
        self.death_overview_value.set(age_text)

    def update_famous_connections(self):
        if (
            not self.current_record_id
            or not self.section_is_current("family_tree")
        ):
            self.famous_connections.set_connections([])
            return

        current_person = deepcopy(self.family_tree.current_person)
        current_person.update(self.current_profile_values())
        current_person.update(self.family_tree.get_relationship_values())
        connection_map = FamousConnectionMap(
            self.people_summary_provider(),
            current_person,
            (
                self.event_controller.events_for_person(
                    self.current_record_id
                )
                if self.event_controller is not None
                else []
            ),
        )
        self.famous_connections.set_connections(
            connection_map.labels_for(self.current_record_id)
        )

    def update_can_give_birth_control(self):
        checkbutton = self.boolean_widgets.get("can_give_birth")
        tooltip = self.tooltips.get("can_give_birth")

        if checkbutton is None or tooltip is None:
            return

        record_id = str(self.current_record_id or "")

        if not record_id:
            checkbutton.configure(state="disabled")
            tooltip.set_text("Select a magician before changing this setting.")
            return

        if not self.section_is_current("family_tree"):
            checkbutton.configure(state="disabled")
            tooltip.set_text("Loading family links.")
            return

        relationship_map = self.family_tree.relationship_map
        birthing_children = relationship_map.children_for_parent_role(
            record_id,
            "mother",
        )
        non_birthing_children = relationship_map.children_for_parent_role(
            record_id,
            "father",
        )

        if birthing_children:
            child_names = [
                str(child.get("displayed_name", "Unnamed"))
                for child in birthing_children
            ]
            visible_names = ", ".join(child_names[:3])

            if len(child_names) > 3:
                visible_names += f", and {len(child_names) - 3} more"

            checkbutton.configure(state="disabled")
            tooltip.set_text(
                "Can give birth is locked because this person is the birthing "
                f"parent of {visible_names}. Remove those family links before "
                "changing it."
            )
            return

        if non_birthing_children:
            child_names = [
                str(child.get("displayed_name", "Unnamed"))
                for child in non_birthing_children
            ]
            visible_names = ", ".join(child_names[:3])

            if len(child_names) > 3:
                visible_names += f", and {len(child_names) - 3} more"

            checkbutton.configure(state="disabled")
            tooltip.set_text(
                "Can give birth is locked because this person is the non-birthing "
                f"parent of {visible_names}. Remove those family links before "
                "changing it."
            )
            return

        mate_ids = relationship_map.mates_of(record_id)

        if mate_ids:
            mate_names = []

            for mate_id in mate_ids:
                mate = relationship_map.person(mate_id)
                mate_names.append(
                    str(mate.get("displayed_name", "Unnamed"))
                    if mate
                    else "Unnamed"
                )

            visible_names = ", ".join(mate_names[:3])

            if len(mate_names) > 3:
                visible_names += f", and {len(mate_names) - 3} more"

            checkbutton.configure(state="disabled")
            tooltip.set_text(
                "Can give birth is locked because this person is linked as a mate "
                f"to {visible_names}. Remove those mate links before changing it."
            )
            return

        checkbutton.configure(state="normal")
        tooltip.set_text(
            "This setting becomes locked once the person is linked as a mate or "
            "as a birthing or non-birthing parent."
        )

    def update_does_not_have_children_control(self):
        checkbutton = self.boolean_widgets.get(
            "does_not_have_children"
        )
        tooltip = self.tooltips.get("does_not_have_children")

        if checkbutton is None or tooltip is None:
            return

        record_id = str(self.current_record_id or "")

        if not record_id:
            checkbutton.configure(state="disabled")
            tooltip.set_text(
                "Select a person before changing this setting."
            )
            return

        if not self.section_is_current("family_tree"):
            checkbutton.configure(state="disabled")
            tooltip.set_text("Loading family links.")
            return

        relationship_map = self.family_tree.relationship_map
        child_ids = relationship_map.children_of(record_id)

        if child_ids:
            child_names = []

            for child_id in child_ids:
                child = relationship_map.person(child_id)
                child_names.append(
                    str(child.get("displayed_name", "Unnamed"))
                    if child
                    else "Unnamed"
                )

            visible_names = ", ".join(child_names[:3])

            if len(child_names) > 3:
                visible_names += f", and {len(child_names) - 3} more"

            checkbutton.configure(state="disabled")
            tooltip.set_text(
                "Does not have children cannot be checked because this "
                f"person is already a parent of {visible_names}. Remove "
                "those parent links first."
            )
            return

        checkbutton.configure(state="normal")
        tooltip.set_text(
            "When checked, this person is excluded from every parent "
            "selection and cannot add a child."
        )

    def update_person_navigation(self):
        if not hasattr(self, "navigation_buttons"):
            return

        is_non_magical = bool(
            self.variables.get("non_magical")
            and self.variables["non_magical"].get()
        )
        restricted_pages = ("development", "books", "ledger")
        variable_pages = (
            "jobs",
            "development",
            "items",
            "books",
            "ledger",
        )

        for page_name in variable_pages:
            if page_name in self.navigation_buttons:
                self.navigation_buttons[page_name].pack_forget()

        if is_non_magical:
            self.navigation_buttons["jobs"].pack(
                side="left",
                padx=(0, 6),
            )
            if "items" in self.navigation_buttons:
                self.navigation_buttons["items"].pack(
                    side="left",
                    padx=(0, 6),
                )

            if self.active_page_name in restricted_pages:
                self.active_page_name = "profile"
        else:
            for page_name in (
                "development",
                "items",
                "books",
                "ledger",
            ):
                if page_name in self.navigation_buttons:
                    self.navigation_buttons[page_name].pack(
                        side="left",
                        padx=(0, 6),
                    )

            if self.active_page_name == "jobs":
                self.active_page_name = "profile"

        if hasattr(self, "change_school_button"):
            self.change_school_button.set_enabled(not is_non_magical)

    def non_magical_changed(self):
        if self.loading:
            return

        is_non_magical = self.variables["non_magical"].get()

        if is_non_magical:
            confirmed = messagebox.askyesno(
                "Mark as non-magical?",
                (
                    "Non-magical people do not have Development years, "
                    "cannot earn Eminence, do not read wizarding books, and "
                    "do not have a Ledger.\n\n"
                    "All existing Development-year, Eminence, wizarding reading, "
                    "and Ledger data will be permanently erased. Existing "
                    "jobs, events, relationships, and children will remain.\n\n"
                    "Continue?"
                ),
                parent=self,
                icon="warning",
                default="no",
            )

            if not confirmed:
                self.loading = True
                self.variables["non_magical"].set(False)
                self.loading = False
                self.update_person_navigation()
                return

            development_values = (
                self.development.get_values()
                if self.section_is_current("development")
                else {
                    "blood_status": self.person_snapshot.get(
                        "blood_status"
                    ),
                    "developmental_environment": self.person_snapshot.get(
                        "developmental_environment"
                    ),
                    "parental_values": deepcopy(
                        self.person_snapshot.get("parental_values")
                    ),
                    "initial_bonuses": deepcopy(
                        self.person_snapshot.get("initial_bonuses")
                    ),
                    "characteristics": deepcopy(
                        self.person_snapshot.get("characteristics")
                    ),
                    "development_plan": deepcopy(
                        self.person_snapshot.get("development_plan")
                    ),
                }
            )
            self.person_snapshot.update(
                {
                    "non_magical": True,
                    "school": "",
                    "blood_status": development_values.get(
                        "blood_status"
                    ),
                    "developmental_environment": development_values.get(
                        "developmental_environment"
                    ),
                    "parental_values": deepcopy(
                        development_values.get("parental_values")
                    ),
                    "initial_bonuses": deepcopy(
                        development_values.get("initial_bonuses")
                    ),
                    "characteristics": deepcopy(
                        development_values.get("characteristics")
                    ),
                    "development_plan": non_magical_development_plan(
                        development_values.get("development_plan")
                    ),
                }
            )
            self.loaded_section_record_ids.pop("development", None)
            self.loaded_section_record_ids.pop("jobs", None)
        else:
            self.person_snapshot["non_magical"] = False
            self.loaded_section_record_ids.pop("development", None)

        self.loaded_section_record_ids.pop("family_tree", None)
        self.update_person_navigation()
        self.update_school_summary_from_person(self.person_snapshot)
        self.change_command()

    def variable_changed(self, *arguments):
        if self.loading:
            return

        if self.section_is_current("development"):
            birth_year_variable = self.variables.get("birth_year")
            birth_month_variable = self.variables.get("birth_month")
            birth_day_variable = self.variables.get("birth_day")
            self.development.set_birth_date(
                (
                    birth_year_variable.get()
                    if birth_year_variable is not None
                    else ""
                ),
                (
                    birth_month_variable.get()
                    if birth_month_variable is not None
                    else ""
                ),
                (
                    birth_day_variable.get()
                    if birth_day_variable is not None
                    else ""
                ),
            )

        self.loaded_section_record_ids.pop("family_tree", None)
        self.update_death_overview()
        self.change_command()

    def text_changed(self, event):
        if event.widget.edit_modified():
            event.widget.edit_modified(False)

            if not self.loading:
                self.change_command()
