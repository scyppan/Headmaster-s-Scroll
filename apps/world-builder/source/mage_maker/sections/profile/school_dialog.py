import tkinter as tk
from copy import deepcopy
from tkinter import messagebox, ttk

from mage_maker.ui.theme import (
    APP_BACKGROUND,
    BORDER,
    BORDER_SOFT,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    FIELD_BACKGROUND,
    LIST_ALTERNATE,
    LIST_SELECTED,
    PRIMARY,
    PRIMARY_HOVER,
    PRIMARY_SOFT,
    SURFACE,
    SURFACE_MUTED,
    SURFACE_RAISED,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import RoundedEntry, SoftButton


def school_detail_values(school):
    if not isinstance(school, dict):
        return None

    school_name = str(
        school.get("name", "") or "Unnamed school"
    ).strip()
    location = str(
        school.get("location", "") or "Unknown"
    ).strip()
    wandless_value = school.get("wandless", False)

    if isinstance(wandless_value, str):
        wandless_value = (
            wandless_value.strip().casefold()
            in ("1", "true", "yes", "y")
        )

    canon_value = school.get("canon")
    curriculum = []

    for year in school.get("curriculum", []) or []:
        if not isinstance(year, dict):
            continue

        core_courses = [
            str(course or "").strip()
            for course in year.get("core", []) or []
            if str(course or "").strip()
        ]
        elective_courses = [
            str(course or "").strip()
            for course in year.get("electives", []) or []
            if str(course or "").strip()
        ]

        try:
            elective_limit = int(
                year.get("elective_limit", 0) or 0
            )
        except (TypeError, ValueError):
            elective_limit = 0

        curriculum.append(
            {
                "year": year.get("year", ""),
                "core": (
                    ", ".join(core_courses)
                    if core_courses
                    else "None"
                ),
                "electives": (
                    ", ".join(elective_courses)
                    if elective_courses
                    else "None"
                ),
                "elective_limit": elective_limit,
            }
        )

    return {
        "name": school_name,
        "location": location,
        "casting_approach": (
            "Non-wand casting"
            if bool(wandless_value)
            else "Wand casting"
        ),
        "school_type": (
            "Canon school"
            if canon_value is True
            else "Original school"
            if canon_value is False
            else "Canon status not specified"
        ),
        "overview": (
            str(school.get("description", "") or "").strip()
            or "No overview is available."
        ),
        "curriculum": curriculum,
    }


def school_curriculum_text(curriculum):
    if not curriculum:
        return "No curriculum information is available."

    lines = []

    for curriculum_year in curriculum:
        lines.extend(
            (
                f"Year {curriculum_year['year']}",
                f"Core courses: {curriculum_year['core']}",
                (
                    "Elective courses: "
                    f"{curriculum_year['electives']}"
                ),
                (
                    "Elective course limit: "
                    f"{curriculum_year['elective_limit']}"
                ),
                "",
            )
        )

    return "\n".join(lines).rstrip()


class ScrollableSchoolOverview(tk.Frame):
    def __init__(self, parent, textvariable):
        super().__init__(parent, bg=SURFACE_MUTED)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(
            self,
            bg=SURFACE_MUTED,
            highlightthickness=0,
            borderwidth=0,
            yscrollincrement=20,
        )
        self.canvas.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.scrollbar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview,
        )
        self.scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
            padx=(6, 0),
        )
        self.canvas.configure(
            yscrollcommand=self.scrollbar.set
        )
        self.label = tk.Label(
            self.canvas,
            textvariable=textvariable,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="nw",
            justify="left",
        )
        self.label_window = self.canvas.create_window(
            0,
            0,
            window=self.label,
            anchor="nw",
        )
        self.label.bind(
            "<Configure>",
            self.update_scroll_region,
        )
        self.canvas.bind(
            "<Configure>",
            self.resize_content,
        )
        self.canvas.bind(
            "<MouseWheel>",
            self.scroll_content,
        )
        self.label.bind(
            "<MouseWheel>",
            self.scroll_content,
        )

    def update_scroll_region(self, event=None):
        content_bounds = self.canvas.bbox("all")

        if content_bounds is not None:
            self.canvas.configure(scrollregion=content_bounds)

    def resize_content(self, event):
        content_width = max(220, int(event.width))
        self.canvas.itemconfigure(
            self.label_window,
            width=content_width,
        )
        self.label.configure(
            wraplength=max(200, content_width - 8)
        )
        self.after_idle(self.update_scroll_region)

    def scroll_content(self, event):
        if not event.delta:
            return "break"

        self.canvas.yview_scroll(
            -1 if event.delta > 0 else 1,
            "units",
        )
        return "break"

    def show_top(self):
        self.after_idle(self.canvas.yview_moveto, 0)


class SchoolSelectionDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        schools,
        current_school,
        save_command,
    ):
        super().__init__(parent)
        self.schools = [
            deepcopy(school)
            for school in schools or []
            if isinstance(school, dict)
            and str(school.get("name", "") or "").strip()
        ]
        self.current_school = str(current_school or "").strip()
        self.save_command = save_command
        self.visible_schools = []
        self.selected_school = None
        self.active_detail_tab = "overview"
        self.search_value = tk.StringVar()
        self.specialty_value = tk.StringVar()
        self.detail_heading_value = tk.StringVar(
            value="Select a school"
        )
        self.detail_location_value = tk.StringVar(value="—")
        self.detail_casting_value = tk.StringVar(value="—")
        self.detail_type_value = tk.StringVar(value="—")
        self.detail_overview_value = tk.StringVar(
            value="Select a school to see its overview."
        )

        if (
            self.current_school
            and not any(
                str(school.get("name", "") or "").strip()
                == self.current_school
                for school in self.schools
            )
        ):
            self.specialty_value.set(self.current_school)

        self.title("Choose School")
        self.geometry("1320x760")
        self.minsize(1120, 640)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.search_value.trace_add("write", self.refresh_results)
        self.refresh_results()
        self.bind("<Escape>", self.close_dialog)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after_idle(self.search_control.focus_set)

    def build_dialog(self):
        card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        card.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=20,
            pady=20,
        )
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(1, weight=1)

        heading = tk.Label(
            card,
            text="Choose a school",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(15, "bold"),
            anchor="w",
        )
        heading.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 12),
        )

        selection_panel = tk.Frame(
            card,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=14,
            pady=14,
            width=480,
        )
        selection_panel.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(0, 8),
        )
        selection_panel.grid_propagate(False)
        selection_panel.grid_rowconfigure(3, weight=1)
        selection_panel.grid_columnconfigure(0, weight=1)
        search_label = tk.Label(
            selection_panel,
            text="Search schools",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        search_label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.search_control = RoundedEntry(
            selection_panel,
            textvariable=self.search_value,
            background=SURFACE_MUTED,
            height=38,
            font=app_font(10),
        )
        self.search_control.grid(row=1, column=0, sticky="ew")
        self.search_control.bind_input(
            "<Escape>",
            self.clear_search,
        )
        self.results_heading = tk.Label(
            selection_panel,
            text="Schools",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        self.results_heading.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(11, 5),
        )
        results_frame = tk.Frame(
            selection_panel,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        results_frame.grid(row=3, column=0, sticky="nsew")
        results_frame.grid_rowconfigure(0, weight=1)
        results_frame.grid_columnconfigure(0, weight=1)
        self.school_list = tk.Listbox(
            results_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=app_font(10),
            activestyle="none",
            exportselection=False,
            width=54,
        )
        self.school_list.grid(row=0, column=0, sticky="nsew")
        self.school_list.bind(
            "<<ListboxSelect>>",
            self.school_selected,
        )
        self.school_list.bind(
            "<Double-Button-1>",
            self.choose_school,
        )
        results_scrollbar = tk.Scrollbar(
            results_frame,
            command=self.school_list.yview,
        )
        results_scrollbar.grid(row=0, column=1, sticky="ns")
        results_horizontal_scrollbar = tk.Scrollbar(
            results_frame,
            orient="horizontal",
            command=self.school_list.xview,
        )
        results_horizontal_scrollbar.grid(
            row=1,
            column=0,
            sticky="ew",
        )
        self.school_list.configure(
            yscrollcommand=results_scrollbar.set,
            xscrollcommand=results_horizontal_scrollbar.set,
        )

        specialty_label = tk.Label(
            selection_panel,
            text="Specialty school",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        specialty_label.grid(
            row=4,
            column=0,
            sticky="ew",
            pady=(13, 5),
        )
        specialty_row = tk.Frame(
            selection_panel,
            bg=SURFACE_MUTED,
        )
        specialty_row.grid(row=5, column=0, sticky="ew")
        specialty_row.grid_columnconfigure(0, weight=1)
        self.specialty_control = RoundedEntry(
            specialty_row,
            textvariable=self.specialty_value,
            background=SURFACE_MUTED,
            height=38,
            font=app_font(10),
        )
        self.specialty_control.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 6),
        )
        specialty_button = SoftButton(
            specialty_row,
            text="Use",
            command=self.choose_specialty_school,
            background=SURFACE_MUTED,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=72,
            height=38,
        )
        specialty_button.grid(row=0, column=1, sticky="e")

        details_panel = tk.Frame(
            card,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=16,
            pady=14,
        )
        details_panel.grid(
            row=1,
            column=1,
            sticky="nsew",
            padx=(8, 0),
        )
        details_panel.grid_rowconfigure(3, weight=1)
        details_panel.grid_columnconfigure(0, weight=1)
        detail_heading = tk.Label(
            details_panel,
            textvariable=self.detail_heading_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(14, "bold"),
            anchor="w",
        )
        detail_heading.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )
        fact_row = tk.Frame(
            details_panel,
            bg=SURFACE_MUTED,
        )
        fact_row.grid(row=1, column=0, sticky="ew")
        fact_row.grid_columnconfigure(
            (0, 1, 2),
            weight=1,
            uniform="school_facts",
        )
        fact_definitions = (
            ("Location", self.detail_location_value),
            ("Casting approach", self.detail_casting_value),
            ("School type", self.detail_type_value),
        )

        for index, (fact_heading, fact_variable) in enumerate(
            fact_definitions
        ):
            fact_card = tk.Frame(
                fact_row,
                bg=SURFACE_RAISED,
                padx=11,
                pady=9,
            )
            fact_card.grid(
                row=0,
                column=index,
                sticky="nsew",
                padx=(
                    (0, 5)
                    if index == 0
                    else (5, 5)
                    if index == 1
                    else (5, 0)
                ),
            )
            fact_label = tk.Label(
                fact_card,
                text=fact_heading,
                bg=SURFACE_RAISED,
                fg=TEXT_MUTED,
                font=app_font(8, "bold"),
                anchor="w",
            )
            fact_label.pack(fill="x")
            fact_value = tk.Label(
                fact_card,
                textvariable=fact_variable,
                bg=SURFACE_RAISED,
                fg=TEXT_DARK,
                font=app_font(10, "bold"),
                anchor="w",
                justify="left",
                wraplength=250,
            )
            fact_value.pack(fill="x", pady=(3, 0))

        detail_tab_row = tk.Frame(
            details_panel,
            bg=SURFACE_MUTED,
        )
        detail_tab_row.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(14, 8),
        )
        self.overview_tab_button = SoftButton(
            detail_tab_row,
            text="Overview",
            command=self.show_overview_tab,
            background=SURFACE_MUTED,
            width=108,
            height=34,
        )
        self.overview_tab_button.pack(side="left")
        self.curriculum_tab_button = SoftButton(
            detail_tab_row,
            text="Curriculum",
            command=self.show_curriculum_tab,
            background=SURFACE_MUTED,
            width=112,
            height=34,
        )
        self.curriculum_tab_button.pack(
            side="left",
            padx=(6, 0),
        )

        detail_tab_content = tk.Frame(
            details_panel,
            bg=SURFACE_MUTED,
        )
        detail_tab_content.grid(
            row=3,
            column=0,
            sticky="nsew",
        )
        detail_tab_content.grid_rowconfigure(0, weight=1)
        detail_tab_content.grid_columnconfigure(0, weight=1)

        self.overview_tab = tk.Frame(
            detail_tab_content,
            bg=SURFACE_MUTED,
        )
        self.overview_tab.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.overview_tab.grid_rowconfigure(1, weight=1)
        self.overview_tab.grid_columnconfigure(0, weight=1)
        overview_heading = tk.Label(
            self.overview_tab,
            text="School overview",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
        )
        overview_heading.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 5),
        )
        self.detail_overview = ScrollableSchoolOverview(
            self.overview_tab,
            self.detail_overview_value,
        )
        self.detail_overview.grid(
            row=1,
            column=0,
            sticky="nsew",
        )

        self.curriculum_tab = tk.Frame(
            detail_tab_content,
            bg=SURFACE_MUTED,
        )
        self.curriculum_tab.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.curriculum_tab.grid_rowconfigure(1, weight=1)
        self.curriculum_tab.grid_columnconfigure(0, weight=1)
        curriculum_heading = tk.Label(
            self.curriculum_tab,
            text="Curriculum by year",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
        )
        curriculum_heading.grid(
            row=0,
            column=0,
            sticky="new",
            pady=(0, 5),
        )
        curriculum_frame = tk.Frame(
            self.curriculum_tab,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        curriculum_frame.grid(
            row=1,
            column=0,
            sticky="nsew",
        )
        curriculum_frame.grid_rowconfigure(0, weight=1)
        curriculum_frame.grid_columnconfigure(0, weight=1)
        self.curriculum_text = tk.Text(
            curriculum_frame,
            wrap="word",
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=app_font(10),
            padx=14,
            pady=12,
            spacing1=2,
            spacing3=5,
            cursor="arrow",
        )
        self.curriculum_text.tag_configure(
            "year",
            font=app_font(11, "bold"),
            foreground=TEXT_DARK,
            spacing1=8,
            spacing3=3,
        )
        self.curriculum_text.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        curriculum_vertical_scrollbar = ttk.Scrollbar(
            curriculum_frame,
            orient="vertical",
            command=self.curriculum_text.yview,
        )
        curriculum_vertical_scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )
        self.curriculum_text.configure(
            yscrollcommand=curriculum_vertical_scrollbar.set,
            state="disabled",
        )
        self.show_overview_tab()

        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(14, 0),
        )
        no_school_button = SoftButton(
            footer,
            text="Use no school",
            command=self.choose_no_school,
            background=SURFACE,
            width=124,
            height=38,
        )
        no_school_button.pack(side="left")
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.destroy,
            background=SURFACE,
            width=88,
            height=38,
        )
        cancel_button.pack(side="right", padx=(6, 0))
        self.choose_button = SoftButton(
            footer,
            text="Use school",
            command=self.choose_school,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=112,
            height=38,
        )
        self.choose_button.pack(side="right")
        self.choose_button.set_enabled(False)

    def refresh_results(self, *arguments):
        query = " ".join(
            self.search_value.get().strip().casefold().split()
        )
        self.visible_schools = []

        for school in self.schools:
            curriculum_text = " ".join(
                " ".join(
                    str(course or "")
                    for course in (
                        list(year.get("core", []) or [])
                        + list(year.get("electives", []) or [])
                    )
                )
                for year in school.get("curriculum", []) or []
                if isinstance(year, dict)
            )
            search_text = " ".join(
                (
                    str(school.get("name", "") or ""),
                    str(school.get("location", "") or ""),
                    str(school.get("description", "") or ""),
                    curriculum_text,
                )
            ).casefold()

            if not query or query in search_text:
                self.visible_schools.append(school)

        self.results_heading.configure(
            text=f"Schools ({len(self.visible_schools)})"
        )
        previous_name = (
            str(self.selected_school.get("name", "") or "").strip()
            if isinstance(self.selected_school, dict)
            else self.current_school
        )
        self.school_list.delete(0, "end")
        selected_index = None

        for index, school in enumerate(self.visible_schools):
            name = str(school.get("name", "") or "").strip()
            location = str(
                school.get("location", "") or "Unknown location"
            ).strip()
            self.school_list.insert(
                "end",
                f"{name} ({location})",
            )
            self.school_list.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

            if name == previous_name:
                selected_index = index

        if selected_index is None and self.visible_schools:
            selected_index = 0

        if selected_index is not None:
            self.school_list.selection_set(selected_index)
            self.school_list.see(selected_index)
            self.selected_school = self.visible_schools[
                selected_index
            ]
            self.render_school_details()
        else:
            self.selected_school = None
            self.render_school_details()

    def school_selected(self, event=None):
        selection = self.school_list.curselection()

        if not selection:
            return

        self.selected_school = self.visible_schools[selection[0]]
        self.render_school_details()

    def render_school_details(self):
        self.curriculum_text.configure(state="normal")
        self.curriculum_text.delete("1.0", "end")

        detail_values = school_detail_values(
            self.selected_school
        )

        if detail_values is None:
            self.detail_heading_value.set("No matching school")
            self.detail_location_value.set("—")
            self.detail_casting_value.set("—")
            self.detail_type_value.set("—")
            self.detail_overview_value.set(
                "Change the search or choose no school."
            )
            self.curriculum_text.insert(
                "end",
                "No curriculum information is available.",
            )
            self.curriculum_text.configure(state="disabled")

            if hasattr(self, "detail_overview"):
                self.detail_overview.show_top()

            self.choose_button.set_enabled(False)
            return

        self.detail_heading_value.set(detail_values["name"])
        self.detail_location_value.set(detail_values["location"])
        self.detail_casting_value.set(
            detail_values["casting_approach"]
        )
        self.detail_type_value.set(
            detail_values["school_type"]
        )
        self.detail_overview_value.set(
            detail_values["overview"]
        )

        if hasattr(self, "detail_overview"):
            self.detail_overview.show_top()

        for index, curriculum_year in enumerate(
            detail_values["curriculum"]
        ):
            if index:
                self.curriculum_text.insert("end", "\n\n")

            self.curriculum_text.insert(
                "end",
                f"Year {curriculum_year['year']}\n",
                "year",
            )
            self.curriculum_text.insert(
                "end",
                f"Core courses: {curriculum_year['core']}\n",
            )
            self.curriculum_text.insert(
                "end",
                (
                    "Elective courses: "
                    f"{curriculum_year['electives']}\n"
                ),
            )
            self.curriculum_text.insert(
                "end",
                (
                    "Elective course limit: "
                    f"{curriculum_year['elective_limit']}"
                ),
            )

        if not detail_values["curriculum"]:
            self.curriculum_text.insert(
                "end",
                school_curriculum_text([]),
            )

        self.curriculum_text.configure(state="disabled")
        self.curriculum_text.see("1.0")

        self.choose_button.set_enabled(True)

    def show_overview_tab(self):
        self.active_detail_tab = "overview"
        self.curriculum_tab.grid_remove()
        self.overview_tab.grid()
        self.overview_tab_button.set_colors(
            PRIMARY_SOFT,
            PRIMARY_HOVER,
            TEXT_DARK,
        )
        self.curriculum_tab_button.set_colors(
            BUTTON_SOFT,
            BUTTON_SOFT_HOVER,
            TEXT_DARK,
        )

    def show_curriculum_tab(self):
        self.active_detail_tab = "curriculum"
        self.overview_tab.grid_remove()
        self.curriculum_tab.grid()
        self.overview_tab_button.set_colors(
            BUTTON_SOFT,
            BUTTON_SOFT_HOVER,
            TEXT_DARK,
        )
        self.curriculum_tab_button.set_colors(
            PRIMARY_SOFT,
            PRIMARY_HOVER,
            TEXT_DARK,
        )

    def choose_school(self, event=None):
        if not isinstance(self.selected_school, dict):
            messagebox.showinfo(
                "Select a school",
                "Select a school first.",
                parent=self,
            )
            return

        school_name = str(
            self.selected_school.get("name", "") or ""
        ).strip()

        if not school_name:
            return

        self.save_command(school_name)
        self.destroy()

    def choose_specialty_school(self):
        specialty_name = self.specialty_value.get().strip()

        if not specialty_name:
            messagebox.showinfo(
                "Specialty school",
                "Enter the specialty school name.",
                parent=self,
            )
            self.specialty_control.focus_set()
            return

        self.save_command(specialty_name)
        self.destroy()

    def choose_no_school(self):
        self.save_command("")
        self.destroy()

    def clear_search(self, event=None):
        if self.search_value.get():
            self.search_value.set("")
            return "break"

        self.destroy()
        return "break"

    def close_dialog(self, event=None):
        self.destroy()
        return "break"
