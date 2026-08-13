import ctypes
import sys
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import messagebox

from mage_maker.core.controller import PeopleController
from mage_maker.core.database import JsonDatabase
from mage_maker.core.game_database import GameDatabase, GameDatabaseError
from mage_maker.sections.events.controller import EventController
from mage_maker.sections.locations.controller import LocationController
from mage_maker.sections.locations.period_definitions import (
    load_period_definitions,
)
from mage_maker.sections.items.controller import ItemController
from mage_maker.sections.books.controller import BookController
from mage_maker.sections.mages.page import MagesPage
from mage_maker.sections.organizations.controller import OrganizationController
from mage_maker.sections.settings.controller import (
    ApplicationSettingsController,
)
from mage_maker.ui.theme import (
    APP_BACKGROUND,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    PRIMARY,
    PRIMARY_DARK,
    PRIMARY_HOVER,
    PRIMARY_LIGHT,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_LIGHT,
    TEXT_MUTED,
    app_font,
    configure_tk_fonts,
)
from mage_maker.ui.widgets import SoftButton


WINDOWS_APPLICATION_ID = "CharmsCheck.WorldBuilder"
PRIMARY_ICON_FILENAME = "crooked-purple-wand.ico"
APPLICATION_SETTINGS_KEY = "_application_settings"
REGION_LOCK_SETTING_KEY = "region_lock_id"
ORGANIZATION_LOCK_SETTING_KEY = "organization_lock_id"


def configure_windows_application_identity():
    if sys.platform != "win32":
        return False

    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        set_application_id = (
            shell32.SetCurrentProcessExplicitAppUserModelID
        )
        set_application_id.argtypes = [ctypes.c_wchar_p]
        set_application_id.restype = ctypes.c_long
        result = set_application_id(WINDOWS_APPLICATION_ID)
    except (AttributeError, OSError, TypeError, ValueError):
        return False

    return result >= 0


