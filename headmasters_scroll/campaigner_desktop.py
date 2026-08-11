from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

from .campaigns import CampaignRepository, format_game_world_date
from .game_board.desktop import GameWorldDateField
from .windowing import apply_window_icon


class CampaignerWindow(tk.Tk):
    PAPER = "#ead8aa"
    LIGHT = "#fff4d1"
    INK = "#352719"
    ACCENT = "#8b3f2b"

    def __init__(self, repository: CampaignRepository | None = None) -> None:
        super().__init__()
        self.repository = repository or CampaignRepository()
        self.campaigns: list[dict] = []
        self.visible_campaigns: list[dict] = []
        self.selected_campaign_id: str | None = None
        self.title("Campaigner")
        self.geometry("820x480")
        self.minsize(680, 400)
        self.configure(background=self.PAPER)
        apply_window_icon(self)
        self._styles()
        self._build()
        self.reload()

    def _styles(self) -> None:
        style = ttk.Style(self)
        style.configure("Campaigner.TFrame", background=self.PAPER)
        style.configure("Campaigner.Card.TFrame", background=self.LIGHT)
        style.configure("Campaigner.TLabel", background=self.PAPER, foreground=self.INK)
        style.configure(
            "Campaigner.Title.TLabel",
            background=self.PAPER,
            foreground=self.INK,
            font=("Georgia", 20, "bold"),
        )

    def _build(self) -> None:
        shell = ttk.Frame(self, padding=12, style="Campaigner.TFrame")
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(1, weight=1)
        ttk.Label(shell, text="Campaigner", style="Campaigner.Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        left = ttk.Frame(shell, padding=10, style="Campaigner.Card.TFrame")
        left.grid(row=1, column=0, sticky="nsw", padx=(0, 10))
        ttk.Label(left, text="Campaigns", style="Campaigner.TLabel").pack(anchor="w")
        self.search_value = tk.StringVar()
        self.search_value.trace_add("write", lambda *_args: self.render_list())
        ttk.Entry(left, textvariable=self.search_value, width=28).pack(fill="x", pady=(4, 6))
        self.campaign_list = tk.Listbox(
            left,
            width=30,
            height=15,
            exportselection=False,
            background="#fff8e6",
            foreground=self.INK,
            selectbackground=self.ACCENT,
            selectforeground="#fff8e7",
        )
        self.campaign_list.pack(fill="both", expand=True)
        self.campaign_list.bind("<<ListboxSelect>>", self.choose_campaign)
        ttk.Button(left, text="New Campaign", command=self.new_campaign).pack(
            fill="x", pady=(7, 0)
        )

        form = ttk.Frame(shell, padding=18, style="Campaigner.Card.TFrame")
        form.grid(row=1, column=1, sticky="nsew")
        form.columnconfigure(0, weight=1)
        ttk.Label(form, text="Campaign name", style="Campaigner.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.name_value = tk.StringVar()
        ttk.Entry(form, textvariable=self.name_value).grid(
            row=1, column=0, sticky="ew", pady=(3, 14)
        )
        ttk.Label(form, text="Game World Start Date", style="Campaigner.TLabel").grid(
            row=2, column=0, sticky="w"
        )
        self.start_date = GameWorldDateField(form, date.today())
        self.start_date.grid(row=3, column=0, sticky="ew", pady=(3, 5))
        ttk.Label(
            form,
            text="New Game Board sessions begin at 08:00 on this date.",
            style="Campaigner.TLabel",
        ).grid(row=4, column=0, sticky="w")
        self.status = ttk.Label(form, text="", style="Campaigner.TLabel")
        self.status.grid(row=5, column=0, sticky="w", pady=(18, 0))
        actions = ttk.Frame(form, style="Campaigner.Card.TFrame")
        actions.grid(row=6, column=0, sticky="ew", pady=(18, 0))
        ttk.Button(actions, text="Delete", command=self.delete_campaign).pack(side="left")
        ttk.Button(actions, text="Save Campaign", command=self.save_campaign).pack(side="right")

    def reload(self, select_id: str | None = None) -> None:
        try:
            self.campaigns = self.repository.list()
        except Exception as error:
            messagebox.showerror("Campaigner", str(error), parent=self)
            self.campaigns = []
        self.render_list(select_id)

    def render_list(self, select_id: str | None = None) -> None:
        query = self.search_value.get().strip().casefold()
        self.visible_campaigns = [
            item for item in self.campaigns if query in item["name"].casefold()
        ]
        self.campaign_list.delete(0, "end")
        for item in self.visible_campaigns:
            self.campaign_list.insert(
                "end",
                f"{item['name']}  —  {format_game_world_date(item['game_world_start_date'])}",
            )
        target = select_id or self.selected_campaign_id
        for index, item in enumerate(self.visible_campaigns):
            if item["record_id"] == target:
                self.campaign_list.selection_set(index)
                self.campaign_list.see(index)
                break

    def choose_campaign(self, _event: tk.Event | None = None) -> None:
        selected = self.campaign_list.curselection()
        if not selected:
            return
        campaign = self.visible_campaigns[selected[0]]
        self.selected_campaign_id = campaign["record_id"]
        self.name_value.set(campaign["name"])
        self.start_date.set_iso(campaign["game_world_start_date"])
        self.status.configure(text="Editing campaign metadata")

    def new_campaign(self) -> None:
        self.selected_campaign_id = None
        self.campaign_list.selection_clear(0, "end")
        self.name_value.set("")
        self.start_date.set_iso(date.today().isoformat())
        self.status.configure(text="Creating a new campaign")

    def save_campaign(self) -> None:
        try:
            campaign = self.repository.save_campaign(
                self.name_value.get(),
                self.start_date.get_iso(),
                self.selected_campaign_id,
            )
        except Exception as error:
            messagebox.showerror("Campaigner", str(error), parent=self)
            return
        self.selected_campaign_id = campaign["record_id"]
        self.status.configure(text="Campaign saved")
        self.reload(campaign["record_id"])

    def delete_campaign(self) -> None:
        if not self.selected_campaign_id:
            return
        if not messagebox.askyesno(
            "Delete campaign",
            "Delete this campaign metadata? Existing session summaries will remain.",
            parent=self,
        ):
            return
        try:
            self.repository.delete(self.selected_campaign_id)
        except Exception as error:
            messagebox.showerror("Campaigner", str(error), parent=self)
            return
        self.new_campaign()
        self.reload()


def main() -> None:
    CampaignerWindow().mainloop()
