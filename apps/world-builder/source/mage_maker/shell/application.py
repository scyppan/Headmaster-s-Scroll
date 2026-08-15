import ctypes
import sys
import tkinter as tk
import traceback
from pathlib import Path
from threading import Thread
from tkinter import messagebox

from mage_maker.core.controller import PeopleController
from mage_maker.core.database import JsonDatabase
from mage_maker.core.world_index import source_fingerprint
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
        # A missing/stale disposable index must not keep the application shell
        # from appearing.  The app starts its rebuild after the UI exists.
        self.database.load(rebuild_index=False)
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
        self.page_refresh_revisions = {}
        self.invalidated_pages = set()
        self.navigation_buttons = {}
        self.active_page_name = "mages"
        self.navigation_history = []
        self.forward_navigation_history = []
        self.region_lock_id = self.saved_region_lock_id()
        self.organization_lock_id = self.saved_organization_lock_id()
        self.content = None
        self._closing = False
        self._close_save_running = False
        self._close_save_error = None
        self._close_save_thread = None
        self._cross_page_refresh_after_id = None
        self._world_watch_after_id = None
        self._external_reload_thread = None
        self._external_reload_database = None
        self._external_reload_error = None
        self._index_rebuild_thread = None
        self._index_rebuild_error = None
        self._index_widget_states = []
        self._observed_world_fingerprint = source_fingerprint(
            self.database.database_path
        )
        self.database.subscribe(self.database_changed)
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
        if self.database.index_dirty:
            self.after_idle(self.start_background_index_rebuild)
        self._world_watch_after_id = self.after(
            2000,
            self.monitor_external_world_save,
        )

        if self.game_database.error:
            self.set_status(self.game_database.error)

    def start_background_index_rebuild(self):
        if self._closing or self._index_rebuild_thread is not None:
            return
        self._index_rebuild_error = None
        self.set_status("Indexing world data... editing will unlock when ready")
        for button in self.navigation_buttons.values():
            button.set_enabled(False)
        self.set_index_editing_enabled(False)
        self._index_rebuild_thread = Thread(
            target=self.rebuild_index_worker,
            name="world-builder-index-rebuild",
            daemon=True,
        )
        self._index_rebuild_thread.start()
        self.after(50, self.poll_background_index_rebuild)

    def rebuild_index_worker(self):
        try:
            self.database.rebuild_world_index()
        except Exception as error:
            self._index_rebuild_error = error

    def poll_background_index_rebuild(self):
        worker = self._index_rebuild_thread
        if worker is not None and worker.is_alive():
            self.after(50, self.poll_background_index_rebuild)
            return
        self._index_rebuild_thread = None
        if self._closing:
            self.finish_close()
            return
        for button in self.navigation_buttons.values():
            button.set_enabled(True)
        self.set_index_editing_enabled(True)
        if self._index_rebuild_error is None and not self.database.index_dirty:
            self.set_status("World index ready")
            self.invalidated_pages.add("mages")
            self.refresh_page_if_needed(self.active_page_name, force=True)
        else:
            self.set_status(
                "World index could not be rebuilt; canonical data remains safe"
            )

    def set_index_editing_enabled(self, enabled):
        if enabled:
            for widget, previous_state in self._index_widget_states:
                try:
                    widget.configure(state=previous_state)
                except tk.TclError:
                    pass
            self._index_widget_states = []
            return

        self._index_widget_states = []
        stack = list(self.content.winfo_children()) if self.content else []
        while stack:
            widget = stack.pop()
            try:
                stack.extend(widget.winfo_children())
            except tk.TclError:
                pass
            try:
                previous_state = str(widget.cget("state"))
            except tk.TclError:
                continue
            if previous_state in ("disabled", "readonly"):
                continue
            try:
                widget.configure(state="disabled")
            except tk.TclError:
                continue
            self._index_widget_states.append((widget, previous_state))

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
        # MagesPage performs its initial population while it is constructed.
        # Mark that revision as seen so the first tkraise does not repeat the
        # full filtering/generation calculation a second time.
        self.page_refresh_revisions["mages"] = self.database.revision

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
            "creatures",
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

        self.refresh_page_if_needed(page_name)

        self.pages[page_name].tkraise()

        for name, button in self.navigation_buttons.items():
            if name == page_name:
                button.set_colors(PRIMARY, PRIMARY_HOVER, TEXT_DARK)
            else:
                button.set_colors(BUTTON_SOFT, BUTTON_SOFT_HOVER, TEXT_DARK)

        return True

    def refresh_page_if_needed(self, page_name, force=False):
        if page_name not in self.pages:
            return False
        last_seen = self.page_refresh_revisions.get(page_name)
        needs_refresh = (
            force
            or page_name in self.invalidated_pages
            or last_seen != self.database.revision
        )
        if not needs_refresh:
            return False

        page = self.pages[page_name]
        if page_name == "mages":
            page.refresh_people(page.current_record_id)
        elif page_name == "locations":
            page.refresh()
        elif page_name == "periods":
            page.refresh()
        elif page_name == "organizations":
            page.refresh()
        elif page_name == "items":
            page.refresh_items()
        elif page_name == "books":
            page.refresh()
        elif page_name == "creatures":
            refresh_command = getattr(page, "refresh", None)
            if callable(refresh_command):
                refresh_command()
        elif page_name == "settings":
            page.refresh()

        self.page_refresh_revisions[page_name] = self.database.revision
        self.invalidated_pages.discard(page_name)
        return True

    def database_changed(self, collection_name, record_ids, revision):
        affected_pages = {
            "people": {"mages", "locations", "periods", "organizations"},
            "events": {
                "mages", "locations", "periods", "organizations", "items", "books"
            },
            "locations": {"locations", "periods", "mages", "organizations"},
            "organizations": {"organizations", "mages", "locations"},
            "items": {"items", "mages", "organizations"},
            "books": {"books", "mages"},
            "book_readings": {"books", "mages"},
            "named_creatures": {"creatures", "mages"},
            "maps": {"locations"},
        }.get(
            str(collection_name or ""),
            set(self.pages),
        )
        self.invalidated_pages.update(affected_pages)

    def monitor_external_world_save(self):
        self._world_watch_after_id = None
        if self._closing:
            return
        try:
            current_fingerprint = source_fingerprint(
                self.database.database_path
            )
        except OSError:
            current_fingerprint = self._observed_world_fingerprint
        if (
            current_fingerprint != self._observed_world_fingerprint
            and not self.database.dirty
            and self.database.world_index.payload.get("source")
            == current_fingerprint
        ):
            # A successful save through this process already rebuilt the
            # index; do not mistake it for an external write.
            self._observed_world_fingerprint = current_fingerprint
        if (
            current_fingerprint != self._observed_world_fingerprint
            and not self.database.dirty
            and self._external_reload_thread is None
        ):
            self.set_status("World data changed externally; refreshing index...")
            self._external_reload_database = None
            self._external_reload_error = None
            self._external_reload_thread = Thread(
                target=self.load_external_world,
                name="world-builder-external-refresh",
                daemon=True,
            )
            self._external_reload_thread.start()
            self.after(50, self.poll_external_world_reload)
            return
        self._world_watch_after_id = self.after(
            2000,
            self.monitor_external_world_save,
        )

    def load_external_world(self):
        try:
            refreshed = JsonDatabase(self.database.database_path)
            refreshed.load()
            self._external_reload_database = refreshed
        except Exception as error:
            self._external_reload_error = error

    def poll_external_world_reload(self):
        worker = self._external_reload_thread
        if worker is not None and worker.is_alive():
            self.after(50, self.poll_external_world_reload)
            return
        self._external_reload_thread = None
        refreshed = self._external_reload_database
        if self._closing:
            self.finish_close()
            return
        if self._external_reload_error is not None:
            self.set_status(
                f"Could not refresh externally changed world data: {self._external_reload_error}"
            )
        elif refreshed is not None and not self.database.dirty:
            next_revision = self.database.revision + 1
            self.database.data = refreshed.data
            self.database.shared_store = refreshed.shared_store
            self.database.shared_session = refreshed.shared_session
            self.database.world_index = refreshed.world_index
            self.database.record_indexes = refreshed.record_indexes
            self.database.index_dirty = refreshed.index_dirty
            self.database.dirty = refreshed.dirty
            self.database.revision = next_revision
            self._observed_world_fingerprint = source_fingerprint(
                self.database.database_path
            )
            self.invalidated_pages.update(self.pages)
            self.refresh_page_if_needed(self.active_page_name, force=True)
            self.set_status("World data refreshed from disk")
        else:
            self.set_status(
                "World data changed externally; save or discard local edits before refreshing"
            )
        self._external_reload_database = None
        self._world_watch_after_id = self.after(
            2000,
            self.monitor_external_world_save,
        )

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
        settings = self.database.get_preference(
            APPLICATION_SETTINGS_KEY,
            {},
        )
        stored_location_id = str(
            settings.get(REGION_LOCK_SETTING_KEY, "") or ""
        ).strip()

        if (
            stored_location_id
            and self.location_controller.get_location(stored_location_id)
            is None
        ):
            return ""

        return stored_location_id

    def remember_region_lock(self, location_id):
        normalized_location_id = str(location_id or "").strip()
        current_settings = self.database.get_preference(
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
        return self.database.set_preference(
            APPLICATION_SETTINGS_KEY,
            settings,
        )

    def saved_organization_lock_id(self):
        settings = self.database.get_preference(
            APPLICATION_SETTINGS_KEY,
            {},
        )
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
        current_settings = self.database.get_preference(
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
        return self.database.set_preference(
            APPLICATION_SETTINGS_KEY,
            settings,
        )

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

    def refresh_cross_page_data(self, collection_name="", record_ids=()):
        if self._closing:
            return
        if collection_name:
            self.database_changed(
                collection_name,
                record_ids,
                self.database.revision,
            )
        else:
            self.invalidated_pages.update(self.pages)

        if self._cross_page_refresh_after_id is not None:
            try:
                self.after_cancel(self._cross_page_refresh_after_id)
            except tk.TclError:
                pass
        self._cross_page_refresh_after_id = self.after(
            120,
            self.finish_cross_page_refresh,
        )

    def finish_cross_page_refresh(self):
        self._cross_page_refresh_after_id = None
        if self._closing:
            return
        ownership_changed = (
            self.event_controller.synchronize_item_ownership_from_events()
        )
        retained_events_changed = (
            self.event_controller.synchronize_retained_item_events_for_deaths()
        )

        if retained_events_changed or ownership_changed:
            self.database.save()
        self.refresh_page_if_needed(self.active_page_name, force=True)

    def refresh_mage_group_data(self):
        mages_page = self.pages.get("mages")

        if mages_page is not None:
            mages_page.refresh_group_data()

    def set_status(self, message):
        self.status_value.set(str(message or "Ready"))

    def close_application(self):
        if self._close_save_running:
            self.set_status("Saving changes before closing...")
            return
        if self._closing:
            return

        self.release_child_grabs()
        if not self.has_unsaved_application_changes():
            self._closing = True
            self.finish_close()
            return

        save_choice = messagebox.askyesnocancel(
            "Unsaved World Builder changes",
            (
                "World Builder has unsaved changes.\n\n"
                "Yes: Save and close\n"
                "No: Discard and close\n"
                "Cancel: Return to World Builder"
            ),
            parent=self,
            icon="warning",
            default="yes",
        )
        if save_choice is None:
            return
        if not save_choice:
            self._closing = True
            self.finish_close()
            return

        self._closing = True
        self.set_status("Preparing changes to save...")
        self.update_idletasks()
        if not self.commit_open_editors():
            self._closing = False
            self.set_status("Close cancelled because an editor could not be saved")
            return
        if not self.database.dirty:
            self.finish_close()
            return
        self.start_close_save()

    def event_editors(self):
        editors = []
        mages_page = self.pages.get("mages")
        person_form = getattr(mages_page, "person_form", None)
        timeline = getattr(person_form, "timeline", None)
        editors.append(getattr(timeline, "event_editor", None))
        location_page = self.pages.get("locations")
        editors.append(getattr(location_page, "event_editor", None))
        periods_page = self.pages.get("periods")
        events_view = getattr(periods_page, "events_view", None)
        editors.append(getattr(events_view, "event_editor", None))
        unique_editors = []
        seen_ids = set()
        for editor in editors:
            if editor is None or id(editor) in seen_ids:
                continue
            seen_ids.add(id(editor))
            unique_editors.append(editor)
        return unique_editors

    def has_unsaved_application_changes(self):
        if self.database.dirty:
            return True
        mages_page = self.pages.get("mages")
        if bool(getattr(mages_page, "form_dirty", False)):
            return True
        location_page = self.pages.get("locations")
        location_dirty = getattr(
            location_page,
            "has_unsaved_location_changes",
            None,
        )
        if callable(location_dirty) and location_dirty():
            return True
        organization_page = self.pages.get("organizations")
        if bool(getattr(organization_page, "form_dirty", False)):
            return True
        for editor in self.event_editors():
            dirty_command = getattr(editor, "has_unsaved_changes", None)
            if callable(dirty_command) and dirty_command():
                return True
        return False

    def commit_open_editors(self):
        for editor in self.event_editors():
            dirty_command = getattr(editor, "has_unsaved_changes", None)
            if not callable(dirty_command) or not dirty_command():
                continue
            if not editor.save():
                messagebox.showerror(
                    "Could not save event",
                    "The open event could not be saved. Correct it or discard it before closing.",
                    parent=self,
                )
                return False

        mages_page = self.pages.get("mages")
        if bool(getattr(mages_page, "form_dirty", False)):
            if not mages_page.save_person():
                return False
        location_page = self.pages.get("locations")
        location_dirty = getattr(
            location_page,
            "has_unsaved_location_changes",
            None,
        )
        if callable(location_dirty) and location_dirty():
            if not location_page.save_location():
                return False
        organization_page = self.pages.get("organizations")
        if bool(getattr(organization_page, "form_dirty", False)):
            if not organization_page.save_organization():
                return False
        return True

    def start_close_save(self):
        self._close_save_running = True
        self._close_save_error = None
        self.set_status("Saving changes before closing...")
        self.update_idletasks()
        self._close_save_thread = Thread(
            target=self.save_for_close,
            name="world-builder-close-save",
            daemon=True,
        )
        self._close_save_thread.start()
        self.after(50, self.poll_close_save)

    def save_for_close(self):
        try:
            self.database.save()
        except Exception as error:
            self._close_save_error = error

    def poll_close_save(self):
        save_thread = self._close_save_thread
        if save_thread is not None and save_thread.is_alive():
            self.after(50, self.poll_close_save)
            return
        self._close_save_running = False
        if self._close_save_error is None:
            self.finish_close()
            return

        error = self._close_save_error
        retry_choice = messagebox.askyesnocancel(
            "Could not save World Builder",
            (
                f"{error}\n\n"
                "Yes: Retry saving\n"
                "No: Discard changes and close\n"
                "Cancel: Return to World Builder"
            ),
            parent=self,
            icon="error",
            default="yes",
        )
        if retry_choice:
            self.start_close_save()
        elif retry_choice is False:
            self.finish_close()
        else:
            self._closing = False
            self.set_status("Save failed; World Builder remains open")

    def release_child_grabs(self):
        try:
            grabbed = self.grab_current()
            if grabbed is not None:
                grabbed.grab_release()
        except tk.TclError:
            pass

    def finish_close(self):
        active_workers = (
            self._index_rebuild_thread,
            self._external_reload_thread,
        )
        if any(
            worker is not None and worker.is_alive()
            for worker in active_workers
        ):
            self.set_status("Closing after background work finishes...")
            self.after(50, self.finish_close)
            return
        if self._cross_page_refresh_after_id is not None:
            try:
                self.after_cancel(self._cross_page_refresh_after_id)
            except tk.TclError:
                pass
            self._cross_page_refresh_after_id = None
        if self._world_watch_after_id is not None:
            try:
                self.after_cancel(self._world_watch_after_id)
            except tk.TclError:
                pass
            self._world_watch_after_id = None
        self.release_child_grabs()
        try:
            self.destroy()
        except tk.TclError:
            pass

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
