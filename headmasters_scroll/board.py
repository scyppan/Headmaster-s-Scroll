from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from .assets import AssetStore


DISPLAY_MODES = {"dot", "token"}
VISIBILITY_MODES = {"players", "headmaster"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_person_board() -> dict[str, Any]:
    return {
        "portrait": None,
        "placement": None,
        "visibility": "players",
        "display_mode": "dot",
        "name_revealed": False,
        "faction_revealed": False,
        "faction_organization_id": "",
    }


def normalize_person_board(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    result = default_person_board()
    portrait = source.get("portrait")
    if portrait is not None:
        if not isinstance(portrait, dict):
            raise ValueError("A portrait reference must be an object or null")
        required = {"asset_id", "sha256", "width", "height", "mime_type"}
        if not required.issubset(portrait):
            raise ValueError("A portrait reference is missing required metadata")
        if portrait.get("width") != 512 or portrait.get("height") != 512:
            raise ValueError("Character portraits must be 512 by 512 pixels")
        if portrait.get("mime_type") != "image/webp":
            raise ValueError("Character portraits must be WebP images")
        result["portrait"] = deepcopy(portrait)
    placement = source.get("placement")
    if placement is not None:
        if not isinstance(placement, dict):
            raise ValueError("Board placement must be an object or null")
        normalized_placement = {
            "location_id": str(placement.get("location_id", "") or "").strip(),
            "floor_id": str(placement.get("floor_id", "") or "").strip(),
            "map_id": str(placement.get("map_id", "") or "").strip(),
            "x": float(placement.get("x", 0.5)),
            "y": float(placement.get("y", 0.5)),
        }
        if not normalized_placement["location_id"] or not normalized_placement["map_id"]:
            raise ValueError("Placed people require a location and map")
        if not 0.0 <= normalized_placement["x"] <= 1.0 or not 0.0 <= normalized_placement["y"] <= 1.0:
            raise ValueError("Board coordinates must be between 0 and 1")
        result["placement"] = normalized_placement
    result["visibility"] = str(source.get("visibility", "players") or "players")
    result["display_mode"] = str(source.get("display_mode", "dot") or "dot")
    if result["visibility"] not in VISIBILITY_MODES:
        raise ValueError("Unknown board visibility")
    if result["display_mode"] not in DISPLAY_MODES:
        raise ValueError("Unknown board display mode")
    result["name_revealed"] = bool(source.get("name_revealed", False))
    result["faction_revealed"] = bool(source.get("faction_revealed", False))
    result["faction_organization_id"] = str(
        source.get("faction_organization_id", "") or ""
    ).strip()
    return result


def normalize_floor(value: Any, index: int = 0) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Every floor must be an object")
    record_id = str(value.get("record_id", "") or "").strip()
    name = str(value.get("name", "") or "").strip()
    if not record_id or not name:
        raise ValueError("Every floor requires a stable ID and name")
    return {
        **deepcopy(value),
        "record_id": record_id,
        "name": name,
        "sort_order": int(value.get("sort_order", index)),
        "primary_map_id": str(value.get("primary_map_id", "") or "").strip(),
    }


def normalize_map(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Every map must be an object")
    result = deepcopy(value)
    for field in ("record_id", "name", "location_id"):
        result[field] = str(result.get(field, "") or "").strip()
        if not result[field]:
            raise ValueError(f"Every map requires {field}")
    result["floor_id"] = str(result.get("floor_id", "") or "").strip()
    result["players_published"] = bool(result.get("players_published", False))
    asset = result.get("asset")
    if asset is not None and not isinstance(asset, dict):
        raise ValueError("Map asset metadata must be an object or null")
    if asset:
        required = {"asset_id", "sha256", "width", "height", "mime_type", "file_extension"}
        if not required.issubset(asset):
            raise ValueError("Map asset metadata is incomplete")
        if not str(asset.get("asset_id", "")).startswith("map:"):
            raise ValueError("A map asset must use a map asset ID")
        if int(asset.get("width", 0)) <= 0 or int(asset.get("height", 0)) <= 0:
            raise ValueError("Map asset dimensions must be positive")
    result["asset"] = deepcopy(asset) if asset else None
    return result


def normalize_group(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Every board group must be an object")
    result = deepcopy(value)
    for field in ("record_id", "name", "location_id"):
        result[field] = str(result.get(field, "") or "").strip()
        if not result[field]:
            raise ValueError(f"Every board group requires {field}")
    members = []
    seen: set[tuple[str, str]] = set()
    for member in result.get("members", []) or []:
        if not isinstance(member, dict):
            raise ValueError("Every group member must be an object")
        actor_type = str(member.get("actor_type", "person") or "person").strip()
        actor_id = str(member.get("actor_id", "") or "").strip()
        member_id = str(member.get("record_id", "") or "").strip()
        if not actor_id or not member_id:
            raise ValueError("Every group member needs record_id and actor_id")
        key = (actor_type, actor_id)
        if key in seen:
            raise ValueError("A board group cannot contain the same actor twice")
        seen.add(key)
        members.append({**deepcopy(member), "record_id": member_id, "actor_type": actor_type, "actor_id": actor_id})
    result["members"] = members
    if len(members) < 2:
        raise ValueError("A board group requires at least two members")
    return result


def ensure_board_collections(document: dict[str, Any]) -> bool:
    changed = False
    for collection in ("maps", "board_groups"):
        if collection not in document:
            document[collection] = []
            changed = True
    for location in document.get("locations", []):
        if not isinstance(location, dict):
            continue
        defaults = {"is_building": False, "floors": [], "default_map_id": ""}
        for key, default in defaults.items():
            if key not in location:
                location[key] = deepcopy(default)
                changed = True
    return changed


def _date_key(value: Any, time_value: Any = "") -> tuple[int, int, int, int, int]:
    text = str(value or "").strip()
    if not text:
        return (-999999, 1, 1, 0, 0)
    sign = -1 if text.startswith("-") else 1
    parts = text.removeprefix("-").split("-")
    try:
        year = sign * int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
        hour, minute = (0, 0)
        if str(time_value or "").strip():
            clock = str(time_value).strip().split(":")
            hour, minute = int(clock[0]), int(clock[1])
        return (year, month, day, hour, minute)
    except (TypeError, ValueError, IndexError) as error:
        raise ValueError(f"Invalid world date: {value}") from error


def active_faction_ids(document: dict[str, Any], person_id: str, game_datetime: str) -> list[str]:
    cutoff_date, _, cutoff_time = str(game_datetime).partition("T")
    cutoff = _date_key(cutoff_date, cutoff_time)
    valid_factions = {
        str(item.get("record_id"))
        for item in document.get("organizations", [])
        if isinstance(item, dict) and item.get("is_faction")
    }
    events = []
    for event in document.get("events", []):
        if not isinstance(event, dict) or event.get("event_type") not in {"joined_faction", "left_faction"}:
            continue
        if person_id not in (event.get("person_ids") or []):
            continue
        organization_id = str(event.get("organization_id", "") or "")
        if organization_id not in valid_factions:
            continue
        key = _date_key(event.get("date"), event.get("time"))
        if key <= cutoff:
            events.append((key, str(event.get("record_id", "")), event))
    state: dict[str, bool] = {}
    for _, __, event in sorted(events, key=lambda item: (item[0], item[1])):
        state[str(event.get("organization_id"))] = event.get("event_type") == "joined_faction"
    return sorted(organization_id for organization_id, active in state.items() if active)


def validate_world_board(document: dict[str, Any]) -> None:
    maps = [normalize_map(item) for item in document.get("maps", [])]
    map_by_id = {item["record_id"]: item for item in maps}
    locations = {
        str(item.get("record_id")): item
        for item in document.get("locations", [])
        if isinstance(item, dict)
    }
    floor_by_id: dict[str, tuple[str, dict[str, Any]]] = {}
    for location_id, location in locations.items():
        floors = [normalize_floor(item, index) for index, item in enumerate(location.get("floors", []) or [])]
        if len({item["record_id"] for item in floors}) != len(floors):
            raise ValueError("Floor IDs must be unique within a location")
        for floor in floors:
            if floor["record_id"] in floor_by_id:
                raise ValueError("Floor IDs must be unique across the world")
            floor_by_id[floor["record_id"]] = (location_id, floor)
        default_map_id = str(location.get("default_map_id", "") or "")
        if default_map_id and default_map_id not in map_by_id:
            raise ValueError("A location default map must exist")
        if default_map_id and map_by_id[default_map_id]["location_id"] != location_id:
            raise ValueError("A location default map must belong to that location")
    for map_record in maps:
        if map_record["location_id"] not in locations:
            raise ValueError("Every map must reference an existing location")
        if map_record["floor_id"]:
            floor = floor_by_id.get(map_record["floor_id"])
            if not floor or floor[0] != map_record["location_id"]:
                raise ValueError("A map floor must belong to its location")
    for floor_id, (location_id, floor) in floor_by_id.items():
        primary_map_id = floor.get("primary_map_id", "")
        if not primary_map_id:
            continue
        primary = map_by_id.get(primary_map_id)
        if primary is None or primary["location_id"] != location_id or primary["floor_id"] != floor_id:
            raise ValueError("A floor primary map must belong to that floor")
    person_ids = {
        str(person.get("record_id"))
        for person in document.get("people", [])
        if isinstance(person, dict)
    }
    person_locations: dict[str, str] = {}
    for person in document.get("people", []):
        if not isinstance(person, dict) or "board" not in person:
            continue
        board = normalize_person_board(person.get("board"))
        placement = board.get("placement")
        if placement:
            person_locations[str(person.get("record_id"))] = placement["location_id"]
            map_record = map_by_id.get(placement["map_id"])
            if map_record is None or map_record["location_id"] != placement["location_id"]:
                raise ValueError("A person's placement must match an existing map and location")
            if placement["floor_id"] != map_record["floor_id"]:
                raise ValueError("A person's placement floor must match the map")
    groups = [normalize_group(item) for item in document.get("board_groups", [])]
    memberships: set[str] = set()
    for group in groups:
        if group["location_id"] not in locations:
            raise ValueError("Every board group must reference an existing location")
        for member in group["members"]:
            if member["actor_type"] != "person":
                continue
            if member["actor_id"] not in person_ids:
                raise ValueError("A group member must reference an existing person")
            if person_locations.get(member["actor_id"]) != group["location_id"]:
                raise ValueError("Every person in a board group must occupy its location")
            if member["actor_id"] in memberships:
                raise ValueError("A person can belong to only one board group")
            memberships.add(member["actor_id"])


class WorldBoardRepository:
    def __init__(self, store=None, assets: AssetStore | None = None):
        if store is None:
            from .store import SharedJsonStore

            store = SharedJsonStore()
        self.store = store
        self.assets = assets or AssetStore()

    def load(self):
        session = self.store.load("world.json")
        ensure_board_collections(session.data)
        return session

    def save(self, session, app_id: str = "game-board") -> dict[str, Any]:
        validate_world_board(session.data)
        outcome = self.store.save(session, app_id)
        if not outcome.saved:
            raise RuntimeError("The world changed in the same place; refresh before trying again")
        return deepcopy(session.data)

    def snapshot(
        self,
        game_datetime: str,
        *,
        player_character_ids: Iterable[str] = (),
        for_players: bool = False,
    ) -> dict[str, Any]:
        document = self.load().data
        player_ids = {str(value) for value in player_character_ids if value}
        maps = [normalize_map(item) for item in document.get("maps", [])]
        occupied_player_maps = {
            normalize_person_board(person.get("board")).get("placement", {}).get("map_id")
            for person in document.get("people", [])
            if isinstance(person, dict)
            and str(person.get("record_id")) in player_ids
            and normalize_person_board(person.get("board")).get("placement")
        }
        visible_map_ids = {
            item["record_id"]
            for item in maps
            if item.get("players_published") or item["record_id"] in occupied_player_maps
        }
        if for_players:
            maps = [item for item in maps if item["record_id"] in visible_map_ids]
            public_maps = []
            for item in maps:
                public = deepcopy(item)
                metadata = public.get("asset")
                public["asset"] = (
                    {
                        "asset_id": metadata.get("asset_id"),
                        "width": metadata.get("width"),
                        "height": metadata.get("height"),
                        "mime_type": metadata.get("mime_type"),
                    }
                    if isinstance(metadata, dict)
                    else None
                )
                public_maps.append(public)
            maps = public_maps
        organizations = {
            str(item.get("record_id")): item
            for item in document.get("organizations", [])
            if isinstance(item, dict)
        }
        actors = []
        for person in document.get("people", []):
            if not isinstance(person, dict):
                continue
            person_id = str(person.get("record_id", "") or "")
            board = normalize_person_board(person.get("board"))
            placement = board.get("placement")
            if not placement:
                continue
            is_player = person_id in player_ids or bool(person.get("player_character"))
            if for_players and (
                placement["map_id"] not in visible_map_ids
                or (board["visibility"] == "headmaster" and not is_player)
            ):
                continue
            active_factions = active_faction_ids(document, person_id, game_datetime)
            chosen = board["faction_organization_id"]
            chosen = chosen if chosen in active_factions else ""
            faction = organizations.get(chosen, {})
            portrait = board.get("portrait")
            display_mode = "token" if is_player else board["display_mode"]
            if display_mode == "token" and not portrait and not is_player:
                display_mode = "dot"
            actor = {
                "actor_type": "person",
                "actor_id": person_id,
                "map_id": placement["map_id"],
                "location_id": placement["location_id"],
                "floor_id": placement["floor_id"],
                "x": placement["x"],
                "y": placement["y"],
                "display_mode": "nameplate" if is_player and not portrait else display_mode,
                "portrait_asset_id": portrait.get("asset_id") if portrait else None,
                "name": str(person.get("displayed_name", "") or "") if (not for_players or is_player or board["name_revealed"]) else "Unknown",
                "name_revealed": bool(is_player or board["name_revealed"]),
                "faction_revealed": bool(board["faction_revealed"]),
                "faction_id": chosen if (not for_players or board["faction_revealed"]) else "",
                "faction_name": (str(faction.get("name", "") or "") or "Unknown") if (not for_players or board["faction_revealed"]) else "Unknown",
                "faction_color": str(faction.get("faction_color", "#808080") or "#808080") if (not for_players or board["faction_revealed"]) else "#808080",
                "active_faction_ids": active_factions if not for_players else [],
                "active_factions": [
                    {
                        "organization_id": faction_id,
                        "name": str(organizations.get(faction_id, {}).get("name", "") or faction_id),
                        "color": str(organizations.get(faction_id, {}).get("faction_color", "#808080") or "#808080"),
                    }
                    for faction_id in active_factions
                ] if not for_players else [],
                "is_player_character": is_player,
                "visibility": board["visibility"] if not for_players else "players",
            }
            actors.append(actor)
        return {
            "game_datetime": game_datetime,
            "maps": maps,
            "actors": actors,
            "groups": deepcopy(document.get("board_groups", [])) if not for_players else [],
            "visible_map_ids": sorted(visible_map_ids),
        }

    def move_person(self, person_id: str, map_id: str, x: float, y: float) -> dict[str, Any]:
        session = self.load()
        map_record = next((item for item in session.data["maps"] if item.get("record_id") == map_id), None)
        person = next((item for item in session.data["people"] if item.get("record_id") == person_id), None)
        if map_record is None or person is None:
            raise KeyError("Unknown map or person")
        board = normalize_person_board(person.get("board"))
        board["placement"] = {
            "location_id": str(map_record["location_id"]),
            "floor_id": str(map_record.get("floor_id", "") or ""),
            "map_id": str(map_id),
            "x": max(0.0, min(1.0, float(x))),
            "y": max(0.0, min(1.0, float(y))),
        }
        person["board"] = board
        self._remove_from_incompatible_groups(session.data, person_id, board["placement"]["location_id"])
        self.save(session)
        return deepcopy(board["placement"])

    @staticmethod
    def _remove_from_incompatible_groups(document: dict[str, Any], person_id: str, location_id: str) -> None:
        retained = []
        for group in document.get("board_groups", []):
            if str(group.get("location_id")) != str(location_id):
                group["members"] = [
                    member for member in group.get("members", [])
                    if not (member.get("actor_type", "person") == "person" and member.get("actor_id") == person_id)
                ]
            if len(group.get("members", [])) >= 2:
                retained.append(group)
        document["board_groups"] = retained

    def update_person_board(self, person_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        session = self.load()
        person = next((item for item in session.data["people"] if item.get("record_id") == person_id), None)
        if person is None:
            raise KeyError("Unknown person")
        board = normalize_person_board(person.get("board"))
        board.update(deepcopy(updates))
        person["board"] = normalize_person_board(board)
        if (
            person["board"]["display_mode"] == "token"
            and not person["board"].get("portrait")
            and not person.get("player_character")
        ):
            raise ValueError("An NPC needs a prepared portrait before becoming a portrait token")
        self.save(session)
        return deepcopy(person["board"])

    def set_map_published(self, map_id: str, published: bool) -> dict[str, Any]:
        session = self.load()
        record = next((item for item in session.data["maps"] if item.get("record_id") == map_id), None)
        if record is None:
            raise KeyError("Unknown map")
        record["players_published"] = bool(published)
        record["last_updated"] = utc_now()
        self.save(session)
        return deepcopy(record)

    def create_group(self, name: str, location_id: str, person_ids: list[str]) -> dict[str, Any]:
        if len(set(person_ids)) < 2:
            raise ValueError("A board group requires at least two people")
        session = self.load()
        existing_members = {
            member.get("actor_id")
            for group in session.data["board_groups"]
            for member in group.get("members", [])
            if member.get("actor_type", "person") == "person"
        }
        people = {str(item.get("record_id")): item for item in session.data["people"]}
        for person_id in person_ids:
            if person_id not in people or person_id in existing_members:
                raise ValueError("Every group member must be an ungrouped person")
            placement = normalize_person_board(people[person_id].get("board")).get("placement")
            if not placement or placement["location_id"] != location_id:
                raise ValueError("All group members must occupy the group's location")
        now = utc_now()
        group = {
            "record_id": str(uuid4()),
            "name": str(name or "").strip(),
            "location_id": str(location_id),
            "members": [
                {"record_id": str(uuid4()), "actor_type": "person", "actor_id": person_id}
                for person_id in person_ids
            ],
            "created_at": now,
            "last_updated": now,
        }
        group = normalize_group(group)
        session.data["board_groups"].append(group)
        self.save(session)
        return deepcopy(group)

    def set_group(self, person_id: str, group_id: str | None) -> dict[str, Any] | None:
        session = self.load()
        person = next((item for item in session.data["people"] if item.get("record_id") == person_id), None)
        if person is None:
            raise KeyError("Unknown person")
        placement = normalize_person_board(person.get("board")).get("placement")
        target = next(
            (item for item in session.data["board_groups"] if item.get("record_id") == group_id),
            None,
        ) if group_id else None
        if group_id and target is None:
            raise KeyError("Unknown board group")
        if target and (not placement or str(target.get("location_id")) != placement["location_id"]):
            raise ValueError("A person can only join a group at the same location")
        for group in session.data["board_groups"]:
            group["members"] = [
                member for member in group.get("members", [])
                if not (member.get("actor_type", "person") == "person" and member.get("actor_id") == person_id)
            ]
        if target is not None:
            target.setdefault("members", []).append({
                "record_id": str(uuid4()),
                "actor_type": "person",
                "actor_id": person_id,
            })
            target["last_updated"] = utc_now()
        session.data["board_groups"] = [
            group for group in session.data["board_groups"]
            if len(group.get("members", [])) >= 2
        ]
        self.save(session)
        if target is None or target not in session.data["board_groups"]:
            return None
        return deepcopy(target)
