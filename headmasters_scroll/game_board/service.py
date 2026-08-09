from __future__ import annotations

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

from .storage import GameBoardRepository


EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class GameBoardService:
    def __init__(self, repository: GameBoardRepository | None = None):
        self.repository = repository or GameBoardRepository()
        self._lock = threading.RLock()
        self._tickets: dict[str, dict[str, Any]] = {}
        self._ticket_by_request: dict[str, str] = {}
        self._restore_for_reapproval()

    def _restore_for_reapproval(self) -> None:
        with self._lock:
            wrapper = self.repository.active()
            session = wrapper.get("session")
            changed = False
            if session:
                for request in session.get("pending", []):
                    if request.get("status") in {"approved", "ticket_issued", "connected"}:
                        request["status"] = "pending"
                        request.pop("approved_at", None)
                        request.pop("connected_at", None)
                        changed = True
            if changed:
                self.repository.save_active(wrapper)

    def list_contacts(self) -> list[dict[str, str]]:
        return deepcopy(self.repository.contacts()["contacts"])

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
            contact = {"id": str(uuid4()), "name": name, "email": email}
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
            ZoneInfo(value["timezone"])
            self._validate_https_url(value["wordpress_player_url"], "WordPress player URL")
            self._validate_https_url(value["allowed_origin"], "Allowed origin", origin_only=True)
            self._validate_https_url(value["public_api_base"], "Public API URL", origin_only=True)
            if value["gmail_sender"] and not EMAIL.fullmatch(value["gmail_sender"]):
                raise ValueError("The Gmail sender address is invalid")
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

    def create_session(
        self,
        title: str,
        game_day: str,
        contact_ids: list[str],
        expiration_time: str = "23:59",
    ) -> dict[str, Any]:
        title = title.strip()
        if not title:
            raise ValueError("Session title is required")
        if not contact_ids:
            raise ValueError("Select at least one player")
        if len(set(contact_ids)) != len(contact_ids) or len(contact_ids) > 9:
            raise ValueError("A session supports one to nine unique players")
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
            if self.repository.active().get("session"):
                raise ValueError("End the active session before creating another")
            session = {
                "id": str(uuid4()),
                "title": title,
                "status": "active",
                "created_at": iso_utc(utc_now()),
                "expires_at": iso_utc(local_expiration),
                "roster": [self._roster_entry(contacts[item]) for item in contact_ids],
                "pending": [],
                "announcement_count": 0,
            }
            self.repository.save_active({"schema_version": 1, "session": session})
            return self.session_view()

    @staticmethod
    def _roster_entry(contact: dict[str, str]) -> dict[str, Any]:
        return {
            "contact_id": contact["id"], "name": contact["name"], "email": contact["email"],
            "invite_hash": None, "invite_status": "not_sent", "sent_at": None,
            "revoked": False,
            "stats": {
                "approvals": 0, "disconnects": 0, "acknowledgements": 0,
                "connected_seconds": 0.0, "latency_total_ms": 0.0, "latency_samples": 0,
            },
        }

    def _active(self) -> tuple[dict[str, Any], dict[str, Any]]:
        wrapper = self.repository.active()
        session = wrapper.get("session")
        if session is None:
            raise ValueError("There is no active session")
        if parse_utc(session["expires_at"]) <= utc_now():
            self.end_session("expired")
            raise ValueError("The session has expired")
        return wrapper, session

    def session_view(self) -> dict[str, Any] | None:
        with self._lock:
            wrapper = self.repository.active()
            session = wrapper.get("session")
            if not session:
                return None
            view = deepcopy(session)
            for player in view["roster"]:
                player.pop("invite_hash", None)
            for request in view["pending"]:
                request.pop("poll_hash", None)
            return view

    def prepare_invite(self, contact_id: str) -> tuple[str, str, dict[str, Any]]:
        with self._lock:
            wrapper, session = self._active()
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
            player["sent_at"] = None
            self.repository.save_active(wrapper)
            return raw, f"{base}#invite={quote(raw)}", deepcopy(player)

    def record_invite_result(self, contact_id: str, success: bool) -> None:
        with self._lock:
            wrapper, session = self._active()
            player = self._player(session, contact_id)
            player["invite_status"] = "sent" if success else "failed"
            player["sent_at"] = iso_utc(utc_now()) if success else None
            self.repository.save_active(wrapper)

    def request_admission(self, invite_token: str, client_ip: str, user_agent: str) -> dict[str, str]:
        if not invite_token or len(invite_token) > 256:
            raise ValueError("Invalid invitation")
        with self._lock:
            wrapper, session = self._active()
            if session["status"] == "paused":
                raise PermissionError("Admissions are paused")
            digest = token_hash(invite_token)
            player = next((item for item in session["roster"] if item.get("invite_hash") == digest), None)
            if player is None or player["revoked"]:
                raise PermissionError("Invalid or revoked invitation")
            existing = next((item for item in session["pending"] if item["contact_id"] == player["contact_id"] and item["status"] in {"pending", "approved", "ticket_issued", "connected"}), None)
            if existing:
                raise PermissionError("An admission request is already active for this player")
            poll_token = token_urlsafe(32)
            request = {
                "id": str(uuid4()), "contact_id": player["contact_id"], "name": player["name"],
                "status": "pending", "requested_at": iso_utc(utc_now()),
                "poll_hash": token_hash(poll_token), "client_ip": client_ip[:128],
                "user_agent": user_agent[:300],
            }
            session["pending"].append(request)
            self.repository.save_active(wrapper)
            return {"request_id": request["id"], "poll_token": poll_token, "status": "pending"}

    def poll_admission(self, request_id: str, poll_token: str) -> dict[str, Any]:
        with self._lock:
            wrapper, session = self._active()
            request = self._request(session, request_id)
            if not poll_token or token_hash(poll_token) != request["poll_hash"]:
                raise PermissionError("Invalid polling credential")
            response: dict[str, Any] = {"status": request["status"], "player_name": request["name"]}
            if request["status"] in {"approved", "ticket_issued"}:
                ticket = self._ticket_by_request.get(request_id)
                if ticket is None:
                    ticket = token_urlsafe(32)
                    self._ticket_by_request[request_id] = ticket
                    self._tickets[token_hash(ticket)] = {
                        "request_id": request_id,
                        "contact_id": request["contact_id"],
                        "expires_at": utc_now() + timedelta(seconds=60),
                    }
                request["status"] = "ticket_issued"
                self.repository.save_active(wrapper)
                response.update(status="approved", ticket=ticket, expires_in=60)
            return response

    def approve(self, request_id: str) -> None:
        with self._lock:
            wrapper, session = self._active()
            request = self._request(session, request_id)
            if request["status"] != "pending":
                raise ValueError("Only pending requests can be approved")
            request["status"] = "approved"
            request["approved_at"] = iso_utc(utc_now())
            self._player(session, request["contact_id"])["stats"]["approvals"] += 1
            self.repository.save_active(wrapper)

    def deny(self, request_id: str) -> None:
        with self._lock:
            wrapper, session = self._active()
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
            wrapper, session = self._active()
            request = self._request(session, details["request_id"])
            player = self._player(session, details["contact_id"])
            if request["status"] != "ticket_issued" or player["revoked"]:
                raise PermissionError("Admission is no longer valid")
            request["status"] = "connected"
            request["connected_at"] = iso_utc(utc_now())
            self.repository.save_active(wrapper)
            return {"request_id": request["id"], "contact_id": player["contact_id"], "name": player["name"], "session_id": session["id"], "session_title": session["title"]}

    def mark_disconnected(
        self,
        request_id: str,
        connected_seconds: float = 0.0,
        latency_total_ms: float = 0.0,
        latency_samples: int = 0,
    ) -> None:
        with self._lock:
            try:
                wrapper, session = self._active()
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

    def record_acknowledgement(self, contact_id: str) -> None:
        with self._lock:
            wrapper, session = self._active()
            self._player(session, contact_id)["stats"]["acknowledgements"] += 1
            self.repository.save_active(wrapper)

    def revoke(self, contact_id: str) -> None:
        with self._lock:
            wrapper, session = self._active()
            player = self._player(session, contact_id)
            player.update(revoked=True, invite_hash=None, invite_status="revoked")
            for request in session["pending"]:
                if request["contact_id"] == contact_id and request["status"] not in {"denied", "disconnected"}:
                    request["status"] = "revoked"
            self.repository.save_active(wrapper)

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            wrapper, session = self._active()
            session["status"] = "paused" if paused else "active"
            self.repository.save_active(wrapper)

    def increment_announcements(self) -> None:
        with self._lock:
            wrapper, session = self._active()
            session["announcement_count"] += 1
            self.repository.save_active(wrapper)

    def end_session(self, reason: str = "ended") -> dict[str, Any]:
        with self._lock:
            wrapper = self.repository.active()
            session = wrapper.get("session")
            if not session:
                raise ValueError("There is no active session")
            ended_at = iso_utc(utc_now())
            summary = {
                "id": session["id"], "title": session["title"], "created_at": session["created_at"],
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
            self.repository.save_active({"schema_version": 1, "session": None})
            self._tickets.clear()
            self._ticket_by_request.clear()
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
