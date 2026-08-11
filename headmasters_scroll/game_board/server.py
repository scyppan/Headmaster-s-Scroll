from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from secrets import token_urlsafe
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..campaigns import CampaignRepository
from .gmail import GmailSender, GmailUnavailable
from .service import (
    GameBoardService,
    format_game_datetime_for_people,
    parse_utc,
    token_hash,
    utc_now,
)
from .storage import GameBoardRepository


MAX_MESSAGE_BYTES = 16_384


class ContactBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)


class CharacterLinkBody(BaseModel):
    character_id: str | None = Field(default=None, max_length=100)


class SettingsBody(BaseModel):
    wordpress_player_url: str = ""
    allowed_origin: str = ""
    public_api_base: str = ""
    gmail_credentials_path: str = "credentials.json"
    gmail_sender: str = ""
    timezone: str = "America/Chicago"


class GmailAuthorizeBody(BaseModel):
    credentials_path: str = Field(default="credentials.json", max_length=2048)
    sender: str = Field(default="", max_length=254)


class SessionBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    campaign_id: str = Field(min_length=1, max_length=100)
    game_day: str
    expiration_time: str = "23:59"
    event_date: str | None = Field(default=None, max_length=32)
    contact_ids: list[str] = Field(min_length=1, max_length=9)


class AdmissionBody(BaseModel):
    invite_token: str = Field(min_length=20, max_length=256)


class SendBody(BaseModel):
    contact_ids: list[str] = Field(min_length=1, max_length=9)
    session_id: str | None = Field(default=None, max_length=100)