class MageMakerApp(tk.Tk):
    def __init__(self, database_path=None, game_database_directory=None):
        super().__init__()
        configure_windows_application_identity()
        configure_tk_fonts(self)
        application_directory = Path(__file__).resolve().parent.parent.parent
        resolved_database_path = (
            database_path or application_directory / "data" / "mage_maker.json"
        )
        resolved_game_database_directory = (
            game_database_directory
            or application_directory / "data" / "dbm"
        )
        self.title("World Builder")
        self.geometry("1320x820")
        self.minsize(1040, 680)
        self.configure(bg=APP_BACKGROUND)
        self.configure_primary_icon(application_directory)

        try:
            self.state("zoomed")
        except tk.TclError:
            pass

        self.database = JsonDatabase(resolved_database_path)
        self.database.load()
        self.game_database = GameDatabase(resolved_game_database_directory)

        try:
            self.game_database.load()
        except GameDatabaseError as error:
            self.game_database.mark_unavailable(error)

        self.settings_controller = ApplicationSettingsController(
            self.database
        )
        self.people_controller = PeopleController(self.database)
        self.item_controller = ItemController(
            self.database,
            self.people_controller.list_people,
        )
        self.location_controller = LocationController(
            self.database,
            self.people_controller.list_people,
        )
        self.event_controller = EventController(
            self.database,
            self.people_controller.list_people,
            self.location_controller.list_locations,
            load_period_definitions,
            self.location_controller.create_location,
            self.people_controller.create_person,
            self.people_controller.list_mage_groups,
            self.people_controller.list_people_summaries,
            self.game_database,
        )

        ownership_changed = (
            self.event_controller.synchronize_item_ownership_from_events()
        )
        retained_events_changed = (
            self.event_controller.synchronize_retained_item_events_for_deaths()
        )

        if retained_events_changed or ownership_changed:
            self.database.save()

        self.organization_controller = OrganizationController(
            self.database,
            self.location_controller.list_locations,
            self.game_database.schools,
            self.game_database.storeroom_items,
            self.location_controller,
        )
        self.book_controller = BookController(
            self.database,
            self.game_database,
            self.people_controller.list_people,
            self.location_controller.list_locations,
            self.organization_controller.list_organizations,
            self.event_controller,
        )
        self.status_value = tk.StringVar(value="Ready")
        self.pages = {}
        self.navigation_buttons = {}
        self.active_page_name = "mages"
        self.navigation_history = []
        self.forward_navigation_history = []
        self.region_lock_id = self.saved_region_lock_id()
        self.organization_lock_id = self.saved_organization_lock_id()
        self.content = None
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_header()
        self.build_pages()
        self.build_status_bar()
        self.show_page("mages", confirm_change=False)
        self.bind("<Control-s>", self.save_shortcut)
        self.bind("<Control-n>", self.create_shortcut)
        self.bind("<Control-f>", self.search_shortcut)
        self.bind("<Alt-Left>", self.go_back)
        self.bind("<Alt-Right>", self.go_forward)

        if sys.platform == "win32":
            for sequence in ("<Button-4>", "<Button-8>"):
                try:
                    self.bind_all(sequence, self.mouse_back, add="+")
                except tk.TclError:
                    continue

            for sequence in ("<Button-5>", "<Button-9>"):
                try:
                    self.bind_all(sequence, self.mouse_forward, add="+")
                except tk.TclError:
                    continue

        self.protocol("WM_DELETE_WINDOW", self.close_application)

        if self.game_database.error:
            self.set_status(self.game_database.error)

    def configure_primary_icon(self, application_directory):
        icon_path = (
            Path(application_directory)
            / "assets"
            / PRIMARY_ICON_FILENAME
        )

        if sys.platform != "win32" or not icon_path.is_file():
            return False

        try:
            self.iconbitmap(default=str(icon_path))
        except (OSError, TypeError, tk.TclError):
            return False

        return True

    def build_header(self):
        header = tk.Frame(self, bg=PRIMARY_DARK, height=64)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)
        title = tk.Label(
            header,
            text="World Builder",
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(19, "bold"),
            anchor="sw",
            padx=24,
            pady=8,
        )
        title.grid(row=0, column=0, sticky="nsew")
        navigation = tk.Frame(header, bg=PRIMARY_DARK)
        navigation.grid(
            row=0,
            column=1,
            sticky="sw",
            padx=(12, 0),
            pady=(0, 7),
        )

        for page_name, label, width in (
            ("mages", "Mages", 104),
            ("locations", "Locations", 116),
            ("periods", "Periods", 104),
            ("organizations", "Organizations", 144),
            ("items", "Items", 96),
            ("books", "Books", 96),
            ("creatures", "Named Creatures", 150),
            ("settings", "Settings", 104),
        ):
            button = SoftButton(
                navigation,
                text=label,
                command=self.navigation_command(page_name),
                background=PRIMARY_DARK,
                fill=BUTTON_SOFT,
                hover_fill=BUTTON_SOFT_HOVER,
                foreground=TEXT_DARK,
                width=width,
                height=38,
            )
            button.pack(side="left", padx=(0, 8))
            self.navigation_buttons[page_name] = button

        subtitle = tk.Label(
            header,
            text="Worldbuilding Database",
            bg=PRIMARY_DARK,
            fg=PRIMARY_LIGHT,
            font=app_font(10),
            padx=24,
            pady=9,
            anchor="se",
        )
        subtitle.grid(row=0, column=2, sticky="nsew")

    def navigation_command(self, page_name):
        return NavigationCommand(self, page_name)

    def build_pages(self):
        self.content = tk.Frame(self, bg=APP_BACKGROUND)
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        self.pages["mages"] = MagesPage(
            self.content,
            self.people_controller,
            self.game_database,
            self.set_status,
            self.refresh_cross_page_data,
            self.event_controller,
            self.open_period_event,
            self.organization_controller.list_organizations,
            self.settings_controller,
            organization_create_command=(
                self.organization_controller.create_organization
            ),
            organization_location_provider=(
                self.organization_controller.location_records
            ),
            item_controller=self.item_controller,
            book_controller=self.book_controller,
        )
        self.pages["mages"].grid(row=0, column=0, sticky="nsew")

    def ensure_page(self, page_name):
        if page_name in self.pages:
            return True

        try:
            if page_name == "locations":
                from mage_maker.sections.locations.page import LocationPage

                page = LocationPage(
                    self.content,
                    self.location_controller,
                    self.set_status,
                    self.open_mage,
                    self.region_lock_changed,
                    self.event_controller,
                    self.open_period_event,
                    self.refresh_cross_page_data,
                    self.open_organization,
                )
            elif page_name == "periods":
                from mage_maker.sections.locations.periods_page import (
                    PeriodsPage,
                )

                page = PeriodsPage(
                    self.content,
                    self.location_controller,
                    self.event_controller,
                    self.set_status,
                    self.open_mage,
                    self.region_lock_changed,
                    self.open_location,
                    self.refresh_cross_page_data,
                )
            elif page_name == "organizations":
                from mage_maker.sections.organizations.page import (
                    OrganizationPage,
                )

                page = OrganizationPage(
                    self.content,
                    self.organization_controller,
                    self.set_status,
                    self.event_controller,
                    self.refresh_cross_page_data,
                    self.organization_lock_changed,
                    auto_refresh=False,
                )
            elif page_name == "items":
                from mage_maker.sections.items.page import ItemsView

                page = ItemsView(
                    self.content,
                    self.item_controller,
                    self.people_controller.list_people,
                    self.set_status,
                    event_controller=self.event_controller,
                    events_changed_command=self.refresh_cross_page_data,
                    global_mode=True,
                )
            elif page_name == "books":
                from mage_maker.sections.books.page import BooksPage

                page = BooksPage(
                    self.content,
                    self.book_controller,
                    self.set_status,
                    self.refresh_cross_page_data,
                    auto_refresh=False,
                )
            elif page_name == "creatures":
                from mage_maker.sections.creatures.page import NamedCreaturesPage

                page = NamedCreaturesPage(
                    self.content,
                    self.database,
                    self.game_database,
                    self.set_status,
                    self.refresh_cross_page_data,
                )
            elif page_name == "settings":
                from mage_maker.sections.settings.page import SettingsPage

                page = SettingsPage(
                    self.content,
                    self.settings_controller,
                    self.set_status,
                    self.refresh_mage_group_data,
                )
            else:
                return False
        except Exception as error:
            self.report_page_error(page_name, error)
            return False

        page.grid(row=0, column=0, sticky="nsew")
        self.pages[page_name] = page

        if page_name in ("locations", "periods"):
            page.set_region_lock(self.region_lock_id)
        elif page_name == "organizations":
            page.set_organization_lock(
                self.organization_lock_id,
                notify=False,
                refresh_page=False,
            )

        return True

    def report_page_error(self, page_name, error):
        crash_log_path = Path(__file__).resolve().parents[2] / (
            "world-builder-crash.log"
        )
        crash_details = traceback.format_exc()

        try:
            crash_log_path.write_text(crash_details, encoding="utf-8")
        except OSError:
            pass

        messagebox.showerror(
            f"Could not open {page_name.title()}",
            (
                f"{type(error).__name__}: {error}\n\n"
                f"Details were saved to {crash_log_path}."
            ),
            parent=self,
        )

    def build_status_bar(self):
        status_bar = tk.Label(
            self,
            textvariable=self.status_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            padx=12,
            pady=7,
        )
        status_bar.grid(row=2, column=0, sticky="ew")

    def show_page(
        self,
        page_name,
        confirm_change=True,
        record_history=True,
    ):
        if page_name not in (
            "mages",
            "locations",
            "periods",
            "organizations",
            "items",
            "books",
            "settings",
        ):
            return False

        if (
            confirm_change
            and self.active_page_name == "mages"
            and page_name != "mages"
            and not self.pages["mages"].confirm_unsaved_changes()
        ):
            return False

        if (
            confirm_change
            and self.active_page_name == "organizations"
            and page_name != "organizations"
            and not self.pages[
                "organizations"
            ].confirm_unsaved_organization_changes()
        ):
            return False

        if (
            confirm_change
            and self.active_page_name == "locations"
            and page_name != "locations"
            and not self.pages[
                "locations"
            ].confirm_unsaved_location_changes()
        ):
            return False

        if not self.ensure_page(page_name):
            return False

        previous_page_name = self.active_page_name

        if (
            record_history
            and previous_page_name != page_name
            and previous_page_name in (
                "mages",
                "locations",
                "periods",
                "organizations",
                "items",
                "books",
                "settings",
            )
        ):
            if (
                not self.navigation_history
                or self.navigation_history[-1] != previous_page_name
            ):
                self.navigation_history.append(previous_page_name)

            self.forward_navigation_history = []

        self.active_page_name = page_name

        if page_name == "mages":
            mages_page = self.pages["mages"]
            mages_page.refresh_people(
                mages_page.current_record_id
            )
        elif page_name == "locations":
            self.pages["locations"].refresh()
        elif page_name == "periods":
            self.pages["periods"].refresh()
        elif page_name == "organizations":
            self.pages["organizations"].refresh()
        elif page_name == "items":
            self.pages["items"].refresh_items()
        elif page_name == "books":
            self.pages["books"].refresh()
        elif page_name == "settings":
            self.pages["settings"].refresh()

        self.pages[page_name].tkraise()

        for name, button in self.navigation_buttons.items():
            if name == page_name:
                button.set_colors(PRIMARY, PRIMARY_HOVER, TEXT_DARK)
            else:
                button.set_colors(BUTTON_SOFT, BUTTON_SOFT_HOVER, TEXT_DARK)

        return True

    def go_back(self, event=None):
        if not self.navigation_history:
            return "break"

        target_page_name = self.navigation_history.pop()
        current_page_name = self.active_page_name

        if self.show_page(
            target_page_name,
            record_history=False,
        ):
            if (
                not self.forward_navigation_history
                or self.forward_navigation_history[-1]
                != current_page_name
            ):
                self.forward_navigation_history.append(current_page_name)
        else:
            self.navigation_history.append(target_page_name)

        return "break"

    def go_forward(self, event=None):
        if not self.forward_navigation_history:
            return "break"

        target_page_name = self.forward_navigation_history.pop()
        current_page_name = self.active_page_name

        if self.show_page(
            target_page_name,
            record_history=False,
        ):
            if (
                not self.navigation_history
                or self.navigation_history[-1] != current_page_name
            ):
                self.navigation_history.append(current_page_name)
        else:
            self.forward_navigation_history.append(target_page_name)

        return "break"

    def mouse_back(self, event=None):
        if not self.mouse_navigation_is_for_application(event):
            return None

        return self.go_back()

    def mouse_forward(self, event=None):
        if not self.mouse_navigation_is_for_application(event):
            return None

        return self.go_forward()

    def mouse_navigation_is_for_application(self, event):
        if event is None:
            return True

        try:
            return event.widget.winfo_toplevel() is self
        except (AttributeError, tk.TclError):
            return False

    def open_mage(self, record_id):
        if not self.show_page("mages"):
            return False

        return self.pages["mages"].select_person(record_id)

    def open_location(self, record_id):
        if not self.show_page("locations"):
            return False

        return self.pages["locations"].open_location(record_id)

    def open_organization(self, record_id):
        if not self.show_page("organizations"):
            return False

        organization_page = self.pages["organizations"]

        if (
            str(record_id or "").strip()
            != str(
                organization_page.current_organization_id or ""
            ).strip()
            and not organization_page.confirm_unsaved_organization_changes()
        ):
            return False

        organization_page.refresh(record_id, force_load=True)
        return (
            organization_page.current_organization_id
            == str(record_id or "").strip()
        )

    def open_period_event(self, record_id):
        if not self.show_page("periods"):
            return False

        return self.pages["periods"].open_event(record_id)

    def saved_region_lock_id(self):
        settings = self.database.data.get(APPLICATION_SETTINGS_KEY, {})
        stored_location_id = (
            str(settings.get(REGION_LOCK_SETTING_KEY, "") or "").strip()
            if isinstance(settings, dict)
            else ""
        )

        if (
            stored_location_id
            and self.location_controller.get_location(stored_location_id)
            is None
        ):
            return ""

        return stored_location_id

    def remember_region_lock(self, location_id):
        normalized_location_id = str(location_id or "").strip()
        current_settings = self.database.data.get(
            APPLICATION_SETTINGS_KEY,
            {},
        )
        settings = (
            dict(current_settings)
            if isinstance(current_settings, dict)
            else {}
        )

        if (
            str(settings.get(REGION_LOCK_SETTING_KEY, "") or "").strip()
            == normalized_location_id
        ):
            return False

        settings[REGION_LOCK_SETTING_KEY] = normalized_location_id
        self.database.data[APPLICATION_SETTINGS_KEY] = settings
        self.database.dirty = True
        return True

    def saved_organization_lock_id(self):
        settings = self.database.data.get(APPLICATION_SETTINGS_KEY, {})
        stored_organization_id = (
            str(
                settings.get(ORGANIZATION_LOCK_SETTING_KEY, "") or ""
            ).strip()
            if isinstance(settings, dict)
            else ""
        )

        if (
            stored_organization_id
            and self.organization_controller.get_organization(
                stored_organization_id
            )
            is None
        ):
            return ""

        return stored_organization_id

    def remember_organization_lock(self, organization_id):
        normalized_organization_id = str(
            organization_id or ""
        ).strip()
        current_settings = self.database.data.get(
            APPLICATION_SETTINGS_KEY,
            {},
        )
        settings = (
            dict(current_settings)
            if isinstance(current_settings, dict)
            else {}
        )

        if (
            str(
                settings.get(ORGANIZATION_LOCK_SETTING_KEY, "") or ""
            ).strip()
            == normalized_organization_id
        ):
            return False

        settings[ORGANIZATION_LOCK_SETTING_KEY] = (
            normalized_organization_id
        )
        self.database.data[APPLICATION_SETTINGS_KEY] = settings
        self.database.dirty = True
        return True

    def organization_lock_changed(self, organization_id):
        self.organization_lock_id = str(
            organization_id or ""
        ).strip()
        self.remember_organization_lock(self.organization_lock_id)

    def region_lock_changed(self, location_id):
        self.region_lock_id = str(location_id or "").strip()
        self.remember_region_lock(self.region_lock_id)

        for page_name in ("locations", "periods"):
            page = self.pages.get(page_name)

            if page is not None:
                page.set_region_lock(self.region_lock_id)

    def refresh_cross_page_data(self):
        ownership_changed = (
            self.event_controller.synchronize_item_ownership_from_events()
        )
        retained_events_changed = (
            self.event_controller.synchronize_retained_item_events_for_deaths()
        )

        if retained_events_changed or ownership_changed:
            self.database.save()

        mages_page = self.pages.get("mages")

        if mages_page is not None:
            mages_page.refresh_people(
                mages_page.current_record_id
            )
            mages_page.refresh_linked_events()

        location_page = self.pages.get("locations")

        if location_page is not None:
            location_page.refresh_person_data()

        periods_page = self.pages.get("periods")

        if periods_page is not None:
            periods_page.refresh()

        organization_page = self.pages.get("organizations")

        if organization_page is not None:
            organization_page.refresh(
                organization_page.current_organization_id
            )

        items_page = self.pages.get("items")

        if items_page is not None:
            items_page.refresh_items(items_page.selected_item_id)

        books_page = self.pages.get("books")

        if books_page is not None:
            books_page.refresh(books_page.selected_book_id)

        if mages_page is not None:
            mages_page.person_form.refresh_books_and_ledger()

    def refresh_mage_group_data(self):
        mages_page = self.pages.get("mages")

        if mages_page is not None:
            mages_page.refresh_group_data()

    def set_status(self, message):
        self.status_value.set(str(message or "Ready"))

    def close_application(self):
        if not self.pages["mages"].confirm_unsaved_changes():
            return

        if (
            "locations" in self.pages
            and not self.pages[
                "locations"
            ].confirm_unsaved_location_changes()
        ):
            return

        if (
            "organizations" in self.pages
            and not self.pages[
                "organizations"
            ].confirm_unsaved_organization_changes()
        ):
            return

        if self.database.dirty:
            try:
                self.database.save()
            except (OSError, TypeError, ValueError) as error:
                messagebox.showerror(
                    "Could not save application data",
                    str(error),
                    parent=self,
                )
                return

        self.destroy()

    def save_shortcut(self, event=None):
        if self.active_page_name == "mages":
            self.pages["mages"].save_shortcut()
        elif (
            self.active_page_name == "locations"
            and "locations" in self.pages
        ):
            self.pages["locations"].save_shortcut()
        elif (
            self.active_page_name == "periods"
            and "periods" in self.pages
        ):
            if self.pages["periods"].active_view_name == "overview":
                self.pages["periods"].save_period_details()
        elif (
            self.active_page_name == "organizations"
            and "organizations" in self.pages
        ):
            self.pages["organizations"].save_organization()

        return "break"

    def create_shortcut(self, event=None):
        if self.active_page_name == "mages":
            self.pages["mages"].create_shortcut()
        elif (
            self.active_page_name == "locations"
            and "locations" in self.pages
        ):
            self.pages["locations"].create_shortcut()
        elif (
            self.active_page_name == "periods"
            and "periods" in self.pages
        ):
            self.pages["periods"].create_shortcut()
        elif (
            self.active_page_name == "organizations"
            and "organizations" in self.pages
        ):
            self.pages["organizations"].create_organization()
        elif self.active_page_name == "items" and "items" in self.pages:
            self.pages["items"].open_add_item_dialog()
        elif self.active_page_name == "books" and "books" in self.pages:
            self.pages["books"].create_shortcut()

        return "break"

    def search_shortcut(self, event=None):
        if self.active_page_name == "mages":
            self.pages["mages"].search_shortcut()
        elif (
            self.active_page_name == "locations"
            and "locations" in self.pages
        ):
            self.pages["locations"].location_tree.search_control.focus_set()
        elif (
            self.active_page_name == "periods"
            and "periods" in self.pages
        ):
            self.pages["periods"].search_shortcut()
        elif (
            self.active_page_name == "organizations"
            and "organizations" in self.pages
        ):
            self.pages["organizations"].search_shortcut()
        elif self.active_page_name == "items" and "items" in self.pages:
            self.pages["items"].search_entry.entry.focus_set()
        elif self.active_page_name == "books" and "books" in self.pages:
            self.pages["books"].search_shortcut()

        return "break"


class NavigationCommand:
    def __init__(self, application, page_name):
        self.application = application
        self.page_name = page_name

    def __call__(self):
        self.application.show_page(self.page_name)
