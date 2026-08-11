from __future__ import annotations

import calendar
import hashlib
import re
import threading
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from secrets import token_urlsafe
from typing import Any
from urllib.parse import quote, urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from ..store import SharedJsonStore
from ..board import WorldBoardRepository
from .storage import GameBoardRepository


EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GAME_DATETIME = re.compile(
    r"^(?P<year>-?[1-9]\d*)-(?P<month>\d{2})-(?P<day>\d{2})T"
    r"(?P<hour>\d{2}):(?P<minute>\d{2})$"
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def normalize_game_datetime(value: str | None, fallback_date: str) -> str:
    """Validate and normalize a timezone-free in-world date and 24-hour time."""

    raw = value.strip() if isinstance(value, str) else ""
    if not raw:
        raw = f"{fallback_date}T08:00"
    match = GAME_DATETIME.fullmatch(raw)
    if not match:
        raise ValueError("Game World Date and time must use YYYY-MM-DD and a 24-hour HH:MM time")
    try:
        values = {key: int(part) for key, part in match.groupdict().items()}
        if values["year"] == 0 or not 1 <= values["month"] <= 12:
            raise ValueError
        if not 1 <= values["day"] <= calendar.monthrange(values["year"], values["month"])[1]:
            raise ValueError
        if not 0 <= values["hour"] <= 23 or not 0 <= values["minute"] <= 59:
            raise ValueError
    except (TypeError, ValueError) as error:
        raise ValueError("Game World Date and time must use YYYY-MM-DD and a 24-hour HH:MM time") from error
    year = f"-{abs(values['year']):04d}" if values["year"] < 0 else f"{values['year']:04d}"
    return (
        f"{year}-{values['month']:02d}-{values['day']:02d}T"
        f"{values['hour']:02d}:{values['minute']:02d}"
    )


def format_game_datetime_for_people(value: str) -> str:
    normalized = normalize_game_datetime(value, date.today().isoformat())
    match = GAME_DATETIME.fullmatch(normalized)
    if match is None:
        return normalized
    values = {key: int(part) for key, part in match.groupdict().items()}
    year = f"{abs(values['year'])} BCE" if values["year"] < 0 else str(values["year"])
    return (
        f"{values['day']:02d} {calendar.month_abbr[values['month']]} {year} "
        f"at {values['hour']:02d}:{values['minute']:02d}"
    )


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class GameBoardService:
    def __init__(self, repository: GameBoardRepository | None = None):
        self.repository = repository or GameBoardRepository()
        self.shared_store = SharedJsonStore()
        self.world_board = WorldBoardRepository(self.shared_store)
        self._lock = threading.RLock()
        self._tickets: dict[str, dict[str, Any]] = {}
        self._ticket_by_request: dict[str, str] = {}
        self._restore_for_reapproval()

    def _restore_for_reapproval(self) -> None:
        with self._lock:
            wrapper = self.repository.active()
            changed = False
            for session in wrapper.get("sessions", []):
                session.setdefault("board_control_grants", {})
                if not session.get("game_datetime"):
                    fallback_date = (
                        session.get("event_date")
                        or session.get("game_day")
                        or date.today().isoformat()
                    )
                    session["game_datetime"] = normalize_game_datetime(None, fallback_date)
                    changed = True
                for request in session.get("pending", []):
                    if request.get("status") in {"approved", "ticket_issued", "connected"}:
                        request["status"] = "pending"
                        request.pop("approved_at", None)
                        request.pop("connected_at", None)
                        changed = True
            if changed:
                self.repository.save_active(wrapper)

    def list_contacts(self) -> list[dict[str, Any]]:
        contacts = deepcopy(self.repository.contacts()["contacts"])
        for contact in contacts:
            contact["display_name"] = contact.get("character_name") or contact["name"]
        return contacts

    def list_characters(self) -> list[dict[str, str]]:
        world = self.shared_store.load("world.json").data
        characters = []
        for person in world.get("people", []):
            record_id = person.get("record_id")
            name = str(person.get("displayed_name") or "").strip()
            if isinstance(record_id, str) and record_id and name:
                characters.append({"id": record_id, "name": name})
        return sorted(characters, key=lambda item: (item["name"].casefold(), item["id"]))

    def add_contact(self, name: str, email: str) -> dict[str, str]:
        name, email = name.strip(), email.strip().lower()
        if not name:
            raise ValueError("Player name is required")
        if not EMAIL.fullmatch(email):
            raise ValueError("A valid email address is required")
        with self._lock:
            value = self.repository.contacts()
            if any(contact["email"].lower() == email for contact in value["contacts"]):
                raise ValueError("That email address is already in the address book")
            contact = {
                "id": str(uuid4()), "name": name, "email": email,
                "character_id": None, "character_name": None,
            }
            value["contacts"].append(contact)
            self.repository.save_contacts(value)
            return deepcopy(contact)

    def update_contact(self, contact_id: str, name: str, email: str) -> dict[str, str]:
        name, email = name.strip(), email.strip().lower()
        if not name or not EMAIL.fullmatch(email):
            raise ValueError("A player name and valid email address are required")
        with self._lock:
            value = self.repository.contacts()
            contact = next((item for item in value["contacts"] if item["id"] == contact_id), None)
            if contact is None:
                raise KeyError("Unknown contact")
            if any(item["id"] != contact_id and item["email"].lower() == email for item in value["contacts"]):
                raise ValueError("That email address is already in the address book")
            contact.update(name=name, email=email)
            self.repository.save_contacts(value)
            return deepcopy(contact)

    def assign_character(self, contact_id: str, character_id: str | None) -> dict[str, Any]:
        characters = {item["id"]: item for item in self.list_characters()}
        if character_id is not None and character_id not in characters:
            raise ValueError("Choose a character from the shared world data")
        with self._lock:
            contacts = self.repository.contacts()
            contact = next((item for item in contacts["contacts"] if item["id"] == contact_id), None)
            if contact is None:
                raise KeyError("Unknown contact")
            if character_id and any(
                item["id"] != contact_id and item.get("character_id") == character_id
                for item in contacts["contacts"]
            ):
                raise ValueError("That character is already linked to another player")
            character_name = characters[character_id]["name"] if character_id else None
            contact["character_id"] = character_id
            contact["character_name"] = character_name
            self.repository.save_contacts(contacts)

            wrapper = self.repository.active()
            sessions_changed = False
            for session in wrapper.get("sessions", []):
                player = next(
                    (item for item in session.get("roster", []) if item["contact_id"] == contact_id),
                    None,
                )
                if player:
                    display_name = character_name or contact["name"]
                    player.update(
                        account_name=contact["name"],
                        character_id=character_id,
                        character_name=character_name,
                        name=display_name,
                    )
                    for request in session.get("pending", []):
                        if request.get("contact_id") == contact_id:
                            request["name"] = display_name
                    for message in session.get("chat", []):
                        if message.get("sender_id") == contact_id:
                            message["sender_name"] = display_name
                    sessions_changed = True
            if sessions_changed:
                self.repository.save_active(wrapper)
            result = deepcopy(contact)
            result["display_name"] = character_name or contact["name"]
            return result

    def delete_contact(self, contact_id: str) -> None:
        with self._lock:
            value = self.repository.contacts()
            updated = [item for item in value["contacts"] if item["id"] != contact_id]
            if len(updated) == len(value["contacts"]):
                raise KeyError("Unknown contact")
            value["contacts"] = updated
            self.repository.save_contacts(value)

    def settings(self, include_private: bool = False) -> dict[str, Any]:
        value = deepcopy(self.repository.settings())
        # Older settings may have the WordPress page but no separately saved
        # origin. Derive it so CORS remains safe and the browser can reconnect.
        if not value.get("allowed_origin") and value.get("wordpress_player_url"):
            try:
                self._validate_https_url(value["wordpress_player_url"], "WordPress player URL")
                value["allowed_origin"] = self._origin(value["wordpress_player_url"])
            except ValueError:
                pass
        if not include_private:
            value.pop("admin_key", None)
        return value

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "wordpress_player_url", "allowed_origin", "public_api_base",
            "gmail_credentials_path", "gmail_sender", "timezone",
        }
        with self._lock:
            value = self.repository.settings()
            for key in allowed:
                if key in updates:
                    if not isinstance(updates[key], str):
                        raise ValueError(f"{key} must be text")
                    value[key] = updates[key].strip()
            credentials_path = value["gmail_credentials_path"]
            if len(credentials_path) >= 2 and credentials_path[0] == credentials_path[-1] and credentials_path[0] in {'"', "'"}:
                value["gmail_credentials_path"] = credentials_path[1:-1].strip()
            ZoneInfo(value["timezone"])
            self._validate_https_url(value["wordpress_player_url"], "WordPress player URL")
            origin_source = value["wordpress_player_url"] or value["allowed_origin"]
            self._validate_https_url(origin_source, "Allowed origin")
            value["allowed_origin"] = self._origin(origin_source)
            self._validate_https_url(value["public_api_base"], "Public API URL")
            value["public_api_base"] = self._origin(value["public_api_base"])
            if value["gmail_sender"] and not EMAIL.fullmatch(value["gmail_sender"]):
                raise ValueError("The Gmail sender address is invalid")
            self.repository.save_settings(value)
            return self.settings()

    def update_gmail_settings(self, credentials_path: str, sender: str = "") -> dict[str, Any]:
        """Save Gmail setup without requiring unrelated connection fields to be complete."""
        if not isinstance(credentials_path, str) or not isinstance(sender, str):
            raise ValueError("Gmail settings must be text")
        credentials_path = credentials_path.strip()
        sender = sender.strip()
        if len(credentials_path) >= 2 and credentials_path[0] == credentials_path[-1] and credentials_path[0] in {'"', "'"}:
            credentials_path = credentials_path[1:-1].strip()
        if sender and not EMAIL.fullmatch(sender):
            raise ValueError("The Gmail sender address is invalid")
        with self._lock:
            value = self.repository.settings()
            value["gmail_credentials_path"] = credentials_path
            value["gmail_sender"] = sender
            self.repository.save_settings(value)
            return self.settings()

    @staticmethod
    def _validate_https_url(value: str, label: str, origin_only: bool = False) -> None:
        if not value:
            return
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"{label} must be an https:// URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError(f"{label} cannot contain credentials, a query, or a fragment")
        if origin_only and parsed.path not in {"", "/"}:
            raise ValueError(f"{label} must contain only its scheme and hostname")

    @staticmethod
    def _origin(value: str) -> str:
        if not value:
            return ""
        parsed = urlsplit(value)
        return f"{parsed.scheme}://{parsed.netloc}"

    def create_session(
        self,
        title: str,
        game_day: str,
        contact_ids: list[str],
        expiration_time: str = "23:59",
        event_date: str | None = None,
        game_datetime: str | None = None,
    ) -> dict[str, Any]:
        title = title.strip()
        if not title:
            raise ValueError("Session title is required")
        if not contact_ids:
            raise ValueError("Select at least one player")
        if len(set(contact_ids)) != len(contact_ids) or len(contact_ids) > 9:
            raise ValueError("A session supports one to nine unique players")
        cleaned_event_date = event_date.strip() if isinstance(event_date, str) else ""
        if cleaned_event_date:
            try:
                date.fromisoformat(cleaned_event_date)
            except ValueError as error:
                raise ValueError("Event date must use YYYY-MM-DD") from error
        cleaned_game_datetime = normalize_game_datetime(
            game_datetime, cleaned_event_date or game_day
        )
        settings = self.repository.settings()
        local_expiration = datetime.combine(
            date.fromisoformat(game_day), time.fromisoformat(expiration_time), ZoneInfo(settings["timezone"])
        )
        if local_expiration <= datetime.now(ZoneInfo(settings["timezone"])):
            raise ValueError("Expiration must be in the future")
        contacts = {item["id"]: item for item in self.list_contacts()}
        if any(contact_id not in contacts for contact_id in contact_ids):
            raise ValueError("The roster contains an unknown contact")
        with self._lock:
            wrapper = self.repository.active()
            session = {
                "id": str(uuid4()),
                "title": title,
                "status": "active",
                "event_date": cleaned_event_date or None,
                "game_datetime": cleaned_game_datetime,
                "game_day": game_day,
                "expiration_time": expiration_time,
                "created_at": iso_utc(utc_now()),
                "expires_at": iso_utc(local_expiration),
                "roster": [self._roster_entry(contacts[item]) for item in contact_ids],
                "pending": [],
                "chat": [],
                "announcement_count": 0,
                "board_control_grants": {},
            }
            wrapper["sessions"].append(session)
            self.repository.save_active(wrapper)
            return self.session_view(session["id"])

    @staticmethod
    def _roster_entry(contact: dict[str, Any]) -> dict[str, Any]:
        character_name = contact.get("character_name")
        return {
            "contact_id": contact["id"],
            "account_name": contact["name"],
            "character_id": contact.get("character_id"),
            "character_name": character_name,
            "name": character_name or contact["name"],
            "email": contact["email"],
            "invite_hash": None, "invite_status": "not_sent", "sent_at": None,
            "has_logged_in": False, "last_connected_at": None,
            "revoked": False,
            "stats": {
                "approvals": 0, "disconnects": 0, "acknowledgements": 0,
                "connected_seconds": 0.0, "latency_total_ms": 0.0, "latency_samples": 0,
            },
        }

    @staticmethod
    def _session(wrapper: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
        sessions = wrapper.get("sessions", [])
        if session_id is None:
            if not sessions:
                raise ValueError("There is no active session")
            return sessions[0]
        session = next((item for item in sessions if item.get("id") == session_id), None)
        if session is None:
            raise KeyError("Unknown session")
        return session

    @staticmethod
    def _session_for_request(wrapper: dict[str, Any], request_id: str) -> dict[str, Any]:
        session = next(
            (
                item
                for item in wrapper.get("sessions", [])
                if any(request.get("id") == request_id for request in item.get("pending", []))
            ),
            None,
        )
        if session is None:
            raise KeyError("Unknown admission request")
        return session

    def _active(self, session_id: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        wrapper = self.repository.active()
        session = self._session(wrapper, session_id)
        if parse_utc(session["expires_at"]) <= utc_now():
            self.end_session("expired", session["id"])
            raise ValueError("The session has expired")
        return wrapper, session

    @staticmethod
    def _public_session(session: dict[str, Any]) -> dict[str, Any]:
        view = deepcopy(session)
        for player in view.get("roster", []):
            player.pop("invite_hash", None)
        for request in view.get("pending", []):
            request.pop("poll_hash", None)
        return view

    def sessions_view(self) -> list[dict[str, Any]]:
        with self._lock:
            wrapper = self.repository.active()
            return [self._public_session(session) for session in wrapper.get("sessions", [])]

    def session_view(self, session_id: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            wrapper = self.repository.active()
            if not wrapper.get("sessions"):
                return None
            return self._public_session(self._session(wrapper, session_id))

    def duplicate_session(self, session_id: str) -> dict[str, Any]:
        original = self.session_view(session_id)
        if original is None:
            raise KeyError("Unknown session")
        local_expiration = parse_utc(original["expires_at"]).astimezone(
            ZoneInfo(self.repository.settings()["timezone"])
        )
        return self.create_session(
            f"{original['title']} Copy",
            original.get("game_day") or local_expiration.date().isoformat(),
            [player["contact_id"] for player in original["roster"]],
            original.get("expiration_time") or local_expiration.strftime("%H:%M"),
            original.get("event_date"),
            original.get("game_datetime"),
        )

    def delete_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            wrapper = self.repository.active()
            session = self._session(wrapper, session_id)
            wrapper["sessions"] = [item for item in wrapper["sessions"] if item["id"] != session_id]
            self._drop_tickets_for_session(session_id)
            self.repository.save_active(wrapper)
            return self._public_session(session)

    def remove_player(self, session_id: str, contact_id: str) -> dict[str, Any]:
        with self._lock:
            wrapper, session = self._active(session_id)
            before = len(session["roster"])
            session["roster"] = [item for item in session["roster"] if item["contact_id"] != contact_id]
            if len(session["roster"]) == before:
                raise KeyError("Unknown session player")
            removed_requests = {
                request["id"] for request in session["pending"] if request["contact_id"] == contact_id
            }
            session["pending"] = [
                request for request in session["pending"] if request["contact_id"] != contact_id
            ]
            for request_id in removed_requests:
                ticket = self._ticket_by_request.pop(request_id, None)
                if ticket:
                    self._tickets.pop(token_hash(ticket), None)
            self.repository.save_active(wrapper)
            return self._public_session(session)

    def prepare_invite(
        self, contact_id: str, session_id: str | None = None
    ) -> tuple[str, str, dict[str, Any]]:
        with self._lock:
            wrapper, session = self._active(session_id)
            player = self._player(session, contact_id)
            if player["revoked"]:
                raise ValueError("That player's access has been revoked")
            settings = self.repository.settings()
            base = settings["wordpress_player_url"].split("#", 1)[0]
            if not base:
                raise ValueError("Configure the WordPress player URL before sending invitations")
            raw = token_urlsafe(32)
            player["invite_hash"] = token_hash(raw)
            player["invite_status"] = "prepared"
            self.repository.save_active(wrapper)
            return raw, f"{base}#invite={quote(raw)}", deepcopy(player)

    def record_invite_result(
        self, contact_id: str, success: bool, session_id: str | None = None
    ) -> None:
        with self._lock:
            wrapper, session = self._active(session_id)
            player = self._player(session, contact_id)
            player["invite_status"] = "sent" if success else "failed"
            if success:
                player["sent_at"] = iso_utc(utc_now())
            self.repository.save_active(wrapper)

    def request_admission(self, invite_token: str, client_ip: str, user_agent: str) -> dict[str, str]:
        if not invite_token or len(invite_token) > 256:
            raise ValueError("Invalid invitation")
        with self._lock:
            wrapper = self.repository.active()
            digest = token_hash(invite_token)
            session = next(
                (
                    item
                    for item in wrapper.get("sessions", [])
                    if any(player.get("invite_hash") == digest for player in item.get("roster", []))
                ),
                None,
            )
            if session is None:
                raise PermissionError("Invalid or revoked invitation")
            if parse_utc(session["expires_at"]) <= utc_now():
                self.end_session("expired", session["id"])
                raise ValueError("The session has expired")
            if session["status"] == "paused":
                raise PermissionError("Admissions are paused")
            player = next((item for item in session["roster"] if item.get("invite_hash") == digest), None)
            if player is None or player["revoked"]:
                raise PermissionError("Invalid or revoked invitation")
            existing = next((item for item in session["pending"] if item["contact_id"] == player["contact_id"] and item["status"] in {"pending", "approved", "ticket_issued", "connected"}), None)
            if existing and existing["status"] == "ticket_issued":
                ticket = self._ticket_by_request.get(existing["id"])
                details = self._tickets.get(token_hash(ticket)) if ticket else None
                if details is None or details["expires_at"] <= utc_now():
                    if ticket:
                        self._tickets.pop(token_hash(ticket), None)
                    self._ticket_by_request.pop(existing["id"], None)
                    existing["status"] = "disconnected"
                    existing["disconnected_at"] = iso_utc(utc_now())
                    existing = None
            if existing:
                # Repeating the same valid invitation resumes the active request
                # instead of consuming rate-limit attempts or stranding the player.
                poll_token = token_urlsafe(32)
                existing["poll_hash"] = token_hash(poll_token)
                self.repository.save_active(wrapper)
                return {
                    "request_id": existing["id"],
                    "poll_token": poll_token,
                    "status": existing["status"],
                    "session_id": session["id"],
                }
            poll_token = token_urlsafe(32)
            request = {
                "id": str(uuid4()), "contact_id": player["contact_id"], "name": player["name"],
                "status": "pending", "requested_at": iso_utc(utc_now()),
                "poll_hash": token_hash(poll_token), "client_ip": client_ip[:128],
                "user_agent": user_agent[:300],
            }
            session["pending"].append(request)
            self.repository.save_active(wrapper)
            return {
                "request_id": request["id"], "poll_token": poll_token,
                "status": "pending", "session_id": session["id"],
            }

    def poll_admission(self, request_id: str, poll_token: str) -> dict[str, Any]:
        with self._lock:
            wrapper = self.repository.active()
            session = self._session_for_request(wrapper, request_id)
            if parse_utc(session["expires_at"]) <= utc_now():
                self.end_session("expired", session["id"])
                raise ValueError("The session has expired")
            request = self._request(session, request_id)
            if not poll_token or token_hash(poll_token) != request["poll_hash"]:
                raise PermissionError("Invalid polling credential")
            response: dict[str, Any] = {"status": request["status"], "player_name": request["name"]}
            if request["status"] in {"approved", "ticket_issued"}:
                ticket = self._ticket_by_request.get(request_id)
                details = self._tickets.get(token_hash(ticket)) if ticket else None
                if ticket and (details is None or details["expires_at"] <= utc_now()):
                    self._tickets.pop(token_hash(ticket), None)
                    self._ticket_by_request.pop(request_id, None)
                    request["status"] = "disconnected"
                    request["disconnected_at"] = iso_utc(utc_now())
                    self.repository.save_active(wrapper)
                    return {"status": "disconnected", "player_name": request["name"]}
                if ticket is None:
                    ticket = token_urlsafe(32)
                    self._ticket_by_request[request_id] = ticket
                    self._tickets[token_hash(ticket)] = {
                        "request_id": request_id,
                        "contact_id": request["contact_id"],
                        "session_id": session["id"],
                        "expires_at": utc_now() + timedelta(seconds=60),
                    }
                request["status"] = "ticket_issued"
                self.repository.save_active(wrapper)
                response.update(status="approved", ticket=ticket, expires_in=60)
            return response

    def approve(self, request_id: str) -> None:
        with self._lock:
            wrapper = self.repository.active()
            session = self._session_for_request(wrapper, request_id)
            request = self._request(session, request_id)
            if request["status"] != "pending":
                raise ValueError("Only pending requests can be approved")
            request["status"] = "approved"
            request["approved_at"] = iso_utc(utc_now())
            self._player(session, request["contact_id"])["stats"]["approvals"] += 1
            self.repository.save_active(wrapper)

    def deny(self, request_id: str) -> None:
        with self._lock:
            wrapper = self.repository.active()
            session = self._session_for_request(wrapper, request_id)
            request = self._request(session, request_id)
            if request["status"] != "pending":
                raise ValueError("Only pending requests can be denied")
            request["status"] = "denied"
            request["resolved_at"] = iso_utc(utc_now())
            self.repository.save_active(wrapper)

    def consume_ticket(self, raw_ticket: str) -> dict[str, Any]:
        with self._lock:
            details = self._tickets.pop(token_hash(raw_ticket), None)
            if details is None or details["expires_at"] < utc_now():
                raise PermissionError("Invalid or expired WebSocket ticket")
            self._ticket_by_request.pop(details["request_id"], None)
            wrapper, session = self._active(details["session_id"])
            request = self._request(session, details["request_id"])
            player = self._player(session, details["contact_id"])
            if request["status"] != "ticket_issued" or player["revoked"]:
                raise PermissionError("Admission is no longer valid")
            request["status"] = "connected"
            request["connected_at"] = iso_utc(utc_now())
            player["has_logged_in"] = True
            player["last_connected_at"] = request["connected_at"]
            self.repository.save_active(wrapper)
            return {
                "request_id": request["id"],
                "contact_id": player["contact_id"],
                "character_id": player.get("character_id"),
                "name": player["name"],
                "session_id": session["id"],
                "session_title": session["title"],
            }

    def board_snapshot(
        self,
        session_id: str | None = None,
        *,
        for_players: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            wrapper, session = self._active(session_id)
            character_ids = [
                str(player.get("character_id"))
                for player in session.get("roster", [])
                if player.get("character_id")
            ]
            snapshot = self.world_board.snapshot(
                str(session.get("game_datetime")),
                player_character_ids=character_ids,
                for_players=for_players,
            )
            snapshot["session_id"] = session["id"]
            return snapshot

    def controlled_character_ids(
        self,
        session_id: str,
        contact_id: str,
    ) -> set[str]:
        with self._lock:
            wrapper, session = self._active(session_id)
            player = self._player(session, contact_id)
            controlled = {
                str(player.get("character_id"))
                for _ in (0,)
                if player.get("character_id")
            }
            grants = session.get("board_control_grants", {}).get(
                contact_id,
                [],
            )
            controlled.update(str(value) for value in grants if value)
            return controlled

    def move_person(
        self,
        session_id: str,
        person_id: str,
        map_id: str,
        x: float,
        y: float,
        *,
        contact_id: str | None = None,
    ) -> dict[str, Any]:
        if contact_id is not None and person_id not in self.controlled_character_ids(
            session_id,
            contact_id,
        ):
            raise PermissionError("You do not control that token")
        return self.world_board.move_person(person_id, map_id, x, y)

    def update_person_board(
        self,
        person_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        return self.world_board.update_person_board(person_id, updates)

    def set_map_published(self, map_id: str, published: bool) -> dict[str, Any]:
        return self.world_board.set_map_published(map_id, published)

    def set_map_presentation(
        self,
        map_id: str,
        *,
        published: bool,
        obscurations: list[dict[str, Any]],
        preview_opacity: float,
        preview_color: str,
    ) -> dict[str, Any]:
        return self.world_board.set_map_presentation(
            map_id,
            published=published,
            obscurations=obscurations,
            preview_opacity=preview_opacity,
            preview_color=preview_color,
        )

    def travel_person(
        self,
        session_id: str,
        contact_id: str,
        person_id: str,
        source_map_id: str,
        region_id: str,
        x: float,
        y: float,
    ) -> dict[str, Any]:
        if person_id not in self.controlled_character_ids(session_id, contact_id):
            raise PermissionError("You do not control that token")
        return self.world_board.travel_person(
            person_id,
            source_map_id,
            region_id,
            x,
            y,
        )

    def create_board_group(
        self,
        name: str,
        location_id: str,
        person_ids: list[str],
    ) -> dict[str, Any]:
        return self.world_board.create_group(name, location_id, person_ids)

    def set_board_group(
        self,
        person_id: str,
        group_id: str | None,
    ) -> dict[str, Any] | None:
        return self.world_board.set_group(person_id, group_id)

    def grant_board_control(
        self,
        session_id: str,
        contact_id: str,
        person_id: str,
        granted: bool,
    ) -> dict[str, Any]:
        with self._lock:
            wrapper, session = self._active(session_id)
            self._player(session, contact_id)
            world_people = {
                item["id"] for item in self.list_characters()
            }
            if person_id not in world_people:
                raise KeyError("Unknown character")
            grants = session.setdefault("board_control_grants", {})
            values = set(grants.get(contact_id, []))
            if granted:
                values.add(person_id)
            else:
                values.discard(person_id)
            grants[contact_id] = sorted(values)
            self.repository.save_active(wrapper)
            return {
                "contact_id": contact_id,
                "character_ids": grants[contact_id],
            }

    def resolve_player_asset(
        self,
        session_id: str,
        asset_id: str,
    ) -> tuple[Any, str]:
        snapshot = self.board_snapshot(session_id, for_players=True)
        authorized_map_ids = {
            str(map_record.get("record_id"))
            for map_record in snapshot.get("maps", [])
        }
        world = self.world_board.load().data
        for map_record in world.get("maps", []):
            metadata = map_record.get("asset")
            if (
                str(map_record.get("record_id")) in authorized_map_ids
                and isinstance(metadata, dict)
                and metadata.get("asset_id") == asset_id
            ):
                return self.world_board.assets.resolve(asset_id, metadata), str(
                    metadata.get("mime_type", "application/octet-stream")
                )
        if any(
            actor.get("portrait_asset_id") == asset_id
            for actor in snapshot.get("actors", [])
        ):
            for person in world.get("people", []):
                portrait = (person.get("board") or {}).get("portrait")
                if isinstance(portrait, dict) and portrait.get("asset_id") == asset_id:
                    return self.world_board.assets.resolve(asset_id, portrait), str(
                        portrait.get("mime_type", "application/octet-stream")
                    )
        raise PermissionError("That asset is not available to this session")

    def mark_disconnected(
        self,
        request_id: str,
        connected_seconds: float = 0.0,
        latency_total_ms: float = 0.0,
        latency_samples: int = 0,
    ) -> None:
        with self._lock:
            try:
                wrapper = self.repository.active()
                session = self._session_for_request(wrapper, request_id)
                request = self._request(session, request_id)
            except (ValueError, KeyError):
                return
            request["status"] = "disconnected"
            request["disconnected_at"] = iso_utc(utc_now())
            stats = self._player(session, request["contact_id"])["stats"]
            stats["disconnects"] += 1
            stats["connected_seconds"] += max(0.0, connected_seconds)
            stats["latency_total_ms"] += max(0.0, latency_total_ms)
            stats["latency_samples"] += max(0, latency_samples)
            self.repository.save_active(wrapper)

    def record_acknowledgement(self, contact_id: str, session_id: str | None = None) -> None:
        with self._lock:
            wrapper, session = self._active(session_id)
            self._player(session, contact_id)["stats"]["acknowledgements"] += 1
            self.repository.save_active(wrapper)

    def post_chat(
        self,
        sender_id: str,
        sender_name: str,
        sender_role: str,
        text: str,
        session_id: str | None = None,
    ) -> dict[str, str]:
        text = text.strip()
        if not text:
            raise ValueError("Chat messages cannot be empty")
        if len(text) > 500:
            raise ValueError("Chat messages are limited to 500 characters")
        if sender_role not in {"player", "headmaster", "system"}:
            raise ValueError("Unknown chat sender")
        with self._lock:
            wrapper, session = self._active(session_id)
            if sender_role == "player":
                player = self._player(session, sender_id)
                if player["revoked"]:
                    raise PermissionError("Access has been revoked")
                sender_name = player["name"]
            message = {
                "id": str(uuid4()),
                "sender_id": sender_id,
                "sender_name": sender_name.strip()[:100] or "Headmaster",
                "sender_role": sender_role,
                "text": text,
                "sent_at": iso_utc(utc_now()),
            }
            chat = session.setdefault("chat", [])
            chat.append(message)
            del chat[:-100]
            self.repository.save_active(wrapper)
            return deepcopy(message)

    def revoke(self, contact_id: str, session_id: str | None = None) -> None:
        with self._lock:
            wrapper, session = self._active(session_id)
            player = self._player(session, contact_id)
            player.update(revoked=True, invite_hash=None, invite_status="revoked")
            for request in session["pending"]:
                if request["contact_id"] == contact_id and request["status"] not in {"denied", "disconnected"}:
                    request["status"] = "revoked"
            self.repository.save_active(wrapper)

    def set_event_date(
        self, event_date: str | None, session_id: str | None = None
    ) -> dict[str, Any]:
        cleaned = event_date.strip() if isinstance(event_date, str) else ""
        if cleaned:
            try:
                date.fromisoformat(cleaned)
            except ValueError as error:
                raise ValueError("Event date must use YYYY-MM-DD") from error
        with self._lock:
            wrapper, session = self._active(session_id)
            session["event_date"] = cleaned or None
            self.repository.save_active(wrapper)
            return self.session_view(session["id"])

    def set_game_datetime(self, session_id: str, game_datetime: str) -> dict[str, Any]:
        with self._lock:
            wrapper, session = self._active(session_id)
            fallback_date = (
                session.get("event_date")
                or session.get("game_day")
                or date.today().isoformat()
            )
            session["game_datetime"] = normalize_game_datetime(
                game_datetime, fallback_date
            )
            self.repository.save_active(wrapper)
            return self._public_session(session)

    def set_paused(self, paused: bool, session_id: str | None = None) -> None:
        with self._lock:
            wrapper, session = self._active(session_id)
            session["status"] = "paused" if paused else "active"
            self.repository.save_active(wrapper)

    def increment_announcements(self, session_id: str | None = None) -> None:
        with self._lock:
            wrapper, session = self._active(session_id)
            session["announcement_count"] += 1
            self.repository.save_active(wrapper)

    def _drop_tickets_for_session(self, session_id: str) -> None:
        request_ids = [
            request_id
            for request_id, raw_ticket in self._ticket_by_request.items()
            if (self._tickets.get(token_hash(raw_ticket)) or {}).get("session_id") == session_id
        ]
        for request_id in request_ids:
            raw_ticket = self._ticket_by_request.pop(request_id, None)
            if raw_ticket:
                self._tickets.pop(token_hash(raw_ticket), None)

    def end_session(
        self, reason: str = "ended", session_id: str | None = None
    ) -> dict[str, Any]:
        with self._lock:
            wrapper = self.repository.active()
            session = self._session(wrapper, session_id)
            ended_at = iso_utc(utc_now())
            summary = {
                "id": session["id"], "title": session["title"], "created_at": session["created_at"],
                "event_date": session.get("event_date"),
                "game_datetime": session.get("game_datetime"),
                "expires_at": session["expires_at"], "ended_at": ended_at, "reason": reason,
                "announcement_count": session.get("announcement_count", 0),
                "players": [
                    {
                        "name": item["name"], "invite_status": item["invite_status"],
                        "approvals": item["stats"]["approvals"],
                        "disconnects": item["stats"]["disconnects"],
                        "acknowledgements": item["stats"]["acknowledgements"],
                        "connected_seconds": round(item["stats"]["connected_seconds"], 2),
                        "average_latency_ms": round(item["stats"]["latency_total_ms"] / item["stats"]["latency_samples"], 1) if item["stats"]["latency_samples"] else None,
                    }
                    for item in session["roster"]
                ],
            }
            summaries = self.repository.summaries()
            summaries["sessions"].append(summary)
            self.repository.save_summaries(summaries)
            wrapper["sessions"] = [item for item in wrapper["sessions"] if item["id"] != session["id"]]
            self.repository.save_active(wrapper)
            self._drop_tickets_for_session(session["id"])
            return summary

    @staticmethod
    def connection_quality(latency_ms: float | None, missed: int, connected: bool = True) -> str:
        if not connected or missed >= 3:
            return "disconnected"
        if missed >= 2 or latency_ms is not None and latency_ms > 750:
            return "poor"
        if missed == 1 or latency_ms is not None and latency_ms >= 250:
            return "fair"
        return "good"

    @staticmethod
    def _player(session: dict[str, Any], contact_id: str) -> dict[str, Any]:
        player = next((item for item in session["roster"] if item["contact_id"] == contact_id), None)
        if player is None:
            raise KeyError("Unknown session player")
        return player

    @staticmethod
    def _request(session: dict[str, Any], request_id: str) -> dict[str, Any]:
        request = next((item for item in session["pending"] if item["id"] == request_id), None)
        if request is None:
            raise KeyError("Unknown admission request")
        return request
