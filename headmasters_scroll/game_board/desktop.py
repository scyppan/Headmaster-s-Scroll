from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

from ..paths import PROJECT_ROOT
from .storage import GameBoardRepository


class AdminClient:
    """Small localhost-only client used by the native Headmaster window."""

    def __init__(self, settings: dict[str, Any]):
        self.base_url = f"http://{settings['admin_host']}:{settings['admin_port']}"
        self.admin_key = settings["admin_key"]

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={"X-Admin-Key": self.admin_key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read().decode("utf-8")).get("detail")
            except Exception:
                detail = None
            raise RuntimeError(detail or f"Game Board returned {error.code}") from error
        except urllib.error.URLError as error:
            raise ConnectionError("The local Game Board service is unavailable") from error

    def state(self) -> dict[str, Any]:
        return self.request("GET", "/api/admin/state")


class LocalServer:
    """Starts the communication engine when the desktop app owns it."""

    def __init__(self, client: AdminClient):
        self.client = client
        self.process: subprocess.Popen | None = None

    def ready(self) -> bool:
        try:
            self.client.state()
            return True
        except Exception:
            return False

    def start(self, timeout: float = 12.0) -> None:
        if self.ready():
            return
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.process = subprocess.Popen(
            [sys.executable, "-B", "-m", "headmasters_scroll.game_board.server"],
            cwd=PROJECT_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.ready():
                return
            if self.process.poll() is not None:
                break
            time.sleep(0.2)
        raise RuntimeError(
            "The Game Board communication service could not start. "
            "Install the optional dependencies with: python -m pip install -e .[game-board]"
        )

    def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            self.process.kill()


class GameBoardWindow(tk.Tk):
    PAPER = "#ead7aa"
    LIGHT = "#f8edcf"
    EDGE = "#c9aa71"
    INK = "#382719"
    MUTED = "#765f45"
    ACCENT = "#7b3f2b"
    GREEN = "#49643d"
    RED = "#8a3328"

    def __init__(self, repository: GameBoardRepository | None = None):
        super().__init__()
        self.repository = repository or GameBoardRepository()
        self.settings = self.repository.settings()
        self.client = AdminClient(self.settings)
        self.server = LocalServer(self.client)
        self.state_data: dict[str, Any] = {"contacts": [], "settings": {}, "session": None, "connections": []}
        self.refreshing = False
        self.closing = False
        self.title("Game Board — Headmaster Controls")
        self.geometry("1240x800")
        self.minsize(980, 650)
        self.configure(background=self.PAPER)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._configure_style()
        self._build()
        self.after(100, self._start_server)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=self.PAPER)
        style.configure("Card.TFrame", background=self.LIGHT, relief="solid", borderwidth=1)
        style.configure("TLabel", background=self.PAPER, foreground=self.INK, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=self.LIGHT, foreground=self.INK)
        style.configure("Title.TLabel", background=self.PAPER, foreground=self.INK, font=("Georgia", 26, "bold"))
        style.configure("Section.TLabel", background=self.LIGHT, foreground=self.INK, font=("Georgia", 14, "bold"))
        style.configure("Muted.TLabel", background=self.PAPER, foreground=self.MUTED)
        style.configure("Status.TLabel", background=self.PAPER, foreground=self.ACCENT, font=("Segoe UI", 9, "bold"))
        style.configure("TButton", background=self.ACCENT, foreground="#fff8e7", padding=(10, 7), font=("Segoe UI", 9, "bold"))
        style.map("TButton", background=[("active", "#63311f")])
        style.configure("Quiet.TButton", background=self.EDGE, foreground=self.INK)
        style.configure("Good.TButton", background=self.GREEN, foreground="white")
        style.configure("Danger.TButton", background=self.RED, foreground="white")
        style.configure("TNotebook", background=self.PAPER, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.EDGE, foreground=self.INK, padding=(16, 9), font=("Segoe UI", 9, "bold"))
        style.map("TNotebook.Tab", background=[("selected", self.LIGHT)])
        style.configure("Treeview", background="#fff8e6", fieldbackground="#fff8e6", foreground=self.INK, rowheight=27)
        style.configure("Treeview.Heading", background=self.EDGE, foreground=self.INK, font=("Segoe UI", 9, "bold"))

    def _build(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x", padx=28, pady=(22, 10))
        ttk.Label(header, text="Game Board", style="Title.TLabel").pack(side="left")
        self.server_status = tk.Label(
            header, text="STARTING LOCAL SERVER", background=self.PAPER,
            foreground=self.ACCENT, font=("Segoe UI", 9, "bold"),
        )
        self.server_status.pack(side="right", pady=10)
        tk.Frame(self, height=2, background=self.ACCENT).pack(fill="x", padx=28, pady=(0, 12))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=28, pady=(0, 16))
        self.overview_tab = ttk.Frame(self.notebook)
        self.contacts_tab = ttk.Frame(self.notebook)
        self.session_tab = ttk.Frame(self.notebook)
        self.settings_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.overview_tab, text="Live Room")
        self.notebook.add(self.contacts_tab, text="Players")
        self.notebook.add(self.session_tab, text="Invitations & Session")
        self.notebook.add(self.settings_tab, text="Connection Setup")
        self._build_overview()
        self._build_contacts()
        self._build_session()
        self._build_settings()

        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=28, pady=(0, 18))
        self.notice = tk.Label(footer, text="Starting…", background=self.PAPER, foreground=self.MUTED)
        self.notice.pack(side="left")
        ttk.Button(footer, text="Refresh", style="Quiet.TButton", command=self.refresh).pack(side="right")

    def _card(self, parent: tk.Misc, title: str) -> ttk.Frame:
        card = ttk.Frame(parent, style="Card.TFrame", padding=16)
        ttk.Label(card, text=title, style="Section.TLabel").pack(anchor="w", pady=(0, 10))
        return card

    def _tree(self, parent: tk.Misc, columns: tuple[str, ...], headings: tuple[str, ...]) -> ttk.Treeview:
        tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="extended")
        for column, heading in zip(columns, headings):
            tree.heading(column, text=heading)
            tree.column(column, width=145, minwidth=80, anchor="w")
        tree.pack(fill="both", expand=True)
        return tree

    def _build_overview(self) -> None:
        self.overview_tab.columnconfigure(0, weight=1)
        self.overview_tab.columnconfigure(1, weight=1)
        self.overview_tab.rowconfigure(0, weight=1)
        pending_card = self._card(self.overview_tab, "Waiting for Approval")
        pending_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=8)
        self.pending_tree = self._tree(pending_card, ("name", "requested", "address"), ("Player", "Requested", "Address"))
        row = ttk.Frame(pending_card, style="Card.TFrame")
        row.pack(fill="x", pady=(10, 0))
        ttk.Button(row, text="Approve", style="Good.TButton", command=lambda: self.resolve_pending("approve")).pack(side="left")
        ttk.Button(row, text="Deny", style="Danger.TButton", command=lambda: self.resolve_pending("deny")).pack(side="left", padx=8)

        connected_card = self._card(self.overview_tab, "Currently Logged In")
        connected_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=8)
        self.connections_tree = self._tree(
            connected_card,
            ("name", "quality", "latency", "activity"),
            ("Player", "Quality", "Latency", "Last Activity"),
        )
        ttk.Button(connected_card, text="Revoke & Disconnect", style="Danger.TButton", command=self.revoke_connected).pack(anchor="e", pady=(10, 0))

        announcement_card = self._card(self.overview_tab, "Announcement")
        announcement_card.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.announcement = tk.Text(announcement_card, height=3, wrap="word", background="#fff8e6", foreground=self.INK, relief="solid", borderwidth=1)
        self.announcement.pack(fill="x")
        ttk.Button(announcement_card, text="Send to Connected Players", command=self.send_announcement).pack(anchor="e", pady=(10, 0))

    def _build_contacts(self) -> None:
        form = self._card(self.contacts_tab, "Add Player")
        form.pack(fill="x", pady=8)
        ttk.Label(form, text="Name", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(form, text="Email", style="Card.TLabel").grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.contact_name = ttk.Entry(form)
        self.contact_email = ttk.Entry(form)
        self.contact_name.grid(row=1, column=0, sticky="ew")
        self.contact_email.grid(row=1, column=1, sticky="ew", padx=(12, 0))
        ttk.Button(form, text="Add Player", command=self.add_contact).grid(row=1, column=2, padx=(12, 0))
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)

        card = self._card(self.contacts_tab, "Private Address Book")
        card.pack(fill="both", expand=True, pady=(0, 8))
        self.contacts_tree = self._tree(card, ("name", "email"), ("Player", "Email Address"))
        ttk.Button(card, text="Remove Selected", style="Danger.TButton", command=self.remove_contacts).pack(anchor="e", pady=(10, 0))

    def _build_session(self) -> None:
        create = self._card(self.session_tab, "Create Game Session")
        create.pack(fill="x", pady=8)
        ttk.Label(create, text="Session title", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(create, text="Game day (YYYY-MM-DD)", style="Card.TLabel").grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Label(create, text="Expires", style="Card.TLabel").grid(row=0, column=2, sticky="w", padx=(12, 0))
        self.session_title = ttk.Entry(create)
        self.game_day = ttk.Entry(create, width=14)
        self.expiration = ttk.Entry(create, width=8)
        self.game_day.insert(0, date.today().isoformat())
        self.expiration.insert(0, "23:59")
        self.session_title.grid(row=1, column=0, sticky="ew")
        self.game_day.grid(row=1, column=1, sticky="ew", padx=(12, 0))
        self.expiration.grid(row=1, column=2, sticky="ew", padx=(12, 0))
        self.roster_list = tk.Listbox(create, height=5, selectmode="multiple", exportselection=False, background="#fff8e6", foreground=self.INK)
        self.roster_list.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        ttk.Button(create, text="Create Session", command=self.create_session).grid(row=2, column=3, padx=(12, 0), sticky="s")
        create.columnconfigure(0, weight=2)
        create.columnconfigure(1, weight=1)

        active = self._card(self.session_tab, "Current Session & Invitations")
        active.pack(fill="both", expand=True, pady=(0, 8))
        self.session_summary = ttk.Label(active, text="No active session", style="Card.TLabel")
        self.session_summary.pack(anchor="w", pady=(0, 10))
        self.invites_tree = self._tree(active, ("name", "email", "status"), ("Player", "Email", "Invitation"))
        controls = ttk.Frame(active, style="Card.TFrame")
        controls.pack(fill="x", pady=(10, 0))
        ttk.Button(controls, text="Preview", style="Quiet.TButton", command=self.preview_invite).pack(side="left")
        ttk.Button(controls, text="Send Selected", command=lambda: self.send_invites(False)).pack(side="left", padx=8)
        ttk.Button(controls, text="Send All", command=lambda: self.send_invites(True)).pack(side="left")
        self.pause_button = ttk.Button(controls, text="Pause Admissions", style="Quiet.TButton", command=self.toggle_pause)
        self.pause_button.pack(side="right", padx=8)
        ttk.Button(controls, text="End Session", style="Danger.TButton", command=self.end_session).pack(side="right")

    def _build_settings(self) -> None:
        card = self._card(self.settings_tab, "Connection & Gmail Setup")
        card.pack(fill="both", expand=True, pady=8)
        fields = (
            ("wordpress_player_url", "WordPress Game Board page"),
            ("allowed_origin", "Allowed WordPress origin"),
            ("public_api_base", "Public Game Board address"),
            ("gmail_credentials_path", "Google credentials file"),
            ("gmail_sender", "Sending Gmail address"),
            ("timezone", "Timezone"),
        )
        self.setting_entries: dict[str, ttk.Entry] = {}
        for row, (key, label) in enumerate(fields):
            ttk.Label(card, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=6)
            entry = ttk.Entry(card)
            entry.grid(row=row, column=1, sticky="ew", padx=(18, 0), pady=6)
            self.setting_entries[key] = entry
        card.columnconfigure(1, weight=1)
        controls = ttk.Frame(card, style="Card.TFrame")
        controls.grid(row=len(fields), column=0, columnspan=2, sticky="e", pady=(18, 0))
        ttk.Button(controls, text="Connect Gmail", style="Quiet.TButton", command=self.connect_gmail).pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="Save Settings", command=self.save_settings).pack(side="left")
        self.gmail_status = ttk.Label(card, text="Gmail status: checking…", style="Card.TLabel")
        self.gmail_status.grid(row=len(fields) + 1, column=0, columnspan=2, sticky="w", pady=(14, 0))

    def _start_server(self) -> None:
        self._background(self.server.start, self._server_started)

    def _server_started(self, _result: Any) -> None:
        self.server_status.configure(text="LOCAL SERVER ONLINE", foreground=self.GREEN)
        self.set_notice("Game Board is ready. Tailscale Funnel remains separately controlled.")
        self.refresh()
        self.after(2000, self._poll)

    def _poll(self) -> None:
        if not self.closing:
            self.refresh(silent=True)
            self.after(2000, self._poll)

    def _background(
        self,
        work: Callable[[], Any],
        success: Callable[[Any], None] | None = None,
        *,
        quiet: bool = False,
    ) -> None:
        def runner() -> None:
            try:
                result = work()
            except Exception as error:
                self.after(0, lambda captured=error: self._failed(captured, quiet))
            else:
                if success:
                    self.after(0, lambda: success(result))

        threading.Thread(target=runner, daemon=True).start()

    def _failed(self, error: Exception, quiet: bool) -> None:
        self.refreshing = False
        self.server_status.configure(text="LOCAL SERVER OFFLINE", foreground=self.RED)
        self.set_notice(str(error), error=True)
        if not quiet:
            messagebox.showerror("Game Board", str(error), parent=self)

    def set_notice(self, text: str, error: bool = False) -> None:
        self.notice.configure(text=text, foreground=self.RED if error else self.MUTED)

    def refresh(self, silent: bool = False) -> None:
        if self.refreshing:
            return
        self.refreshing = True

        def done(state: dict[str, Any]) -> None:
            self.refreshing = False
            self.server_status.configure(text="LOCAL SERVER ONLINE", foreground=self.GREEN)
            self.render(state)

        self._background(self.client.state, done, quiet=silent)

    def render(self, state: dict[str, Any]) -> None:
        self.state_data = state
        contacts = state.get("contacts", [])
        self._replace_tree(self.contacts_tree, [(c["id"], (c["name"], c["email"])) for c in contacts])
        current_selection = set(self.roster_list.curselection())
        self.roster_list.delete(0, "end")
        for contact in contacts:
            self.roster_list.insert("end", f"{contact['name']}  —  {contact['email']}")
        for index in current_selection:
            if index < self.roster_list.size():
                self.roster_list.selection_set(index)

        settings = state.get("settings", {})
        for key, entry in self.setting_entries.items():
            if self.focus_get() is not entry:
                entry.delete(0, "end")
                entry.insert(0, settings.get(key, ""))
        gmail = state.get("gmail", {})
        gmail_text = "connected" if gmail.get("connected") else gmail.get("error") or "not connected"
        self.gmail_status.configure(text=f"Gmail status: {gmail_text}")

        session = state.get("session")
        pending_rows: list[tuple[str, tuple[Any, ...]]] = []
        invite_rows: list[tuple[str, tuple[Any, ...]]] = []
        if session:
            self.session_summary.configure(
                text=f"{session['title']}  •  {session['status'].upper()}  •  expires {session['expires_at']}"
            )
            for request in session.get("pending", []):
                if request.get("status") == "pending":
                    pending_rows.append((request["id"], (request["name"], request["requested_at"], request.get("client_ip", ""))))
            for player in session.get("roster", []):
                invite_rows.append((player["contact_id"], (player["name"], player["email"], player["invite_status"])))
            self.pause_button.configure(text="Resume Admissions" if session["status"] == "paused" else "Pause Admissions")
        else:
            self.session_summary.configure(text="No active session")
            self.pause_button.configure(text="Pause Admissions")
        self._replace_tree(self.pending_tree, pending_rows)
        self._replace_tree(self.invites_tree, invite_rows)

        connection_rows = []
        for connection in state.get("connections", []):
            latency = "Measuring" if connection.get("latency_ms") is None else f"{connection['latency_ms']} ms"
            connection_rows.append((connection["contact_id"], (
                connection["name"], connection["quality"].title(), latency, connection["last_activity"]
            )))
        self._replace_tree(self.connections_tree, connection_rows)

    @staticmethod
    def _replace_tree(tree: ttk.Treeview, rows: list[tuple[str, tuple[Any, ...]]]) -> None:
        selected = set(tree.selection())
        tree.delete(*tree.get_children())
        for item_id, values in rows:
            tree.insert("", "end", iid=item_id, values=values)
        for item_id in selected:
            if tree.exists(item_id):
                tree.selection_add(item_id)

    def _api_action(self, method: str, path: str, payload: dict[str, Any] | None, success_message: str) -> None:
        def done(_result: Any) -> None:
            self.set_notice(success_message)
            self.refresh()

        self._background(lambda: self.client.request(method, path, payload), done)

    def add_contact(self) -> None:
        name, email = self.contact_name.get().strip(), self.contact_email.get().strip()
        if not name or not email:
            messagebox.showwarning("Add player", "Enter both a name and email address.", parent=self)
            return
        self._api_action("POST", "/api/admin/contacts", {"name": name, "email": email}, "Player added")
        self.contact_name.delete(0, "end")
        self.contact_email.delete(0, "end")

    def remove_contacts(self) -> None:
        selected = list(self.contacts_tree.selection())
        if not selected or not messagebox.askyesno("Remove players", "Remove the selected players?", parent=self):
            return

        def work() -> None:
            for contact_id in selected:
                self.client.request("DELETE", f"/api/admin/contacts/{contact_id}")

        self._background(work, lambda _value: (self.set_notice("Players removed"), self.refresh()))

    def create_session(self) -> None:
        contacts = self.state_data.get("contacts", [])
        selected = [contacts[index]["id"] for index in self.roster_list.curselection() if index < len(contacts)]
        if not selected:
            messagebox.showwarning("Create session", "Select at least one player.", parent=self)
            return
        payload = {
            "title": self.session_title.get().strip(),
            "game_day": self.game_day.get().strip(),
            "expiration_time": self.expiration.get().strip(),
            "contact_ids": selected,
        }
        self._api_action("POST", "/api/admin/sessions", payload, "Session created")

    def send_invites(self, all_players: bool) -> None:
        session = self.state_data.get("session")
        if not session:
            messagebox.showwarning("Invitations", "Create a session first.", parent=self)
            return
        ids = [p["contact_id"] for p in session["roster"] if not p.get("revoked")] if all_players else list(self.invites_tree.selection())
        if not ids:
            messagebox.showwarning("Invitations", "Select at least one player.", parent=self)
            return

        def done(result: dict[str, Any]) -> None:
            failures = [item for item in result["results"] if not item.get("success")]
            sent = len(result["results"]) - len(failures)
            message = f"{sent} invitation(s) sent"
            if failures:
                message += f"; {len(failures)} failed"
            self.set_notice(message, error=bool(failures))
            self.refresh()

        self._background(lambda: self.client.request("POST", "/api/admin/invitations/send", {"contact_ids": ids}), done)

    def preview_invite(self) -> None:
        session = self.state_data.get("session")
        if not session:
            return
        selected = list(self.invites_tree.selection())
        contact_id = selected[0] if selected else session["roster"][0]["contact_id"]
        player = next(item for item in session["roster"] if item["contact_id"] == contact_id)
        page = self.state_data.get("settings", {}).get("wordpress_player_url") or "[WordPress Game Board page]"
        text = (
            f"To: {player['email']}\n\nHello {player['name']},\n\n"
            f"Use this private link to request admission to {session['title']}:\n\n"
            f"{page}#invite=[private token]\n\nThe Headmaster must approve every connection."
        )
        messagebox.showinfo("Invitation preview", text, parent=self)

    def resolve_pending(self, action: str) -> None:
        selected = list(self.pending_tree.selection())
        if not selected:
            return
        result_word = "approved" if action == "approve" else "denied"
        for request_id in selected:
            self._api_action("POST", f"/api/admin/admissions/{request_id}/{action}", None, f"Admission {result_word}")

    def revoke_connected(self) -> None:
        selected = list(self.connections_tree.selection())
        if not selected:
            return
        if not messagebox.askyesno("Revoke access", "Revoke and disconnect the selected players?", parent=self):
            return
        for contact_id in selected:
            self._api_action("POST", f"/api/admin/players/{contact_id}/revoke", None, "Player disconnected")

    def toggle_pause(self) -> None:
        session = self.state_data.get("session")
        if not session:
            return
        action = "resume" if session["status"] == "paused" else "pause"
        result_word = "resumed" if action == "resume" else "paused"
        self._api_action("POST", f"/api/admin/session/{action}", None, f"Admissions {result_word}")

    def end_session(self) -> None:
        if not self.state_data.get("session"):
            return
        if messagebox.askyesno("End session", "End the session and disconnect every player?", parent=self):
            self._api_action("POST", "/api/admin/session/end", None, "Session ended")

    def send_announcement(self) -> None:
        text = self.announcement.get("1.0", "end").strip()
        if not text:
            return
        self._api_action("POST", "/api/admin/announcements", {"message": text}, "Announcement sent")
        self.announcement.delete("1.0", "end")

    def save_settings(self) -> None:
        payload = {key: entry.get().strip() for key, entry in self.setting_entries.items()}

        def work() -> Any:
            result = self.client.request("PUT", "/api/admin/settings", payload)
            if self.server.process is not None:
                self.server.stop()
                self.server.start()
            return result

        def done(_result: Any) -> None:
            self.set_notice("Settings saved; the local communication service was refreshed")
            self.refresh()

        self._background(work, done)

    def connect_gmail(self) -> None:
        self.set_notice("Complete Google authorization in the browser window.")
        self._api_action("POST", "/api/admin/gmail/authorize", None, "Gmail connected")

    def close(self) -> None:
        self.closing = True
        self.server.stop()
        self.destroy()


def main() -> None:
    GameBoardWindow().mainloop()


if __name__ == "__main__":
    main()
