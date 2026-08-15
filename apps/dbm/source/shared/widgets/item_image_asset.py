from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from PIL import Image, ImageTk, UnidentifiedImageError

from runtime_theme import bind_theme
from shared.item_assets import (
    ITEM_ASSET_DIRECTORY,
    list_item_image_assets,
    normalize_item_image_reference,
    resolve_item_image_reference,
)
from shared.widgets.controls import RoundedEntry, SoftButton
from theme import (
    BORDER,
    FIELD_BACKGROUND,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)


class ItemImageAssetDialog(tk.Toplevel):
    """Search and choose an existing reusable image without copying it."""

    def __init__(self, parent, current_reference=""):
        super().__init__(parent)
        self.result = None
        self.current_reference = str(current_reference or "")
        self.references = []
        self.preview_photo = None

        self.title("Choose Item Image")
        self.geometry("780x500")
        self.minsize(620, 400)
        self.configure(bg=SURFACE)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        bind_theme(self, background="SURFACE")

        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)

        search_panel = tk.Frame(self, bg=SURFACE)
        search_panel.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=(14, 10),
        )
        search_panel.grid_columnconfigure(0, weight=1)
        bind_theme(search_panel, background="SURFACE")

        self.search_value = tk.StringVar()
        self.search_value.trace_add("write", self.refresh_assets)
        self.search_entry = RoundedEntry(
            search_panel,
            textvariable=self.search_value,
            background=SURFACE,
            height=38,
            font=app_font(10),
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        refresh_button = SoftButton(
            search_panel,
            text="Refresh",
            command=self.refresh_assets,
            height=38,
            width=88,
        )
        refresh_button.grid(row=0, column=1, padx=(0, 8))

        browse_button = SoftButton(
            search_panel,
            text="Browse folder...",
            command=self.browse,
            height=38,
            width=126,
        )
        browse_button.grid(row=0, column=2)

        list_panel = tk.Frame(self, bg=SURFACE)
        list_panel.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(14, 8),
        )
        list_panel.grid_columnconfigure(0, weight=1)
        list_panel.grid_rowconfigure(0, weight=1)
        bind_theme(list_panel, background="SURFACE")

        self.asset_list = tk.Listbox(
            list_panel,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=BORDER,
            selectforeground=TEXT_DARK,
            borderwidth=1,
            relief="solid",
            highlightthickness=0,
            font=app_font(10),
            activestyle="none",
            exportselection=False,
        )
        self.asset_list.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(
            list_panel,
            orient="vertical",
            command=self.asset_list.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.asset_list.configure(yscrollcommand=scrollbar.set)
        self.asset_list.bind("<<ListboxSelect>>", self.handle_selection)
        self.asset_list.bind("<Double-Button-1>", self.accept)

        preview_panel = tk.Frame(self, bg=SURFACE)
        preview_panel.grid(
            row=1,
            column=1,
            sticky="nsew",
            padx=(8, 14),
        )
        preview_panel.grid_columnconfigure(0, weight=1)
        preview_panel.grid_rowconfigure(0, weight=1)
        bind_theme(preview_panel, background="SURFACE")

        self.preview = tk.Label(
            preview_panel,
            text="Select an image to preview it",
            bg=FIELD_BACKGROUND,
            fg=TEXT_MUTED,
            relief="solid",
            borderwidth=1,
            compound="top",
            justify="center",
            wraplength=260,
            font=app_font(9),
        )
        self.preview.grid(row=0, column=0, sticky="nsew")
        bind_theme(
            self.preview,
            background="FIELD_BACKGROUND",
            foreground="TEXT_MUTED",
        )

        action_panel = tk.Frame(self, bg=SURFACE)
        action_panel.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="e",
            padx=14,
            pady=14,
        )
        bind_theme(action_panel, background="SURFACE")

        cancel_button = SoftButton(
            action_panel,
            text="Cancel",
            command=self.cancel,
            width=92,
        )
        cancel_button.pack(side="left", padx=(0, 8))
        self.use_button = SoftButton(
            action_panel,
            text="Use selected",
            command=self.accept,
            width=126,
        )
        self.use_button.pack(side="left")
        self.use_button.set_enabled(False)

        self.refresh_assets()
        self.after_idle(self.finish_opening)

    def finish_opening(self):
        self.search_entry.focus_set()
        self.grab_set()

    def refresh_assets(self, *arguments):
        selected_reference = self.selected_reference() or self.current_reference
        self.references = list_item_image_assets(self.search_value.get())
        self.asset_list.delete(0, "end")
        for reference in self.references:
            display = str(Path(reference).relative_to("assets/items"))
            self.asset_list.insert("end", display)

        if selected_reference in self.references:
            index = self.references.index(selected_reference)
            self.asset_list.selection_set(index)
            self.asset_list.see(index)
            self.show_preview(selected_reference)
        else:
            self.show_preview("")

    def selected_reference(self):
        selection = self.asset_list.curselection()
        if not selection:
            return ""
        index = int(selection[0])
        if not 0 <= index < len(self.references):
            return ""
        return self.references[index]

    def handle_selection(self, event=None):
        self.show_preview(self.selected_reference())

    def browse(self):
        ITEM_ASSET_DIRECTORY.mkdir(parents=True, exist_ok=True)
        selected_path = filedialog.askopenfilename(
            parent=self,
            title="Choose an image from assets/items",
            initialdir=ITEM_ASSET_DIRECTORY,
            filetypes=(
                ("Supported images", "*.png *.jpg *.jpeg *.webp *.gif"),
                ("All files", "*.*"),
            ),
        )
        if not selected_path:
            return

        try:
            reference = normalize_item_image_reference(
                selected_path,
                require_exists=True,
            )
        except ValueError as error:
            messagebox.showerror(
                "Cannot use image",
                f"{error}\n\nDBM points to existing files and will not copy them.",
                parent=self,
            )
            return

        self.search_value.set("")
        self.refresh_assets()
        if reference in self.references:
            index = self.references.index(reference)
            self.asset_list.selection_clear(0, "end")
            self.asset_list.selection_set(index)
            self.asset_list.see(index)
            self.show_preview(reference)

    def show_preview(self, reference):
        self.preview_photo = None
        self.use_button.set_enabled(bool(reference))
        if not reference:
            message = (
                "No matching images"
                if self.search_value.get().strip()
                else "Select an image to preview it"
            )
            self.preview.configure(image="", text=message)
            return

        path = resolve_item_image_reference(reference)
        try:
            with Image.open(path) as source:
                image = source.convert("RGBA")
                image.thumbnail((280, 330), Image.Resampling.LANCZOS)
                image.load()
        except (FileNotFoundError, OSError, UnidentifiedImageError):
            self.preview.configure(
                image="",
                text=f"Preview unavailable\n\n{reference}",
            )
            return

        self.preview_photo = ImageTk.PhotoImage(image)
        self.preview.configure(
            image=self.preview_photo,
            text=f"\n{reference}",
        )

    def accept(self, event=None):
        reference = self.selected_reference()
        if not reference:
            return
        self.result = reference
        self.close()

    def cancel(self):
        self.result = None
        self.close()

    def close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def show(self):
        self.wait_window()
        return self.result


