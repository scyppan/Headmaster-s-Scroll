from __future__ import annotations

import calendar
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

if TYPE_CHECKING:
    from .store import SharedJsonStore


GAME_WORLD_DATE = re.compile(
    r"^(?P<year>-?[1-9]\d*)-(?P<month>\d{2})-(?P<day>\d{2})$"
)
GAME_WORLD_DATETIME = re.compile(r"^-?[1-9]\d*-\d{2}-\d{2}T\d{2}:\d{2}$")
HISTORY_KEEP = "keep"
HISTORY_DISCARD = "discard"
HISTORY_POLICIES = {HISTORY_KEEP, HISTORY_DISCARD}

LEGACY_GENERATED_ZOOM_TIERS = {
    "0": {"token_size": 0, "nameplate_size": 11},
    "3": {"token_size": 0, "nameplate_size": 11},
    "6": {"token_size": 0, "nameplate_size": 10},
    "9": {"token_size": 0, "nameplate_size": 10},
    "12": {"token_size": 0, "nameplate_size": 9},
    "15": {"token_size": 0, "nameplate_size": 9},
    "18": {"token_size": 68, "nameplate_size": 9},
    "21": {"token_size": 64, "nameplate_size": 8},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_game_world_date(value: Any) -> str:
    raw = str(value or "").strip()
    match = GAME_WORLD_DATE.fullmatch(raw)
    if match is None:
        raise ValueError("Game World Start Date must use YYYY-MM-DD")
    try:
        year, month, day = (
            int(match.group(field)) for field in ("year", "month", "day")
        )
        if year == 0 or not 1 <= month <= 12:
            raise ValueError
        if not 1 <= day <= calendar.monthrange(year, month)[1]:
            raise ValueError
    except ValueError as error:
        raise ValueError("Game World Start Date is not a valid historical date") from error
    shown_year = f"-{abs(year):04d}" if year < 0 else f"{year:04d}"
    return f"{shown_year}-{month:02d}-{day:02d}"


def format_game_world_date(value: Any) -> str:
    normalized = normalize_game_world_date(value)
    match = GAME_WORLD_DATE.fullmatch(normalized)
    if match is None:
        return normalized
    year, month, day = (
        int(match.group(field)) for field in ("year", "month", "day")
    )
    shown_year = f"{abs(year)} BCE" if year < 0 else str(year)
    return f"{day:02d} {calendar.month_abbr[month]} {shown_year}"


def normalize_board_camera(value: Any) -> dict[str, float]:
    raw = value if isinstance(value, dict) else {}
    zoom = float(raw.get("zoom", 1.0))
    center_x = float(raw.get("center_x", 0.5))
    center_y = float(raw.get("center_y", 0.5))
    if not 1.0 <= zoom <= 32.0:
        raise ValueError("Campaign map camera zoom must be between 1 and 32")
    if not 0.0 <= center_x <= 1.0 or not 0.0 <= center_y <= 1.0:
        raise ValueError("Campaign map camera center must be on the map")
    return {
        "zoom": zoom,
        "center_x": center_x,
        "center_y": center_y,
    }


def normalize_zoom_profile(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    default_zoom = float(raw.get("default_zoom", 1.0))
    if not 1.0 <= default_zoom <= 32.0:
        raise ValueError("Default map zoom must be between 1 and 32")
    default_center_x = float(raw.get("default_center_x", 0.5))
    default_center_y = float(raw.get("default_center_y", 0.5))
    if not 0.0 <= default_center_x <= 1.0 or not 0.0 <= default_center_y <= 1.0:
        raise ValueError("Default map position must be on the map")
    default_nameplate_size = int(raw.get("default_nameplate_size", 10))
    if not 6 <= default_nameplate_size <= 32:
        raise ValueError("Default map nameplate size must be between 6 and 32 pixels")
    raw_tiers = raw.get("tiers", {}) or {}
    if not isinstance(raw_tiers, dict):
        raise ValueError("Map zoom tiers must be keyed by click level")
    tiers: dict[str, dict[str, int]] = {}
    for raw_clicks, item in raw_tiers.items():
        try:
            clicks = int(raw_clicks)
        except (TypeError, ValueError) as error:
            raise ValueError("Map zoom click levels must be whole numbers") from error
        if not 0 <= clicks <= 250:
            raise ValueError("Map zoom click levels must be between 0 and 250")
        if not isinstance(item, dict):
            raise ValueError("Every map zoom-tier override must be an object")
        token_size = int(item.get("token_size", 0))
        nameplate_size = int(item.get("nameplate_size", 10))
        if not 0 <= token_size <= 240:
            raise ValueError("Zoom-tier token size must be between 0 and 240 pixels")
        if not 6 <= nameplate_size <= 32:
            raise ValueError("Zoom-tier nameplate size must be between 6 and 32 pixels")
        tiers[str(clicks)] = {
            "token_size": token_size,
            "nameplate_size": nameplate_size,
        }
    # Older builds generated this exact preset for every map. These were not
    # user-created overrides, so discard only that known automatic set.
    if tiers == LEGACY_GENERATED_ZOOM_TIERS:
        tiers = {}
    return {
        "default_zoom": default_zoom,
        "default_center_x": default_center_x,
        "default_center_y": default_center_y,
        "default_nameplate_size": default_nameplate_size,
        "tiers": dict(sorted(tiers.items(), key=lambda item: int(item[0]))),
    }


def normalize_campaign_game_state(
    value: Any,
    game_world_start_date: str,
) -> dict[str, Any]:
    from .board import (
        DEFAULT_MAP_TOKEN_SCALE,
        MIN_MAP_TOKEN_SCALE,
        normalize_group,
        normalize_obscuration,
        normalize_person_board,
        normalize_map_point,
    )

    raw = deepcopy(value) if isinstance(value, dict) else {}
    current = str(
        raw.get("current_game_datetime")
        or f"{game_world_start_date}T08:00"
    ).strip()
    if not GAME_WORLD_DATETIME.fullmatch(current):
        raise ValueError("Campaign Game World Date and time must use YYYY-MM-DDTHH:MM")

    loaded_map_ids: list[str] = []
    for map_id in raw.get("loaded_map_ids", []) or []:
        map_id = str(map_id or "").strip()
        if map_id and map_id not in loaded_map_ids:
            loaded_map_ids.append(map_id)
    active_map_id = str(raw.get("active_map_id", "") or "").strip()
    if active_map_id and active_map_id not in loaded_map_ids:
        loaded_map_ids.append(active_map_id)
    raw_player_active_maps = raw.get("player_active_map_ids", {}) or {}
    if not isinstance(raw_player_active_maps, dict):
        raise ValueError("Campaign player active maps must be keyed by player ID")
    player_active_map_ids = {
        str(player_id).strip(): str(map_id).strip()
        for player_id, map_id in raw_player_active_maps.items()
        if str(player_id).strip() and str(map_id).strip()
    }

    map_states: dict[str, dict[str, Any]] = {}
    maps = raw.get("maps", {}) or {}
    if not isinstance(maps, dict):
        raise ValueError("Campaign map state must be an object keyed by map ID")
    for raw_map_id, raw_state in maps.items():
        map_id = str(raw_map_id or "").strip()
        if not map_id or not isinstance(raw_state, dict):
            raise ValueError("Every campaign map state requires a stable map ID")
        token_scale = float(raw_state.get("token_scale", DEFAULT_MAP_TOKEN_SCALE))
        if not MIN_MAP_TOKEN_SCALE <= token_scale <= 0.03:
            raise ValueError("Campaign token size is outside the supported range")
        obscurations = [
            normalize_obscuration(item)
            for item in (raw_state.get("obscurations", []) or [])
        ]
        if len({item["record_id"] for item in obscurations}) != len(obscurations):
            raise ValueError("Campaign obscuration IDs must be unique within a map")
        opacity = float(raw_state.get("obscuration_preview_opacity", 0.35))
        if not 0.05 <= opacity <= 1.0:
            raise ValueError("Campaign obscuration preview opacity is invalid")
        color = str(raw_state.get("obscuration_preview_color", "#ff0000") or "#ff0000").lower()
        if not re.fullmatch(r"#[0-9a-f]{6}", color):
            raise ValueError("Campaign obscuration preview color is invalid")
        raw_player_cameras = raw_state.get("player_cameras", {}) or {}
        if not isinstance(raw_player_cameras, dict):
            raise ValueError("Campaign player cameras must be keyed by player ID")
        player_cameras: dict[str, dict[str, float]] = {}
        for raw_player_id, raw_camera in raw_player_cameras.items():
            player_id = str(raw_player_id or "").strip()
            if not player_id:
                raise ValueError("Every saved player camera requires a player ID")
            player_cameras[player_id] = normalize_board_camera(raw_camera)
        map_states[map_id] = {
            "players_published": bool(raw_state.get("players_published", False)),
            "obscurations": obscurations,
            "obscuration_preview_opacity": opacity,
            "obscuration_preview_color": color,
            "token_scale": token_scale,
            "start_point": normalize_map_point(
                raw_state.get("start_point"), "Campaign map start point", optional=True
            ),
            "headmaster_camera": normalize_board_camera(
                raw_state.get("headmaster_camera")
            ),
            "player_cameras": player_cameras,
            "zoom_profile": normalize_zoom_profile(raw_state.get("zoom_profile")),
        }

    people: dict[str, dict[str, Any]] = {}
    raw_people = raw.get("people", {}) or {}
    if not isinstance(raw_people, dict):
        raise ValueError("Campaign person state must be an object keyed by person ID")
    for raw_person_id, raw_state in raw_people.items():
        person_id = str(raw_person_id or "").strip()
        if not person_id or not isinstance(raw_state, dict):
            raise ValueError("Every campaign person state requires a stable person ID")
        board = normalize_person_board({**raw_state, "portrait": None})
        wounds = []
        for wound in raw_state.get("wounds", []) or []:
            if not isinstance(wound, dict):
                raise ValueError("Campaign wounds must be objects")
            severity = str(wound.get("severity", "") or "").strip().lower()
            if severity not in {"light", "medium", "heavy"}:
                raise ValueError("Campaign wounds must be light, medium, or heavy")
            wounds.append({
                "record_id": str(wound.get("record_id", "") or uuid4()),
                "severity": severity,
                "note": str(wound.get("note", "") or "").strip()[:1000],
                "created_at": str(wound.get("created_at", "") or utc_now()),
            })
        notes = []
        for note in raw_state.get("character_notes", []) or []:
            if not isinstance(note, dict):
                raise ValueError("Campaign character notes must be objects")
            text = str(note.get("text", "") or "").strip()
            if text:
                notes.append({
                    "record_id": str(note.get("record_id", "") or uuid4()),
                    "text": text[:4000],
                    "created_at": str(note.get("created_at", "") or utc_now()),
                })
        battle = raw_state.get("battle")
        if battle is not None and not isinstance(battle, dict):
            raise ValueError("Campaign battle state must be an object")
        normalized_battle = None
        if isinstance(battle, dict) and bool(battle.get("active", True)):
            normalized_battle = {
                "active": True,
                "name": str(battle.get("name", "Battle") or "Battle").strip()[:200],
                "entered_at": str(battle.get("entered_at", "") or utc_now()),
            }
        people[person_id] = {
            "placement": deepcopy(board["placement"]),
            "visibility": board["visibility"],
            "display_mode": board["display_mode"],
            "name_revealed": board["name_revealed"],
            "faction_revealed": board["faction_revealed"],
            "faction_organization_id": board["faction_organization_id"],
            "label_offset": deepcopy(board["label_offset"]),
            "wounds": wounds,
            "battle": normalized_battle,
            "character_notes": notes,
        }

    groups = [normalize_group(item) for item in (raw.get("groups", []) or [])]
    if len({item["record_id"] for item in groups}) != len(groups):
        raise ValueError("Campaign board group IDs must be unique")
    return {
        "initialized": bool(raw.get("initialized", False)),
        "current_game_datetime": current,
        "loaded_map_ids": loaded_map_ids,
        "active_map_id": active_map_id,
        "player_active_map_ids": player_active_map_ids,
        "maps": map_states,
        "people": people,
        "groups": groups,
    }


def normalize_campaign(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Every campaign must be an object")
    record_id = str(value.get("record_id", "") or "").strip()
    name = str(value.get("name", "") or "").strip()
    if not record_id:
        raise ValueError("Every campaign requires a stable record ID")
    if not name:
        raise ValueError("Every campaign requires a name")
    result = deepcopy(value)
    result.update({
        "record_id": record_id,
        "name": name,
        "game_world_start_date": normalize_game_world_date(
            value.get("game_world_start_date")
        ),
        "created_at": str(value.get("created_at", "") or "").strip(),
        "last_updated": str(value.get("last_updated", "") or "").strip(),
        "history_policy": str(value.get("history_policy", HISTORY_KEEP) or HISTORY_KEEP)
        .strip()
        .casefold(),
    })
    if result["history_policy"] not in HISTORY_POLICIES:
        raise ValueError("Campaign history policy must keep or discard later world history")
    raw_events = value.get("events", []) or []
    if not isinstance(raw_events, list):
        raise ValueError("Campaign events must be a list")
    events: list[dict[str, Any]] = []
    event_ids: set[str] = set()
    for raw_event in raw_events:
        if not isinstance(raw_event, dict):
            raise ValueError("Every campaign event must be an object")
        event = deepcopy(raw_event)
        record_id = str(event.get("record_id", "") or "").strip()
        event_type = str(event.get("event_type", "") or "").strip()
        event_date = str(event.get("date", "") or "").strip()
        if not record_id or record_id in event_ids:
            raise ValueError("Campaign event IDs must be present and unique")
        if not event_type:
            raise ValueError("Every campaign event requires a type")
        # Campaign events use the same historical date representation as the
        # campaign clock. A time is optional but, when supplied, must be valid.
        normalize_game_world_date(event_date)
        event_time = str(event.get("time", "") or "").strip()
        if event_time and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", event_time):
            raise ValueError("Campaign event time must use a 24-hour HH:MM value")
        event.update({
            "record_id": record_id,
            "event_type": event_type,
            "date": event_date,
            "time": event_time,
        })
        event_ids.add(record_id)
        events.append(event)
    result["events"] = events
    result["game_state"] = normalize_campaign_game_state(
        value.get("game_state"), result["game_world_start_date"]
    )
    return result


def validate_campaigns(document: dict[str, Any]) -> None:
    campaigns = document.get("campaigns")
    if not isinstance(campaigns, list):
        raise ValueError("campaign.json requires a campaigns list")
    normalized = [normalize_campaign(item) for item in campaigns]
    ids = [item["record_id"] for item in normalized]
    if len(ids) != len(set(ids)):
        raise ValueError("Campaign IDs must be unique")


class CampaignRepository:
    def __init__(self, store: SharedJsonStore | None = None):
        if store is None:
            from .store import SharedJsonStore

            store = SharedJsonStore()
        self.store = store

    def list(self) -> list[dict[str, Any]]:
        session = self.store.load("campaign.json")
        return sorted(
            (normalize_campaign(item) for item in session.data["campaigns"]),
            key=lambda item: (item["name"].casefold(), item["record_id"]),
        )

    def get(self, campaign_id: str) -> dict[str, Any]:
        campaign = next(
            (item for item in self.list() if item["record_id"] == campaign_id),
            None,
        )
        if campaign is None:
            raise KeyError("Unknown campaign")
        return campaign

    @staticmethod
    def _person_state(
        board: dict[str, Any],
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from .board import normalize_person_board

        normalized = normalize_person_board(board)
        prior = existing if isinstance(existing, dict) else {}
        return {
            "placement": deepcopy(normalized["placement"]),
            "visibility": normalized["visibility"],
            "display_mode": normalized["display_mode"],
            "name_revealed": normalized["name_revealed"],
            "faction_revealed": normalized["faction_revealed"],
            "faction_organization_id": normalized["faction_organization_id"],
            "label_offset": deepcopy(normalized["label_offset"]),
            "wounds": deepcopy(prior.get("wounds", []) or []),
            "battle": deepcopy(prior.get("battle")),
            "character_notes": deepcopy(prior.get("character_notes", []) or []),
        }

    def ensure_game_state(
        self,
        campaign_id: str,
        world_document: dict[str, Any],
        current_game_datetime: str | None = None,
    ) -> dict[str, Any]:
        from .board import DEFAULT_MAP_TOKEN_SCALE, WorldBoardRepository, normalize_person_board

        session = self.store.load("campaign.json")
        campaign = next(
            (item for item in session.data["campaigns"] if item.get("record_id") == campaign_id),
            None,
        )
        if campaign is None:
            raise KeyError("Unknown campaign")
        normalized = normalize_campaign(campaign)
        if normalized["game_state"]["initialized"]:
            return normalized

        maps = WorldBoardRepository._location_maps(world_document)
        assigned_ids = {item["record_id"] for item in maps}
        map_states = {
            item["record_id"]: {
                "players_published": bool(item.get("players_published", False)),
                "obscurations": deepcopy(item.get("obscurations", []) or []),
                "obscuration_preview_opacity": float(item.get("obscuration_preview_opacity", 0.35)),
                "obscuration_preview_color": str(item.get("obscuration_preview_color", "#ff0000") or "#ff0000"),
                "token_scale": DEFAULT_MAP_TOKEN_SCALE,
                "start_point": deepcopy(item.get("start_point")),
                "headmaster_camera": normalize_board_camera(None),
                "player_cameras": {},
                "zoom_profile": normalize_zoom_profile(None),
            }
            for item in maps
        }
        people = {}
        occupied_map_ids: list[str] = []
        for person in world_document.get("people", []):
            if not isinstance(person, dict) or not person.get("record_id"):
                continue
            board = normalize_person_board(person.get("board"))
            people[str(person["record_id"])] = self._person_state(board)
            placement = board.get("placement")
            if placement and placement["map_id"] in assigned_ids:
                occupied_map_ids.append(placement["map_id"])
        loaded = [item["record_id"] for item in maps if item.get("players_published")]
        for map_id in occupied_map_ids:
            if map_id not in loaded:
                loaded.append(map_id)
        state = {
            "initialized": True,
            "current_game_datetime": (
                current_game_datetime
                or normalized["game_state"]["current_game_datetime"]
            ),
            "loaded_map_ids": loaded,
            "active_map_id": loaded[0] if loaded else "",
            "player_active_map_ids": {},
            "maps": map_states,
            "people": people,
            "groups": deepcopy(world_document.get("board_groups", []) or []),
        }
        campaign["game_state"] = normalize_campaign_game_state(
            state, normalized["game_world_start_date"]
        )
        campaign["last_updated"] = utc_now()
        outcome = self.store.save(session, "game-board")
        if not outcome.saved:
            raise RuntimeError("The campaign changed elsewhere; reload before saving")
        return normalize_campaign(campaign)

    def update_game_state(
        self,
        campaign_id: str,
        updater: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        session = self.store.load("campaign.json")
        campaign = next(
            (item for item in session.data["campaigns"] if item.get("record_id") == campaign_id),
            None,
        )
        if campaign is None:
            raise KeyError("Unknown campaign")
        normalized = normalize_campaign(campaign)
        state = deepcopy(normalized["game_state"])
        updater(state)
        campaign["game_state"] = normalize_campaign_game_state(
            state, normalized["game_world_start_date"]
        )
        campaign["last_updated"] = utc_now()
        outcome = self.store.save(session, "game-board")
        if not outcome.saved:
            raise RuntimeError("The campaign changed elsewhere; reload before saving")
        return normalize_campaign(campaign)

    def add_event(
        self,
        campaign_id: str,
        event_type: str,
        event_date: str,
        *,
        event_time: str = "",
        details: dict[str, Any] | None = None,
        app_id: str = "game-board",
    ) -> dict[str, Any]:
        """Append one campaign-only dated event without changing world.json."""

        session = self.store.load("campaign.json")
        campaign = next(
            (
                item for item in session.data["campaigns"]
                if item.get("record_id") == campaign_id
            ),
            None,
        )
        if campaign is None:
            raise KeyError("Unknown campaign")
        event = deepcopy(details) if isinstance(details, dict) else {}
        event.update({
            "record_id": str(uuid4()),
            "event_type": str(event_type or "").strip(),
            "date": normalize_game_world_date(event_date),
            "time": str(event_time or "").strip(),
        })
        campaign.setdefault("events", []).append(event)
        campaign["last_updated"] = utc_now()
        normalized = normalize_campaign(campaign)
        campaign.clear()
        campaign.update(normalized)
        outcome = self.store.save(session, app_id)
        if not outcome.saved:
            raise RuntimeError("The campaign changed elsewhere; reload before saving")
        return deepcopy(event)

    def save_campaign(
        self,
        name: str,
        game_world_start_date: str,
        campaign_id: str | None = None,
        history_policy: str | None = None,
    ) -> dict[str, Any]:
        session = self.store.load("campaign.json")
        now = utc_now()
        if campaign_id:
            campaign = next(
                (
                    item
                    for item in session.data["campaigns"]
                    if item.get("record_id") == campaign_id
                ),
                None,
            )
            if campaign is None:
                raise KeyError("Unknown campaign")
        else:
            campaign = {
                "record_id": str(uuid4()),
                "created_at": now,
            }
            session.data["campaigns"].append(campaign)
        campaign.update({
            "name": str(name or "").strip(),
            "game_world_start_date": game_world_start_date,
            "history_policy": str(
                history_policy
                if history_policy is not None
                else campaign.get("history_policy", HISTORY_KEEP)
            ).strip().casefold(),
            "events": deepcopy(campaign.get("events", []) or []),
            "last_updated": now,
        })
        normalized = normalize_campaign(campaign)
        campaign.clear()
        campaign.update(normalized)
        outcome = self.store.save(session, "campaigner")
        if not outcome.saved:
            raise RuntimeError("The campaign changed elsewhere; reload before saving")
        return deepcopy(campaign)

    def delete(self, campaign_id: str) -> None:
        session = self.store.load("campaign.json")
        before = len(session.data["campaigns"])
        session.data["campaigns"] = [
            item
            for item in session.data["campaigns"]
            if item.get("record_id") != campaign_id
        ]
        if len(session.data["campaigns"]) == before:
            raise KeyError("Unknown campaign")
        outcome = self.store.save(session, "campaigner")
        if not outcome.saved:
            raise RuntimeError("The campaign changed elsewhere; reload before deleting")
