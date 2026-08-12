from __future__ import annotations

import calendar
import hashlib
import math
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
from ..board import (
    DEFAULT_MAP_TOKEN_SCALE,
    OFF_LIMITS_MESSAGE,
    WorldBoardRepository,
    normalize_group,
    normalize_map,
    normalize_map_point,
    normalize_obscuration,
    normalize_person_board,
    point_in_polygon,
)
from ..campaigns import CampaignRepository, normalize_board_camera, normalize_zoom_profile
from ..character_attributes import calculate_character_attributes
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
    def __init__(
        self,
        repository: GameBoardRepository | None = None,
        campaign_repository: CampaignRepository | None = None,
    ):
        self.repository = repository or GameBoardRepository()
        self.shared_store = SharedJsonStore()
        self.world_board = WorldBoardRepository(self.shared_store)
        self.campaign_repository = campaign_repository or CampaignRepository()
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

    def list_campaigns(self) -> list[dict[str, Any]]:
        return self.campaign_repository.list()

    def _campaign_document(
        self,
        session: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        world = deepcopy(self.shared_store.load("world.json").data)
        campaign_id = str(session.get("campaign_id", "") or "")
        if not campaign_id:
            raise ValueError("This session is not linked to a campaign")
        campaign = self.campaign_repository.ensure_game_state(
            campaign_id,
            world,
            str(session.get("game_datetime") or "") or None,
        )
        state = campaign["game_state"]
        map_states = state.get("maps", {})
        for map_record in world.get("maps", []):
            map_id = str(map_record.get("record_id", "") or "")
            override = map_states.get(map_id)
            if override:
                map_record.update(deepcopy(override))
            else:
                map_record.update({
                    "players_published": False,
                    "obscurations": [],
                    "obscuration_preview_opacity": 0.35,
                    "obscuration_preview_color": "#ff0000",
                    "token_scale": DEFAULT_MAP_TOKEN_SCALE,
                    "start_point": None,
                    "headmaster_camera": normalize_board_camera(None),
                    "player_cameras": {},
                    "zoom_profile": normalize_zoom_profile(None),
                })
        people_state = state.get("people", {})
        for person in world.get("people", []):
            person_id = str(person.get("record_id", "") or "")
            base = normalize_person_board(person.get("board"))
            override = people_state.get(person_id)
            if override:
                base.update(deepcopy(override))
            person["board"] = normalize_person_board(base)
        world["board_groups"] = deepcopy(state.get("groups", []))
        return campaign, world

    def _persist_campaign_document(
        self,
        campaign_id: str,
        document: dict[str, Any],
    ) -> dict[str, Any]:
        assigned_maps = self.world_board._location_maps(document)
        existing_people = (
            self.campaign_repository.get(campaign_id).get("game_state", {}).get(
                "people", {}
            )
            or {}
        )
        map_states = {
            item["record_id"]: {
                "players_published": bool(item.get("players_published", False)),
                "obscurations": deepcopy(item.get("obscurations", []) or []),
                "obscuration_preview_opacity": float(item.get("obscuration_preview_opacity", 0.35)),
                "obscuration_preview_color": str(item.get("obscuration_preview_color", "#ff0000") or "#ff0000"),
                "token_scale": float(item.get("token_scale", DEFAULT_MAP_TOKEN_SCALE)),
                "start_point": deepcopy(item.get("start_point")),
                "headmaster_camera": normalize_board_camera(
                    item.get("headmaster_camera")
                ),
                "player_cameras": deepcopy(item.get("player_cameras", {}) or {}),
                "zoom_profile": normalize_zoom_profile(item.get("zoom_profile")),
            }
            for item in assigned_maps
        }
        people = {
            str(item["record_id"]): self.campaign_repository._person_state(
                normalize_person_board(item.get("board")),
                existing_people.get(str(item["record_id"]), {}),
            )
            for item in document.get("people", [])
            if isinstance(item, dict) and item.get("record_id")
        }
        groups = deepcopy(document.get("board_groups", []) or [])

        def update(state: dict[str, Any]) -> None:
            state["initialized"] = True
            state["maps"] = map_states
            state["people"] = people
            state["groups"] = groups

        return self.campaign_repository.update_game_state(campaign_id, update)

    @staticmethod
    def _campaign_map(document: dict[str, Any], map_id: str) -> dict[str, Any]:
        assigned = {
            item["record_id"] for item in WorldBoardRepository._location_maps(document)
        }
        if map_id not in assigned:
            raise KeyError("That map is not assigned to a location or floor")
        record = next(
            (item for item in document.get("maps", []) if item.get("record_id") == map_id),
            None,
        )
        if record is None:
            raise KeyError("Unknown map")
        return record

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
        campaign_id: str | None = None,
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
        campaign_id = str(campaign_id or "").strip()
        if not campaign_id:
            raise ValueError("Choose a campaign before creating a session")
        campaign = self.campaign_repository.ensure_game_state(
            campaign_id,
            self.shared_store.load("world.json").data,
        )
        cleaned_game_datetime = normalize_game_datetime(
            campaign["game_state"]["current_game_datetime"],
            campaign["game_world_start_date"],
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
                "campaign_id": campaign["record_id"],
                "campaign_name": campaign["name"],
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

    def archived_sessions_view(self) -> list[dict[str, Any]]:
        """Return ended sessions as campaign-board contexts, never as live sessions."""

        with self._lock:
            summaries = self.repository.summaries().get("sessions", [])
            result = []
            for summary in reversed(summaries):
                if not summary.get("campaign_id"):
                    continue
                view = deepcopy(summary)
                view["archived"] = True
                view["status"] = str(summary.get("reason") or "ended")
                view["pending"] = []
                view["chat"] = []
                view["roster"] = []
                result.append(view)
            return result

    def _board_context(self, session_id: str) -> dict[str, Any]:
        """Resolve either a live session or its retained campaign summary."""

        wrapper = self.repository.active()
        active = next(
            (item for item in wrapper.get("sessions", []) if item.get("id") == session_id),
            None,
        )
        if active is not None:
            return active
        summary = next(
            (
                item for item in reversed(self.repository.summaries().get("sessions", []))
                if item.get("id") == session_id and item.get("campaign_id")
            ),
            None,
        )
        if summary is None:
            raise KeyError("Unknown session")
        return summary

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
            original.get("campaign_id"),
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
            character_id = player.get("character_id")
            if character_id:
                self.ensure_person_placement(session["id"], str(character_id))
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
        contact_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            session = self._board_context(str(session_id or ""))
            campaign, document = self._campaign_document(session)
            game_datetime = str(campaign["game_state"]["current_game_datetime"])
            character_ids = [
                str(player.get("character_id"))
                for player in session.get("roster", [])
                if player.get("character_id")
            ]
            if for_players and contact_id:
                viewer = next(
                    (
                        player for player in session.get("roster", [])
                        if str(player.get("contact_id", "")) == contact_id
                    ),
                    None,
                )
                viewer_character_id = str((viewer or {}).get("character_id", "") or "")
                viewer_person = next(
                    (
                        person for person in document.get("people", [])
                        if str(person.get("record_id", "")) == viewer_character_id
                    ),
                    None,
                )
                viewer_placement = normalize_person_board(
                    (viewer_person or {}).get("board")
                ).get("placement")
                viewer_map_id = str((viewer_placement or {}).get("map_id", "") or "")
                if viewer_map_id:
                    viewer_map = next(
                        (
                            item for item in document.get("maps", [])
                            if str(item.get("record_id", "")) == viewer_map_id
                        ),
                        None,
                    )
                    if viewer_map is not None:
                        # This document is a private per-request copy. Reveal
                        # the occupied destination only to its linked player.
                        viewer_map["players_published"] = True
            snapshot = self.world_board.snapshot(
                game_datetime,
                player_character_ids=character_ids,
                for_players=for_players,
                document_override=document,
            )
            snapshot["session_id"] = session["id"]
            snapshot["campaign_id"] = campaign["record_id"]
            snapshot["loaded_map_ids"] = deepcopy(
                campaign["game_state"]["loaded_map_ids"]
            )
            snapshot["active_map_id"] = str(
                campaign["game_state"].get("active_map_id", "") or ""
            )
            if for_players and contact_id:
                player_active = str(
                    campaign["game_state"].get("player_active_map_ids", {}).get(
                        contact_id, ""
                    ) or ""
                )
                visible_ids = {
                    str(item.get("record_id", "") or "")
                    for item in snapshot.get("maps", [])
                }
                if player_active in visible_ids:
                    snapshot["active_map_id"] = player_active
                viewer_character_id = str((viewer or {}).get("character_id", "") or "")
                viewer_person = next(
                    (
                        person for person in document.get("people", [])
                        if str(person.get("record_id", "")) == viewer_character_id
                    ),
                    None,
                )
                if viewer_person is not None:
                    try:
                        rules_database = self.shared_store.load("db.json").data
                    except FileNotFoundError:
                        rules_database = {"schools": []}
                    snapshot["character_attributes"] = calculate_character_attributes(
                        viewer_person,
                        document,
                        rules_database,
                        game_datetime,
                    )
                else:
                    snapshot["character_attributes"] = None
            campaign_maps = campaign["game_state"].get("maps", {})
            for map_record in snapshot.get("maps", []):
                map_id = str(map_record.get("record_id", "") or "")
                map_state = campaign_maps.get(map_id, {})
                headmaster_camera = normalize_board_camera(
                    map_state.get("headmaster_camera")
                )
                if for_players and contact_id:
                    camera = (map_state.get("player_cameras", {}) or {}).get(
                        contact_id, headmaster_camera
                    )
                else:
                    camera = headmaster_camera
                map_record["camera"] = normalize_board_camera(camera)
                # Camera ownership is private. A snapshot contains only the
                # camera selected for its viewer, never every player's view.
                map_record.pop("headmaster_camera", None)
                map_record.pop("player_cameras", None)
            if not for_players:
                campaign_people = campaign.get("game_state", {}).get("people", {}) or {}
                for actor in snapshot.get("actors", []):
                    person_state = campaign_people.get(str(actor.get("actor_id", "")), {})
                    actor["wounds"] = deepcopy(person_state.get("wounds", []) or [])
                    actor["battle"] = deepcopy(person_state.get("battle"))
                    actor["character_notes"] = deepcopy(
                        person_state.get("character_notes", []) or []
                    )
            return snapshot

    def character_attributes_for(
        self,
        session_id: str,
        contact_id: str,
    ) -> dict[str, Any] | None:
        """Return the linked World Builder character sheet for one player."""

        with self._lock:
            session = self._board_context(session_id)
            campaign, document = self._campaign_document(session)
            viewer = next(
                (
                    player for player in session.get("roster", [])
                    if str(player.get("contact_id", "")) == contact_id
                ),
                None,
            )
            character_id = str((viewer or {}).get("character_id", "") or "")
            person = next(
                (
                    item for item in document.get("people", [])
                    if str(item.get("record_id", "")) == character_id
                ),
                None,
            )
            if person is None:
                return None
            try:
                rules_database = self.shared_store.load("db.json").data
            except FileNotFoundError:
                rules_database = {"schools": []}
            return calculate_character_attributes(
                person,
                document,
                rules_database,
                str(campaign["game_state"]["current_game_datetime"]),
            )

    def update_person_campaign_action(
        self,
        session_id: str,
        person_id: str,
        action: str,
        *,
        severity: str = "",
        text: str = "",
        battle_name: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            session = self._board_context(session_id)
            campaign, document = self._campaign_document(session)
            if not any(
                str(person.get("record_id", "")) == person_id
                for person in document.get("people", [])
                if isinstance(person, dict)
            ):
                raise KeyError("Unknown person")

            result: dict[str, Any] = {}

            def update(state: dict[str, Any]) -> None:
                nonlocal result
                person = state.setdefault("people", {}).setdefault(person_id, {})
                if action == "add_wound":
                    normalized_severity = str(severity or "").strip().lower()
                    if normalized_severity not in {"light", "medium", "heavy"}:
                        raise ValueError("Choose a light, medium, or heavy wound")
                    wound = {
                        "record_id": str(uuid4()),
                        "severity": normalized_severity,
                        "note": str(text or "").strip()[:1000],
                        "created_at": iso_utc(utc_now()),
                    }
                    person.setdefault("wounds", []).append(wound)
                    result = deepcopy(wound)
                elif action == "enter_battle":
                    battle = {
                        "active": True,
                        "name": str(battle_name or "Battle").strip()[:200] or "Battle",
                        "entered_at": iso_utc(utc_now()),
                    }
                    person["battle"] = battle
                    result = deepcopy(battle)
                elif action == "leave_battle":
                    person["battle"] = None
                    result = {"active": False}
                elif action == "add_note":
                    note_text = str(text or "").strip()
                    if not note_text:
                        raise ValueError("A character note cannot be empty")
                    note = {
                        "record_id": str(uuid4()),
                        "text": note_text[:4000],
                        "created_at": iso_utc(utc_now()),
                    }
                    person.setdefault("character_notes", []).append(note)
                    result = deepcopy(note)
                else:
                    raise ValueError("Unknown character action")

            self.campaign_repository.update_game_state(campaign["record_id"], update)
            return result

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
        with self._lock:
            session = self._board_context(session_id)
            campaign, document = self._campaign_document(session)
            map_record = self._campaign_map(document, map_id)
            person = next(
                (item for item in document.get("people", []) if item.get("record_id") == person_id),
                None,
            )
            if person is None:
                raise KeyError("Unknown person")
            board = normalize_person_board(person.get("board"))
            board["placement"] = {
                "location_id": str(map_record["location_id"]),
                "floor_id": str(map_record.get("floor_id", "") or ""),
                "map_id": str(map_id),
                "x": max(0.0, min(1.0, float(x))),
                "y": max(0.0, min(1.0, float(y))),
            }
            person["board"] = board
            self.world_board._remove_from_incompatible_groups(
                document, person_id, board["placement"]["location_id"]
            )
            self._persist_campaign_document(campaign["record_id"], document)
            return deepcopy(board["placement"])

    def transport_person(
        self,
        session_id: str,
        person_id: str,
        map_id: str,
        warp_point_id: str,
    ) -> dict[str, Any]:
        """Move a person to an explicit warp and focus their linked player there."""

        with self._lock:
            session = self._board_context(session_id)
            campaign, document = self._campaign_document(session)
            target = self._campaign_map(document, map_id)
            person = next(
                (
                    item for item in document.get("people", [])
                    if str(item.get("record_id", "")) == person_id
                ),
                None,
            )
            if person is None:
                raise KeyError("Unknown person")
            current = normalize_person_board(person.get("board")).get("placement")
            if current and str(current.get("map_id", "")) == map_id:
                raise ValueError("Choose a different destination map")
            warp = next(
                (
                    item for item in target.get("warp_points", []) or []
                    if str(item.get("record_id", "")) == warp_point_id
                ),
                None,
            )
            if warp is None:
                raise KeyError("Choose a warp point on the destination map")
            arrival = normalize_map_point(warp, "Transport warp point")
            board = normalize_person_board(person.get("board"))
            board["placement"] = {
                "location_id": str(target["location_id"]),
                "floor_id": str(target.get("floor_id", "") or ""),
                "map_id": map_id,
                "x": arrival["x"],
                "y": arrival["y"],
            }
            person["board"] = board
            self.world_board._remove_from_incompatible_groups(
                document, person_id, board["placement"]["location_id"]
            )
            self._persist_campaign_document(campaign["record_id"], document)

            contact_ids = [
                str(player["contact_id"])
                for player in session.get("roster", [])
                if str(player.get("character_id", "") or "") == person_id
            ]
            profile = normalize_zoom_profile(target.get("zoom_profile"))
            camera = {
                "zoom": float(profile.get("default_zoom", 1.0)),
                "center_x": arrival["x"],
                "center_y": arrival["y"],
            }

            def update(state: dict[str, Any]) -> None:
                loaded = state.setdefault("loaded_map_ids", [])
                if map_id not in loaded:
                    loaded.append(map_id)
                map_state = state.setdefault("maps", {}).setdefault(map_id, {})
                player_cameras = map_state.setdefault("player_cameras", {})
                active_maps = state.setdefault("player_active_map_ids", {})
                for contact_id in contact_ids:
                    active_maps[contact_id] = map_id
                    player_cameras[contact_id] = deepcopy(camera)

            self.campaign_repository.update_game_state(campaign["record_id"], update)
            return {
                "placement": deepcopy(board["placement"]),
                "warp_point_id": warp_point_id,
                "warp_point_name": str(warp.get("name", "") or "Warp point"),
                "contact_ids": contact_ids,
                "camera": camera,
            }

    def ensure_person_placement(
        self,
        session_id: str,
        person_id: str,
    ) -> dict[str, Any] | None:
        with self._lock:
            _wrapper, session = self._active(session_id)
            campaign, document = self._campaign_document(session)
            person = next(
                (item for item in document.get("people", []) if item.get("record_id") == person_id),
                None,
            )
            if person is None:
                raise KeyError("Unknown person")
            board = normalize_person_board(person.get("board"))
            if board.get("placement"):
                return deepcopy(board["placement"])
            state = campaign["game_state"]
            maps_by_id = {
                item["record_id"]: item for item in self.world_board._location_maps(document)
            }
            candidates = [
                maps_by_id[map_id]
                for map_id in state.get("loaded_map_ids", [])
                if map_id in maps_by_id and maps_by_id[map_id].get("players_published")
            ]
            if not candidates:
                candidates = [item for item in maps_by_id.values() if item.get("players_published")]
            if not candidates:
                return None
            target = candidates[0]
            start = normalize_map_point(
                next(
                    (
                        point for point in target.get("warp_points", []) or []
                        if point.get("player_arrival")
                    ),
                    None,
                ) or {"x": 0.5, "y": 0.5},
                "Player arrival warp",
            )
            occupied = []
            for other in document.get("people", []):
                if not isinstance(other, dict) or other is person:
                    continue
                placement = normalize_person_board(other.get("board")).get("placement")
                if placement and placement["map_id"] == target["record_id"]:
                    occupied.append((float(placement["x"]), float(placement["y"])))
            spacing = max(0.006, float(target.get("token_scale", DEFAULT_MAP_TOKEN_SCALE)) * 1.15)
            points = [(start["x"], start["y"])]
            for ring in range(1, 7):
                radius = spacing * ring
                count = max(8, ring * 8)
                for index in range(count):
                    angle = (2.0 * math.pi * index) / count
                    points.append((
                        max(0.005, min(0.995, start["x"] + math.cos(angle) * radius)),
                        max(0.005, min(0.995, start["y"] + math.sin(angle) * radius)),
                    ))
            px, py = next(
                (
                    point for point in points
                    if all(math.hypot(point[0] - ox, point[1] - oy) >= spacing for ox, oy in occupied)
                ),
                points[-1],
            )
            board["placement"] = {
                "location_id": str(target["location_id"]),
                "floor_id": str(target.get("floor_id", "") or ""),
                "map_id": str(target["record_id"]),
                "x": px,
                "y": py,
            }
            person["board"] = board
            self._persist_campaign_document(campaign["record_id"], document)
            return deepcopy(board["placement"])

    def update_person_board(
        self,
        session_id: str,
        person_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            session = self._board_context(session_id)
            campaign, document = self._campaign_document(session)
            person = next(
                (item for item in document.get("people", []) if item.get("record_id") == person_id),
                None,
            )
            if person is None:
                raise KeyError("Unknown person")
            board = normalize_person_board(person.get("board"))
            board.update(deepcopy(updates))
            board = normalize_person_board(board)
            if board["display_mode"] == "token" and not board.get("portrait") and not person.get("player_character"):
                raise ValueError("An NPC needs a prepared portrait before becoming a portrait token")
            person["board"] = board
            self._persist_campaign_document(campaign["record_id"], document)
            return deepcopy(board)

    def set_map_published(self, session_id: str, map_id: str, published: bool) -> dict[str, Any]:
        with self._lock:
            session = self._board_context(session_id)
            campaign, document = self._campaign_document(session)
            record = self._campaign_map(document, map_id)
            record["players_published"] = bool(published)
            self._persist_campaign_document(campaign["record_id"], document)
            return deepcopy(record)

    def set_map_settings(
        self,
        session_id: str,
        map_id: str,
        *,
        token_scale: float | None = None,
        zoom_profile: dict[str, Any] | None = None,
        preview_opacity: float | None = None,
        preview_color: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            session = self._board_context(session_id)
            campaign, document = self._campaign_document(session)
            record = self._campaign_map(document, map_id)
            if token_scale is not None:
                record["token_scale"] = float(token_scale)
            if zoom_profile is not None:
                record["zoom_profile"] = normalize_zoom_profile(zoom_profile)
            if preview_opacity is not None:
                record["obscuration_preview_opacity"] = float(preview_opacity)
            if preview_color is not None:
                record["obscuration_preview_color"] = str(preview_color).lower()
            record.update(normalize_map(record))
            self._persist_campaign_document(campaign["record_id"], document)
            return deepcopy(record)

    def location_maps(self, session_id: str | None = None) -> list[dict[str, Any]]:
        if session_id:
            with self._lock:
                session = self._board_context(session_id)
                _campaign, document = self._campaign_document(session)
                return self.world_board._location_maps(document)
        return self.world_board.location_maps()

    def set_board_workspace(
        self,
        session_id: str,
        loaded_map_ids: list[str],
        active_map_id: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            session = self._board_context(session_id)
            campaign, document = self._campaign_document(session)
            valid_ids = {
                item["record_id"] for item in self.world_board._location_maps(document)
            }
            loaded = []
            for map_id in loaded_map_ids:
                map_id = str(map_id or "")
                if map_id not in valid_ids:
                    raise KeyError("A loaded map is not assigned to a location or floor")
                if map_id not in loaded:
                    loaded.append(map_id)
            active = str(active_map_id or "")
            if active and active not in loaded:
                raise ValueError("The active map must be loaded")

            def update(state: dict[str, Any]) -> None:
                state["loaded_map_ids"] = loaded
                state["active_map_id"] = active

            saved = self.campaign_repository.update_game_state(campaign["record_id"], update)
            return deepcopy(saved["game_state"])

    def set_board_camera(
        self,
        session_id: str,
        map_id: str,
        camera: dict[str, Any],
        *,
        contact_id: str | None = None,
    ) -> dict[str, float]:
        normalized_camera = normalize_board_camera(camera)
        with self._lock:
            session = self._board_context(session_id)
            if contact_id is not None:
                if session.get("archived") or session.get("ended_at"):
                    raise ValueError("Players cannot update an ended session")
                self._player(session, contact_id)
            campaign, document = self._campaign_document(session)
            self._campaign_map(document, map_id)

            def update(state: dict[str, Any]) -> None:
                map_state = state.setdefault("maps", {}).setdefault(map_id, {})
                if contact_id is None:
                    map_state["headmaster_camera"] = normalized_camera
                else:
                    map_state.setdefault("player_cameras", {})[contact_id] = normalized_camera
                    state.setdefault("player_active_map_ids", {})[contact_id] = map_id

            self.campaign_repository.update_game_state(campaign["record_id"], update)
            return deepcopy(normalized_camera)

    def set_map_presentation(
        self,
        session_id: str,
        map_id: str,
        *,
        published: bool,
        obscurations: list[dict[str, Any]],
        preview_opacity: float,
        preview_color: str,
    ) -> dict[str, Any]:
        with self._lock:
            session = self._board_context(session_id)
            campaign, document = self._campaign_document(session)
            record = self._campaign_map(document, map_id)
            record["players_published"] = bool(published)
            record["obscurations"] = [normalize_obscuration(item) for item in obscurations]
            record["obscuration_preview_opacity"] = float(preview_opacity)
            record["obscuration_preview_color"] = str(preview_color).lower()
            record.update(normalize_map(record))
            self._persist_campaign_document(campaign["record_id"], document)
            return deepcopy(record)

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
        with self._lock:
            _wrapper, session = self._active(session_id)
            campaign, document = self._campaign_document(session)
            source = normalize_map(self._campaign_map(document, source_map_id))
            person = next(
                (item for item in document.get("people", []) if item.get("record_id") == person_id),
                None,
            )
            if person is None:
                raise KeyError("Unknown person")
            region = next((item for item in source["regions"] if item["record_id"] == region_id), None)
            if region is None or region.get("behavior_type") != "travel":
                raise ValueError("That area is not a travel destination")
            if not point_in_polygon(float(x), float(y), region["points"]):
                raise ValueError("The travel point is outside that area")
            if any(point_in_polygon(float(x), float(y), item["points"]) for item in source["obscurations"]):
                raise PermissionError("That part of the map is obscured")
            board = normalize_person_board(person.get("board"))
            placement = board.get("placement")
            if not placement or placement["map_id"] != source_map_id:
                raise PermissionError("Your character is not on that map")
            target_location_id = str(region.get("target_location_id", "") or "")
            warp_id = str(region.get("target_warp_point_id", "") or "")
            target = None
            warp = None
            if warp_id:
                for candidate in document.get("maps", []):
                    point = next(
                        (item for item in candidate.get("warp_points", []) or [] if str(item.get("record_id")) == warp_id),
                        None,
                    )
                    if point is not None:
                        target, warp = candidate, point
                        break
            if target is None:
                location = next(
                    (item for item in document.get("locations", []) if str(item.get("record_id")) == target_location_id),
                    None,
                )
                target_map_id = str((location or {}).get("default_map_id", "") or "")
                target = next(
                    (item for item in document.get("maps", []) if item.get("record_id") == target_map_id),
                    None,
                )
            if target is None or not bool(target.get("players_published", False)):
                raise PermissionError(OFF_LIMITS_MESSAGE)
            arrival = normalize_map_point(
                warp or target.get("start_point") or {"x": 0.5, "y": 0.5},
                "Travel arrival point",
            )
            board["placement"] = {
                "location_id": str(target["location_id"]),
                "floor_id": str(target.get("floor_id", "") or ""),
                "map_id": str(target["record_id"]),
                "x": arrival["x"],
                "y": arrival["y"],
            }
            person["board"] = board
            self.world_board._remove_from_incompatible_groups(
                document, person_id, board["placement"]["location_id"]
            )
            self._persist_campaign_document(campaign["record_id"], document)
            return deepcopy(board["placement"])

    def create_board_group(
        self,
        session_id: str,
        name: str,
        location_id: str,
        person_ids: list[str],
    ) -> dict[str, Any]:
        with self._lock:
            session = self._board_context(session_id)
            campaign, document = self._campaign_document(session)
            if len(set(person_ids)) < 2:
                raise ValueError("A board group requires at least two people")
            existing = {
                member.get("actor_id")
                for group in document.get("board_groups", [])
                for member in group.get("members", [])
                if member.get("actor_type", "person") == "person"
            }
            people = {str(item.get("record_id")): item for item in document.get("people", [])}
            for person_id in person_ids:
                placement = normalize_person_board(people.get(person_id, {}).get("board")).get("placement") if person_id in people else None
                if person_id not in people or person_id in existing or not placement or placement["location_id"] != location_id:
                    raise ValueError("Every group member must be an ungrouped person at this location")
            now = iso_utc(utc_now())
            group = normalize_group({
                "record_id": str(uuid4()),
                "name": str(name or "").strip(),
                "location_id": str(location_id),
                "members": [
                    {"record_id": str(uuid4()), "actor_type": "person", "actor_id": person_id}
                    for person_id in person_ids
                ],
                "created_at": now,
                "last_updated": now,
            })
            document.setdefault("board_groups", []).append(group)
            self._persist_campaign_document(campaign["record_id"], document)
            return deepcopy(group)

    def set_board_group(
        self,
        session_id: str,
        person_id: str,
        group_id: str | None,
    ) -> dict[str, Any] | None:
        with self._lock:
            session = self._board_context(session_id)
            campaign, document = self._campaign_document(session)
            person = next((item for item in document.get("people", []) if item.get("record_id") == person_id), None)
            if person is None:
                raise KeyError("Unknown person")
            placement = normalize_person_board(person.get("board")).get("placement")
            target = next(
                (item for item in document.get("board_groups", []) if item.get("record_id") == group_id),
                None,
            ) if group_id else None
            if group_id and target is None:
                raise KeyError("Unknown board group")
            if target and (not placement or str(target.get("location_id")) != placement["location_id"]):
                raise ValueError("A person can only join a group at the same location")
            for group in document.get("board_groups", []):
                group["members"] = [
                    member for member in group.get("members", [])
                    if not (member.get("actor_type", "person") == "person" and member.get("actor_id") == person_id)
                ]
            if target is not None:
                target.setdefault("members", []).append({
                    "record_id": str(uuid4()), "actor_type": "person", "actor_id": person_id,
                })
                target["last_updated"] = iso_utc(utc_now())
            document["board_groups"] = [
                group for group in document.get("board_groups", [])
                if len(group.get("members", [])) >= 2
            ]
            self._persist_campaign_document(campaign["record_id"], document)
            return deepcopy(target) if target in document["board_groups"] else None

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
            campaign = self.campaign_repository.get(str(session.get("campaign_id", "")))
            normalized = normalize_game_datetime(
                game_datetime, campaign["game_world_start_date"]
            )

            def update(state: dict[str, Any]) -> None:
                state["current_game_datetime"] = normalized

            self.campaign_repository.update_game_state(campaign["record_id"], update)
            for active_session in wrapper.get("sessions", []):
                if active_session.get("campaign_id") == campaign["record_id"]:
                    active_session["game_datetime"] = normalized
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
                "campaign_id": session.get("campaign_id"),
                "campaign_name": session.get("campaign_name"),
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
