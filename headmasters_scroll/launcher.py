from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .errors import ManifestError
from .manifests import AppManifest, load_manifests
from .paths import PROJECT_ROOT


def command_for(manifest: AppManifest) -> list[str]:
    replacements = {"{python}": sys.executable, "{root}": str(PROJECT_ROOT)}
    command: list[str] = []
    for token in manifest.entry_command:
        expanded = token
        for source, destination in replacements.items():
            expanded = expanded.replace(source, destination)
        command.append(expanded)
    return command


def launch_app(manifest: AppManifest) -> subprocess.Popen:
    if not manifest.enabled:
        raise ValueError(f"{manifest.name} is not enabled")
    return subprocess.Popen(command_for(manifest), cwd=PROJECT_ROOT)


class HomeScreen(tk.Tk):
    def __init__(self, manifests: list[AppManifest] | None = None):
        super().__init__()
        self.title("Headmaster's Scroll")
        self.geometry("680x430")
        self.minsize(560, 340)
        self.configure(background="#17121f")
        self.manifests = manifests if manifests is not None else load_manifests()
        self._build()

    def _build(self) -> None:
        style = ttk.Style(self)
        style.configure("Title.TLabel", font=("Segoe UI", 24, "bold"), foreground="#f0dfad", background="#17121f")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 11), foreground="#c9bdd8", background="#17121f")
        ttk.Label(self, text="Headmaster's Scroll", style="Title.TLabel").pack(pady=(38, 4))
        ttk.Label(self, text="Choose an application", style="Subtitle.TLabel").pack(pady=(0, 24))
        cards = tk.Frame(self, background="#17121f")
        cards.pack(fill="both", expand=True, padx=55)
        for manifest in self.manifests:
            card = tk.Frame(cards, background="#292039", highlightbackground="#493b60", highlightthickness=1)
            card.pack(fill="x", pady=7)
            tk.Label(card, text=manifest.name, font=("Segoe UI", 14, "bold"), foreground="#f4eef8", background="#292039").pack(side="left", padx=18, pady=17)
            label = "Open" if manifest.enabled else "Coming soon"
            button = ttk.Button(card, text=label, state="normal" if manifest.enabled else "disabled", command=lambda app=manifest: self._launch(app))
            button.pack(side="right", padx=16, pady=14)

    def _launch(self, manifest: AppManifest) -> None:
        try:
            launch_app(manifest)
        except OSError as error:
            messagebox.showerror("Could not open app", str(error), parent=self)


def main() -> None:
    try:
        HomeScreen().mainloop()
    except ManifestError as error:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Invalid app configuration", str(error), parent=root)
        root.destroy()


if __name__ == "__main__":
    main()

