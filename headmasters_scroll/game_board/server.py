from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .gmail import GmailSender
from .service import GameBoardService, parse_utc, token_hash, utc_now
from .storage import GameBoardRepository


MAX_MESSAGE_BYTES = 16_384


class ContactBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)


class SettingsBody(BaseModel):
    wordpress_player_url: str = ""
    allowed_origin: str = ""
    public_api_base: str = ""
    gmail_credentials_path: str = "credentials.json"
    gmail_sender: str = ""
    timezone: str = "America/Chicago"


class SessionBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    game_day: str
    expiration_time: str = "23:59"
    contact_ids: list[str] = Field(min_length=1, max_length=9)


class AdmissionBody(BaseModel):
    invite_token: str = Field(min_length=20, max_length=256)


class SendBody(BaseModel):
    contact_ids: list[str] = Field(min_length=1, max_length=9)


class AnnouncementBody(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


@dataclass
class PlayerConnection:
    websocket: Any
    request_id: str
    contact_id: str
    name: str
    connected_at: float = field(default_factory=time.monotonic)
    latency_ms: float | None = None
    latency_total_ms: float = 0.0
    latency_samples: int = 0
    missed: int = 0
    heartbeats: dict[str, float] = field(default_factory=dict)
    last_activity: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    persisted: bool = False

    def public(self, service: GameBoardService) -> dict[str, Any]:
        return {
            "request_id": self.request_id, "contact_id": self.contact_id, "name": self.name,
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

    def state(self) -> dict[str, Any]:
        return {
            "contacts": self.service.list_contacts(),
            "settings": self.service.settings(),
            "session": self.service.session_view(),
            "connections": [item.public(self.service) for item in self.connections.values()],
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

    async def disconnect(self, contact_id: str, event_type: str, message: str) -> None:
        connection = self.connections.pop(contact_id, None)
        if not connection:
            return
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
            *(self.disconnect(contact_id, event_type, message) for contact_id in list(self.connections)),
            return_exceptions=True,
        )

    async def announce(self, text: str) -> str:
        self._announcement_id += 1
        announcement_id = f"announcement-{self._announcement_id}"
        message = {"v": 1, "type": "announcement", "id": announcement_id, "message": text}
        await asyncio.gather(
            *(connection.websocket.send_json(message) for connection in list(self.connections.values())),
            return_exceptions=True,
        )
        self.service.increment_announcements()
        return announcement_id


def create_apps(repository: GameBoardRepository | None = None):
    service = GameBoardService(repository)
    runtime = GameBoardRuntime(service)
    settings = service.settings(include_private=True)

    async def expiration_loop():
        while True:
            await asyncio.sleep(1)
            session = service.session_view()
            if session and parse_utc(session["expires_at"]) <= utc_now():
                await runtime.disconnect_all("session_expired", "The game session has expired.")
                try:
                    service.end_session("expired")
                except ValueError:
                    pass
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
            allow_methods=["GET", "POST"],
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

    @admin_app.delete("/api/admin/contacts/{contact_id}", dependencies=[Depends(admin_guard)])
    async def delete_contact(contact_id: str):
        admin_result(service.delete_contact, contact_id)
        await runtime.notify_admins()
        return {"deleted": True}

    @admin_app.post("/api/admin/sessions", dependencies=[Depends(admin_guard)])
    async def create_session(body: SessionBody):
        result = admin_result(service.create_session, body.title, body.game_day, body.contact_ids, body.expiration_time)
        await runtime.notify_admins()
        return result

    @admin_app.post("/api/admin/gmail/authorize", dependencies=[Depends(admin_guard)])
    def authorize_gmail():
        return runtime.gmail().authorize()

    @admin_app.post("/api/admin/invitations/send", dependencies=[Depends(admin_guard)])
    async def send_invitations(body: SendBody):
        session = service.session_view()
        if not session:
            raise HTTPException(status_code=400, detail="There is no active session")
        players = {item["contact_id"]: item for item in session["roster"]}
        results = []
        for contact_id in body.contact_ids:
            if contact_id not in players:
                results.append({"contact_id": contact_id, "success": False, "error": "Not in session roster"})
                continue
            if players[contact_id]["invite_status"] == "sent":
                results.append({"contact_id": contact_id, "success": True, "skipped": True})
                continue
            try:
                _raw, link, player = service.prepare_invite(contact_id)
                subject = f"Game Board invitation: {session['title']}"
                local_expiration = parse_utc(session["expires_at"]).astimezone(
                    ZoneInfo(service.settings(include_private=True)["timezone"])
                ).strftime("%B %d, %Y at %I:%M %p %Z")
                email_body = (
                    f"Hello {player['name']},\n\n"
                    f"Use this private link to request admission to {session['title']}:\n\n{link}\n\n"
                    f"The invitation expires {local_expiration}. The headmaster must approve every connection.\n"
                )
                message_id = runtime.gmail().send(player["email"], subject, email_body)
                service.record_invite_result(contact_id, True)
                results.append({"contact_id": contact_id, "success": True, "message_id": message_id})
            except Exception as error:
                try:
                    service.record_invite_result(contact_id, False)
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
            announcement_id = await runtime.announce(body.message.strip())
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        await runtime.notify_admins()
        return {"id": announcement_id}

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
        session = service.session_view()
        return {"service": "game-board", "available": bool(session), "paused": bool(session and session["status"] == "paused")}

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

    @player_app.websocket("/v1/session")
    async def player_websocket(websocket: WebSocket, ticket: str = Query(default="")):
        try:
            require_origin(websocket.headers.get("origin", ""))
            identity = service.consume_ticket(ticket)
        except Exception:
            await websocket.close(code=4403)
            return
        await websocket.accept()
        connection = PlayerConnection(
            websocket, identity["request_id"], identity["contact_id"], identity["name"]
        )
        runtime.connections[identity["contact_id"]] = connection
        await websocket.send_json({
            "v": 1, "type": "connection_accepted", "player": identity["name"],
            "session": identity["session_title"],
        })
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
                    service.record_acknowledgement(connection.contact_id)
                    await runtime.notify_admins()
                else:
                    await websocket.send_json({"v": 1, "type": "server_error", "message": "Unknown message type"})
        except Exception:
            pass
        finally:
            heartbeat_task.cancel()
            runtime.connections.pop(connection.contact_id, None)
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