class AnnouncementBody(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    session_id: str | None = Field(default=None, max_length=100)


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    session_id: str | None = Field(default=None, max_length=100)


class EventDateBody(BaseModel):
    event_date: str | None = Field(default=None, max_length=32)
    session_id: str | None = Field(default=None, max_length=100)


class GameDateTimeBody(BaseModel):
    game_datetime: str = Field(min_length=1, max_length=32)


class BoardMoveBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    person_id: str = Field(min_length=1, max_length=100)
    map_id: str = Field(min_length=1, max_length=100)
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class BoardPersonBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    visibility: str | None = Field(default=None, max_length=20)
    display_mode: str | None = Field(default=None, max_length=20)
    name_revealed: bool | None = None
    faction_revealed: bool | None = None
    faction_organization_id: str | None = Field(default=None, max_length=100)


class MapVisibilityBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    published: bool


class MapPresentationBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    published: bool
    obscurations: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    preview_opacity: float = Field(default=0.35, ge=0.05, le=1.0)
    preview_color: str = Field(default="#ff0000", min_length=7, max_length=7)


class MapBoardSettingsBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    token_scale: float | None = Field(default=None, ge=0.002, le=0.03)
    start_point: dict[str, float] | None = None
    update_start_point: bool = False


class BoardGroupBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    location_id: str = Field(min_length=1, max_length=100)
    person_ids: list[str] = Field(min_length=2, max_length=100)


class ControlGrantBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    contact_id: str = Field(min_length=1, max_length=100)
    person_id: str = Field(min_length=1, max_length=100)
    granted: bool = True


class GroupMembershipBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    group_id: str | None = Field(default=None, max_length=100)


class BoardWorkspaceBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    loaded_map_ids: list[str] = Field(default_factory=list, max_length=200)
    active_map_id: str = Field(default="", max_length=100)


@dataclass
class PlayerConnection:
    websocket: Any
    request_id: str
    contact_id: str
    name: str
    session_id: str = ""
    character_id: str | None = None
    asset_credential_hash: str = ""
    connected_at: float = field(default_factory=time.monotonic)
    latency_ms: float | None = None
    latency_total_ms: float = 0.0
    latency_samples: int = 0
    missed: int = 0
    heartbeats: dict[str, float] = field(default_factory=dict)
    last_activity: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    persisted: bool = False
    chat_events: deque[float] = field(default_factory=deque)
    move_events: deque[float] = field(default_factory=deque)

    def public(self, service: GameBoardService) -> dict[str, Any]:
        return {
            "request_id": self.request_id, "contact_id": self.contact_id, "name": self.name,
            "session_id": self.session_id,
            "character_id": self.character_id,
            "connected_seconds": round(time.monotonic() - self.connected_at, 1),
            "latency_ms": round(self.latency_ms, 1) if self.latency_ms is not None else None,
            "missed_heartbeats": self.missed,
            "quality": service.connection_quality(self.latency_ms, self.missed),
            "last_activity": self.last_activity,
        }


class RateLimiter:
    def __init__(self, attempts: int = 5, window_seconds: int = 60):
        self.attempts = attempts
        self.window_seconds = window_seconds
        self.events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        queue = self.events[key]
        while queue and queue[0] <= now - self.window_seconds:
            queue.popleft()
        if len(queue) >= self.attempts:
            return False
        queue.append(now)
        return True


class GameBoardRuntime:
    def __init__(self, service: GameBoardService):
        self.service = service
        self.connections: dict[str, PlayerConnection] = {}
        self.admin_sockets: set[Any] = set()
        self.rate_limiter = RateLimiter()
        self._announcement_id = 0
        self.asset_credentials: dict[str, str] = {}

    def state(self) -> dict[str, Any]:
        sessions = self.service.sessions_view()
        boards = {}
        for session in sessions:
            try:
                boards[session["id"]] = self.service.board_snapshot(
                    session["id"],
                    for_players=False,
                )
            except (KeyError, ValueError):
                continue
        try:
            location_maps = self.service.location_maps()
        except (KeyError, ValueError):
            location_maps = []
        return {
            "contacts": self.service.list_contacts(),
            "characters": self.service.list_characters(),
            "campaigns": self.service.list_campaigns(),
            "settings": self.service.settings(),
            "sessions": sessions,
            "session": sessions[0] if sessions else None,
            "connections": [item.public(self.service) for item in self.connections.values()],
            "boards": boards,
            "location_maps": location_maps,
            "gmail": self.gmail().status(),
        }

    def gmail(self) -> GmailSender:
        settings = self.service.settings(include_private=True)
        return GmailSender(settings["gmail_credentials_path"], settings["gmail_sender"])

    async def notify_admins(self) -> None:
        message = {"v": 1, "type": "state", "data": self.state()}
        stale = []
        for socket in list(self.admin_sockets):
            try:
                await socket.send_json(message)
            except Exception:
                stale.append(socket)
        for socket in stale:
            self.admin_sockets.discard(socket)

    async def disconnect(
        self, contact_id: str, event_type: str, message: str, session_id: str | None = None
    ) -> None:
        keys = [
            key for key, connection in self.connections.items()
            if connection.contact_id == contact_id
            and (session_id is None or connection.session_id == session_id)
        ]
        for key in keys:
            connection = self.connections.pop(key, None)
            if not connection:
                continue
            if connection.asset_credential_hash:
                self.asset_credentials.pop(
                    connection.asset_credential_hash,
                    None,
                )
            self.service.mark_disconnected(
                connection.request_id,
                time.monotonic() - connection.connected_at,
                connection.latency_total_ms,
                connection.latency_samples,
            )
            connection.persisted = True
            try:
                await connection.websocket.send_json({"v": 1, "type": event_type, "message": message})
                await connection.websocket.close(code=4003)
            except Exception:
                pass

    async def disconnect_all(self, event_type: str, message: str) -> None:
        await asyncio.gather(
            *(
                self.disconnect(connection.contact_id, event_type, message, connection.session_id)
                for connection in list(self.connections.values())
            ),
            return_exceptions=True,
        )

    async def disconnect_session(self, session_id: str, event_type: str, message: str) -> None:
        await asyncio.gather(
            *(
                self.disconnect(connection.contact_id, event_type, message, session_id)
                for connection in list(self.connections.values())
                if connection.session_id == session_id
            ),
            return_exceptions=True,
        )

    async def announce(self, text: str, session_id: str | None = None) -> str:
        self._announcement_id += 1
        announcement_id = f"announcement-{self._announcement_id}"
        message = {"v": 1, "type": "announcement", "id": announcement_id, "message": text}
        await asyncio.gather(
            *(
                connection.websocket.send_json(message)
                for connection in list(self.connections.values())
                if session_id is None or getattr(connection, "session_id", "") == session_id
            ),
            return_exceptions=True,
        )
        self.service.increment_announcements(session_id)
        return announcement_id

    async def chat(
        self, sender_id: str, sender_name: str, sender_role: str, text: str,
        session_id: str | None = None,
    ) -> dict[str, str]:
        chat = self.service.post_chat(sender_id, sender_name, sender_role, text, session_id)
        envelope = {"v": 1, "type": "chat_message", "message": chat}
        await asyncio.gather(
            *(
                connection.websocket.send_json(envelope)
                for connection in list(self.connections.values())
                if session_id is None or getattr(connection, "session_id", "") == session_id
            ),
            return_exceptions=True,
        )
        await self.notify_admins()
        return chat

    async def send_board_snapshot(
        self,
        connection: PlayerConnection,
    ) -> None:
        snapshot = self.service.board_snapshot(
            connection.session_id,
            for_players=True,
        )
        snapshot["controlled_character_ids"] = sorted(
            self.service.controlled_character_ids(
                connection.session_id,
                connection.contact_id,
            )
        )
        await connection.websocket.send_json(
            {"v": 1, "type": "board_snapshot", "board": snapshot}
        )

    async def broadcast_board(self, session_id: str) -> None:
        await asyncio.gather(
            *(
                self.send_board_snapshot(connection)
                for connection in list(self.connections.values())
                if connection.session_id == session_id
            ),
            return_exceptions=True,
        )
        await self.notify_admins()

    async def preview_move(
        self,
        connection: PlayerConnection,
        person_id: str,
        map_id: str,
        x: float,
        y: float,
    ) -> None:
        if person_id not in self.service.controlled_character_ids(
            connection.session_id,
            connection.contact_id,
        ):
            raise PermissionError("You do not control that token")
        envelope = {
            "v": 1,
            "type": "board_move_preview",
            "person_id": person_id,
            "map_id": map_id,
            "x": max(0.0, min(1.0, float(x))),
            "y": max(0.0, min(1.0, float(y))),
        }
        await asyncio.gather(
            *(
                item.websocket.send_json(envelope)
                for item in list(self.connections.values())
                if item.session_id == connection.session_id
            ),
            return_exceptions=True,
        )

    async def broadcast_move_preview(
        self,
        session_id: str,
        person_id: str,
        map_id: str,
        x: float,
        y: float,
    ) -> None:
        envelope = {
            "v": 1,
            "type": "board_move_preview",
            "person_id": person_id,
            "map_id": map_id,
            "x": max(0.0, min(1.0, float(x))),
            "y": max(0.0, min(1.0, float(y))),
        }
        await asyncio.gather(
            *(
                item.websocket.send_json(envelope)
                for item in list(self.connections.values())
                if item.session_id == session_id
            ),
            return_exceptions=True,
        )


def create_apps(
    repository: GameBoardRepository | None = None,
    campaign_repository: CampaignRepository | None = None,
):
    service = GameBoardService(repository, campaign_repository)
    runtime = GameBoardRuntime(service)
    settings = service.settings(include_private=True)

    async def expiration_loop():
        while True:
            await asyncio.sleep(1)
            expired = [
                session for session in service.sessions_view()
                if parse_utc(session["expires_at"]) <= utc_now()
            ]
            for session in expired:
                await runtime.disconnect_session(
                    session["id"], "session_expired", "The game session has expired."
                )
                try:
                    service.end_session("expired", session["id"])
                except ValueError:
                    pass
            if expired:
                await runtime.notify_admins()

    @asynccontextmanager
    async def lifespan(_app):
        task = asyncio.create_task(expiration_loop())
        try:
            yield
        finally:
            task.cancel()

    admin_app = FastAPI(
        title="Game Board Headmaster Dashboard", docs_url=None, redoc_url=None,
        lifespan=lifespan,
    )
    player_app = FastAPI(title="Game Board Player Service", docs_url=None, redoc_url=None)
    if settings["allowed_origin"]:
        player_app.add_middleware(
            CORSMiddleware,
            allow_origins=[settings["allowed_origin"]],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
            allow_credentials=False,
        )

    def admin_guard(x_admin_key: str = Header(default="")) -> None:
        if x_admin_key != settings["admin_key"]:
            raise HTTPException(status_code=403, detail="Invalid dashboard key")

    def admin_result(callable_, *args, **kwargs):
        try:
            return callable_(*args, **kwargs)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @admin_app.get("/api/admin/state", dependencies=[Depends(admin_guard)])
    async def admin_state():
        return runtime.state()

    @admin_app.put("/api/admin/settings", dependencies=[Depends(admin_guard)])
    async def update_settings(body: SettingsBody):
        result = admin_result(service.update_settings, body.model_dump())
        await runtime.notify_admins()
        return result

    @admin_app.post("/api/admin/contacts", dependencies=[Depends(admin_guard)])
    async def add_contact(body: ContactBody):
        result = admin_result(service.add_contact, body.name, body.email)
        await runtime.notify_admins()
        return result

    @admin_app.put("/api/admin/contacts/{contact_id}", dependencies=[Depends(admin_guard)])
    async def update_contact(contact_id: str, body: ContactBody):
        result = admin_result(service.update_contact, contact_id, body.name, body.email)
        await runtime.notify_admins()
        return result

    @admin_app.put("/api/admin/contacts/{contact_id}/character", dependencies=[Depends(admin_guard)])
    async def assign_character(contact_id: str, body: CharacterLinkBody):
        result = admin_result(service.assign_character, contact_id, body.character_id)
        connections = [
            connection for connection in runtime.connections.values()
            if connection.contact_id == contact_id
        ]
        for connection in connections:
            connection.name = result["display_name"]
            connection.character_id = result.get("character_id")
            try:
                await connection.websocket.send_json({
                    "v": 1,
                    "type": "identity_updated",
                    "player": result["display_name"],
                    "character_id": result.get("character_id"),
                })
            except Exception:
                pass
        await runtime.notify_admins()
        for connection in connections:
            await runtime.broadcast_board(connection.session_id)
        return result

    @admin_app.delete("/api/admin/contacts/{contact_id}", dependencies=[Depends(admin_guard)])
    async def delete_contact(contact_id: str):
        admin_result(service.delete_contact, contact_id)
        await runtime.notify_admins()
        return {"deleted": True}

    @admin_app.post("/api/admin/sessions", dependencies=[Depends(admin_guard)])
    async def create_session(body: SessionBody):
        result = admin_result(
            service.create_session, body.title, body.game_day, body.contact_ids,
            body.expiration_time, body.event_date, body.campaign_id,
        )
        await runtime.notify_admins()
        return result

    @admin_app.post("/api/admin/sessions/{session_id}/duplicate", dependencies=[Depends(admin_guard)])
    async def duplicate_session(session_id: str):
        result = admin_result(service.duplicate_session, session_id)
        await runtime.notify_admins()
        return result

    @admin_app.post("/api/admin/sessions/{session_id}/end", dependencies=[Depends(admin_guard)])
    async def end_selected_session(session_id: str):
        await runtime.disconnect_session(
            session_id, "session_expired", "The game session has ended."
        )
        result = admin_result(service.end_session, "ended", session_id)
        await runtime.notify_admins()
        return result

    @admin_app.delete("/api/admin/sessions/{session_id}", dependencies=[Depends(admin_guard)])
    async def delete_session(session_id: str):
        await runtime.disconnect_session(
            session_id, "session_expired", "The game session was deleted."
        )
        result = admin_result(service.delete_session, session_id)
        await runtime.notify_admins()
        return result

    @admin_app.delete(
        "/api/admin/sessions/{session_id}/players/{contact_id}",
        dependencies=[Depends(admin_guard)],
    )
    async def remove_session_player(session_id: str, contact_id: str):
        await runtime.disconnect(
            contact_id, "access_revoked", "You were removed from this game session.", session_id
        )
        result = admin_result(service.remove_player, session_id, contact_id)
        await runtime.notify_admins()
        return result

    @admin_app.put("/api/admin/session/event-date", dependencies=[Depends(admin_guard)])
    async def set_event_date(body: EventDateBody):
        result = admin_result(service.set_event_date, body.event_date, body.session_id)
        await runtime.notify_admins()
        return result

    @admin_app.put(
        "/api/admin/sessions/{session_id}/game-datetime",
        dependencies=[Depends(admin_guard)],
    )
    async def set_game_datetime(session_id: str, body: GameDateTimeBody):
        result = admin_result(
            service.set_game_datetime, session_id, body.game_datetime
        )
        await runtime.broadcast_board(session_id)
        return result

    @admin_app.post("/api/admin/board/move", dependencies=[Depends(admin_guard)])
    async def move_board_person(body: BoardMoveBody):
        result = admin_result(
            service.move_person,
            body.session_id,
            body.person_id,
            body.map_id,
            body.x,
            body.y,
        )
        await runtime.broadcast_board(body.session_id)
        return result

    @admin_app.post("/api/admin/board/move-preview", dependencies=[Depends(admin_guard)])
    async def preview_board_person(body: BoardMoveBody):
        await runtime.broadcast_move_preview(
            body.session_id,
            body.person_id,
            body.map_id,
            body.x,
            body.y,
        )
        return {"broadcast": True}

    @admin_app.put(
        "/api/admin/board/people/{person_id}",
        dependencies=[Depends(admin_guard)],
    )
    async def update_board_person(person_id: str, body: BoardPersonBody):
        updates = {
            key: value
            for key, value in body.model_dump().items()
            if key != "session_id" and value is not None
        }
        result = admin_result(
            service.update_person_board,
            body.session_id,
            person_id,
            updates,
        )
        for session in service.sessions_view():
            await runtime.broadcast_board(session["id"])
        return result

    @admin_app.put(
        "/api/admin/board/maps/{map_id}/visibility",
        dependencies=[Depends(admin_guard)],
    )
    async def publish_board_map(map_id: str, body: MapVisibilityBody):
        result = admin_result(
            service.set_map_published,
            body.session_id,
            map_id,
            body.published,
        )
        for session in service.sessions_view():
            await runtime.broadcast_board(session["id"])
        return result

    @admin_app.put(
        "/api/admin/board/maps/{map_id}/presentation",
        dependencies=[Depends(admin_guard)],
    )
    async def update_board_map_presentation(map_id: str, body: MapPresentationBody):
        result = admin_result(
            service.set_map_presentation,
            body.session_id,
            map_id,
            published=body.published,
            obscurations=body.obscurations,
            preview_opacity=body.preview_opacity,
            preview_color=body.preview_color,
        )
        for session in service.sessions_view():
            await runtime.broadcast_board(session["id"])
        return result

    @admin_app.put(
        "/api/admin/board/maps/{map_id}/settings",
        dependencies=[Depends(admin_guard)],
    )
    async def update_board_map_settings(map_id: str, body: MapBoardSettingsBody):
        result = admin_result(
            service.set_map_settings,
            body.session_id,
            map_id,
            token_scale=body.token_scale,
            start_point=body.start_point,
            update_start_point=body.update_start_point,
        )
        for session in service.sessions_view():
            await runtime.broadcast_board(session["id"])
        return result

    @admin_app.post(
        "/api/admin/board/groups",
        dependencies=[Depends(admin_guard)],
    )
    async def create_board_group(body: BoardGroupBody):
        result = admin_result(
            service.create_board_group,
            body.session_id,
            body.name,
            body.location_id,
            body.person_ids,
        )
        for session in service.sessions_view():
            await runtime.broadcast_board(session["id"])
        return result

    @admin_app.put(
        "/api/admin/board/groups/people/{person_id}",
        dependencies=[Depends(admin_guard)],
    )
    async def set_board_group(person_id: str, body: GroupMembershipBody):
        result = admin_result(
            service.set_board_group, body.session_id, person_id, body.group_id
        )
        for session in service.sessions_view():
            await runtime.broadcast_board(session["id"])
        return {"group": result}

    @admin_app.put(
        "/api/admin/board/workspace",
        dependencies=[Depends(admin_guard)],
    )
    async def update_board_workspace(body: BoardWorkspaceBody):
        result = admin_result(
            service.set_board_workspace,
            body.session_id,
            body.loaded_map_ids,
            body.active_map_id,
        )
        await runtime.notify_admins()
        return result

    @admin_app.put(
        "/api/admin/board/control",
        dependencies=[Depends(admin_guard)],
    )
    async def grant_board_control(body: ControlGrantBody):
        result = admin_result(
            service.grant_board_control,
            body.session_id,
            body.contact_id,
            body.person_id,
            body.granted,
        )
        await runtime.broadcast_board(body.session_id)
        return result

    @admin_app.post("/api/admin/gmail/authorize", dependencies=[Depends(admin_guard)])
    def authorize_gmail(body: GmailAuthorizeBody | None = None):
        try:
            if body is not None:
                runtime.service.update_gmail_settings(body.credentials_path, body.sender)
            return runtime.gmail().authorize()
        except GmailUnavailable as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=400, detail=f"Gmail connection failed: {error}") from error

    @admin_app.post("/api/admin/invitations/send", dependencies=[Depends(admin_guard)])
    async def send_invitations(body: SendBody):
        session = service.session_view(body.session_id)
        if not session:
            raise HTTPException(status_code=400, detail="There is no active session")
        players = {item["contact_id"]: item for item in session["roster"]}
        results = []
        for contact_id in body.contact_ids:
            if contact_id not in players:
                results.append({"contact_id": contact_id, "success": False, "error": "Not in session roster"})
                continue
            try:
                _raw, link, player = service.prepare_invite(contact_id, session["id"])
                subject = f"Game Board invitation: {session['title']}"
                local_expiration = parse_utc(session["expires_at"]).astimezone(
                    ZoneInfo(service.settings(include_private=True)["timezone"])
                ).strftime("%B %d, %Y at %I:%M %p %Z")
                game_datetime = format_game_datetime_for_people(session["game_datetime"])
                email_body = (
                    f"Hello {player['name']},\n\n"
                    f"Use this private link to request admission to {session['title']}:\n\n{link}\n\n"
                    f"Game World Date: {game_datetime}.\n"
                    f"The invitation expires {local_expiration}. The headmaster must approve every connection.\n"
                )
                # Gmail delivery previously proved reliable on the server's owning
                # thread. Keep it there; the desktop client now supplies the longer
                # batch timeout and prevents duplicate clicks while this completes.
                message_id = runtime.gmail().send(player["email"], subject, email_body)
                service.record_invite_result(contact_id, True, session["id"])
                results.append({"contact_id": contact_id, "success": True, "message_id": message_id})
            except Exception as error:
                try:
                    service.record_invite_result(contact_id, False, session["id"])
                except Exception:
                    pass
                results.append({"contact_id": contact_id, "success": False, "error": str(error)})
        await runtime.notify_admins()
        return {"results": results}

    @admin_app.post("/api/admin/admissions/{request_id}/approve", dependencies=[Depends(admin_guard)])
    async def approve(request_id: str):
        admin_result(service.approve, request_id)
        await runtime.notify_admins()
        return {"approved": True}

    @admin_app.post("/api/admin/admissions/{request_id}/deny", dependencies=[Depends(admin_guard)])
    async def deny(request_id: str):
        admin_result(service.deny, request_id)
        await runtime.notify_admins()
        return {"denied": True}

    @admin_app.post("/api/admin/players/{contact_id}/revoke", dependencies=[Depends(admin_guard)])
    async def revoke(contact_id: str):
        admin_result(service.revoke, contact_id)
        await runtime.disconnect(contact_id, "access_revoked", "The headmaster revoked this invitation.")
        await runtime.notify_admins()
        return {"revoked": True}

    @admin_app.post(
        "/api/admin/sessions/{session_id}/players/{contact_id}/revoke",
        dependencies=[Depends(admin_guard)],
    )
    async def revoke_session_player(session_id: str, contact_id: str):
        admin_result(service.revoke, contact_id, session_id)
        await runtime.disconnect(
            contact_id, "access_revoked", "The headmaster revoked this invitation.", session_id
        )
        await runtime.notify_admins()
        return {"revoked": True}

    @admin_app.post("/api/admin/session/{action}", dependencies=[Depends(admin_guard)])
    async def session_action(action: str):
        if action == "pause":
            admin_result(service.set_paused, True)
        elif action == "resume":
            admin_result(service.set_paused, False)
        elif action == "end":
            await runtime.disconnect_all("session_expired", "The game session has ended.")
            admin_result(service.end_session, "ended")
        else:
            raise HTTPException(status_code=404, detail="Unknown session action")
        await runtime.notify_admins()
        return {"action": action}

    @admin_app.post("/api/admin/announcements", dependencies=[Depends(admin_guard)])
    async def announcement(body: AnnouncementBody):
        try:
            announcement_id = await runtime.announce(body.message.strip(), body.session_id)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        await runtime.notify_admins()
        return {"id": announcement_id}

    @admin_app.post("/api/admin/chat", dependencies=[Depends(admin_guard)])
    async def headmaster_chat(body: ChatBody):
        try:
            return await runtime.chat(
                "headmaster", "Headmaster", "headmaster", body.message, body.session_id
            )
        except (PermissionError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @admin_app.websocket("/ws/admin")
    async def admin_websocket(websocket: WebSocket, key: str = Query(default="")):
        if key != settings["admin_key"]:
            await websocket.close(code=4403)
            return
        await websocket.accept()
        runtime.admin_sockets.add(websocket)
        try:
            await websocket.send_json({"v": 1, "type": "state", "data": runtime.state()})
            while True:
                await websocket.receive_text()
        except Exception:
            runtime.admin_sockets.discard(websocket)

    @player_app.get("/health")
    async def health():
        sessions = service.sessions_view()
        return {
            "service": "game-board",
            "available": bool(sessions),
            "paused": bool(sessions and all(session["status"] == "paused" for session in sessions)),
        }

    def require_origin(origin: str) -> None:
        allowed = service.settings(include_private=True)["allowed_origin"]
        if not allowed or origin != allowed:
            raise PermissionError("This player-page origin is not allowed")

    @player_app.post("/v1/admissions")
    async def request_admission(body: AdmissionBody, request: Request):
        try:
            require_origin(request.headers.get("origin", ""))
            client_ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")
            key = f"{client_ip}:{token_hash(body.invite_token)[:16]}"
            if not runtime.rate_limiter.allow(key):
                raise HTTPException(status_code=429, detail="Too many admission attempts")
            result = service.request_admission(body.invite_token, client_ip, request.headers.get("user-agent", ""))
            await runtime.notify_admins()
            return result
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @player_app.get("/v1/admissions/{request_id}")
    async def poll_admission(request_id: str, request: Request, authorization: str = Header(default="")):
        try:
            require_origin(request.headers.get("origin", ""))
            if not authorization.startswith("Bearer "):
                raise PermissionError("Missing polling credential")
            return service.poll_admission(request_id, authorization.removeprefix("Bearer "))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Unknown admission request") from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=410, detail=str(error)) from error

    @player_app.get("/v1/assets/{asset_id:path}")
    async def player_asset(
        asset_id: str,
        request: Request,
        authorization: str = Header(default=""),
    ):
        try:
            require_origin(request.headers.get("origin", ""))
            if not authorization.startswith("Bearer "):
                raise PermissionError("Missing asset credential")
            credential = authorization.removeprefix("Bearer ").strip()
            connection_key = runtime.asset_credentials.get(token_hash(credential))
            connection = runtime.connections.get(connection_key or "")
            if connection is None:
                raise PermissionError("This asset credential is no longer active")
            path, media_type = service.resolve_player_asset(
                connection.session_id,
                asset_id,
            )
            return FileResponse(
                path,
                media_type=media_type,
                headers={"Cache-Control": "private, no-store"},
            )
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Asset not found") from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @player_app.websocket("/v1/session")
    async def player_websocket(websocket: WebSocket, ticket: str = Query(default="")):
        try:
            require_origin(websocket.headers.get("origin", ""))
            identity = service.consume_ticket(ticket)
        except Exception:
            await websocket.close(code=4403)
            return
        await websocket.accept()
        asset_credential = token_urlsafe(32)
        asset_credential_hash = token_hash(asset_credential)
        connection = PlayerConnection(
            websocket=websocket,
            request_id=identity["request_id"],
            contact_id=identity["contact_id"],
            name=identity["name"],
            session_id=identity["session_id"],
            character_id=identity.get("character_id"),
            asset_credential_hash=asset_credential_hash,
        )
        connection_key = f"{identity['session_id']}:{identity['contact_id']}"
        runtime.connections[connection_key] = connection
        runtime.asset_credentials[asset_credential_hash] = connection_key
        await websocket.send_json({
            "v": 1, "type": "connection_accepted", "player": identity["name"],
            "player_id": identity["contact_id"], "session": identity["session_title"],
            "character_id": identity.get("character_id"),
            "asset_credential": asset_credential,
        })
        session = service.session_view(identity["session_id"])
        await websocket.send_json({
            "v": 1,
            "type": "chat_history",
            "messages": list((session or {}).get("chat", []))[-100:],
        })
        await runtime.chat(
            "system",
            "Game Board",
            "system",
            f"{identity['name']} is here!",
            identity["session_id"],
        )
        await runtime.send_board_snapshot(connection)
        await runtime.notify_admins()

        async def heartbeat_loop():
            while True:
                await asyncio.sleep(5)
                if connection.heartbeats:
                    connection.missed += 1
                if connection.missed >= 3:
                    await websocket.close(code=4000, reason="Heartbeat timeout")
                    return
                heartbeat_id = str(uuid4())
                connection.heartbeats[heartbeat_id] = time.monotonic()
                await websocket.send_json({"v": 1, "type": "heartbeat", "id": heartbeat_id})
                await runtime.notify_admins()

        heartbeat_task = asyncio.create_task(heartbeat_loop())
        try:
            while True:
                message = await websocket.receive_json()
                if not isinstance(message, dict) or message.get("v") != 1:
                    await websocket.send_json({"v": 1, "type": "server_error", "message": "Invalid message envelope"})
                    continue
                connection.last_activity = datetime.now(timezone.utc).isoformat()
                if message.get("type") == "heartbeat_ack":
                    started = connection.heartbeats.pop(str(message.get("id", "")), None)
                    if started is None:
                        continue
                    latency = (time.monotonic() - started) * 1000
                    connection.latency_ms = latency
                    connection.latency_total_ms += latency
                    connection.latency_samples += 1
                    connection.missed = 0
                    connection.heartbeats.clear()
                    quality = service.connection_quality(latency, 0)
                    await websocket.send_json({
                        "v": 1, "type": "connection_quality",
                        "quality": quality, "latency_ms": round(latency, 1),
                    })
                    await runtime.notify_admins()
                elif message.get("type") == "acknowledgement" and isinstance(message.get("announcement_id"), str):
                    service.record_acknowledgement(
                        connection.contact_id, connection.session_id
                    )
                    await runtime.notify_admins()
                elif message.get("type") == "chat_message" and isinstance(message.get("message"), str):
                    now = time.monotonic()
                    while connection.chat_events and connection.chat_events[0] <= now - 10:
                        connection.chat_events.popleft()
                    if len(connection.chat_events) >= 5:
                        await websocket.send_json({
                            "v": 1, "type": "server_error",
                            "message": "Please wait a moment before sending another chat message.",
                        })
                        continue
                    connection.chat_events.append(now)
                    try:
                        await runtime.chat(
                            connection.contact_id, connection.name, "player", message["message"],
                            connection.session_id,
                        )
                    except (PermissionError, ValueError) as error:
                        await websocket.send_json({
                            "v": 1, "type": "server_error", "message": str(error),
                        })
                elif message.get("type") == "board_travel":
                    try:
                        person_id = str(message.get("person_id", ""))
                        source_map_id = str(message.get("source_map_id", ""))
                        region_id = str(message.get("region_id", ""))
                        x, y = float(message.get("x")), float(message.get("y"))
                        if not person_id or not source_map_id or not region_id:
                            raise ValueError("A character, source map, and travel area are required")
                        if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
                            raise ValueError("Travel coordinates must be between zero and one")
                        service.travel_person(
                            connection.session_id,
                            connection.contact_id,
                            person_id,
                            source_map_id,
                            region_id,
                            x,
                            y,
                        )
                        await runtime.broadcast_board(connection.session_id)
                    except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as error:
                        await websocket.send_json({
                            "v": 1, "type": "server_error", "message": str(error),
                        })
                elif message.get("type") in {"board_move_preview", "board_move_commit"}:
                    try:
                        person_id = str(message.get("person_id", ""))
                        map_id = str(message.get("map_id", ""))
                        x = float(message.get("x"))
                        y = float(message.get("y"))
                        if not person_id or not map_id:
                            raise ValueError("A person and map are required")
                        if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
                            raise ValueError("Board coordinates must be between zero and one")
                        now = time.monotonic()
                        while connection.move_events and connection.move_events[0] <= now - 1:
                            connection.move_events.popleft()
                        if len(connection.move_events) >= 30:
                            raise PermissionError("Token movement is arriving too quickly")
                        connection.move_events.append(now)
                        if message["type"] == "board_move_preview":
                            await runtime.preview_move(connection, person_id, map_id, x, y)
                        else:
                            service.move_person(
                                connection.session_id,
                                person_id,
                                map_id,
                                x,
                                y,
                                contact_id=connection.contact_id,
                            )
                            await runtime.broadcast_board(connection.session_id)
                    except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as error:
                        await websocket.send_json({
                            "v": 1,
                            "type": "server_error",
                            "message": str(error),
                        })
                        await runtime.send_board_snapshot(connection)
                else:
                    await websocket.send_json({"v": 1, "type": "server_error", "message": "Unknown message type"})
        except Exception:
            pass
        finally:
            heartbeat_task.cancel()
            runtime.connections.pop(connection_key, None)
            runtime.asset_credentials.pop(asset_credential_hash, None)
            if not connection.persisted:
                service.mark_disconnected(
                    connection.request_id,
                    time.monotonic() - connection.connected_at,
                    connection.latency_total_ms,
                    connection.latency_samples,
                )
            await runtime.notify_admins()

    return admin_app, player_app, runtime


async def _serve() -> None:
    try:
        import uvicorn
    except ImportError as error:
        raise RuntimeError(
            "Install the Game Board dependencies with: python -m pip install -e .[game-board]"
        ) from error
    admin_app, player_app, runtime = create_apps()
    settings = runtime.service.settings(include_private=True)
    print(f"Headmaster control API: http://{settings['admin_host']}:{settings['admin_port']}")
    print(f"Player origin service: http://{settings['player_host']}:{settings['player_port']}")
    admin_server = uvicorn.Server(uvicorn.Config(
        admin_app, host=settings["admin_host"], port=settings["admin_port"],
        log_level="info", ws_max_size=MAX_MESSAGE_BYTES,
    ))
    player_server = uvicorn.Server(uvicorn.Config(
        player_app, host=settings["player_host"], port=settings["player_port"],
        log_level="info", ws_max_size=MAX_MESSAGE_BYTES,
    ))
    await asyncio.gather(admin_server.serve(), player_server.serve())


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
