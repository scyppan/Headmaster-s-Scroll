from __future__ import annotations

import asyncio
import hashlib
import json
import os
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from secrets import token_urlsafe
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..campaigns import CampaignRepository
from ..paths import RUNTIME_DIRECTORY
from .gmail import GmailSender, GmailUnavailable
from .service import (
    GameBoardService,
    format_game_datetime_for_people,
    iso_utc,
    parse_utc,
    token_hash,
    utc_now,
)
from .storage import GameBoardRepository


MAX_MESSAGE_BYTES = 16_384
PLAYER_PREVIEW_DIRECTORY = RUNTIME_DIRECTORY / "game-board-image-previews"


def _json_signature(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _preview_image(path: Path, asset_id: str) -> tuple[Path, str]:
    """Return a small disposable WebP for the browser's first paint."""

    from PIL import Image, ImageOps

    source = Path(path)
    stat = source.stat()
    cache_key = hashlib.sha256(
        f"{asset_id}:{stat.st_size}:{stat.st_mtime_ns}:v1".encode("utf-8")
    ).hexdigest()
    PLAYER_PREVIEW_DIRECTORY.mkdir(parents=True, exist_ok=True)
    destination = PLAYER_PREVIEW_DIRECTORY / f"{cache_key}.webp"
    if destination.is_file() and destination.stat().st_size:
        return destination, "image/webp"
    temporary = destination.with_suffix(
        f".webp.{os.getpid()}.{uuid4().hex}.tmp"
    )
    try:
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            maximum = 1280 if max(image.size) > 1024 else 256
            image.thumbnail((maximum, maximum), Image.Resampling.LANCZOS)
            image.save(temporary, format="WEBP", quality=68, method=4)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination, "image/webp"


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


class SessionExpirationBody(BaseModel):
    expires_at: str = Field(min_length=1, max_length=64)
    expected_expires_at: str = Field(min_length=1, max_length=64)


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


class TeachingBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    teacher_person_id: str = Field(min_length=1, max_length=100)
    pupil_person_id: str = Field(min_length=1, max_length=100)
    knowledge_kind: str = Field(min_length=1, max_length=30)
    knowledge_record_id: str = Field(min_length=1, max_length=120)
    knowledge_collection: str = Field(default="", max_length=80)


class TeachingOptionsBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    teacher_person_id: str = Field(min_length=1, max_length=100)


class AdminRegionSearchOptionsBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    person_id: str = Field(min_length=1, max_length=100)


class AdminRegionSearchBody(AdminRegionSearchOptionsBody):
    map_id: str = Field(min_length=1, max_length=120)
    region_id: str = Field(min_length=1, max_length=120)
    mode_id: str = Field(min_length=1, max_length=120)
    extraction_method_id: str = Field(default="", max_length=120)


class RequestResolutionBody(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=100)
    decision: str = Field(min_length=1, max_length=20)
    pupil_person_id: str = Field(default="", max_length=100)
    knowledge_kind: str = Field(default="", max_length=30)
    knowledge_record_id: str = Field(default="", max_length=120)
    knowledge_collection: str = Field(default="", max_length=80)
    actor_person_id: str = Field(default="", max_length=100)
    interaction_action: str = Field(default="", max_length=20)
    creature_name: str = Field(default="", max_length=200)


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


class BoardTransportBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    person_id: str = Field(min_length=1, max_length=100)
    map_id: str = Field(min_length=1, max_length=100)
    warp_point_id: str = Field(min_length=1, max_length=100)


class BoardPlaceCharacterBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    person_id: str = Field(min_length=1, max_length=100)
    map_id: str = Field(min_length=1, max_length=100)
    x: float = Field(default=0.5, ge=0.0, le=1.0)
    y: float = Field(default=0.5, ge=0.0, le=1.0)
    confirm_move: bool = False


class QuickCharacterBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    map_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    age: int = Field(ge=0, le=1000)
    development_strategy: str = Field(default="random", min_length=1, max_length=80)
    player_character: bool = False


class BoardPersonBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    visibility: str | None = Field(default=None, max_length=20)
    display_mode: str | None = Field(default=None, max_length=20)
    name_revealed: bool | None = None
    faction_revealed: bool | None = None
    faction_organization_id: str | None = Field(default=None, max_length=100)
    label_offset: dict[str, float] | None = None
    nameplate_scale: float | None = Field(default=None, ge=0.5, le=3.0)


class BoardPersonActionBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    action: str = Field(min_length=1, max_length=30)
    severity: str = Field(default="", max_length=20)
    text: str = Field(default="", max_length=4000)
    battle_name: str = Field(default="", max_length=200)


class CharacterCurrencyAdjustmentBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    change_knuts: int = Field(ge=-2_147_483_647, le=2_147_483_647)


class MapVisibilityBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    published: bool


class SecretRevealBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    map_id: str = Field(min_length=1, max_length=100)
    revealed: bool


class MapPresentationBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    published: bool
    obscurations: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    preview_opacity: float = Field(default=0.35, ge=0.05, le=1.0)
    preview_color: str = Field(default="#ff0000", min_length=7, max_length=7)


class MapBoardSettingsBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    token_scale: float | None = Field(default=None, ge=0.002, le=0.03)
    zoom_profile: dict[str, Any] | None = None
    preview_opacity: float | None = Field(default=None, ge=0.05, le=1.0)
    preview_color: str | None = Field(default=None, min_length=7, max_length=7)


class BoardGroupBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    location_id: str = Field(min_length=1, max_length=100)
    person_ids: list[str] = Field(min_length=1, max_length=100)
    color: str = Field(default="#b0b0b0", min_length=7, max_length=7)


class BoardFactionBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    person_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    color: str = Field(default="#808080", min_length=7, max_length=7)


class BoardFactionColorBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    color: str = Field(min_length=7, max_length=7)


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


class BoardCameraBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    zoom: float = Field(ge=1.0, le=32.0)
    center_x: float = Field(ge=0.0, le=1.0)
    center_y: float = Field(ge=0.0, le=1.0)
    force_players: bool = False


class CreaturePlaceBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    species_id: str = Field(min_length=1, max_length=120)
    map_id: str = Field(min_length=1, max_length=100)
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class CreatureUpdateBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    map_id: str | None = Field(default=None, max_length=100)
    x: float | None = Field(default=None, ge=0.0, le=1.0)
    y: float | None = Field(default=None, ge=0.0, le=1.0)
    label_x: float | None = Field(default=None, ge=-1.0, le=1.0)
    label_y: float | None = Field(default=None, ge=-1.0, le=1.0)
    visibility: str | None = Field(default=None, max_length=20)


class CreatureActionBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    action: str = Field(min_length=1, max_length=30)
    severity: str = Field(default="", max_length=20)
    note: str = Field(default="", max_length=1000)
    battle_name: str = Field(default="", max_length=200)


class CreatureRollBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    action_id: str = Field(min_length=1, max_length=160)


class CreatureInteractionBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    actor_person_id: str = Field(min_length=1, max_length=100)
    action: str = Field(min_length=1, max_length=20)
    creature_name: str = Field(default="", max_length=200)


class BattleCreateBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    map_id: str = Field(min_length=1, max_length=120)


class BattleActorBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    actor_type: str = Field(min_length=1, max_length=20)
    actor_id: str = Field(min_length=1, max_length=120)
    transfer: bool = False


class BattleActorReference(BaseModel):
    actor_type: str = Field(min_length=1, max_length=20)
    actor_id: str = Field(min_length=1, max_length=120)


class BattleActorsBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    actors: list[BattleActorReference] = Field(min_length=1, max_length=500)
    transfer: bool = False


class BattleNamedCreatureBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    named_creature_id: str = Field(min_length=1, max_length=120)
    map_id: str = Field(min_length=1, max_length=120)
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class BattleOrderBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    order: list[str] | None = Field(default=None, max_length=500)


class BattleTurnBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    action: str = Field(min_length=1, max_length=20)
    summary: str = Field(default="", max_length=1000)


class BattleConsequenceBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    action: str = Field(min_length=1, max_length=30)
    wound_id: str = Field(default="", max_length=120)
    severity: str = Field(default="", max_length=20)
    injury_type: str = Field(default="", max_length=120)
    text: str = Field(default="", max_length=4000)


class HeadmasterPersonRollBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    roll_type: str = Field(min_length=1, max_length=30)
    target_id: str = Field(min_length=1, max_length=160)


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
    roll_events: deque[float] = field(default_factory=deque)
    board_state: dict[str, Any] | None = None
    character_sheet_signature: str = ""
    controlled_ids: set[str] = field(default_factory=set)

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
        self._world_fingerprint = self.service.world_fingerprint()
        self._state_lock = threading.RLock()
        self._state_build_lock = threading.Lock()
        self._state_cache: dict[str, Any] | None = None
        self._state_dirty = True
        self._state_generation = 0
        self._board_broadcast_generations: dict[str, int] = defaultdict(int)
        self._board_broadcast_tasks: dict[str, asyncio.Task[Any]] = {}
        # Gmail credentials and transports are shared process-wide.  Keep one
        # invitation batch in flight so two desktop windows cannot accidentally
        # send the same roster at the same time.
        self.invitation_batch_lock = asyncio.Lock()
        # Session removal and expiration must not invalidate links midway
        # through a confirmed delivery batch for that same session.
        self.session_lifecycle_locks: defaultdict[str, asyncio.Lock] = defaultdict(
            asyncio.Lock
        )

    def world_changed(self) -> bool:
        try:
            fingerprint = self.service.world_fingerprint()
        except OSError:
            return False
        if fingerprint == self._world_fingerprint:
            return False
        self._world_fingerprint = fingerprint
        self.invalidate_state()
        return True

    def invalidate_state(self) -> None:
        with self._state_lock:
            self._state_dirty = True
            self._state_generation += 1

    def queue_board_broadcast(self, session_id: str, delay: float = 0.075) -> None:
        """Coalesce expensive per-player board snapshots after rapid moves."""

        session_id = str(session_id or "")
        if not session_id:
            return
        self._board_broadcast_generations[session_id] += 1
        current = self._board_broadcast_tasks.get(session_id)
        if current is not None and not current.done():
            return

        async def publish() -> None:
            try:
                while True:
                    generation = self._board_broadcast_generations[session_id]
                    await asyncio.sleep(max(0.0, delay))
                    await self.broadcast_board(session_id)
                    if generation == self._board_broadcast_generations[session_id]:
                        return
            finally:
                self._board_broadcast_tasks.pop(session_id, None)

        self._board_broadcast_tasks[session_id] = asyncio.create_task(publish())

    def state(self) -> dict[str, Any]:
        # Only one worker may assemble the large admin snapshot.  Concurrent
        # polls reuse its result instead of multiplying JSON/campaign work.
        with self._state_build_lock:
            with self._state_lock:
                if self._state_cache is not None and not self._state_dirty:
                    return self._state_cache
                generation = self._state_generation
            sessions = self.service.sessions_view()
            archived_sessions = self.service.archived_sessions_view()
            board_session = self.service.board_session_view()
            board_session_id = (
                str(board_session.get("id", "")) if board_session else None
            )
            boards = {}
            battles = {}
            if board_session_id:
                try:
                    boards[board_session_id] = self.service.board_snapshot(
                        board_session_id,
                        for_players=False,
                    )
                except (KeyError, ValueError):
                    board_session = None
                    board_session_id = None
                    boards = {}
                if board_session and board_session.get("campaign_id"):
                    try:
                        battles[board_session_id] = self.service.battle_snapshot(
                            board_session_id
                        )
                    except (KeyError, ValueError):
                        pass
            location_maps = []
            if board_session_id:
                try:
                    location_maps = self.service.location_maps(board_session_id)
                except (KeyError, ValueError):
                    location_maps = []
            try:
                characters = self.service.list_characters(board_session_id)
            except (KeyError, ValueError):
                # A session can end between the earlier snapshot and this
                # compact navigator projection.  Keep admin state available;
                # the next generation will advertise no designated board.
                characters = self.service.list_characters()
            result = {
                "contacts": self.service.list_contacts(),
                "characters": characters,
                "campaigns": self.service.list_campaigns(),
                "settings": self.service.settings(),
                "sessions": sessions,
                "archived_sessions": archived_sessions,
                "board_session_id": board_session_id,
                "session": board_session,
                "connections": [item.public(self.service) for item in self.connections.values()],
                "boards": boards,
                "battles": battles,
                "location_maps": location_maps,
                "gmail": self.gmail().status(),
                "requests": self.service.pending_campaign_requests(),
                "teaching_catalog": self.service.teaching_catalog(),
            }
            with self._state_lock:
                self._state_cache = result
                self._state_dirty = self._state_generation != generation
            return result

    def gmail(self) -> GmailSender:
        settings = self.service.settings(include_private=True)
        return GmailSender(settings["gmail_credentials_path"], settings["gmail_sender"])

    async def notify_admins(self) -> None:
        self.invalidate_state()
        if not self.admin_sockets:
            return
        state = await asyncio.to_thread(self.state)
        message = {"v": 1, "type": "state", "data": state}
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

    async def expire_due_sessions(self) -> int:
        """Expire every due session independently so one bad record cannot kill the loop."""

        try:
            sessions = self.service.sessions_view()
        except Exception:
            return 0
        expired_count = 0
        checked_at = utc_now()
        for session in sessions:
            session_id = str(session.get("id", ""))
            try:
                expires_at = str(session["expires_at"])
                if parse_utc(expires_at) > checked_at:
                    continue
            except Exception:
                continue
            async with self.session_lifecycle_locks[session_id]:
                try:
                    claimed = self.service.begin_session_expiration(
                        session_id, expires_at, now=checked_at
                    )
                except Exception:
                    continue
                if not claimed:
                    continue
                try:
                    await self.disconnect_session(
                        session_id,
                        "session_expired",
                        "The game session has expired.",
                    )
                    summary = self.service.finish_session_expiration(
                        session_id, expires_at
                    )
                except Exception:
                    try:
                        self.service.cancel_session_expiration(session_id)
                    except Exception:
                        pass
                    continue
                if summary is None:
                    try:
                        self.service.cancel_session_expiration(session_id)
                    except Exception:
                        pass
                    continue
                expired_count += 1
        if expired_count:
            try:
                await self.notify_admins()
            except Exception:
                pass
        return expired_count

    async def announce(
        self,
        text: str,
        session_id: str | None = None,
        *,
        require_board_session: bool = False,
    ) -> str:
        if require_board_session:
            await asyncio.to_thread(
                self.service.run_for_board_session,
                str(session_id or ""),
                self.service.increment_announcements,
                session_id,
            )
        else:
            self.service.increment_announcements(session_id)
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
        return announcement_id

    async def chat(
        self, sender_id: str, sender_name: str, sender_role: str, text: str,
        session_id: str | None = None,
        activity: dict[str, Any] | None = None,
        *,
        notify_admins: bool = True,
        require_board_session: bool = False,
    ) -> dict[str, Any]:
        arguments = (
            sender_id, sender_name, sender_role, text, session_id, activity,
        )
        if require_board_session:
            chat = await asyncio.to_thread(
                self.service.run_for_board_session,
                str(session_id or ""),
                self.service.post_chat,
                *arguments,
            )
        else:
            chat = await asyncio.to_thread(
                self.service.post_chat,
                *arguments,
            )
        creature_activity = isinstance(activity, dict) and activity.get(
            "activity_type"
        ) in {"creature_action", "creature_harvest"}

        def viewer_message(connection: Any) -> dict[str, Any]:
            if not creature_activity:
                return chat
            return self.service.chat_message_for_viewer(
                chat,
                str(session_id or getattr(connection, "session_id", "")),
                str(getattr(connection, "contact_id", "")),
            )

        await asyncio.gather(
            *(
                connection.websocket.send_json({
                    "v": 1,
                    "type": "chat_message",
                    "message": viewer_message(connection),
                })
                for connection in list(self.connections.values())
                if session_id is None or getattr(connection, "session_id", "") == session_id
            ),
            return_exceptions=True,
        )
        if notify_admins:
            await self.notify_admins()
        return chat

    async def send_board_snapshot(
        self,
        connection: PlayerConnection,
        *,
        force: bool = False,
    ) -> None:
        snapshot = await asyncio.to_thread(
            self.service.board_snapshot,
            connection.session_id,
            for_players=True,
            contact_id=connection.contact_id,
        )
        connection.controlled_ids = set(
            self.service.controlled_character_ids(
                connection.session_id, connection.contact_id,
            )
        )
        snapshot["controlled_character_ids"] = sorted(connection.controlled_ids)
        previous = connection.board_state
        connection.board_state = deepcopy(snapshot)
        if force or previous is None:
            await connection.websocket.send_json(
                {"v": 1, "type": "board_snapshot", "board": snapshot}
            )
            return

        previous_maps = {
            str(item.get("record_id", "")): item
            for item in previous.get("maps", []) or []
        }
        current_maps = {
            str(item.get("record_id", "")): item
            for item in snapshot.get("maps", []) or []
        }
        previous_actors = {
            str(item.get("actor_id", "")): item
            for item in previous.get("actors", []) or []
        }
        current_actors = {
            str(item.get("actor_id", "")): item
            for item in snapshot.get("actors", []) or []
        }
        scalars = {
            key: deepcopy(value)
            for key, value in snapshot.items()
            if key not in {"maps", "actors"} and previous.get(key) != value
        }
        patch = {
            "scalars": scalars,
            "maps_upsert": [
                deepcopy(value) for key, value in current_maps.items()
                if previous_maps.get(key) != value
            ],
            "map_ids_removed": sorted(set(previous_maps) - set(current_maps)),
            "actors_upsert": [
                deepcopy(value) for key, value in current_actors.items()
                if previous_actors.get(key) != value
            ],
            "actor_ids_removed": sorted(set(previous_actors) - set(current_actors)),
        }
        if not any((
            scalars, patch["maps_upsert"], patch["map_ids_removed"],
            patch["actors_upsert"], patch["actor_ids_removed"],
        )):
            return
        await connection.websocket.send_json(
            {"v": 1, "type": "board_patch", "patch": patch}
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

    async def send_battle_snapshot(
        self, connection: PlayerConnection, message_type: str = "battle_snapshot",
    ) -> None:
        snapshot = await asyncio.to_thread(
            self.service.battle_snapshot,
            connection.session_id,
            contact_id=connection.contact_id,
            for_players=True,
        )
        await connection.websocket.send_json({
            "v": 1, "type": message_type, "battle_state": snapshot,
        })

    async def broadcast_battles(self, session_id: str) -> None:
        await asyncio.gather(*(
            self.send_battle_snapshot(connection, "battle_updated")
            for connection in list(self.connections.values())
            if connection.session_id == session_id
        ), return_exceptions=True)
        await self.notify_admins()

    async def broadcast_character_sheets(self, session_id: str) -> None:
        await asyncio.gather(*(
            self.send_character_sheet(connection, "character_sheet_updated")
            for connection in list(self.connections.values())
            if connection.session_id == session_id
        ), return_exceptions=True)

    async def send_character_sheet(
        self,
        connection: PlayerConnection,
        message_type: str = "character_sheet_snapshot",
        *,
        force: bool = False,
    ) -> None:
        sheet = await asyncio.to_thread(
            self.service.character_sheet_for,
            connection.session_id,
            connection.contact_id,
        )
        signature = _json_signature(sheet)
        if not force and signature == connection.character_sheet_signature:
            return
        connection.character_sheet_signature = signature
        await connection.websocket.send_json({
            "v": 1,
            "type": message_type,
            "character_sheet": sheet,
        })

    async def focus_players(
        self,
        session_id: str,
        map_id: str,
        camera: dict[str, float],
    ) -> None:
        envelope = {
            "v": 1,
            "type": "board_camera_focus",
            "map_id": map_id,
            "camera": camera,
        }
        await asyncio.gather(
            *(
                connection.websocket.send_json(envelope)
                for connection in list(self.connections.values())
                if connection.session_id == session_id
            ),
            return_exceptions=True,
        )

    async def focus_transported_player(
        self,
        session_id: str,
        contact_ids: list[str],
        map_id: str,
        camera: dict[str, float],
    ) -> None:
        recipients = set(contact_ids)
        envelope = {
            "v": 1,
            "type": "board_transport",
            "map_id": map_id,
            "camera": camera,
        }
        await asyncio.gather(
            *(
                connection.websocket.send_json(envelope)
                for connection in list(self.connections.values())
                if connection.session_id == session_id
                and connection.contact_id in recipients
            ),
            return_exceptions=True,
        )

    async def preview_move(
        self,
        connection: PlayerConnection,
        person_id: str,
        map_id: str,
        x: float,
        y: float,
    ) -> None:
        if person_id not in connection.controlled_ids:
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
                and item is not connection
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
            await runtime.expire_due_sessions()
            try:
                if runtime.world_changed():
                    sessions = service.sessions_view()
                    await asyncio.gather(
                        *(
                            coroutine
                            for session in sessions
                            for coroutine in (
                                runtime.broadcast_board(session["id"]),
                                runtime.broadcast_character_sheets(session["id"]),
                            )
                        ),
                        return_exceptions=True,
                    )
                    if not sessions:
                        await runtime.notify_admins()
            except Exception:
                # A transient world/campaign read must not stop expiration.
                continue

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

    board_session_calls = {
        "add_battle_actor", "add_battle_actors", "add_named_creature_to_battle",
        "adjust_person_currency", "battle_actor_choices", "battle_combatant_sheet",
        "battle_snapshot", "admin_region_search_options", "admin_search_region",
        "character_sheet_for_person", "create_battle", "create_board_faction",
        "create_board_group", "create_quick_character", "creature_campaign_action",
        "end_battle", "grant_board_control", "headmaster_creature_interaction",
        "headmaster_roll_person_action", "place_campaign_creature",
        "move_person", "place_person_on_map", "remove_battle_actor", "reorder_battle",
        "roll_campaign_creature_action", "set_board_camera", "set_board_group",
        "set_board_workspace", "set_campaign_creature_group", "set_game_datetime",
        "set_map_presentation", "set_map_published", "set_map_settings",
        "set_secret_revealed", "start_battle", "transport_person",
        "teach_character", "teaching_options",
        "update_battle_combatant", "update_battle_turn",
        "update_board_faction_color", "update_campaign_creature",
        "update_person_board", "update_person_campaign_action",
    }

    def admin_result(callable_, *args, **kwargs):
        try:
            if getattr(callable_, "__name__", "") in board_session_calls and args:
                return service.run_for_board_session(
                    str(args[0] or ""), callable_, *args, **kwargs
                )
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
        return await asyncio.to_thread(runtime.state)

    @admin_app.get("/api/admin/health", dependencies=[Depends(admin_guard)])
    async def admin_health():
        # Deliberately performs no canonical-data reads.  Desktop startup must
        # distinguish a listening service from completion of the first state.
        return {"service": "game-board", "ready": True}

    @admin_app.get(
        "/api/admin/board/people/{person_id}/sheet",
        dependencies=[Depends(admin_guard)],
    )
    async def headmaster_character_sheet(person_id: str, session_id: str = Query(...)):
        return await asyncio.to_thread(
            admin_result,
            service.character_sheet_for_person,
            session_id,
            person_id,
        )

    @admin_app.get("/api/admin/admissions/pending", dependencies=[Depends(admin_guard)])
    async def pending_admissions():
        """Return the tiny admission queue without building full board state."""

        pending = []
        for session in service.sessions_view():
            for request in session.get("pending", []) or []:
                if request.get("status") != "pending":
                    continue
                pending.append({
                    "request_id": str(request.get("id", "")),
                    "name": str(request.get("name", "Player")),
                    "requested_at": str(request.get("requested_at", "")),
                    "client_ip": str(request.get("client_ip", "")),
                    "session_id": str(session.get("id", "")),
                    "session_title": str(session.get("title", "Session")),
                })
        return {"pending": pending}

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
        refreshed_sessions: set[str] = set()
        for connection in connections:
            connection.name = result["display_name"]
            connection.character_id = result.get("character_id")
            connection.controlled_ids = set(
                service.controlled_character_ids(
                    connection.session_id, connection.contact_id,
                )
            )
            connection.character_sheet_signature = ""
            connection.board_state = None
            if connection.character_id:
                service.activate_player_character_map(
                    connection.session_id,
                    contact_id,
                    str(connection.character_id),
                )
            refreshed_sessions.add(connection.session_id)
            try:
                await connection.websocket.send_json({
                    "v": 1,
                    "type": "identity_updated",
                    "player": result["display_name"],
                    "character_id": result.get("character_id"),
                })
                await runtime.send_character_sheet(
                    connection, "character_sheet_updated", force=True
                )
            except Exception:
                pass
        await runtime.notify_admins()
        for session_id in refreshed_sessions:
            await runtime.broadcast_board(session_id)
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

    @admin_app.put(
        "/api/admin/sessions/{session_id}/select",
        dependencies=[Depends(admin_guard)],
    )
    async def select_board_session(session_id: str):
        result = admin_result(service.select_board_session, session_id)
        for connection in runtime.connections.values():
            connection.board_state = None
        await runtime.notify_admins()
        return result

    @admin_app.put(
        "/api/admin/sessions/{session_id}/expiration",
        dependencies=[Depends(admin_guard)],
    )
    async def update_session_expiration(
        session_id: str, body: SessionExpirationBody
    ):
        result = admin_result(
            service.update_session_expiration,
            session_id,
            body.expires_at,
            body.expected_expires_at,
        )
        await runtime.notify_admins()
        return result

    @admin_app.post("/api/admin/sessions/{session_id}/end", dependencies=[Depends(admin_guard)])
    async def end_selected_session(session_id: str):
        async with runtime.session_lifecycle_locks[session_id]:
            await runtime.disconnect_session(
                session_id, "session_expired", "The game session has ended."
            )
            result = await asyncio.to_thread(
                admin_result, service.end_session, "ended", session_id
            )
        await runtime.notify_admins()
        return result

    @admin_app.delete("/api/admin/sessions/{session_id}", dependencies=[Depends(admin_guard)])
    async def delete_session(session_id: str):
        async with runtime.session_lifecycle_locks[session_id]:
            await runtime.disconnect_session(
                session_id, "session_expired", "The game session was deleted."
            )
            result = await asyncio.to_thread(
                admin_result, service.delete_session, session_id
            )
        await runtime.notify_admins()
        return result

    @admin_app.delete(
        "/api/admin/sessions/{session_id}/players/{contact_id}",
        dependencies=[Depends(admin_guard)],
    )
    async def remove_session_player(session_id: str, contact_id: str):
        async with runtime.session_lifecycle_locks[session_id]:
            await runtime.disconnect(
                contact_id,
                "access_revoked",
                "You were removed from this game session.",
                session_id,
            )
            result = await asyncio.to_thread(
                admin_result, service.remove_player, session_id, contact_id
            )
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
        await runtime.broadcast_character_sheets(session_id)
        return result

    @admin_app.post("/api/admin/board/move", dependencies=[Depends(admin_guard)])
    async def move_board_person(body: BoardMoveBody):
        result = await asyncio.to_thread(
            admin_result,
            service.move_person,
            body.session_id,
            body.person_id,
            body.map_id,
            body.x,
            body.y,
        )
        runtime.invalidate_state()
        runtime.queue_board_broadcast(body.session_id)
        return result

    @admin_app.post("/api/admin/board/transport", dependencies=[Depends(admin_guard)])
    async def transport_board_person(body: BoardTransportBody):
        result = admin_result(
            service.transport_person,
            body.session_id,
            body.person_id,
            body.map_id,
            body.warp_point_id,
        )
        await runtime.broadcast_board(body.session_id)
        await runtime.focus_transported_player(
            body.session_id,
            result.get("contact_ids", []),
            body.map_id,
            result["camera"],
        )
        return result

    @admin_app.post("/api/admin/board/place-character", dependencies=[Depends(admin_guard)])
    async def place_board_character(body: BoardPlaceCharacterBody):
        result = admin_result(
            service.place_person_on_map,
            body.session_id,
            body.person_id,
            body.map_id,
            body.x,
            body.y,
            confirm_move=body.confirm_move,
        )
        if not result.get("requires_confirmation"):
            await runtime.broadcast_board(body.session_id)
            await runtime.notify_admins()
        return result

    @admin_app.post("/api/admin/board/quick-character", dependencies=[Depends(admin_guard)])
    async def quick_board_character(body: QuickCharacterBody):
        result = admin_result(
            service.create_quick_character,
            body.session_id,
            body.map_id,
            body.name,
            body.age,
            body.development_strategy,
            body.player_character,
        )
        await runtime.broadcast_board(body.session_id)
        await runtime.notify_admins()
        return result

    async def publish_battle_change(session_id: str, battle_id: str) -> None:
        snapshot = admin_result(service.battle_snapshot, session_id)
        active = any(
            str(item.get("record_id", "")) == battle_id
            and str(item.get("status", "")) == "active"
            for item in snapshot.get("battles", []) or []
        )
        if active:
            await runtime.broadcast_battles(session_id)
        else:
            await runtime.notify_admins()

    @admin_app.get("/api/admin/battles", dependencies=[Depends(admin_guard)])
    async def list_battles(session_id: str = Query(min_length=1, max_length=100)):
        return admin_result(service.battle_snapshot, session_id)

    @admin_app.get(
        "/api/admin/battles/{battle_id}/actor-choices",
        dependencies=[Depends(admin_guard)],
    )
    async def battle_actor_choices(
        battle_id: str,
        session_id: str = Query(min_length=1, max_length=100),
        q: str = Query(default="", max_length=200),
    ):
        return await asyncio.to_thread(
            admin_result, service.battle_actor_choices,
            session_id, battle_id, q,
        )

    @admin_app.get(
        "/api/admin/battle-actor-choices",
        dependencies=[Depends(admin_guard)],
    )
    async def local_battle_actor_choices(
        session_id: str = Query(min_length=1, max_length=100),
        map_id: str = Query(min_length=1, max_length=120),
        q: str = Query(default="", max_length=200),
    ):
        return await asyncio.to_thread(
            admin_result, service.battle_actor_choices,
            session_id, "", q, map_id=map_id,
        )

    @admin_app.post("/api/admin/battles", dependencies=[Depends(admin_guard)])
    async def create_battle(body: BattleCreateBody):
        result = admin_result(
            service.create_battle, body.session_id, body.name, body.map_id
        )
        await runtime.notify_admins()
        return result

    @admin_app.post(
        "/api/admin/battles/{battle_id}/start",
        dependencies=[Depends(admin_guard)],
    )
    async def start_battle(battle_id: str, body: BattleTurnBody):
        result = admin_result(service.start_battle, body.session_id, battle_id)
        await runtime.broadcast_battles(body.session_id)
        return result

    @admin_app.delete(
        "/api/admin/battles/{battle_id}", dependencies=[Depends(admin_guard)]
    )
    async def end_battle(battle_id: str, session_id: str = Query(min_length=1, max_length=100)):
        admin_result(service.end_battle, session_id, battle_id)
        await runtime.broadcast_battles(session_id)
        return {"ended": True}

    @admin_app.post(
        "/api/admin/battles/{battle_id}/participants",
        dependencies=[Depends(admin_guard)],
    )
    async def add_battle_participant(battle_id: str, body: BattleActorBody):
        result = admin_result(
            service.add_battle_actor, body.session_id, battle_id,
            body.actor_type, body.actor_id, transfer=body.transfer,
        )
        await publish_battle_change(body.session_id, battle_id)
        return result

    @admin_app.post(
        "/api/admin/battles/{battle_id}/participants/bulk",
        dependencies=[Depends(admin_guard)],
    )
    async def add_battle_participants_bulk(
        battle_id: str, body: BattleActorsBody,
    ):
        result = admin_result(
            service.add_battle_actors, body.session_id, battle_id,
            [item.model_dump() for item in body.actors], transfer=body.transfer,
        )
        await publish_battle_change(body.session_id, battle_id)
        return {"participants": result}

    @admin_app.post(
        "/api/admin/battles/{battle_id}/named-creatures",
        dependencies=[Depends(admin_guard)],
    )
    async def add_named_battle_participant(
        battle_id: str, body: BattleNamedCreatureBody,
    ):
        result = admin_result(
            service.add_named_creature_to_battle,
            body.session_id, battle_id, body.named_creature_id,
            body.map_id, body.x, body.y,
        )
        await runtime.broadcast_board(body.session_id)
        await publish_battle_change(body.session_id, battle_id)
        return result

    @admin_app.delete(
        "/api/admin/battles/{battle_id}/participants/{participant_id}",
        dependencies=[Depends(admin_guard)],
    )
    async def remove_battle_participant(
        battle_id: str, participant_id: str,
        session_id: str = Query(min_length=1, max_length=100),
    ):
        admin_result(
            service.remove_battle_actor, session_id, battle_id, participant_id
        )
        await publish_battle_change(session_id, battle_id)
        return {"removed": True}

    @admin_app.put(
        "/api/admin/battles/{battle_id}/order",
        dependencies=[Depends(admin_guard)],
    )
    async def reorder_battle(battle_id: str, body: BattleOrderBody):
        result = admin_result(
            service.reorder_battle, body.session_id, battle_id, body.order
        )
        await publish_battle_change(body.session_id, battle_id)
        return result

    @admin_app.post(
        "/api/admin/battles/{battle_id}/turn",
        dependencies=[Depends(admin_guard)],
    )
    async def change_battle_turn(battle_id: str, body: BattleTurnBody):
        result = admin_result(
            service.update_battle_turn, body.session_id, battle_id,
            body.action, summary=body.summary,
        )
        await runtime.broadcast_battles(body.session_id)
        return result

    @admin_app.get(
        "/api/admin/battles/{battle_id}/participants/{participant_id}/sheet",
        dependencies=[Depends(admin_guard)],
    )
    async def battle_participant_sheet(
        battle_id: str, participant_id: str,
        session_id: str = Query(min_length=1, max_length=100),
    ):
        return await asyncio.to_thread(
            admin_result, service.battle_combatant_sheet,
            session_id, battle_id, participant_id,
        )

    @admin_app.post(
        "/api/admin/battles/{battle_id}/participants/{participant_id}/consequences",
        dependencies=[Depends(admin_guard)],
    )
    async def update_battle_participant_consequence(
        battle_id: str, participant_id: str, body: BattleConsequenceBody,
    ):
        result = admin_result(
            service.update_battle_combatant,
            body.session_id, battle_id, participant_id, body.action,
            wound_id=body.wound_id, severity=body.severity,
            injury_type=body.injury_type, text=body.text,
        )
        await runtime.broadcast_board(body.session_id)
        await runtime.broadcast_character_sheets(body.session_id)
        await runtime.broadcast_battles(body.session_id)
        return result

    @admin_app.post(
        "/api/admin/battles/people/{person_id}/roll",
        dependencies=[Depends(admin_guard)],
    )
    async def headmaster_battle_person_roll(
        person_id: str, body: HeadmasterPersonRollBody,
    ):
        result = admin_result(
            service.headmaster_roll_person_action,
            body.session_id, person_id, body.roll_type, body.target_id,
        )
        await runtime.chat(
            person_id, str(result.get("character_name") or "Character"),
            "headmaster", str(result.get("text") or "A character acts."),
            body.session_id, result,
        )
        await runtime.broadcast_battles(body.session_id)
        return result

    @admin_app.get("/api/admin/creatures", dependencies=[Depends(admin_guard)])
    def search_creature_species(
        q: str = Query(default="", max_length=200),
        limit: int = Query(default=100, ge=1, le=500),
    ):
        return {"creatures": admin_result(service.creature_species, q, limit)}

    @admin_app.post(
        "/api/admin/board/creatures", dependencies=[Depends(admin_guard)]
    )
    async def place_board_creature(body: CreaturePlaceBody):
        result = admin_result(
            service.place_campaign_creature,
            body.session_id, body.species_id, body.map_id, body.x, body.y,
        )
        await runtime.broadcast_board(body.session_id)
        return result

    @admin_app.put(
        "/api/admin/board/creatures/{creature_id}",
        dependencies=[Depends(admin_guard)],
    )
    async def update_board_creature(creature_id: str, body: CreatureUpdateBody):
        result = admin_result(
            service.update_campaign_creature,
            body.session_id,
            creature_id,
            x=body.x, y=body.y, map_id=body.map_id,
            label_x=body.label_x, label_y=body.label_y,
            visibility=body.visibility,
        )
        await runtime.broadcast_board(body.session_id)
        return result

    @admin_app.post(
        "/api/admin/board/creatures/{creature_id}/actions",
        dependencies=[Depends(admin_guard)],
    )
    async def update_board_creature_action(
        creature_id: str, body: CreatureActionBody
    ):
        result = admin_result(
            service.creature_campaign_action,
            body.session_id,
            creature_id,
            body.action,
            severity=body.severity,
            note=body.note,
            battle_name=body.battle_name,
        )
        await runtime.broadcast_board(body.session_id)
        return {"creature": result}

    @admin_app.put(
        "/api/admin/board/groups/creatures/{creature_id}",
        dependencies=[Depends(admin_guard)],
    )
    async def set_board_creature_group(
        creature_id: str, body: GroupMembershipBody
    ):
        result = admin_result(
            service.set_campaign_creature_group,
            body.session_id,
            creature_id,
            body.group_id,
        )
        await runtime.broadcast_board(body.session_id)
        return {"group": result}

    @admin_app.post(
        "/api/admin/board/creatures/{creature_id}/roll",
        dependencies=[Depends(admin_guard)],
    )
    async def roll_board_creature_action(
        creature_id: str, body: CreatureRollBody
    ):
        result = admin_result(
            service.roll_campaign_creature_action,
            body.session_id,
            creature_id,
            body.action_id,
        )
        await runtime.chat(
            creature_id,
            str(result.get("species_name") or "Creature"),
            "creature",
            str(result.get("text") or "A creature acts."),
            body.session_id,
            result,
        )
        await runtime.broadcast_battles(body.session_id)
        return result

    @admin_app.post(
        "/api/admin/board/creatures/{creature_id}/interact",
        dependencies=[Depends(admin_guard)],
    )
    async def interact_with_board_creature(
        creature_id: str, body: CreatureInteractionBody,
    ):
        result = admin_result(
            service.headmaster_creature_interaction,
            body.session_id, body.actor_person_id, creature_id,
            body.action, body.creature_name,
        )
        await runtime.chat(
            "headmaster", "Headmaster", "headmaster",
            str(result.get("text") or "A creature interaction was resolved."),
            body.session_id, result,
        )
        await runtime.broadcast_board(body.session_id)
        await runtime.broadcast_character_sheets(body.session_id)
        await runtime.notify_admins()
        return result

    @admin_app.post("/api/admin/board/move-preview", dependencies=[Depends(admin_guard)])
    async def preview_board_person(body: BoardMoveBody):
        admin_result(service.require_board_session, body.session_id)
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

    @admin_app.post(
        "/api/admin/board/people/{person_id}/actions",
        dependencies=[Depends(admin_guard)],
    )
    async def update_board_person_action(person_id: str, body: BoardPersonActionBody):
        result = admin_result(
            service.update_person_campaign_action,
            body.session_id,
            person_id,
            body.action,
            severity=body.severity,
            text=body.text,
            battle_name=body.battle_name,
        )
        await runtime.broadcast_board(body.session_id)
        await runtime.broadcast_character_sheets(body.session_id)
        await runtime.notify_admins()
        return result

    @admin_app.post(
        "/api/admin/board/people/{person_id}/currency-adjustment",
        dependencies=[Depends(admin_guard)],
    )
    async def adjust_character_currency(
        person_id: str, body: CharacterCurrencyAdjustmentBody
    ):
        result = admin_result(
            service.adjust_person_currency,
            body.session_id,
            person_id,
            body.change_knuts,
        )
        await runtime.broadcast_character_sheets(body.session_id)
        await runtime.notify_admins()
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
        "/api/admin/board/secrets/{region_id}/visibility",
        dependencies=[Depends(admin_guard)],
    )
    async def reveal_board_secret(
        region_id: str,
        body: SecretRevealBody,
    ):
        result = admin_result(
            service.set_secret_revealed,
            body.session_id,
            body.map_id,
            region_id,
            body.revealed,
        )
        await runtime.broadcast_board(body.session_id)
        await runtime.notify_admins()
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
            zoom_profile=body.zoom_profile,
            preview_opacity=body.preview_opacity,
            preview_color=body.preview_color,
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
            body.color,
        )
        for session in service.sessions_view():
            await runtime.broadcast_board(session["id"])
        return result

    @admin_app.post(
        "/api/admin/board/factions",
        dependencies=[Depends(admin_guard)],
    )
    async def create_board_faction(body: BoardFactionBody):
        result = admin_result(
            service.create_board_faction,
            body.session_id,
            body.person_id,
            body.name,
            body.color,
        )
        for session in service.sessions_view():
            await runtime.broadcast_board(session["id"])
        return result

    @admin_app.put(
        "/api/admin/board/factions/{organization_id}",
        dependencies=[Depends(admin_guard)],
    )
    async def update_board_faction_color(
        organization_id: str,
        body: BoardFactionColorBody,
    ):
        result = admin_result(
            service.update_board_faction_color,
            body.session_id,
            organization_id,
            body.color,
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
        "/api/admin/board/maps/{map_id}/camera",
        dependencies=[Depends(admin_guard)],
    )
    async def update_board_camera(map_id: str, body: BoardCameraBody):
        camera = admin_result(
            service.set_board_camera,
            body.session_id,
            map_id,
            {
                "zoom": body.zoom,
                "center_x": body.center_x,
                "center_y": body.center_y,
            },
        )
        if body.force_players:
            await runtime.focus_players(body.session_id, map_id, camera)
        return {"camera": camera}

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
        for connection in runtime.connections.values():
            if (
                connection.session_id == body.session_id
                and connection.contact_id == body.contact_id
            ):
                connection.controlled_ids = set(
                    service.controlled_character_ids(
                        connection.session_id, connection.contact_id,
                    )
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
        if runtime.invitation_batch_lock.locked():
            raise HTTPException(
                status_code=409,
                detail="An invitation batch is already being sent",
            )
        results = []

        async def current_session(session_id: str | None):
            try:
                return await asyncio.to_thread(
                    service.session_view, session_id
                )
            except (KeyError, ValueError):
                return None

        async with runtime.invitation_batch_lock:
            # Resolve an omitted board-session choice once.  Every recipient in
            # this batch must remain attached to that concrete session even if
            # the Headmaster selects a different live board while Gmail works.
            initial_session = await current_session(body.session_id)
            if not initial_session:
                raise HTTPException(
                    status_code=400, detail="There is no active session"
                )
            session_id = str(initial_session["id"])
            async with runtime.session_lifecycle_locks[session_id]:
                initial_session = await current_session(session_id)
            if not initial_session:
                raise HTTPException(
                    status_code=400, detail="There is no active session"
                )
            for contact_id in body.contact_ids:
                # Release the lifecycle lock between recipients.  End/delete/
                # expiration may wait for one confirmed Gmail call, never an
                # entire serial batch; a later recipient is revalidated before
                # any message is sent.
                async with runtime.session_lifecycle_locks[session_id]:
                    session = await current_session(session_id)
                    if not session:
                        results.append({
                            "contact_id": contact_id,
                            "success": False,
                            "error": (
                                "The session ended before this invitation "
                                "could be sent"
                            ),
                        })
                        continue
                    players = {
                        item["contact_id"]: item
                        for item in session["roster"]
                    }
                    if contact_id not in players:
                        results.append({
                            "contact_id": contact_id,
                            "success": False,
                            "error": "Not in session roster",
                        })
                        continue
                    delivered_message_id = ""
                    try:
                        _raw, link, player = await asyncio.to_thread(
                            service.prepare_invite, contact_id, session["id"]
                        )
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
                        # Gmail/curl is blocking I/O and may legitimately take tens
                        # of seconds.  Running it in a worker keeps health, state,
                        # admission, and player websocket traffic responsive.
                        sender = runtime.gmail()
                        message_id = await asyncio.to_thread(
                            sender.send, player["email"], subject, email_body
                        )
                        delivered_message_id = str(message_id or "")
                        await asyncio.to_thread(
                            service.record_invite_result,
                            contact_id,
                            True,
                            session["id"],
                        )
                        results.append({"contact_id": contact_id, "success": True, "message_id": message_id})
                    except Exception as error:
                        if delivered_message_id:
                            results.append({
                                "contact_id": contact_id,
                                "success": True,
                                "message_id": delivered_message_id,
                                "warning": (
                                    "Gmail confirmed delivery, but the local "
                                    f"status could not be recorded: {error}"
                                ),
                            })
                            continue
                        try:
                            await asyncio.to_thread(
                                service.record_invite_result,
                                contact_id,
                                False,
                                session["id"],
                            )
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
        async with runtime.invitation_batch_lock:
            await asyncio.to_thread(admin_result, service.revoke, contact_id)
            await runtime.disconnect(
                contact_id,
                "access_revoked",
                "The headmaster revoked this invitation.",
            )
        await runtime.notify_admins()
        return {"revoked": True}

    @admin_app.post(
        "/api/admin/sessions/{session_id}/players/{contact_id}/revoke",
        dependencies=[Depends(admin_guard)],
    )
    async def revoke_session_player(session_id: str, contact_id: str):
        async with runtime.session_lifecycle_locks[session_id]:
            await asyncio.to_thread(
                admin_result, service.revoke, contact_id, session_id
            )
            await runtime.disconnect(
                contact_id,
                "access_revoked",
                "The headmaster revoked this invitation.",
                session_id,
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
            session_id = service.board_session_id()
            if not session_id:
                raise HTTPException(
                    status_code=409,
                    detail="There is no active board session",
                )
            async with runtime.session_lifecycle_locks[session_id]:
                await runtime.disconnect_session(
                    session_id, "session_expired", "The game session has ended."
                )
                await asyncio.to_thread(
                    admin_result, service.end_session, "ended", session_id
                )
        else:
            raise HTTPException(status_code=404, detail="Unknown session action")
        await runtime.notify_admins()
        return {"action": action}

    @admin_app.post("/api/admin/announcements", dependencies=[Depends(admin_guard)])
    async def announcement(body: AnnouncementBody):
        session_id = body.session_id or service.board_session_id()
        if not session_id:
            raise HTTPException(status_code=409, detail="There is no active board session")
        try:
            announcement_id = await runtime.announce(
                body.message.strip(),
                session_id,
                require_board_session=True,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        await runtime.notify_admins()
        return {"id": announcement_id}

    @admin_app.post("/api/admin/chat", dependencies=[Depends(admin_guard)])
    async def headmaster_chat(body: ChatBody):
        session_id = body.session_id or service.board_session_id()
        if not session_id:
            raise HTTPException(status_code=409, detail="There is no active board session")
        try:
            return await runtime.chat(
                "headmaster",
                "Headmaster",
                "headmaster",
                body.message,
                session_id,
                require_board_session=True,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @admin_app.post("/api/admin/teaching", dependencies=[Depends(admin_guard)])
    async def teach_character(body: TeachingBody):
        result = admin_result(
            service.teach_character,
            body.session_id,
            body.pupil_person_id,
            body.knowledge_kind,
            body.knowledge_record_id,
            knowledge_collection=body.knowledge_collection,
            teacher_person_id=body.teacher_person_id,
        )
        await runtime.broadcast_character_sheets(body.session_id)
        await runtime.notify_admins()
        return result

    @admin_app.post(
        "/api/admin/teaching/options", dependencies=[Depends(admin_guard)]
    )
    async def teaching_options(body: TeachingOptionsBody):
        return admin_result(
            service.teaching_options,
            body.session_id,
            body.teacher_person_id,
        )

    @admin_app.post(
        "/api/admin/regions/search-options", dependencies=[Depends(admin_guard)]
    )
    async def admin_region_search_options(body: AdminRegionSearchOptionsBody):
        return admin_result(
            service.admin_region_search_options,
            body.session_id,
            body.person_id,
        )

    @admin_app.post(
        "/api/admin/regions/search", dependencies=[Depends(admin_guard)]
    )
    async def admin_region_search(body: AdminRegionSearchBody):
        result = admin_result(
            service.admin_search_region,
            body.session_id,
            body.person_id,
            body.map_id,
            body.region_id,
            body.mode_id,
            body.extraction_method_id,
        )
        await runtime.chat(
            "headmaster", "Headmaster", "headmaster",
            result["text"], body.session_id, result,
        )
        await runtime.broadcast_board(body.session_id)
        await runtime.broadcast_character_sheets(body.session_id)
        await runtime.notify_admins()
        return result

    @admin_app.post(
        "/api/admin/requests/{request_id}/resolve",
        dependencies=[Depends(admin_guard)],
    )
    async def resolve_campaign_request(request_id: str, body: RequestResolutionBody):
        result = admin_result(
            service.resolve_campaign_request,
            body.campaign_id,
            request_id,
            body.decision,
            pupil_person_id=body.pupil_person_id,
            knowledge_kind=body.knowledge_kind,
            knowledge_record_id=body.knowledge_record_id,
            knowledge_collection=body.knowledge_collection,
            actor_person_id=body.actor_person_id,
            interaction_action=body.interaction_action,
            creature_name=body.creature_name,
        )
        session_id = next((
            item.get("id") for item in service.sessions_view()
            if item.get("campaign_id") == body.campaign_id
        ), "")
        if session_id and body.decision == "approved":
            roll = result.get("roll")
            if isinstance(roll, dict):
                await runtime.chat(
                    "headmaster", "Headmaster", "headmaster",
                    str(roll.get("text") or "A Flying check was made."),
                    str(session_id), roll,
                )
            await runtime.broadcast_character_sheets(str(session_id))
            await runtime.broadcast_board(str(session_id))
        await runtime.notify_admins()
        return result

    @admin_app.websocket("/ws/admin")
    async def admin_websocket(websocket: WebSocket, key: str = Query(default="")):
        if key != settings["admin_key"]:
            await websocket.close(code=4403)
            return
        await websocket.accept()
        runtime.admin_sockets.add(websocket)
        try:
            state = await asyncio.to_thread(runtime.state)
            await websocket.send_json({"v": 1, "type": "state", "data": state})
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
        quality: str = Query(default="full", pattern="^(preview|full)$"),
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
                connection.contact_id,
            )
            if quality == "preview":
                path, media_type = await asyncio.to_thread(
                    _preview_image, Path(path), asset_id
                )
            stat = Path(path).stat()
            etag = hashlib.sha256(
                f"{asset_id}:{quality}:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8")
            ).hexdigest()
            return FileResponse(
                path,
                media_type=media_type,
                headers={
                    # Network caching must not outlive the connection-scoped
                    # credential. The client keeps an explicitly player-
                    # scoped IndexedDB copy instead, after authorization.
                    "Cache-Control": "private, no-store",
                    "ETag": f'"{etag}"',
                    "Vary": "Authorization, Origin",
                },
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
        connection.controlled_ids = set(
            service.controlled_character_ids(
                identity["session_id"], identity["contact_id"],
            )
        )
        connection_key = f"{identity['session_id']}:{identity['contact_id']}"
        runtime.connections[connection_key] = connection
        runtime.asset_credentials[asset_credential_hash] = connection_key
        session = service.session_view(identity["session_id"])
        await websocket.send_json({
            "v": 1, "type": "connection_accepted", "player": identity["name"],
            "player_id": identity["contact_id"], "session": identity["session_title"],
            "character_id": identity.get("character_id"),
            "campaign_id": str((session or {}).get("campaign_id", "") or ""),
            # Kept as a protocol key for older published clients. The
            # authoritative value follows in the single sheet snapshot.
            "character_attributes": None,
            "asset_credential": asset_credential,
        })

        async def bootstrap_connection() -> None:
            # The receive loop starts immediately, so a disconnect revokes the
            # credential even while a large private sheet is being prepared.
            # Keep the established protocol order for older web clients.  The
            # sheet path is now cached and no longer expands every possible
            # teaching target, so it completes quickly without blocking on
            # unrelated characters.
            await runtime.send_character_sheet(connection, force=True)
            await websocket.send_json({
                "v": 1,
                "type": "chat_history",
                "messages": [
                    service.chat_message_for_viewer(
                        item, identity["session_id"], identity["contact_id"]
                    )
                    for item in list((session or {}).get("chat", []))[-100:]
                ],
            })
            await runtime.chat(
                "system",
                "Game Board",
                "system",
                f"{identity['name']} is here!",
                identity["session_id"],
                notify_admins=False,
            )
            await runtime.send_board_snapshot(connection)
            await runtime.send_battle_snapshot(connection)
            await runtime.notify_admins()

        bootstrap_task = asyncio.create_task(bootstrap_connection())

        async def heartbeat_loop():
            # Keep the deterministic bootstrap message order while the
            # receive loop remains active for immediate disconnect handling.
            await bootstrap_task
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
                elif message.get("type") in {
                    "character_roll_request", "recipe_attempt_request"
                }:
                    client_request_id = str(
                        message.get("request_id", "") or ""
                    )[:100]
                    now = time.monotonic()
                    while connection.roll_events and connection.roll_events[0] <= now - 10:
                        connection.roll_events.popleft()
                    if len(connection.roll_events) >= 10:
                        await websocket.send_json({
                            "v": 1,
                            "type": "server_error",
                            "message": "Please wait a moment before rolling again.",
                        })
                        continue
                    connection.roll_events.append(now)
                    try:
                        if message.get("type") == "recipe_attempt_request":
                            result = await asyncio.to_thread(
                                service.attempt_character_recipe,
                                connection.session_id, connection.contact_id,
                                str(message.get("target_id", ""))[:120],
                            )
                        else:
                            result = await asyncio.to_thread(
                                service.roll_character_action,
                                connection.session_id, connection.contact_id,
                                str(message.get("roll_type", ""))[:30],
                                str(message.get("target_id", ""))[:120],
                            )
                        if client_request_id:
                            result["client_request_id"] = client_request_id
                        # The server still generates and verifies the roll.
                        # Give the roller that authoritative result before the
                        # durable chat write and room/admin fan-out complete.
                        await websocket.send_json({
                            "v": 1,
                            "type": "roll_result_preview",
                            "request_id": client_request_id,
                            "result": result,
                            "sender_id": connection.contact_id,
                            "sender_name": connection.name,
                            "sent_at": iso_utc(utc_now()),
                        })
                        await runtime.chat(
                            connection.contact_id,
                            connection.name,
                            "player",
                            result["text"],
                            connection.session_id,
                            result,
                        )
                        if str(message.get("roll_type", "")).casefold() in {
                            "spell", "proficiency", "item", "item_action", "potion"
                        } or message.get("type") == "recipe_attempt_request":
                            await runtime.broadcast_battles(connection.session_id)
                        if message.get("type") == "recipe_attempt_request":
                            await runtime.broadcast_character_sheets(
                                connection.session_id
                            )
                    except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as error:
                        await websocket.send_json({
                            "v": 1,
                            # Keep the long-standing error envelope so an
                            # already-published client still displays it.
                            "type": "server_error",
                            "request_id": client_request_id,
                            "message": str(error),
                        })
                elif message.get("type") == "teaching_options_request":
                    try:
                        if not connection.character_id:
                            raise PermissionError("A linked character is required to teach")
                        options = await asyncio.to_thread(
                            service.teaching_options,
                            connection.session_id,
                            str(connection.character_id),
                        )
                        await websocket.send_json({
                            "v": 1,
                            "type": "teaching_options",
                            "pupils": options.get("pupils", []),
                        })
                    except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as error:
                        await websocket.send_json({
                            "v": 1, "type": "server_error", "message": str(error),
                        })
                elif message.get("type") == "teaching_request":
                    try:
                        result = service.submit_teaching_request(
                            connection.session_id,
                            connection.contact_id,
                            str(message.get("pupil_person_id", ""))[:100],
                            str(message.get("knowledge_kind", ""))[:30],
                            str(message.get("knowledge_record_id", ""))[:120],
                            str(message.get("knowledge_collection", ""))[:80],
                        )
                        await websocket.send_json({
                            "v": 1,
                            "type": "request_submitted",
                            "request_id": result["record_id"],
                            "message": "Teaching request sent to the Headmaster.",
                        })
                        await runtime.notify_admins()
                    except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as error:
                        await websocket.send_json({
                            "v": 1, "type": "server_error", "message": str(error),
                        })
                elif message.get("type") == "equipment_change_request":
                    try:
                        result = service.update_character_equipment(
                            connection.session_id, connection.contact_id,
                            str(message.get("slot", ""))[:30],
                            str(message.get("item_id", ""))[:160],
                        )
                        if result.get("status") == "pending":
                            await websocket.send_json({
                                "v": 1, "type": "request_submitted",
                                "request_id": result["request"]["record_id"],
                                "message": "Equipment change sent to the Headmaster.",
                            })
                            await runtime.notify_admins()
                        else:
                            roll = result.get("roll")
                            if isinstance(roll, dict):
                                await runtime.chat(
                                    connection.contact_id,
                                    connection.name,
                                    "player",
                                    str(roll.get("text") or "A Flying check was made."),
                                    connection.session_id,
                                    roll,
                                )
                            await websocket.send_json({
                                "v": 1,
                                "type": "equipment_change_result",
                                "result": result,
                            })
                            await runtime.broadcast_board(connection.session_id)
                            await runtime.broadcast_character_sheets(connection.session_id)
                    except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as error:
                        await websocket.send_json({"v": 1, "type": "server_error", "message": str(error)})
                elif message.get("type") == "inventory_item_action":
                    try:
                        result = service.use_inventory_item(
                            connection.session_id, connection.contact_id,
                            str(message.get("item_id", ""))[:160],
                            str(message.get("action_id", ""))[:160],
                        )
                        await runtime.chat(
                            connection.contact_id, connection.name, "player",
                            str(result.get("text") or "An item was used."),
                            connection.session_id, result,
                        )
                        await runtime.broadcast_character_sheets(connection.session_id)
                    except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as error:
                        await websocket.send_json({"v": 1, "type": "server_error", "message": str(error)})
                elif message.get("type") == "catalog_tag_add":
                    try:
                        service.add_shared_catalog_tag(
                            connection.session_id, connection.contact_id,
                            str(message.get("collection", ""))[:80],
                            str(message.get("target_record_id", ""))[:160],
                            str(message.get("name", ""))[:100],
                        )
                        await runtime.broadcast_character_sheets(connection.session_id)
                    except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as error:
                        await websocket.send_json({"v": 1, "type": "server_error", "message": str(error)})
                elif message.get("type") == "region_interaction_request":
                    try:
                        snapshot = service.region_interaction_snapshot(
                            connection.session_id, connection.contact_id,
                            str(message.get("map_id", ""))[:120],
                            str(message.get("region_id", ""))[:120],
                        )
                        await websocket.send_json({
                            "v": 1, "type": "region_interaction_snapshot",
                            "interaction": snapshot,
                        })
                    except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as error:
                        await websocket.send_json({"v": 1, "type": "server_error", "message": str(error)})
                elif message.get("type") in {"secret_gate_request", "region_search_request"}:
                    now = time.monotonic()
                    while connection.roll_events and connection.roll_events[0] <= now - 10:
                        connection.roll_events.popleft()
                    if len(connection.roll_events) >= 10:
                        await websocket.send_json({
                            "v": 1, "type": "server_error",
                            "message": "Please wait a moment before searching again.",
                        })
                        continue
                    connection.roll_events.append(now)
                    try:
                        if message.get("type") == "secret_gate_request":
                            result = service.attempt_secret_gate(
                                connection.session_id, connection.contact_id,
                                str(message.get("map_id", ""))[:120],
                                str(message.get("region_id", ""))[:120],
                            )
                        else:
                            result = service.search_region(
                                connection.session_id, connection.contact_id,
                                str(message.get("map_id", ""))[:120],
                                str(message.get("region_id", ""))[:120],
                                str(message.get("mode_id", ""))[:120],
                                str(message.get("extraction_method_id", ""))[:120],
                            )
                        await runtime.chat(
                            connection.contact_id, connection.name, "player",
                            result["text"], connection.session_id, result,
                        )
                        await websocket.send_json({
                            "v": 1, "type": str(result.get("kind") or "region_search_result"),
                            "result": result,
                        })
                        await runtime.broadcast_board(connection.session_id)
                        await runtime.broadcast_character_sheets(connection.session_id)
                    except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as error:
                        await websocket.send_json({"v": 1, "type": "server_error", "message": str(error)})
                elif message.get("type") == "shop_purchase_request":
                    try:
                        result = service.purchase_shop_listing(
                            connection.session_id, connection.contact_id,
                            str(message.get("map_id", ""))[:120],
                            str(message.get("region_id", ""))[:120],
                            str(message.get("listing_id", ""))[:120],
                        )
                        await runtime.chat(
                            connection.contact_id, connection.name, "player",
                            result["text"], connection.session_id, result,
                        )
                        await websocket.send_json({
                            "v": 1, "type": "shop_purchase_result", "result": result,
                        })
                        await runtime.broadcast_character_sheets(connection.session_id)
                        snapshot = service.region_interaction_snapshot(
                            connection.session_id, connection.contact_id,
                            str(message.get("map_id", ""))[:120],
                            str(message.get("region_id", ""))[:120],
                        )
                        await websocket.send_json({
                            "v": 1, "type": "region_interaction_snapshot",
                            "interaction": snapshot,
                        })
                    except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as error:
                        await websocket.send_json({"v": 1, "type": "server_error", "message": str(error)})
                elif message.get("type") == "creature_interaction_request":
                    try:
                        result = service.submit_creature_interaction_request(
                            connection.session_id, connection.contact_id,
                            str(message.get("creature_id", ""))[:120],
                            str(message.get("action", ""))[:20],
                            str(message.get("creature_name", ""))[:200],
                        )
                        await websocket.send_json({
                            "v": 1, "type": "request_submitted",
                            "request_id": result["record_id"],
                            "message": "Creature interaction sent to the Headmaster.",
                        })
                        await runtime.notify_admins()
                    except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as error:
                        await websocket.send_json({"v": 1, "type": "server_error", "message": str(error)})
                elif message.get("type") == "creature_harvest_request":
                    try:
                        result = service.harvest_campaign_creature(
                            connection.session_id,
                            connection.contact_id,
                            str(message.get("creature_id", ""))[:100],
                            str(message.get("part_id", ""))[:160],
                        )
                        await runtime.chat(
                            connection.contact_id,
                            connection.name,
                            "player",
                            result["text"],
                            connection.session_id,
                            result,
                        )
                        await websocket.send_json({
                            "v": 1, "type": "creature_harvest_result",
                            "result": {
                                "part_id": result["part_id"],
                                "part_name": result["part_name"],
                                "quantity_awarded": result["quantity_awarded"],
                                "outcome": result["outcome"],
                                "corpse_removed": result["corpse_removed"],
                            },
                        })
                        await runtime.broadcast_board(connection.session_id)
                        await runtime.broadcast_character_sheets(connection.session_id)
                    except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as error:
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
                        if person_id not in connection.controlled_ids:
                            raise PermissionError("You do not control that token")
                        if message["type"] == "board_move_preview":
                            await runtime.preview_move(connection, person_id, map_id, x, y)
                        else:
                            # Everyone sees the final drop immediately. The
                            # locked atomic campaign save continues on a worker
                            # so a 5 MB JSON commit cannot freeze WebSockets.
                            await runtime.broadcast_move_preview(
                                connection.session_id, person_id, map_id, x, y,
                            )
                            placement = await asyncio.to_thread(
                                service.move_person,
                                connection.session_id, person_id, map_id, x, y,
                            )
                            await websocket.send_json({
                                "v": 1,
                                "type": "board_move_committed",
                                "request_id": str(message.get("request_id", ""))[:100],
                                "person_id": person_id,
                                "map_id": map_id,
                                "x": placement["x"],
                                "y": placement["y"],
                            })
                            runtime.queue_board_broadcast(connection.session_id)
                    except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as error:
                        if message.get("type") == "board_move_commit":
                            # A final position may already have been shown as
                            # an optimistic room preview. Restore every client
                            # from canonical state if persistence rejected it.
                            runtime.queue_board_broadcast(connection.session_id, delay=0.0)
                        await websocket.send_json({
                            "v": 1,
                            "type": "server_error",
                            "message": str(error),
                        })
                        await runtime.send_board_snapshot(connection)
                elif message.get("type") == "board_label_move":
                    try:
                        person_id = str(message.get("person_id", ""))
                        if person_id not in service.controlled_character_ids(
                            connection.session_id, connection.contact_id
                        ):
                            raise PermissionError("You do not control that character")
                        raw_offset = message.get("label_offset") or {}
                        label_offset = {
                            "x": float(raw_offset.get("x")),
                            "y": float(raw_offset.get("y")),
                        }
                        service.update_person_board(
                            connection.session_id,
                            person_id,
                            {"label_offset": label_offset},
                        )
                        await runtime.broadcast_board(connection.session_id)
                    except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as error:
                        await websocket.send_json({
                            "v": 1, "type": "server_error", "message": str(error),
                        })
                        await runtime.send_board_snapshot(connection)
                elif message.get("type") == "board_camera":
                    try:
                        map_id = str(message.get("map_id", ""))
                        if not map_id:
                            raise ValueError("A map is required")
                        service.set_board_camera(
                            connection.session_id,
                            map_id,
                            {
                                "zoom": float(message.get("zoom")),
                                "center_x": float(message.get("center_x")),
                                "center_y": float(message.get("center_y")),
                            },
                            contact_id=connection.contact_id,
                        )
                    except (KeyError, PermissionError, RuntimeError, TypeError, ValueError) as error:
                        await websocket.send_json({
                            "v": 1,
                            "type": "server_error",
                            "message": str(error),
                        })
                else:
                    await websocket.send_json({"v": 1, "type": "server_error", "message": "Unknown message type"})
        except Exception:
            pass
        finally:
            heartbeat_task.cancel()
            bootstrap_task.cancel()
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