class ItemImageAssetField(tk.Frame):
    """Small clickable item-image thumbnail."""

    def __init__(self, parent, change_command):
        super().__init__(parent, bg=SURFACE, width=86, height=86)
        bind_theme(self, background="SURFACE")
        self.change_command = change_command
        self.reference = ""
        self.preview_photo = None
        self.grid_propagate(False)

        self.preview = tk.Canvas(
            self,
            width=84,
            height=84,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER,
            highlightthickness=1,
            borderwidth=0,
            cursor="hand2",
        )
        self.preview.grid(row=0, column=0, sticky="nw")
        self.preview_image_item = self.preview.create_image(42, 42)
        self.preview_text_item = self.preview.create_text(
            42,
            42,
            text="Add\nimage",
            fill=TEXT_MUTED,
            font=app_font(8),
            justify="center",
            width=70,
        )
        self.clear_item = self.preview.create_text(
            75,
            9,
            text="x",
            fill=TEXT_DARK,
            font=app_font(9),
            state="hidden",
            tags=("clear_image",),
        )
        self.preview.bind("<Button-1>", self.choose)
        self.preview.bind("<Button-3>", self.clear_from_preview)
        self.preview.tag_bind(
            "clear_image", "<Button-1>", self.clear_from_preview
        )
        bind_theme(
            self.preview,
            background="FIELD_BACKGROUND",
            highlightbackground="BORDER",
        )

    def get_value(self):
        return self.reference

    def set_value(self, value):
        try:
            self.reference = normalize_item_image_reference(value)
        except ValueError:
            self.reference = str(value or "").strip()
        self.refresh_preview()

    def choose(self, event=None):
        reference = ItemImageAssetDialog(
            self,
            current_reference=self.reference,
        ).show()
        if reference is None or reference == self.reference:
            return
        self.reference = reference
        self.refresh_preview()
        self.change_command()
        return "break"

    def clear_from_preview(self, event=None):
        self.clear()
        return "break"

    def clear(self, notify=True):
        if not self.reference:
            return
        self.reference = ""
        self.refresh_preview()
        if notify:
            self.change_command()

    def refresh_preview(self):
        self.preview_photo = None
        self.preview.itemconfigure(
            self.clear_item,
            state="normal" if self.reference else "hidden",
        )
        if not self.reference:
            self.set_preview_content(text="Add\nimage")
            return

        try:
            path = resolve_item_image_reference(self.reference)
        except ValueError:
            self.set_preview_content(text="Invalid\nreference")
            return

        if path is None or not path.is_file():
            self.set_preview_content(text="Missing\nimage")
            return

        try:
            with Image.open(path) as source:
                image = source.convert("RGBA")
                image.thumbnail((80, 80), Image.Resampling.LANCZOS)
                image.load()
        except (OSError, UnidentifiedImageError):
            self.set_preview_content(text="Preview\nunavailable")
            return

        self.preview_photo = ImageTk.PhotoImage(image)
        self.set_preview_content(image=self.preview_photo)

    def set_preview_content(self, *, image=None, text=""):
        self.preview.itemconfigure(
            self.preview_image_item,
            image=image or "",
        )
        self.preview.itemconfigure(
            self.preview_text_item,
            text="" if image else text,
        )
