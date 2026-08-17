from __future__ import annotations

import calendar
import hashlib
import math
import os
import random
import re
import sys
import threading
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from difflib import SequenceMatcher
from secrets import token_urlsafe
from typing import Any
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from ..store import SharedJsonStore
from ..board import (
    DEFAULT_MAP_TOKEN_SCALE,
    OFF_LIMITS_MESSAGE,
    WorldBoardRepository,
    active_faction_ids,
    normalize_group,
    normalize_map,
    normalize_map_point,
    normalize_obscuration,
    normalize_person_board,
    point_in_polygon,
)
from ..campaigns import CampaignRepository, normalize_board_camera, normalize_zoom_profile
from ..battles import calculated_order, normalize_battle, participant, public_battle
from ..character_attributes import calculate_character_attributes
from ..character_sheet import build_character_sheet
from ..character_rolls import perform_character_roll
from ..creatures import (
    generate_creature_instance,
    normalize_campaign_creature,
    roll_creature_action,
    utc_now as creature_utc_now,
)
from ..region_interactions import draw_loot, loot_cost, shop_window
from .storage import GameBoardRepository


EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GAME_DATETIME = re.compile(
    r"^(?P<year>-?[1-9]\d*)-(?P<month>\d{2})-(?P<day>\d{2})T"
    r"(?P<hour>\d{2}):(?P<minute>\d{2})$"
)
BOOK_COVER_DIRECTORY = Path(__file__).resolve().parents[2] / "assets" / "book covers"
BOOK_COVER_FILES = {
    "alchemy": "Alchemy.png",
    "arithmancy": "exec-119cccea-4701-43fc-a21b-ca399d09be17.png",
    "artificing": "Artificing.png",
    "astronomy": "Astronomy.png",
    "charms": "Charms.png",
    "creatures": "Creatures.png",
    "dark-arts": "Dark Arts.png",
    "defense": "Defense.png",
    "divination": "Divination.png",
    "flying": "Flying.png",
    "herbology": "Herbology.png",
    "history": "History.png",
    "muggles": "Muggles.png",
    "potions": "Potions.png",
    "runes": "Runes.png",
    "transfiguration": "Transfiguration.png",
}


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
        self._world_cache_fingerprint: tuple[int, int] | None = None
        self._world_cache: dict[str, Any] | None = None
        self._database_cache_fingerprint: tuple[int, int] | None = None
        self._database_cache: dict[str, Any] | None = None
        self._character_sheet_cache: dict[tuple[Any, ...], dict[str, Any] | None] = {}
        self._tickets: dict[str, dict[str, Any]] = {}
        self._ticket_by_request: dict[str, str] = {}
        self._restore_for_reapproval()

    def world_fingerprint(self) -> tuple[int, int]:
        """Return the canonical world's cheap filesystem change token."""

        return self.shared_store.fingerprint("world.json")

    def _world_document(self) -> dict[str, Any]:
        """Return a read-only, revision-aware world snapshot.

        Game Board used to decode and validate the very large world file for
        every catalog, map, board, and one-second change check.  The cached
        object is never handed to an editor; mutation paths still open their
        own revision-aware DataSession.
        """

        fingerprint = self.world_fingerprint()
        with self._lock:
            if (
                self._world_cache is not None
                and fingerprint == self._world_cache_fingerprint
            ):
                return self._world_cache
            document = self.shared_store.read_document("world.json")
            self._world_cache = document
            self._world_cache_fingerprint = fingerprint
            return document

    def _database_document(self) -> dict[str, Any]:
        """Return the validated rules catalog without repeated session copies."""

        fingerprint = self.shared_store.fingerprint("db.json")
        with self._lock:
            if (
                self._database_cache is not None
                and fingerprint == self._database_cache_fingerprint
            ):
                return self._database_cache
            document = self.shared_store.read_document("db.json")
            self._database_cache = document
            self._database_cache_fingerprint = fingerprint
            return document

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
        world = self._world_document()
        characters = []
        for person in world.get("people", []):
            record_id = person.get("record_id")
            name = str(person.get("displayed_name") or "").strip()
            if isinstance(record_id, str) and record_id and name:
                characters.append({"id": record_id, "name": name})
        return sorted(characters, key=lambda item: (item["name"].casefold(), item["id"]))

    def list_campaigns(self) -> list[dict[str, Any]]:
        return self.campaign_repository.list()

    def teaching_catalog(self) -> dict[str, list[dict[str, str]]]:
        """Return compact searchable catalogs for the Headmaster UI."""

        try:
            database = self._database_document()
        except FileNotFoundError:
            # Board-only fixtures and recovery mode may intentionally omit the
            # rules catalog.  The rest of the Headmaster state must still load.
            database = {
                "spells": [], "proficiencies": [], "potions": [],
                "preparations": [], "foods_and_drinks": [], "recipes": [],
            }
        result: dict[str, list[dict[str, str]]] = {
            "spell": [], "proficiency": [], "recipe": [],
        }
        for kind, collections in (
            ("spell", ("spells",)),
            ("proficiency", ("proficiencies",)),
            ("recipe", ("recipes", "potions", "preparations", "foods_and_drinks")),
        ):
            for collection in collections:
                for item in database.get(collection, []) or []:
                    if not isinstance(item, dict) or not item.get("record_id"):
                        continue
                    result[kind].append({
                        "record_id": str(item["record_id"]),
                        "name": str(item.get("name") or item.get("title") or "Unknown"),
                        "collection": collection,
                        "skill": str(item.get("skill") or ""),
                    })
            result[kind].sort(key=lambda item: (item["name"].casefold(), item["record_id"]))
        return result

    def _teaching_context(
        self, session_id: str, pupil_person_id: str, knowledge_kind: str,
        knowledge_record_id: str, knowledge_collection: str = "",
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
        session = self._board_context(session_id)
        campaign, world = self._campaign_document(session)
        pupil = next((
            item for item in world.get("people", []) or []
            if isinstance(item, dict) and str(item.get("record_id", "")) == pupil_person_id
        ), None)
        if pupil is None:
            raise KeyError("Unknown pupil")
        kind = str(knowledge_kind or "").strip().casefold()
        if kind not in {"spell", "proficiency", "recipe"}:
            raise ValueError("Choose a spell, proficiency, or recipe")
        catalog = self.teaching_catalog()[kind]
        record = next((item for item in catalog if item["record_id"] == knowledge_record_id), None)
        if record is None:
            raise KeyError("Unknown teaching subject")
        if knowledge_collection and record["collection"] != knowledge_collection:
            raise ValueError("The teaching subject does not belong to that collection")
        return campaign, pupil, record

    def _sheet_for_person(
        self, session_id: str, person_id: str,
    ) -> dict[str, Any]:
        """Build one character's date-effective sheet without exposing the world."""
        session = self._board_context(session_id)
        campaign, document = self._campaign_document(session)
        person = next((
            item for item in document.get("people", []) or []
            if isinstance(item, dict) and str(item.get("record_id", "")) == person_id
        ), None)
        if person is None:
            raise KeyError("Unknown teacher")
        try:
            database = self._database_document()
        except FileNotFoundError:
            database = {
                "schools": [], "spells": [], "proficiencies": [],
                "potions": [], "preparations": [], "foods_and_drinks": [], "recipes": [],
                "creatures": [], "books": [],
            }
        return build_character_sheet(person, document, database, campaign)

    def _battle_person_sort_key(
        self, person: dict[str, Any], world: dict[str, Any], database: dict[str, Any],
        campaign: dict[str, Any], random_key: float,
    ) -> tuple[Any, ...]:
        attributes = calculate_character_attributes(
            person, world, database,
            str(campaign["game_state"]["current_game_datetime"]),
            (campaign["game_state"].get("people", {}) or {}).get(
                str(person.get("record_id", "")), {}
            ),
        )
        eminence = sum(
            int((item.get("breakdown") or {}).get("eminence", 0) or 0)
            for item in attributes.get("skills", []) or []
            if isinstance(item, dict)
        )
        try:
            birth = (
                int(person.get("birth_year")),
                int(person.get("birth_month") or 1),
                int(person.get("birth_day") or 1),
            )
        except (TypeError, ValueError):
            birth = (999999, 12, 31)
        return (-eminence, birth, float(random_key), str(person.get("record_id", "")))

    def _recalculate_battle_order(
        self, battle: dict[str, Any], world: dict[str, Any], database: dict[str, Any],
        campaign: dict[str, Any], *, preserve_manual: bool = True,
    ) -> None:
        people_by_id = {
            str(item.get("record_id", "")): item
            for item in world.get("people", []) or [] if isinstance(item, dict)
        }
        person_entries = [
            item for item in battle["participants"] if item["actor_type"] == "person"
        ]
        person_entries.sort(key=lambda item: self._battle_person_sort_key(
            people_by_id.get(item["actor_id"], {}), world, database, campaign,
            item["random_key"],
        ))
        for rank, item in enumerate(person_entries):
            item["calculated_rank"] = rank
        creatures = [
            item for item in battle["participants"] if item["actor_type"] == "creature"
        ]
        new_calculated = calculated_order(person_entries, creatures)
        prior_order = list(battle.get("order", []))
        battle["calculated_order"] = new_calculated
        if not preserve_manual or not battle.get("manual_order"):
            battle["order"] = new_calculated
        else:
            retained = [item for item in prior_order if item in set(new_calculated)]
            retained.extend(item for item in new_calculated if item not in retained)
            battle["order"] = retained
        if battle.get("current_participant_id") not in battle["order"]:
            battle["current_participant_id"] = battle["order"][0] if battle["order"] else ""

    @staticmethod
    def _battle_participant_by_id(
        battle: dict[str, Any], participant_id: str,
    ) -> dict[str, Any]:
        found = next((
            item for item in battle.get("participants", [])
            if item.get("record_id") == participant_id
        ), None)
        if found is None:
            raise KeyError("Unknown battle participant")
        return found

    def _battle_actor_catalog(
        self, campaign: dict[str, Any], world: dict[str, Any], *, for_players: bool = False,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        result: dict[tuple[str, str], dict[str, Any]] = {}
        people_state = campaign["game_state"].get("people", {}) or {}
        for person in world.get("people", []) or []:
            if not isinstance(person, dict) or not person.get("record_id"):
                continue
            actor_id = str(person["record_id"])
            state = people_state.get(actor_id, {}) or {}
            result[("person", actor_id)] = {
                "actor_id": actor_id,
                "actor_type": "person",
                "name": str(person.get("displayed_name") or "Unknown"),
                "true_name": str(person.get("displayed_name") or "Unknown"),
                "map_id": str((state.get("placement") or {}).get("map_id", "") or ""),
                "x": (state.get("placement") or {}).get("x"),
                "y": (state.get("placement") or {}).get("y"),
                "visibility": str(state.get("visibility", "headmaster") or "headmaster"),
                "name_revealed": bool(state.get("name_revealed", False)),
                "wounds": deepcopy(state.get("wounds", []) or []),
                "battle": deepcopy(state.get("battle")),
            }
        for creature_id, creature in (campaign["game_state"].get("creatures", {}) or {}).items():
            creature = normalize_campaign_creature(creature)
            result[("creature", str(creature_id))] = {
                "actor_id": str(creature_id),
                "actor_type": "creature",
                "name": str(creature.get("display_name") or creature.get("species_name") or "Creature"),
                "true_name": str(creature.get("display_name") or creature.get("internal_label") or "Creature"),
                "map_id": str((creature.get("placement") or {}).get("map_id", "") or ""),
                "x": (creature.get("placement") or {}).get("x"),
                "y": (creature.get("placement") or {}).get("y"),
                "visibility": str(creature.get("visibility", "headmaster") or "headmaster"),
                "wounds": deepcopy(creature.get("wounds", []) or []),
                "life_state": str(creature.get("life_state", "alive") or "alive"),
                "named_creature_id": str(creature.get("named_creature_id", "") or ""),
            }
        return result

    def battle_snapshot(
        self, session_id: str, *, contact_id: str = "", for_players: bool = False,
    ) -> dict[str, Any]:
        session = self._board_context(session_id)
        campaign, world = self._campaign_document(session)
        actors = self._battle_actor_catalog(campaign, world, for_players=for_players)
        battles = list((campaign["game_state"].get("battles", {}) or {}).values())
        if not for_players:
            rendered = []
            for raw in battles:
                battle = normalize_battle(raw)
                by_id = {item["record_id"]: item for item in battle["participants"]}
                order = []
                for participant_id in battle["order"]:
                    item = by_id.get(participant_id)
                    if not item:
                        continue
                    actor = actors.get((item["actor_type"], item["actor_id"]), {})
                    order.append({
                        **deepcopy(item),
                        "name": str(actor.get("true_name") or actor.get("name") or "Unknown"),
                        "map_id": str(actor.get("map_id", "") or ""),
                        "wounds": deepcopy(actor.get("wounds", []) or []),
                        "life_state": str(actor.get("life_state", "alive") or "alive"),
                        "current": participant_id == battle["current_participant_id"],
                        "acted": item["acted_round"] == battle["round"],
                        "skipped": item["skipped_round"] == battle["round"],
                    })
                rendered.append({**deepcopy(battle), "order_entries": order})
            return {"campaign_id": campaign["record_id"], "battles": rendered}
        roster = next((
            item for item in session.get("roster", [])
            if str(item.get("contact_id", "")) == str(contact_id)
        ), None)
        character_id = str((roster or {}).get("character_id", "") or "")
        visible = [
            item for item in (
                public_battle(normalize_battle(raw), actors, viewer_character_id=character_id)
                for raw in battles
            ) if item is not None
        ]
        return {"campaign_id": campaign["record_id"], "battles": visible}

    def battle_actor_choices(
        self, session_id: str, battle_id: str, query: str = "",
    ) -> dict[str, Any]:
        session = self._board_context(session_id)
        campaign, world = self._campaign_document(session)
        battle = normalize_battle(
            (campaign["game_state"].get("battles", {}) or {}).get(battle_id)
        )
        needle = str(query or "").strip().casefold()
        actors = self._battle_actor_catalog(campaign, world)
        occupied = {
            (item["actor_type"], item["actor_id"]): str(battle_key)
            for battle_key, raw in (campaign["game_state"].get("battles", {}) or {}).items()
            for item in normalize_battle(raw)["participants"]
        }
        choices: list[dict[str, Any]] = []
        for key, actor in actors.items():
            name = str(actor.get("true_name") or actor.get("name") or "Unknown")
            if needle and needle not in name.casefold():
                continue
            choices.append({
                "actor_type": key[0], "actor_id": key[1], "name": name,
                "map_id": str(actor.get("map_id", "") or ""),
                "x": actor.get("x"), "y": actor.get("y"),
                "on_battle_map": str(actor.get("map_id", "")) == battle["map_id"],
                "already_in_battle": key in occupied,
                "battle_id": occupied.get(key, ""),
                "source": "campaign" if key[0] == "creature" else "world",
            })
        overlaid_named = {
            str(item.get("named_creature_id", "") or "")
            for item in (campaign["game_state"].get("creatures", {}) or {}).values()
        }
        for named in world.get("named_creatures", []) or []:
            named_id = str(named.get("record_id", "") or "")
            name = str(named.get("name") or "Named creature")
            if not named_id or named_id in overlaid_named or (needle and needle not in name.casefold()):
                continue
            placement = named.get("placement") or {}
            choices.append({
                "actor_type": "named_creature", "actor_id": named_id,
                "name": name, "map_id": str(placement.get("map_id", "") or ""),
                "x": placement.get("x"), "y": placement.get("y"),
                "on_battle_map": str(placement.get("map_id", "")) == battle["map_id"],
                "already_in_battle": False, "source": "world",
            })
        choices.sort(key=lambda item: (
            not item["on_battle_map"], item["already_in_battle"],
            item["name"].casefold(), item["actor_id"],
        ))
        return {"battle": deepcopy(battle), "actors": choices[:10000]}

    def add_named_creature_to_battle(
        self, session_id: str, battle_id: str, named_creature_id: str,
        map_id: str, x: float, y: float,
    ) -> dict[str, Any]:
        with self._lock:
            session = self._board_context(session_id)
            campaign, world = self._campaign_document(session)
            named = next((
                item for item in world.get("named_creatures", []) or []
                if str(item.get("record_id", "")) == named_creature_id
            ), None)
            if named is None:
                raise KeyError("Unknown named creature")
            species_id = str(named.get("species_record_id", "") or "")
            species = next((
                item for item in self._database_document().get("creatures", []) or []
                if str(item.get("record_id", "")) == species_id
            ), None)
            if species is None:
                raise KeyError("That named creature's species is unavailable")
            map_record = self._campaign_map(world, map_id)
            result: dict[str, Any] = {}

            def create(state: dict[str, Any]) -> None:
                nonlocal result
                counters = state.setdefault("creature_counters", {})
                counter = int(counters.get(species_id, 0) or 0) + 1
                counters[species_id] = counter
                creature = generate_creature_instance(species, counter, {
                    "location_id": str(map_record.get("location_id", "")),
                    "floor_id": str(map_record.get("floor_id", "") or ""),
                    "map_id": map_id, "x": float(x), "y": float(y),
                })
                creature["named_creature_id"] = named_creature_id
                creature["display_name"] = str(named.get("name") or creature["species_name"])
                creature["visibility"] = "headmaster"
                saved_stats = named.get("generated") or named.get("statistics")
                if isinstance(saved_stats, dict) and saved_stats:
                    creature["generated"].update(deepcopy(saved_stats))
                state.setdefault("creatures", {})[creature["record_id"]] = creature
                result = deepcopy(creature)

            self.campaign_repository.update_game_state(campaign["record_id"], create)
            self.add_battle_actor(
                session_id, battle_id, "creature", str(result["record_id"])
            )
            return result

    def create_battle(self, session_id: str, name: str, map_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._board_context(session_id)
            campaign, world = self._campaign_document(session)
            valid_maps = {
                str(item.get("record_id", ""))
                for item in self.world_board._location_maps(world)
            }
            if map_id not in valid_maps:
                raise KeyError("Unknown battle map")
            now = iso_utc(utc_now())
            battle = normalize_battle({
                "record_id": str(uuid4()), "name": str(name or "Battle"),
                "map_id": map_id, "status": "draft", "round": 1,
                "participants": [], "order": [], "calculated_order": [],
                "created_at": now, "updated_at": now,
            })
            self.campaign_repository.update_game_state(
                campaign["record_id"],
                lambda state: state.setdefault("battles", {}).__setitem__(battle["record_id"], battle),
            )
            return battle

    def start_battle(self, session_id: str, battle_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._board_context(session_id)
            campaign, world = self._campaign_document(session)
            database = self._database_document()
            result: dict[str, Any] = {}
            now = iso_utc(utc_now())
            def update(state: dict[str, Any]) -> None:
                nonlocal result
                battle = state.setdefault("battles", {}).get(battle_id)
                if battle is None:
                    raise KeyError("Unknown battle")
                battle = normalize_battle(battle)
                self._recalculate_battle_order(battle, world, database, campaign, preserve_manual=True)
                battle["status"] = "active"
                battle["started_at"] = battle.get("started_at") or now
                battle["updated_at"] = now
                if not battle["current_participant_id"] and battle["order"]:
                    battle["current_participant_id"] = battle["order"][0]
                state["battles"][battle_id] = battle
                result = deepcopy(battle)
            self.campaign_repository.update_game_state(campaign["record_id"], update)
            return result

    def end_battle(self, session_id: str, battle_id: str) -> None:
        with self._lock:
            session = self._board_context(session_id)
            campaign, _world = self._campaign_document(session)
            def update(state: dict[str, Any]) -> None:
                battle = state.setdefault("battles", {}).pop(battle_id, None)
                if battle is None:
                    raise KeyError("Unknown battle")
                for item in battle.get("participants", []) or []:
                    if item.get("actor_type") == "person":
                        (state.setdefault("people", {}).setdefault(item["actor_id"], {}))["battle"] = None
                    elif item.get("actor_type") == "creature" and item["actor_id"] in state.get("creatures", {}):
                        state["creatures"][item["actor_id"]]["battle"] = None
            self.campaign_repository.update_game_state(campaign["record_id"], update)

    def add_battle_actor(
        self, session_id: str, battle_id: str, actor_type: str, actor_id: str,
        *, transfer: bool = False,
    ) -> dict[str, Any]:
        actor_type = str(actor_type or "").casefold()
        if actor_type not in {"person", "creature"}:
            raise ValueError("Battles support people and creatures")
        with self._lock:
            session = self._board_context(session_id)
            campaign, world = self._campaign_document(session)
            database = self._database_document()
            actors = self._battle_actor_catalog(campaign, world)
            if (actor_type, actor_id) not in actors:
                raise KeyError("Unknown battle actor")
            now = iso_utc(utc_now())
            result: dict[str, Any] = {}
            def update(state: dict[str, Any]) -> None:
                nonlocal result
                battles = state.setdefault("battles", {})
                for other_id, other in list(battles.items()):
                    if other_id == battle_id:
                        continue
                    matching = next((item for item in normalize_battle(other)["participants"] if
                        item.get("actor_type") == actor_type and item.get("actor_id") == actor_id
                    ), None)
                    if matching is None:
                        continue
                    if not transfer:
                        raise ValueError("That actor is already in another active battle")
                    old = normalize_battle(other)
                    removed_id = matching["record_id"]
                    old["participants"] = [item for item in old["participants"] if item["record_id"] != removed_id]
                    old["order"] = [item for item in old["order"] if item != removed_id]
                    old["calculated_order"] = [item for item in old["calculated_order"] if item != removed_id]
                    if old["current_participant_id"] == removed_id:
                        old["current_participant_id"] = old["order"][0] if old["order"] else ""
                    old["updated_at"] = now
                    battles[other_id] = old
                raw_battle = battles.get(battle_id)
                if raw_battle is None:
                    raise KeyError("Unknown battle")
                battle = normalize_battle(raw_battle)
                if any(item["actor_type"] == actor_type and item["actor_id"] == actor_id for item in battle["participants"]):
                    raise ValueError("That actor is already in this battle")
                new_item = participant(actor_type, actor_id, now=now, eligible_round=battle["round"])
                prior_current = battle.get("current_participant_id", "")
                prior_order = list(battle["order"])
                prior_index = prior_order.index(prior_current) if prior_current in prior_order else -1
                battle["participants"].append(new_item)
                self._recalculate_battle_order(battle, world, database, campaign, preserve_manual=True)
                new_index = battle["order"].index(new_item["record_id"])
                current_index = battle["order"].index(prior_current) if prior_current in battle["order"] else -1
                if battle["status"] == "active" and prior_index >= 0 and new_index <= current_index:
                    new_item["eligible_round"] = battle["round"] + 1
                battle["current_participant_id"] = prior_current or (
                    battle["order"][0] if battle["order"] else ""
                )
                battle["updated_at"] = now
                actor_state = (
                    state.setdefault("people", {}).setdefault(actor_id, {})
                    if actor_type == "person" else state.setdefault("creatures", {})[actor_id]
                )
                actor_state["battle"] = {
                    "active": True, "record_id": battle_id, "name": battle["name"],
                    "entered_at": now,
                }
                battles[battle_id] = battle
                result = deepcopy(new_item)
            self.campaign_repository.update_game_state(campaign["record_id"], update)
            return result

    def add_battle_actors(
        self, session_id: str, battle_id: str,
        actor_references: list[dict[str, Any]], *, transfer: bool = False,
    ) -> list[dict[str, Any]]:
        """Add a staged lineup with one validation pass and one campaign save."""
        references: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for raw in actor_references[:500]:
            actor_type = str((raw or {}).get("actor_type", "") or "").casefold()
            actor_id = str((raw or {}).get("actor_id", "") or "")
            key = (actor_type, actor_id)
            if actor_type not in {"person", "creature"} or not actor_id:
                raise ValueError("Battles support people and creatures")
            if key not in seen:
                references.append(key)
                seen.add(key)
        if not references:
            return []
        with self._lock:
            session = self._board_context(session_id)
            campaign, world = self._campaign_document(session)
            database = self._database_document()
            catalog = self._battle_actor_catalog(campaign, world)
            missing = [key for key in references if key not in catalog]
            if missing:
                raise KeyError("One or more battle actors are unavailable")
            now = iso_utc(utc_now())
            result: list[dict[str, Any]] = []

            def update(state: dict[str, Any]) -> None:
                nonlocal result
                battles = state.setdefault("battles", {})
                raw_battle = battles.get(battle_id)
                if raw_battle is None:
                    raise KeyError("Unknown battle")
                battle = normalize_battle(raw_battle)
                prior_current = battle.get("current_participant_id", "")
                prior_order = list(battle["order"])
                prior_index = prior_order.index(prior_current) if prior_current in prior_order else -1
                added: list[dict[str, Any]] = []
                for actor_type, actor_id in references:
                    if any(
                        item["actor_type"] == actor_type and item["actor_id"] == actor_id
                        for item in battle["participants"]
                    ):
                        continue
                    for other_id, raw_other in list(battles.items()):
                        if other_id == battle_id:
                            continue
                        other = normalize_battle(raw_other)
                        matching = next((
                            item for item in other["participants"]
                            if item["actor_type"] == actor_type and item["actor_id"] == actor_id
                        ), None)
                        if matching is None:
                            continue
                        if not transfer:
                            raise ValueError("One or more actors are already in another active battle")
                        removed_id = matching["record_id"]
                        other["participants"] = [item for item in other["participants"] if item["record_id"] != removed_id]
                        other["order"] = [item for item in other["order"] if item != removed_id]
                        other["calculated_order"] = [item for item in other["calculated_order"] if item != removed_id]
                        if other["current_participant_id"] == removed_id:
                            other["current_participant_id"] = other["order"][0] if other["order"] else ""
                        other["updated_at"] = now
                        battles[other_id] = other
                    item = participant(
                        actor_type, actor_id, now=now,
                        eligible_round=battle["round"],
                    )
                    battle["participants"].append(item)
                    added.append(item)
                self._recalculate_battle_order(
                    battle, world, database, campaign, preserve_manual=True
                )
                current_index = battle["order"].index(prior_current) if prior_current in battle["order"] else -1
                for item in added:
                    new_index = battle["order"].index(item["record_id"])
                    if battle["status"] == "active" and prior_index >= 0 and new_index <= current_index:
                        item["eligible_round"] = battle["round"] + 1
                    actor_state = (
                        state.setdefault("people", {}).setdefault(item["actor_id"], {})
                        if item["actor_type"] == "person"
                        else state.setdefault("creatures", {})[item["actor_id"]]
                    )
                    actor_state["battle"] = {
                        "active": True, "record_id": battle_id,
                        "name": battle["name"], "entered_at": now,
                    }
                battle["current_participant_id"] = prior_current or (
                    battle["order"][0] if battle["order"] else ""
                )
                battle["updated_at"] = now
                battles[battle_id] = battle
                result = deepcopy(added)

            self.campaign_repository.update_game_state(campaign["record_id"], update)
            return result

    def remove_battle_actor(
        self, session_id: str, battle_id: str, participant_id: str,
    ) -> None:
        with self._lock:
            session = self._board_context(session_id)
            campaign, _world = self._campaign_document(session)
            def update(state: dict[str, Any]) -> None:
                battle = normalize_battle(state.setdefault("battles", {}).get(battle_id))
                item = self._battle_participant_by_id(battle, participant_id)
                battle["participants"] = [entry for entry in battle["participants"] if entry["record_id"] != participant_id]
                battle["order"] = [entry for entry in battle["order"] if entry != participant_id]
                battle["calculated_order"] = [entry for entry in battle["calculated_order"] if entry != participant_id]
                if battle["current_participant_id"] == participant_id:
                    battle["current_participant_id"] = battle["order"][0] if battle["order"] else ""
                actor_state = (
                    state.setdefault("people", {}).setdefault(item["actor_id"], {})
                    if item["actor_type"] == "person" else state.setdefault("creatures", {}).get(item["actor_id"], {})
                )
                actor_state["battle"] = None
                state["battles"][battle_id] = battle
            self.campaign_repository.update_game_state(campaign["record_id"], update)

    def reorder_battle(
        self, session_id: str, battle_id: str, order: list[str] | None,
    ) -> dict[str, Any]:
        with self._lock:
            session = self._board_context(session_id)
            campaign, world = self._campaign_document(session)
            database = self._database_document()
            result: dict[str, Any] = {}
            def update(state: dict[str, Any]) -> None:
                nonlocal result
                battle = normalize_battle(state.setdefault("battles", {}).get(battle_id))
                expected = set(item["record_id"] for item in battle["participants"])
                if order is None:
                    self._recalculate_battle_order(battle, world, database, campaign, preserve_manual=False)
                    battle["manual_order"] = False
                else:
                    normalized = [str(item) for item in order]
                    if len(normalized) != len(expected) or set(normalized) != expected:
                        raise ValueError("Battle order must contain every participant exactly once")
                    battle["order"] = normalized
                    battle["manual_order"] = True
                state["battles"][battle_id] = battle
                result = deepcopy(battle)
            self.campaign_repository.update_game_state(campaign["record_id"], update)
            return result

    def update_battle_turn(
        self, session_id: str, battle_id: str, action: str, *, summary: str = "",
    ) -> dict[str, Any]:
        action = str(action or "").casefold()
        with self._lock:
            session = self._board_context(session_id)
            campaign, _world = self._campaign_document(session)
            result: dict[str, Any] = {}
            def update(state: dict[str, Any]) -> None:
                nonlocal result
                battle = normalize_battle(state.setdefault("battles", {}).get(battle_id))
                current = self._battle_participant_by_id(battle, battle["current_participant_id"])
                if action == "mark":
                    current["acted_round"] = battle["round"]
                    current["skipped_round"] = 0
                    current["action_summary"] = str(summary or "Action completed")[:1000]
                elif action == "undo":
                    current["acted_round"] = 0
                    current["skipped_round"] = 0
                    current["action_summary"] = ""
                elif action == "skip":
                    current["skipped_round"] = battle["round"]
                    current["acted_round"] = 0
                    current["action_summary"] = str(summary or "Turn skipped")[:1000]
                elif action in {"next", "previous"}:
                    if action == "next" and current["acted_round"] != battle["round"] and current["skipped_round"] != battle["round"]:
                        current["skipped_round"] = battle["round"]
                    order = battle["order"]
                    start = order.index(current["record_id"])
                    direction = 1 if action == "next" else -1
                    selected = ""
                    for offset in range(1, len(order) + 1):
                        index = start + direction * offset
                        if action == "next" and index >= len(order):
                            break
                        if action == "previous" and index < 0:
                            break
                        candidate = self._battle_participant_by_id(battle, order[index])
                        dead_creature = (
                            candidate["actor_type"] == "creature"
                            and str((state.get("creatures", {}).get(candidate["actor_id"], {}) or {}).get("life_state", "alive")) == "dead"
                        )
                        if dead_creature:
                            candidate["skipped_round"] = battle["round"]
                            candidate["action_summary"] = "Skipped — dead"
                            continue
                        if candidate["eligible_round"] <= battle["round"]:
                            selected = candidate["record_id"]
                            break
                    if not selected and action == "next" and order:
                        battle["round"] += 1
                        selected = next((
                            item_id for item_id in order
                            if self._battle_participant_by_id(battle, item_id)["eligible_round"] <= battle["round"]
                            and not (
                                self._battle_participant_by_id(battle, item_id)["actor_type"] == "creature"
                                and str((state.get("creatures", {}).get(
                                    self._battle_participant_by_id(battle, item_id)["actor_id"], {}
                                ) or {}).get("life_state", "alive")) == "dead"
                            )
                        ), order[0])
                    if selected:
                        battle["current_participant_id"] = selected
                else:
                    raise ValueError("Unknown battle turn action")
                state["battles"][battle_id] = battle
                result = deepcopy(battle)
            self.campaign_repository.update_game_state(campaign["record_id"], update)
            return result

    def battle_combatant_sheet(
        self, session_id: str, battle_id: str, participant_id: str,
    ) -> dict[str, Any]:
        session = self._board_context(session_id)
        campaign, world = self._campaign_document(session)
        battle = normalize_battle((campaign["game_state"].get("battles", {}) or {}).get(battle_id))
        item = self._battle_participant_by_id(battle, participant_id)
        if item["actor_type"] == "person":
            return {"actor_type": "person", "participant": deepcopy(item), "sheet": self._sheet_for_person(session_id, item["actor_id"])}
        creature = normalize_campaign_creature(
            (campaign["game_state"].get("creatures", {}) or {}).get(item["actor_id"])
        )
        species = next((
            record for record in self._database_document().get("creatures", []) or []
            if str(record.get("record_id", "")) == creature["species_record_id"]
        ), {})
        return {
            "actor_type": "creature", "participant": deepcopy(item),
            "creature": deepcopy(creature), "species": deepcopy(species),
        }

    def update_battle_combatant(
        self, session_id: str, battle_id: str, participant_id: str, action: str,
        *, wound_id: str = "", severity: str = "", text: str = "",
    ) -> dict[str, Any]:
        """Apply a non-action consequence without consuming the combatant's turn."""
        action = str(action or "").strip().casefold()
        with self._lock:
            session = self._board_context(session_id)
            campaign, _world = self._campaign_document(session)
            result: dict[str, Any] = {}

            def update(state: dict[str, Any]) -> None:
                nonlocal result
                raw_battle = state.setdefault("battles", {}).get(battle_id)
                if raw_battle is None:
                    raise KeyError("Unknown battle")
                battle = normalize_battle(raw_battle)
                entry = self._battle_participant_by_id(battle, participant_id)
                actor = (
                    state.setdefault("people", {}).setdefault(entry["actor_id"], {})
                    if entry["actor_type"] == "person"
                    else state.setdefault("creatures", {}).get(entry["actor_id"])
                )
                if actor is None:
                    raise KeyError("Unknown combatant")
                wounds = actor.setdefault("wounds", [])
                if action == "add_wound":
                    level = str(severity or "").strip().casefold()
                    if level not in {"light", "medium", "heavy"}:
                        raise ValueError("Choose a light, medium, or heavy wound")
                    item = {
                        "record_id": str(uuid4()), "severity": level,
                        "note": str(text or "").strip()[:1000],
                        "created_at": iso_utc(utc_now()),
                    }
                    wounds.append(item)
                    result = deepcopy(item)
                elif action == "edit_wound":
                    item = next((row for row in wounds if str(row.get("record_id", "")) == wound_id), None)
                    if item is None:
                        raise KeyError("Unknown wound")
                    level = str(severity or item.get("severity", "")).strip().casefold()
                    if level not in {"light", "medium", "heavy"}:
                        raise ValueError("Choose a light, medium, or heavy wound")
                    item["severity"] = level
                    item["note"] = str(text if text != "" else item.get("note", ""))[:1000]
                    result = deepcopy(item)
                elif action in {"heal_wound", "remove_wound"}:
                    before = len(wounds)
                    actor["wounds"] = [row for row in wounds if str(row.get("record_id", "")) != wound_id]
                    if len(actor["wounds"]) == before:
                        raise KeyError("Unknown wound")
                    result = {"record_id": wound_id, "removed": True}
                elif action == "add_note":
                    value = str(text or "").strip()
                    if not value:
                        raise ValueError("A battle note cannot be empty")
                    item = {
                        "record_id": str(uuid4()), "text": value[:4000],
                        "created_at": iso_utc(utc_now()),
                    }
                    note_collection = (
                        "character_notes" if entry["actor_type"] == "person"
                        else "encounter_notes"
                    )
                    actor.setdefault(note_collection, []).append(item)
                    result = deepcopy(item)
                else:
                    raise ValueError("Unknown combatant update")
                actor["last_updated"] = iso_utc(utc_now())

            self.campaign_repository.update_game_state(campaign["record_id"], update)
            return result

    def _battle_for_actor(
        self, state: dict[str, Any], actor_type: str, actor_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        for raw in (state.get("battles", {}) or {}).values():
            battle = normalize_battle(raw)
            found = next((
                item for item in battle["participants"]
                if item["actor_type"] == actor_type and item["actor_id"] == actor_id
            ), None)
            if found is not None:
                return battle, found
        return None

    def _assert_battle_action_available(
        self, state: dict[str, Any], actor_type: str, actor_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        context = self._battle_for_actor(state, actor_type, actor_id)
        if context is None:
            return None
        battle, item = context
        if battle["status"] != "active":
            return context
        if battle["current_participant_id"] != item["record_id"]:
            raise PermissionError("It is not this combatant's turn")
        if item["eligible_round"] > battle["round"]:
            raise PermissionError("This combatant becomes eligible next round")
        if item["acted_round"] == battle["round"]:
            raise PermissionError("This combatant has already used an action this round")
        if item["skipped_round"] == battle["round"]:
            raise PermissionError("This combatant's turn was skipped")
        return context

    def _commit_battle_action(
        self, campaign_id: str, actor_type: str, actor_id: str, summary: str,
    ) -> dict[str, Any] | None:
        result: dict[str, Any] | None = None

        def update(state: dict[str, Any]) -> None:
            nonlocal result
            context = self._assert_battle_action_available(state, actor_type, actor_id)
            if context is None:
                return
            battle, item = context
            if battle["status"] != "active":
                return
            item["acted_round"] = battle["round"]
            item["skipped_round"] = 0
            item["action_summary"] = str(summary or "Action completed")[:1000]
            battle["updated_at"] = iso_utc(utc_now())
            state.setdefault("battles", {})[battle["record_id"]] = battle
            result = deepcopy(battle)

        self.campaign_repository.update_game_state(campaign_id, update)
        return result

    @staticmethod
    def _roll_consumes_battle_action(roll_type: str) -> bool:
        return str(roll_type or "").strip().casefold() in {
            "spell", "proficiency", "item", "item_action", "potion",
        }

    def headmaster_roll_person_action(
        self, session_id: str, person_id: str, roll_type: str, target_id: str,
    ) -> dict[str, Any]:
        with self._lock:
            session = self._board_context(session_id)
            campaign, _world = self._campaign_document(session)
            if self._roll_consumes_battle_action(roll_type):
                self._assert_battle_action_available(
                    campaign["game_state"], "person", person_id
                )
            sheet = self._sheet_for_person(session_id, person_id)
            result = perform_character_roll(sheet, roll_type, target_id)
            if self._roll_consumes_battle_action(roll_type):
                self._commit_battle_action(
                    campaign["record_id"], "person", person_id,
                    str(result.get("text") or result.get("target_name") or "Action completed"),
                )
            return result

    def teaching_options(
        self, session_id: str, teacher_person_id: str,
    ) -> dict[str, Any]:
        """Return only subjects known by the teacher and pupils on the same map."""
        with self._lock:
            snapshot = self.board_snapshot(session_id, for_players=False)
            actors = [
                item for item in snapshot.get("actors", []) or []
                if isinstance(item, dict)
            ]
            teacher = next((
                item for item in actors
                if str(item.get("actor_id", "")) == teacher_person_id
            ), None)
            if teacher is None or not str(teacher.get("map_id", "")):
                raise ValueError("The teacher must be present on an open map")
            map_id = str(teacher["map_id"])
            pupils = sorted((
                {
                    "record_id": str(item.get("actor_id", "")),
                    "name": str(item.get("true_name") or item.get("name") or "Unknown"),
                    "map_id": map_id,
                }
                for item in actors
                if str(item.get("map_id", "")) == map_id
                and str(item.get("actor_id", "")) != teacher_person_id
            ), key=lambda item: (item["name"].casefold(), item["record_id"]))
            sheet = self._sheet_for_person(session_id, teacher_person_id)
            for pupil in pupils:
                pupil_sheet = self._sheet_for_person(
                    session_id, str(pupil["record_id"])
                )
                pupil["known"] = {
                    kind: sorted({
                        str(item.get("record_id", ""))
                        for item in pupil_sheet.get(collection, []) or []
                        if isinstance(item, dict) and item.get("record_id")
                    })
                    for kind, collection in (
                        ("spell", "spells"),
                        ("proficiency", "proficiencies"),
                        ("recipe", "recipes"),
                    )
                }
            return {
                "teacher": {
                    "record_id": teacher_person_id,
                    "name": str(teacher.get("true_name") or teacher.get("name") or "Unknown"),
                    "map_id": map_id,
                },
                "pupils": pupils,
                "spell": deepcopy(sheet.get("spells", []) or []),
                "proficiency": deepcopy(sheet.get("proficiencies", []) or []),
                "recipe": deepcopy(sheet.get("recipes", []) or []),
            }

    def _validate_teaching_action(
        self, session_id: str, teacher_person_id: str, pupil_person_id: str,
        knowledge_kind: str, knowledge_record_id: str,
    ) -> dict[str, Any]:
        options = self.teaching_options(session_id, teacher_person_id)
        if not any(item["record_id"] == pupil_person_id for item in options["pupils"]):
            raise PermissionError("The pupil must be on the same map as the teacher")
        kind = str(knowledge_kind or "").strip().casefold()
        if not any(
            str(item.get("record_id", "")) == knowledge_record_id
            for item in options.get(kind, [])
        ):
            raise PermissionError("That character does not know this subject")
        pupil = next(
            item for item in options["pupils"]
            if item["record_id"] == pupil_person_id
        )
        if knowledge_record_id in set((pupil.get("known") or {}).get(kind, [])):
            raise PermissionError("That pupil already knows this subject")
        return options

    @staticmethod
    def _teaching_event_details(
        pupil: dict[str, Any], record: dict[str, str], kind: str,
        teacher_person_id: str = "", teacher_name: str = "Headmaster",
    ) -> dict[str, Any]:
        return {
            "person_id": str(pupil["record_id"]),
            "person_ids": [str(pupil["record_id"])],
            "pupil_person_id": str(pupil["record_id"]),
            "pupil_name": str(pupil.get("displayed_name") or "Unknown pupil"),
            "teacher_person_id": str(teacher_person_id or ""),
            "teacher_name": str(teacher_name or "Headmaster"),
            "knowledge_record_id": record["record_id"],
            "knowledge_collection": record["collection"],
            "knowledge_name": record["name"],
            "knowledge_kind": kind,
            "description": f"{teacher_name or 'Headmaster'} taught {record['name']}",
            "source": "game-board",
        }

    def teach_character(
        self, session_id: str, pupil_person_id: str, knowledge_kind: str,
        knowledge_record_id: str, *, knowledge_collection: str = "",
        teacher_person_id: str = "", teacher_name: str = "Headmaster",
    ) -> dict[str, Any]:
        with self._lock:
            normalized_kind = str(knowledge_kind or "").strip().casefold()
            if not teacher_person_id:
                raise ValueError("Choose the character who is teaching")
            options = self._validate_teaching_action(
                session_id, teacher_person_id, pupil_person_id,
                normalized_kind, knowledge_record_id,
            )
            teacher_name = str(options["teacher"]["name"])
            campaign, pupil, record = self._teaching_context(
                session_id, pupil_person_id, knowledge_kind,
                knowledge_record_id, knowledge_collection,
            )
            current = str(campaign["game_state"]["current_game_datetime"])
            event_date, event_time = current.split("T", 1)
            return self.campaign_repository.add_event(
                campaign["record_id"], f"taught_{normalized_kind}", event_date,
                event_time=event_time,
                details=self._teaching_event_details(
                    pupil, record, normalized_kind, teacher_person_id, teacher_name
                ),
            )

    def submit_teaching_request(
        self, session_id: str, contact_id: str, pupil_person_id: str,
        knowledge_kind: str, knowledge_record_id: str,
        knowledge_collection: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            wrapper, session = self._active(session_id)
            teacher = self._player(session, contact_id)
            teacher_id = str(teacher.get("character_id") or "")
            if not teacher_id:
                raise PermissionError("A linked character is required to teach")
            sheet = self.character_sheet_for(session_id, contact_id)
            key = {"spell": "spells", "proficiency": "proficiencies", "recipe": "recipes"}.get(knowledge_kind)
            known = next((item for item in (sheet or {}).get(key or "", []) if str(item.get("record_id")) == knowledge_record_id), None)
            if known is None:
                raise PermissionError("That character does not know this subject")
            self._validate_teaching_action(
                session_id, teacher_id, pupil_person_id,
                knowledge_kind, knowledge_record_id,
            )
            campaign, pupil, record = self._teaching_context(
                session_id, pupil_person_id, knowledge_kind,
                knowledge_record_id, knowledge_collection,
            )
            if pupil_person_id == teacher_id:
                raise ValueError("A character cannot submit a request to teach themselves")
            details = self._teaching_event_details(
                pupil, record, knowledge_kind, teacher_id,
                str(teacher.get("character_name") or teacher.get("name") or "Player"),
            )
            details.update({
                "session_id": session_id,
                "campaign_id": campaign["record_id"],
                "submitted_by_contact_id": contact_id,
                "request_summary": f"{details['teacher_name']} wants to teach {details['pupil_name']} {record['name']}",
            })
            return self.campaign_repository.add_request(
                campaign["record_id"], "teaching", details
            )

    def _creature_interaction_context(
        self, session_id: str, actor_person_id: str, creature_id: str, action: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        action = str(action or "").strip().casefold()
        if action not in {"capture", "lure", "tame", "bond"}:
            raise ValueError("Choose Capture, Lure, Tame, or Bond")
        session = self._board_context(session_id)
        campaign, world = self._campaign_document(session)
        actor = next(
            (item for item in world.get("people", []) if str(item.get("record_id", "")) == actor_person_id),
            None,
        )
        creature = (campaign.get("game_state", {}).get("creatures", {}) or {}).get(creature_id)
        if actor is None or creature is None:
            raise KeyError("Unknown character or creature")
        if str(creature.get("life_state", "alive")) != "alive":
            raise ValueError("Only a living creature can be approached")
        actor_placement = (campaign.get("game_state", {}).get("people", {}).get(actor_person_id, {}) or {}).get("placement") or {}
        creature_placement = creature.get("placement") or {}
        if not actor_placement.get("map_id") or actor_placement.get("map_id") != creature_placement.get("map_id"):
            raise ValueError("The character and creature must be on the same map")
        database = self.shared_store.load("db.json").data
        species = next(
            (item for item in database.get("creatures", []) if str(item.get("record_id", "")) == str(creature.get("species_record_id", ""))),
            None,
        )
        if species is None:
            raise KeyError("The creature species is no longer in the database")
        rule = (species.get("interaction_rules") or {}).get(action) or {}
        if not rule.get("enabled", False):
            raise ValueError(f"This creature cannot currently be {action}d")
        sheet = build_character_sheet(actor, world, database, campaign)
        required_id = str(rule.get("required_proficiency_id", "") or "")
        known_ids = {str(item.get("record_id", "")) for item in sheet.get("proficiencies", []) or []}
        if required_id and required_id not in known_ids:
            raise PermissionError("This character lacks the required creature proficiency")
        return campaign, actor, creature, species, {**rule, "sheet": sheet}

    def submit_creature_interaction_request(
        self, session_id: str, contact_id: str, creature_id: str, action: str,
        creature_name: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            _wrapper, session = self._active(session_id)
            player = self._player(session, contact_id)
            actor_id = str(player.get("character_id", "") or "")
            if not actor_id:
                raise PermissionError("A linked character is required")
            campaign, actor, creature, _species, _rule = self._creature_interaction_context(
                session_id, actor_id, creature_id, action
            )
            action_name = str(action).strip().casefold()
            actor_name = str(actor.get("displayed_name", "") or "Character")
            details = {
                "session_id": session_id,
                "contact_id": contact_id,
                "actor_person_id": actor_id,
                "actor_name": actor_name,
                "creature_id": creature_id,
                "species_name": str(creature.get("species_name", "") or "Creature"),
                "interaction_action": action_name,
                "creature_name": str(creature_name or "").strip()[:200],
                "request_summary": f"{actor_name} wants to {action_name} {creature.get('species_name', 'a creature')}",
            }
            return self.campaign_repository.add_request(
                campaign["record_id"], "creature_interaction", details
            )

    @staticmethod
    def _apply_creature_interaction(
        target: dict[str, Any], action: str, actor_id: str,
        current: str, creature_name: str = "",
    ) -> None:
        target["relationship_state"] = {
            "capture": "captured", "lure": "lured",
            "tame": "tamed", "bond": "bonded",
        }[action]
        target["related_character_id"] = actor_id
        target.setdefault("relationship_history", []).append({
            "record_id": str(uuid4()), "action": action,
            "character_id": actor_id, "at": current,
        })
        if action == "tame":
            target["name"] = str(
                creature_name or target.get("species_name") or "Creature"
            )[:200]
            target["needs_name"] = not bool(creature_name)
        elif action == "capture":
            size = int((target.get("generated") or {}).get("size", 1) or 1)
            if size <= 2:
                target["carried_by_character_id"] = actor_id
                target["visibility"] = "headmaster"
            else:
                target["restrained"] = True

    def headmaster_creature_interaction(
        self, session_id: str, actor_person_id: str, creature_id: str,
        action: str, creature_name: str = "",
    ) -> dict[str, Any]:
        """Roll and commit a Headmaster-directed creature interaction."""

        with self._lock:
            campaign, actor, creature, _species, rule = self._creature_interaction_context(
                session_id, actor_person_id, creature_id, action
            )
            normalized_action = str(action).strip().casefold()
            roll = perform_character_roll(
                rule["sheet"], "skill", str(rule.get("skill") or "Creatures")
            )
            threshold = int(rule.get("threshold", 12) or 12)
            success = roll.get("critical") == "success" or (
                roll.get("critical") != "failure"
                and int(roll.get("total", 0)) >= threshold
            )
            current = str(campaign["game_state"]["current_game_datetime"])
            event_date, event_time = current.split("T", 1)

            def update(value: dict[str, Any]) -> None:
                if success:
                    target = value.setdefault("game_state", {}).setdefault(
                        "creatures", {}
                    ).get(creature_id)
                    if target is None:
                        raise KeyError("The creature is no longer in this campaign")
                    self._apply_creature_interaction(
                        target, normalized_action, actor_person_id, current, creature_name
                    )
                value.setdefault("events", []).append({
                    "record_id": str(uuid4()),
                    "event_type": f"creature_{normalized_action}_attempt",
                    "date": event_date, "time": event_time,
                    "person_ids": [actor_person_id], "creature_id": creature_id,
                    "interaction_action": normalized_action, "success": success,
                    "threshold": threshold, "roll": deepcopy(roll),
                })

            self.campaign_repository.update_campaign(campaign["record_id"], update)
            return {
                "activity_type": "creature_interaction", "creature_id": creature_id,
                "species_name": str(creature.get("species_name") or "Creature"),
                "actor_name": str(actor.get("displayed_name") or "Character"),
                "interaction_action": normalized_action, "threshold": threshold,
                "success": success, "roll": roll,
                "text": (
                    f"{actor.get('displayed_name', 'A character')} attempts to "
                    f"{normalized_action} {creature.get('species_name', 'a creature')} "
                    f"and {'succeeds' if success else 'fails'}."
                ),
            }

    def pending_campaign_requests(self) -> list[dict[str, Any]]:
        sessions = self.sessions_view()
        session_by_campaign = {
            str(item.get("campaign_id", "")): item for item in sessions if item.get("campaign_id")
        }
        result: list[dict[str, Any]] = []
        for campaign in self.campaign_repository.list():
            for request in campaign.get("requests", []) or []:
                if request.get("status") != "pending":
                    continue
                item = deepcopy(request)
                session = session_by_campaign.get(campaign["record_id"], {})
                item["campaign_id"] = campaign["record_id"]
                item["campaign_name"] = campaign["name"]
                item["session_id"] = str(item.get("session_id") or session.get("id") or "")
                item["session_title"] = str(session.get("title") or "")
                result.append(item)
        result.sort(key=lambda item: (str(item.get("submitted_at", "")), str(item.get("record_id", ""))))
        return result

    def resolve_campaign_request(
        self, campaign_id: str, request_id: str, decision: str,
        *, pupil_person_id: str = "", knowledge_kind: str = "",
        knowledge_record_id: str = "", knowledge_collection: str = "",
        actor_person_id: str = "", interaction_action: str = "",
        creature_name: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            campaign = self.campaign_repository.get(campaign_id)
            request = next((item for item in campaign.get("requests", []) if item.get("record_id") == request_id), None)
            if request is None:
                raise KeyError("Unknown campaign request")
            if decision == "rejected":
                return self.campaign_repository.resolve_request(campaign_id, request_id, "rejected")
            if request.get("request_type") == "equipment_change":
                person_id = str(request.get("person_id") or "")
                slot = str(request.get("slot") or "")
                item_id = str(request.get("item_id") or "")
                if slot not in {"focus", "accessory_1", "accessory_2", "flyable"}:
                    raise ValueError("The requested equipment slot is invalid")
                current = str(campaign["game_state"]["current_game_datetime"])
                event_date, event_time = current.split("T", 1)
                flight_roll: dict[str, Any] | None = None
                flight_success = True
                if slot == "flyable" and item_id:
                    session_id = str(request.get("session_id") or "")
                    contact_id = str(request.get("contact_id") or "")
                    sheet = self.character_sheet_for(session_id, contact_id) or {}
                    item = next(
                        (
                            value for value in sheet.get("inventory", []) or []
                            if str(value.get("record_id", "") or "") == item_id
                        ),
                        None,
                    )
                    if item is None or str(item.get("equipment_slot_type", "")) != "flyable":
                        raise PermissionError("That Flyable is no longer available")
                    threshold = int(item.get("flight_threshold"))
                    flight_roll = perform_character_roll(sheet, "skill", "Flying")
                    natural = int((flight_roll.get("dice") or [0])[0] or 0)
                    flight_success = (
                        natural != 1
                        and int(flight_roll.get("total", 0) or 0) >= threshold
                    )
                    critical = (
                        "failure" if natural == 1
                        else "success" if natural == 10 and flight_success
                        else ""
                    )
                    character_name = str(sheet.get("character_name") or "A character")
                    item_name = str(item.get("name") or "a flyable item")
                    flight_roll.update({
                        "action_type": "flyable",
                        "target_id": item_id,
                        "target_name": item_name,
                        "threshold": threshold,
                        "success": flight_success,
                        "critical": critical,
                        "outcome": (
                            "critical_success" if critical == "success"
                            else "critical_failure" if critical == "failure"
                            else "success" if flight_success else "failure"
                        ),
                        "text": (
                            f"{character_name} gets airborne on {item_name} "
                            f"with a Flying total of {flight_roll.get('total')} against {threshold}."
                            if flight_success else
                            f"{character_name} fails to get airborne on {item_name} "
                            f"with a Flying total of {flight_roll.get('total')} against {threshold}."
                        ),
                    })
                def equip(state: dict[str, Any]) -> None:
                    person = state.setdefault("people", {}).setdefault(person_id, {})
                    equipment = person.setdefault("equipment", {})
                    if flight_success:
                        equipment[slot] = item_id
                    if slot == "flyable" and flight_success:
                        person["airborne"] = bool(item_id)
                    for other_slot, equipped_id in list(equipment.items()):
                        if other_slot != slot and item_id and flight_success and equipped_id == item_id:
                            equipment[other_slot] = ""
                resolved = self.campaign_repository.resolve_request(
                    campaign_id, request_id, "approved",
                    event_type="equipment_changed", event_date=event_date,
                    event_time=event_time,
                    event_details={
                        "person_ids": [person_id], "slot": slot,
                        "item_id": item_id if flight_success else "",
                        "flight_roll": deepcopy(flight_roll),
                    },
                    state_updater=equip,
                )
                if flight_roll is not None:
                    resolved["roll"] = flight_roll
                    resolved["text"] = flight_roll["text"]
                return resolved
            if request.get("request_type") == "creature_interaction":
                session_id = str(request.get("session_id") or "")
                actor_id = actor_person_id or str(request.get("actor_person_id") or "")
                creature_id = str(request.get("creature_id") or "")
                action = interaction_action or str(request.get("interaction_action") or "")
                checked_campaign, actor, creature, _species, rule = self._creature_interaction_context(
                    session_id, actor_id, creature_id, action
                )
                if checked_campaign["record_id"] != campaign_id:
                    raise ValueError("The request session belongs to another campaign")
                roll = perform_character_roll(rule["sheet"], "skill", str(rule.get("skill") or "Creatures"))
                threshold = int(rule.get("threshold", 12) or 12)
                success = roll.get("critical") == "success" or (
                    roll.get("critical") != "failure" and int(roll.get("total", 0)) >= threshold
                )
                current = str(campaign["game_state"]["current_game_datetime"])
                event_date, event_time = current.split("T", 1)

                def update_state(state: dict[str, Any]) -> None:
                    target = state.setdefault("creatures", {}).get(creature_id)
                    if target is None:
                        raise KeyError("The creature is no longer in this campaign")
                    if not success:
                        return
                    self._apply_creature_interaction(
                        target, action, actor_id, current,
                        creature_name or str(request.get("creature_name") or ""),
                    )

                details = {
                    "person_ids": [actor_id], "creature_id": creature_id,
                    "interaction_action": action, "success": success,
                    "threshold": threshold, "roll": deepcopy(roll),
                }
                resolved = self.campaign_repository.resolve_request(
                    campaign_id, request_id, "approved",
                    event_type=f"creature_{action}_attempt", event_date=event_date,
                    event_time=event_time, event_details=details,
                    state_updater=update_state,
                )
                resolved["roll"] = roll
                resolved["success"] = success
                return resolved
            if request.get("request_type") != "teaching":
                raise ValueError("This request type does not yet have an approval action")
            session_id = str(request.get("session_id") or "")
            pupil_id = pupil_person_id or str(request.get("pupil_person_id") or "")
            kind = knowledge_kind or str(request.get("knowledge_kind") or "")
            if not kind:
                event_type = str(request.get("knowledge_collection") or "")
                kind = "spell" if event_type == "spells" else "proficiency" if event_type == "proficiencies" else "recipe"
            record_id = knowledge_record_id or str(request.get("knowledge_record_id") or "")
            collection = knowledge_collection or str(request.get("knowledge_collection") or "")
            checked_campaign, pupil, record = self._teaching_context(
                session_id, pupil_id, kind, record_id, collection
            )
            if checked_campaign["record_id"] != campaign_id:
                raise ValueError("The request session belongs to another campaign")
            details = self._teaching_event_details(
                pupil, record, kind,
                str(request.get("teacher_person_id") or ""),
                str(request.get("teacher_name") or "Player"),
            )
            current = str(campaign["game_state"]["current_game_datetime"])
            event_date, event_time = current.split("T", 1)
            return self.campaign_repository.resolve_request(
                campaign_id, request_id, "approved",
                event_type=f"taught_{kind}", event_date=event_date,
                event_time=event_time, event_details=details,
            )

    def _campaign_document(
        self,
        session: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        world = deepcopy(self._world_document())
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
        world["campaign_creatures"] = deepcopy(state.get("creatures", {}))
        world["campaign_creature_counters"] = deepcopy(
            state.get("creature_counters", {})
        )
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
        creatures = deepcopy(document.get("campaign_creatures", {}) or {})
        creature_counters = deepcopy(
            document.get("campaign_creature_counters", {}) or {}
        )

        def update(state: dict[str, Any]) -> None:
            state["initialized"] = True
            state["maps"] = map_states
            state["people"] = people
            state["groups"] = groups
            state["creatures"] = creatures
            state["creature_counters"] = creature_counters

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
            former_character_links: list[tuple[str, str]] = []
            for session in wrapper.get("sessions", []):
                player = next(
                    (item for item in session.get("roster", []) if item["contact_id"] == contact_id),
                    None,
                )
                if player:
                    previous_character_id = str(player.get("character_id", "") or "")
                    if previous_character_id and previous_character_id != str(character_id or ""):
                        former_character_links.append((str(session.get("id", "")), previous_character_id))
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
            for session_id, former_character_id in former_character_links:
                if session_id:
                    self.update_person_board(
                        session_id, former_character_id, {"name_revealed": True}
                    )
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
            self._world_document(),
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
            session = next(
                (
                    item for item in wrapper.get("sessions", [])
                    if item.get("id") == session_id
                ),
                None,
            )
            if session is not None:
                wrapper["sessions"] = [
                    item for item in wrapper["sessions"]
                    if item.get("id") != session_id
                ]
                self._drop_tickets_for_session(session_id)
                self.repository.save_active(wrapper)
                return self._public_session(session)

            # Ended and expired sessions live in session-summaries.json. They
            # remain visible in the Control Room and must be deletable there.
            summaries = self.repository.summaries()
            archived = next(
                (
                    item for item in summaries.get("sessions", [])
                    if item.get("id") == session_id
                ),
                None,
            )
            if archived is None:
                raise KeyError("Unknown session")
            summaries["sessions"] = [
                item for item in summaries["sessions"]
                if item.get("id") != session_id
            ]
            self._drop_tickets_for_session(session_id)
            self.repository.save_summaries(summaries)
            return self._public_session(archived)

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
                self.activate_player_character_map(
                    session["id"], player["contact_id"], str(character_id)
                )
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
            interaction_state = (
                campaign.get("game_state", {}).get("region_interactions", {}) or {}
            )
            revealed_secret_ids = {
                str(item.get("region_id", "") or "")
                for item in interaction_state.get("revealed_secrets", []) or []
                if str(item.get("region_id", "") or "")
            }
            if for_players and contact_id:
                viewer_character_id = str(
                    (viewer or {}).get("character_id", "") or ""
                )
                game_day = self._game_day(campaign)
                revealed_secret_ids.update(
                    str(item.get("region_id", "") or "")
                    for item in interaction_state.get("secret_unlocks", []) or []
                    if str(item.get("character_id", "") or "")
                    == viewer_character_id
                    and str(item.get("game_day", "") or "") == game_day
                )
            if for_players and revealed_secret_ids:
                for map_record in document.get("maps", []) or []:
                    for region in map_record.get("regions", []) or []:
                        if (
                            str(region.get("behavior_type", "") or "") == "secret"
                            and str(region.get("record_id", "") or "")
                            in revealed_secret_ids
                        ):
                            region["_secret_revealed"] = True
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
            if not for_players:
                snapshot["revealed_secret_region_ids"] = sorted(
                    revealed_secret_ids
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
                # Character sheets travel on their own private channel.  They
                # must never be rebuilt and embedded in a board update: a
                # one-pixel token move otherwise retransmits books, inventory,
                # relationships, and every known action.
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
            campaign_people = campaign.get("game_state", {}).get("people", {}) or {}
            for actor in snapshot.get("actors", []):
                person_state = campaign_people.get(str(actor.get("actor_id", "")), {})
                actor["airborne"] = bool(person_state.get("airborne", False))
                if not for_players:
                    actor["wounds"] = deepcopy(person_state.get("wounds", []) or [])
                    actor["battle"] = deepcopy(person_state.get("battle"))
                    actor["character_notes"] = deepcopy(
                        person_state.get("character_notes", []) or []
                    )
            self._append_creature_actors(
                snapshot, campaign, session,
                for_players=for_players, contact_id=contact_id,
            )
            return snapshot

    def _append_creature_actors(
        self,
        snapshot: dict[str, Any],
        campaign: dict[str, Any],
        session: dict[str, Any],
        *,
        for_players: bool,
        contact_id: str | None,
    ) -> None:
        """Add campaign-only creatures with viewer-specific identification."""

        visible_maps = {
            str(item.get("record_id", "") or "")
            for item in snapshot.get("maps", [])
        }
        known_proficiencies: set[str] = set()
        viewer_character_id = ""
        if for_players and contact_id:
            viewer = next(
                (
                    item for item in session.get("roster", [])
                    if str(item.get("contact_id", "")) == str(contact_id)
                ),
                None,
            )
            viewer_character_id = str((viewer or {}).get("character_id", "") or "")
            known_proficiencies = {
                str(item.get("record_id", "") or "")
                for item in (snapshot.get("character_sheet") or {}).get(
                    "proficiencies", []
                )
                if isinstance(item, dict)
            }
        group_by_creature: dict[str, dict[str, Any]] = {}
        try:
            creature_definitions = (
                self.shared_store.load("db.json").data.get("creatures", []) or []
            )
        except FileNotFoundError:
            # Minimal board fixtures and legacy local installations can exist
            # before the canonical catalog has been copied into place.  Their
            # person/map state remains usable; there are simply no campaign
            # creature definitions to project yet.
            creature_definitions = []
        species_by_id = {
            str(item.get("record_id", "")): item
            for item in creature_definitions
            if isinstance(item, dict)
        }
        viewer_placement = (
            campaign.get("game_state", {}).get("people", {}).get(viewer_character_id, {}) or {}
        ).get("placement") or {}
        for group in campaign.get("game_state", {}).get("groups", []) or []:
            for member in group.get("members", []) or []:
                if str(member.get("actor_type", "")) == "creature":
                    group_by_creature[str(member.get("actor_id", ""))] = group
        for raw in (
            campaign.get("game_state", {}).get("creatures", {}) or {}
        ).values():
            creature = normalize_campaign_creature(raw)
            if creature.get("carried_by_character_id"):
                continue
            placement = creature["placement"]
            if placement["map_id"] not in visible_maps:
                continue
            if for_players and creature["visibility"] != "players":
                continue
            identified = (
                not for_players
                or creature["awareness_proficiency_id"] in known_proficiencies
            )
            group = group_by_creature.get(creature["record_id"])
            group_color = str((group or {}).get("color", "#808080") or "#808080")
            # A player's styling must not disclose group membership before that
            # player can identify the species.
            viewer_color = group_color if identified else "#808080"
            actor = {
                "actor_type": "creature",
                "actor_id": creature["record_id"],
                "name": creature["species_name"] if identified else "Unknown Creature",
                "location_id": placement["location_id"],
                "floor_id": placement["floor_id"],
                "map_id": placement["map_id"],
                "x": placement["x"],
                "y": placement["y"],
                "label_offset": deepcopy(creature["label_offset"]),
                "display_mode": "dot",
                "name_revealed": True,
                "faction_revealed": False,
                "faction_name": None,
                "faction_color": viewer_color,
                "group_id": str((group or {}).get("record_id", "") or ""),
                "group_name": str((group or {}).get("name", "") or ""),
                "group_color": viewer_color,
                "is_player_character": False,
                "is_creature": True,
                "identified": identified,
                "life_state": creature["life_state"],
            }
            if not for_players:
                actor.update({
                    "species_record_id": creature["species_record_id"],
                    "true_name": creature["species_name"],
                    "internal_label": creature["internal_label"],
                    "generated": deepcopy(creature["generated"]),
                    "actions": deepcopy(creature["actions"]),
                    "wounds": deepcopy(creature["wounds"]),
                    "battle": deepcopy(creature["battle"]),
                    "visibility": creature["visibility"],
                    "harvest_pools": deepcopy(creature["harvest_pools"]),
                    "interaction_rules": deepcopy(
                        (species_by_id.get(creature["species_record_id"], {}) or {}).get(
                            "interaction_rules", {}
                        )
                    ),
                })
            elif creature["life_state"] == "dead" and viewer_character_id:
                actor["harvest_actions"] = [
                    {
                        "part_id": pool["part_id"],
                        "name": pool["name"],
                        "quantity": pool["remaining_quantity"],
                    }
                    for pool in creature["harvest_pools"]
                    if pool["remaining_quantity"] > 0
                    and not any(
                        str(attempt.get("character_id", "")) == viewer_character_id
                        and str(attempt.get("part_id", "")) == pool["part_id"]
                        for attempt in creature["harvest_attempts"]
                    )
                ]
            elif for_players and creature["life_state"] == "alive" and viewer_character_id and viewer_placement.get("map_id") == placement["map_id"]:
                rules = (species_by_id.get(creature["species_record_id"], {}).get("interaction_rules") or {})
                actor["interaction_actions"] = [
                    action for action in ("capture", "lure", "tame", "bond")
                    if (rules.get(action) or {}).get("enabled", False)
                    and (
                        not str((rules.get(action) or {}).get("required_proficiency_id", "") or "")
                        or str((rules.get(action) or {}).get("required_proficiency_id")) in known_proficiencies
                    )
                ]
            snapshot.setdefault("actors", []).append(actor)

    def creature_species(self, query: str = "", limit: int = 100) -> list[dict[str, Any]]:
        database = self.shared_store.load("db.json").data
        needle = " ".join(str(query or "").casefold().split())
        matches: list[dict[str, Any]] = []
        for species in database.get("creatures", []) or []:
            if not isinstance(species, dict) or not species.get("record_id"):
                continue
            haystack = " ".join(
                str(species.get(key, "") or "")
                for key in ("name", "creature_family", "classification", "description")
            ).casefold()
            score = 1.0 if needle and needle in haystack else (
                SequenceMatcher(None, needle, str(species.get("name", "")).casefold()).ratio()
                if needle else 0.0
            )
            if needle and score < 0.34:
                continue
            matches.append({
                "record_id": str(species["record_id"]),
                "name": str(species.get("name") or "Creature"),
                "family": str(species.get("creature_family") or ""),
                "classification": str(species.get("classification") or ""),
                "description": str(species.get("description") or ""),
                "attacks": len(species.get("attacks", []) or []),
                "abilities": len(species.get("abilities", []) or []),
                "parts": len(species.get("parts", []) or []),
                "_search_score": score,
            })
        matches.sort(key=lambda item: (-float(item["_search_score"]), item["name"].casefold()))
        result = matches[: max(1, min(500, int(limit)))]
        for item in result:
            item.pop("_search_score", None)
        return result

    def _species_record(self, species_id: str) -> dict[str, Any]:
        record = next(
            (
                item for item in self.shared_store.load("db.json").data.get(
                    "creatures", []
                )
                if str(item.get("record_id", "")) == str(species_id)
            ),
            None,
        )
        if record is None:
            raise KeyError("Unknown creature species")
        return record

    @staticmethod
    def _nudge_creature_point(
        x: float, y: float, occupied: list[tuple[float, float]]
    ) -> tuple[float, float]:
        x, y = max(0.0, min(1.0, float(x))), max(0.0, min(1.0, float(y)))
        if all(math.hypot(x - ox, y - oy) >= 0.018 for ox, oy in occupied):
            return x, y
        for ring in range(1, 10):
            radius = 0.012 * ring
            for step in range(8 * ring):
                angle = (math.tau * step) / (8 * ring)
                candidate = (
                    max(0.0, min(1.0, x + math.cos(angle) * radius)),
                    max(0.0, min(1.0, y + math.sin(angle) * radius)),
                )
                if all(
                    math.hypot(candidate[0] - ox, candidate[1] - oy) >= 0.018
                    for ox, oy in occupied
                ):
                    return candidate
        return x, y

    def place_campaign_creature(
        self, session_id: str, species_id: str, map_id: str, x: float, y: float
    ) -> dict[str, Any]:
        with self._lock:
            session = self._board_context(session_id)
            campaign, document = self._campaign_document(session)
            map_record = self._campaign_map(document, map_id)
            species = self._species_record(species_id)
            creatures = document.setdefault("campaign_creatures", {})
            occupied = [
                (float(item["placement"]["x"]), float(item["placement"]["y"]))
                for item in creatures.values()
                if item.get("placement", {}).get("map_id") == map_id
            ]
            for person in document.get("people", []) or []:
                placement = normalize_person_board(person.get("board")).get("placement")
                if placement and placement.get("map_id") == map_id:
                    occupied.append((float(placement["x"]), float(placement["y"])))
            px, py = self._nudge_creature_point(x, y, occupied)
            counters = document.setdefault("campaign_creature_counters", {})
            counter = int(counters.get(species_id, 0) or 0) + 1
            counters[species_id] = counter
            creature = generate_creature_instance(species, counter, {
                "location_id": str(map_record.get("location_id", "")),
                "floor_id": str(map_record.get("floor_id", "") or ""),
                "map_id": map_id, "x": px, "y": py,
            })
            creatures[creature["record_id"]] = creature
            self._persist_campaign_document(campaign["record_id"], document)
            return deepcopy(creature)

    def update_campaign_creature(
        self,
        session_id: str,
        creature_id: str,
        *,
        x: float | None = None,
        y: float | None = None,
        map_id: str | None = None,
        label_x: float | None = None,
        label_y: float | None = None,
        visibility: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            session = self._board_context(session_id)
            campaign, document = self._campaign_document(session)
            raw = document.setdefault("campaign_creatures", {}).get(creature_id)
            if raw is None:
                raise KeyError("Unknown campaign creature")
            creature = normalize_campaign_creature(raw)
            if map_id is not None:
                target = self._campaign_map(document, map_id)
                previous_location_id = creature["placement"]["location_id"]
                creature["placement"].update({
                    "map_id": map_id,
                    "location_id": str(target.get("location_id", "")),
                    "floor_id": str(target.get("floor_id", "") or ""),
                })
                if creature["placement"]["location_id"] != previous_location_id:
                    self._remove_actor_from_groups(document, "creature", creature_id)
            if x is not None:
                creature["placement"]["x"] = max(0.0, min(1.0, float(x)))
            if y is not None:
                creature["placement"]["y"] = max(0.0, min(1.0, float(y)))
            if label_x is not None:
                creature["label_offset"]["x"] = max(-1.0, min(1.0, float(label_x)))
            if label_y is not None:
                creature["label_offset"]["y"] = max(-1.0, min(1.0, float(label_y)))
            if visibility is not None:
                if visibility not in {"headmaster", "players"}:
                    raise ValueError("Visibility must be headmaster or players")
                creature["visibility"] = visibility
            creature["last_updated"] = creature_utc_now()
            document["campaign_creatures"][creature_id] = normalize_campaign_creature(creature)
            self._persist_campaign_document(campaign["record_id"], document)
            return deepcopy(creature)

    @staticmethod
    def _remove_actor_from_groups(
        document: dict[str, Any], actor_type: str, actor_id: str
    ) -> None:
        groups = []
        for group in document.get("board_groups", []) or []:
            members = [
                member for member in group.get("members", []) or []
                if not (
                    str(member.get("actor_type", "")) == actor_type
                    and str(member.get("actor_id", "")) == actor_id
                )
            ]
            if len(members) >= 2:
                updated = deepcopy(group)
                updated["members"] = members
                groups.append(updated)
        document["board_groups"] = groups

    def set_campaign_creature_group(
        self, session_id: str, creature_id: str, group_id: str | None
    ) -> dict[str, Any] | None:
        with self._lock:
            session = self._board_context(session_id)
            campaign, document = self._campaign_document(session)
            creature = document.setdefault("campaign_creatures", {}).get(creature_id)
            if creature is None:
                raise KeyError("Unknown campaign creature")
            placement = normalize_campaign_creature(creature)["placement"]
            target = next(
                (
                    item for item in document.get("board_groups", []) or []
                    if str(item.get("record_id", "")) == str(group_id or "")
                ),
                None,
            ) if group_id else None
            if group_id and target is None:
                raise KeyError("Unknown board group")
            if target and str(target.get("location_id", "")) != placement["location_id"]:
                raise ValueError("A creature can only join a group at the same location")
            for group in document.get("board_groups", []) or []:
                group["members"] = [
                    member for member in group.get("members", []) or []
                    if not (
                        str(member.get("actor_type", "")) == "creature"
                        and str(member.get("actor_id", "")) == creature_id
                    )
                ]
            if target is not None:
                target.setdefault("members", []).append({
                    "record_id": str(uuid4()),
                    "actor_type": "creature",
                    "actor_id": creature_id,
                })
                target["last_updated"] = iso_utc(utc_now())
            document["board_groups"] = [
                group for group in document.get("board_groups", []) or []
                if len(group.get("members", []) or []) >= 2
            ]
            self._persist_campaign_document(campaign["record_id"], document)
            return deepcopy(target) if target in document["board_groups"] else None

    def creature_campaign_action(
        self,
        session_id: str,
        creature_id: str,
        action: str,
        *,
        severity: str = "",
        note: str = "",
        battle_name: str = "",
    ) -> dict[str, Any] | None:
        with self._lock:
            session = self._board_context(session_id)
            campaign, document = self._campaign_document(session)
            creatures = document.setdefault("campaign_creatures", {})
            raw = creatures.get(creature_id)
            if raw is None:
                raise KeyError("Unknown campaign creature")
            creature = normalize_campaign_creature(raw)
            normalized_action = str(action or "").strip().casefold()
            if normalized_action == "wound":
                level = str(severity or "").strip().casefold()
                if level not in {"light", "medium", "heavy"}:
                    raise ValueError("Wounds must be light, medium, or heavy")
                creature["wounds"].append({
                    "record_id": str(uuid4()), "severity": level,
                    "note": str(note or "")[:1000], "created_at": creature_utc_now(),
                })
                if level == "heavy" and sum(
                    item["severity"] == "heavy" for item in creature["wounds"]
                ) >= int(creature["generated"]["heavy_wound_cap"]):
                    creature["life_state"] = "dead"
                    creature["died_at"] = creature_utc_now()
            elif normalized_action == "kill":
                creature["life_state"] = "dead"
                creature["death_override"] = True
                creature["died_at"] = creature_utc_now()
            elif normalized_action == "revive":
                creature["life_state"] = "alive"
                creature["death_override"] = False
                creature["died_at"] = None
            elif normalized_action == "enter_battle":
                creature["battle"] = {
                    "active": True, "name": str(battle_name or "Battle")[:200],
                    "entered_at": creature_utc_now(),
                }
            elif normalized_action == "leave_battle":
                creature["battle"] = None
            elif normalized_action == "reroll":
                if creature["life_state"] != "alive" or creature["wounds"]:
                    raise ValueError("Only an alive, unwounded creature can be rerolled")
                replacement = generate_creature_instance(
                    self._species_record(creature["species_record_id"]),
                    creature["counter"], deepcopy(creature["placement"]),
                )
                for key in (
                    "record_id", "internal_label", "label_offset", "visibility",
                    "battle", "created_at",
                ):
                    replacement[key] = deepcopy(creature[key])
                creature = replacement
            elif normalized_action == "delete":
                del creatures[creature_id]
                self._remove_actor_from_groups(document, "creature", creature_id)
                self._persist_campaign_document(campaign["record_id"], document)
                return None
            else:
                raise ValueError("Unknown creature action")
            if creature["life_state"] == "dead" and not creature["harvest_pools"]:
                del creatures[creature_id]
                self._remove_actor_from_groups(document, "creature", creature_id)
                self._persist_campaign_document(campaign["record_id"], document)
                return None
            creature["last_updated"] = creature_utc_now()
            creatures[creature_id] = normalize_campaign_creature(creature)
            self._persist_campaign_document(campaign["record_id"], document)
            return deepcopy(creature)

    def roll_campaign_creature_action(
        self, session_id: str, creature_id: str, action_id: str
    ) -> dict[str, Any]:
        with self._lock:
            session = self._board_context(session_id)
            campaign, _document = self._campaign_document(session)
            creature = campaign.get("game_state", {}).get("creatures", {}).get(creature_id)
            if creature is None:
                raise KeyError("Unknown campaign creature")
            self._assert_battle_action_available(
                campaign["game_state"], "creature", creature_id
            )
            result = roll_creature_action(creature, action_id)
            result["awareness_proficiency_id"] = str(
                creature.get("awareness_proficiency_id", "")
            )
            self._commit_battle_action(
                campaign["record_id"], "creature", creature_id,
                str(result.get("text") or result.get("name") or "Creature action"),
            )
            return result

    def harvest_campaign_creature(
        self, session_id: str, contact_id: str, creature_id: str, part_id: str
    ) -> dict[str, Any]:
        """Atomically attempt one character's one allowed claim on a corpse part."""

        with self._lock:
            session = self._board_context(session_id)
            player = self._player(session, contact_id)
            character_id = str(player.get("character_id", "") or "")
            if not character_id:
                raise PermissionError("This player has no linked character")
            campaign, document = self._campaign_document(session)
            creatures = document.setdefault("campaign_creatures", {})
            raw = creatures.get(creature_id)
            if raw is None:
                raise KeyError("Unknown campaign creature")
            creature = normalize_campaign_creature(raw)
            if creature["life_state"] != "dead" or creature["visibility"] != "players":
                raise PermissionError("That creature cannot be harvested")
            person = next(
                (
                    item for item in document.get("people", []) or []
                    if str(item.get("record_id", "")) == character_id
                ),
                None,
            )
            if person is None:
                raise PermissionError("The linked character no longer exists")
            person_placement = normalize_person_board(person.get("board")).get("placement")
            if not person_placement or person_placement.get("map_id") != creature["placement"]["map_id"]:
                raise PermissionError("The character and corpse must be on the same map")
            pool = next(
                (item for item in creature["harvest_pools"] if item["part_id"] == part_id),
                None,
            )
            if pool is None or int(pool["remaining_quantity"]) <= 0:
                raise ValueError("That part is no longer available")
            if any(
                str(item.get("character_id", "")) == character_id
                and str(item.get("part_id", "")) == part_id
                for item in creature["harvest_attempts"]
            ):
                raise PermissionError("This character already attempted that part")
            sheet = build_character_sheet(
                person, document, self.shared_store.load("db.json").data, campaign
            )
            known = {
                str(item.get("record_id", "")): item
                for item in sheet.get("proficiencies", []) or []
                if isinstance(item, dict)
            }
            awareness_id = creature["awareness_proficiency_id"]
            if awareness_id not in known:
                raise PermissionError("Creature awareness is required to harvest this corpse")
            proficiency_id = str(pool.get("required_proficiency_id") or awareness_id)
            if proficiency_id not in known:
                raise PermissionError("A specialized proficiency is required for that part")
            roll = perform_character_roll(sheet, "proficiency", proficiency_id)
            outcome = str(roll.get("outcome", "") or "")
            attempt = {
                "character_id": character_id,
                "part_id": part_id,
                "attempted_at": creature_utc_now(),
                "outcome": outcome,
                "roll": deepcopy(roll),
            }
            creature["harvest_attempts"].append(attempt)
            awarded = 0
            if outcome in {"success", "critical_success"}:
                awarded = int(pool["remaining_quantity"])
                pool["remaining_quantity"] = 0
                pool["status"] = "claimed"
                existing_people = campaign["game_state"].get("people", {}) or {}
                person_state = existing_people.get(character_id, {})
                inventory = deepcopy(person_state.get("campaign_inventory", []) or [])
                inventory.append({
                    "record_id": str(uuid4()),
                    "item_id": part_id,
                    "part_id": part_id,
                    "name": str(pool.get("name") or "Creature part"),
                    "category": "Creature Part",
                    "quantity": awarded,
                    "source_creature_id": creature_id,
                    "source_species_id": creature["species_record_id"],
                    "acquired_at": creature_utc_now(),
                })
                person["board"] = normalize_person_board(person.get("board"))
                override = document.setdefault("_campaign_person_inventory", {})
                override[character_id] = inventory
            elif outcome == "critical_failure":
                pool["remaining_quantity"] = 0
                pool["status"] = "destroyed"
            creature["last_updated"] = creature_utc_now()
            removed = all(
                int(item.get("remaining_quantity", 0)) <= 0
                for item in creature["harvest_pools"]
            )
            if removed:
                del creatures[creature_id]
                self._remove_actor_from_groups(document, "creature", creature_id)
            else:
                creatures[creature_id] = normalize_campaign_creature(creature)

            campaign_id = campaign["record_id"]
            inventory_override = document.pop("_campaign_person_inventory", {})
            self._persist_campaign_document(campaign_id, document)
            if inventory_override:
                def save_inventory(state: dict[str, Any]) -> None:
                    for person_id, stacks in inventory_override.items():
                        state.setdefault("people", {}).setdefault(
                            person_id, {}
                        )["campaign_inventory"] = stacks
                self.campaign_repository.update_game_state(campaign_id, save_inventory)
            return {
                "activity_type": "creature_harvest",
                "creature_id": creature_id,
                "species_name": creature["species_name"],
                "awareness_proficiency_id": creature["awareness_proficiency_id"],
                "part_id": part_id,
                "part_name": str(pool.get("name") or "Creature part"),
                "quantity_awarded": awarded,
                "outcome": outcome,
                "roll": roll,
                "corpse_removed": removed,
                "text": (
                    f"{sheet.get('name', 'A character')} harvested {awarded} "
                    f"{pool.get('name', 'creature part')}."
                    if awarded else
                    f"{sheet.get('name', 'A character')} failed to harvest "
                    f"{pool.get('name', 'creature part')}."
                ),
            }

    def character_attributes_for(
        self,
        session_id: str,
        contact_id: str,
    ) -> dict[str, Any] | None:
        """Return the linked World Builder character sheet for one player."""

        # The full private sheet is sent immediately after connection. Build it
        # once here and let the bootstrap reuse the revision-keyed cache instead
        # of performing the same expensive calculation twice.
        sheet = self.character_sheet_for(session_id, contact_id)
        return deepcopy(sheet.get("attributes", {})) if sheet else None

    def character_sheet_for(
        self,
        session_id: str,
        contact_id: str,
    ) -> dict[str, Any] | None:
        """Return only one admitted player's authorized, effective sheet."""

        with self._lock:
            session = self._board_context(session_id)
            try:
                cache_key = (
                    session_id,
                    contact_id,
                    self.world_fingerprint(),
                    self.shared_store.fingerprint("db.json"),
                    self.campaign_repository.store.fingerprint("campaign.json"),
                )
            except OSError:
                cache_key = ()
            if cache_key and cache_key in self._character_sheet_cache:
                return self._character_sheet_cache[cache_key]
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
                database = self._database_document()
            except FileNotFoundError:
                # Small integration fixtures may exercise board-only behavior
                # without a rules catalog. Production always has db.json.
                database = {
                    "schools": [], "spells": [], "proficiencies": [],
                    "potions": [], "preparations": [],
                    "foods_and_drinks": [], "creatures": [], "books": [],
                }
            sheet = build_character_sheet(person, document, database, campaign)
            # Nearby pupils are expensive and relevant only after the player
            # opens Teach. They are requested lazily over the live connection.
            sheet["teaching_targets"] = []
            if cache_key:
                if len(self._character_sheet_cache) >= 32:
                    self._character_sheet_cache.clear()
                self._character_sheet_cache[cache_key] = sheet
            return sheet

    @staticmethod
    def _catalog_record(
        database: dict[str, Any], reference: dict[str, Any]
    ) -> dict[str, Any]:
        collection = str(reference.get("collection", "") or "")
        record_id = str(reference.get("record_id", "") or "")
        if collection in {"creature_parts", "plant_parts"}:
            parents = "creatures" if collection == "creature_parts" else "plants"
            parent_id = str(reference.get("parent_record_id", "") or "")
            parent = next(
                (item for item in database.get(parents, []) or []
                 if str(item.get("record_id", "")) == parent_id), None
            )
            record = next(
                (item for item in (parent or {}).get("parts", []) or []
                 if str(item.get("record_id", "")) == record_id), None
            )
        else:
            record = next(
                (item for item in database.get(collection, []) or []
                 if str(item.get("record_id", "")) == record_id), None
            )
        if record is None:
            raise KeyError("A region references a missing catalog record")
        return record

    def _region_player_context(
        self, session_id: str, contact_id: str, map_id: str, region_id: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        _wrapper, session = self._active(session_id)
        player = self._player(session, contact_id)
        character_id = str(player.get("character_id", "") or "")
        if not character_id:
            raise PermissionError("This player is not linked to a character")
        campaign, document = self._campaign_document(session)
        person = next(
            (item for item in document.get("people", []) or []
             if str(item.get("record_id", "")) == character_id), None
        )
        if person is None:
            raise PermissionError("The linked character no longer exists")
        placement = normalize_person_board(person.get("board")).get("placement") or {}
        if str(placement.get("map_id", "") or "") != str(map_id):
            raise PermissionError("The character must occupy the same map")
        map_record = self._campaign_map(document, map_id)
        region = next(
            (item for item in map_record.get("regions", []) or []
             if str(item.get("record_id", "")) == str(region_id)), None
        )
        if region is None:
            raise KeyError("Unknown region")
        globally_or_personally_revealed = (
            str(region.get("behavior_type", "") or "") == "secret"
            and self._secret_is_revealed(
                campaign,
                str(region.get("record_id", "") or ""),
                str(person.get("record_id", "") or ""),
            )
        )
        if not bool(region.get("players_visible", True)) and not globally_or_personally_revealed:
            raise KeyError("Unknown region")
        return session, campaign, document, person, region

    @staticmethod
    def _raw_skill(sheet: dict[str, Any], skill_name: str) -> int:
        needle = str(skill_name or "").strip().casefold()
        skill = next(
            (item for item in (sheet.get("attributes") or {}).get("skills", []) or []
             if str(item.get("name", "")).strip().casefold() == needle), None
        )
        if skill is None:
            return 0
        return int(skill.get("total", skill.get("value", 0)) or 0)

    @staticmethod
    def _game_day(campaign: dict[str, Any]) -> str:
        return str(campaign["game_state"]["current_game_datetime"]).split("T", 1)[0]

    @classmethod
    def _secret_is_revealed(
        cls,
        campaign: dict[str, Any],
        region_id: str,
        character_id: str,
    ) -> bool:
        interactions = (
            campaign.get("game_state", {}).get("region_interactions", {}) or {}
        )
        if any(
            str(item.get("region_id", "") or "") == region_id
            for item in interactions.get("revealed_secrets", []) or []
        ):
            return True
        day = cls._game_day(campaign)
        return any(
            str(item.get("character_id", "") or "") == character_id
            and str(item.get("region_id", "") or "") == region_id
            and str(item.get("game_day", "") or "") == day
            for item in interactions.get("secret_unlocks", []) or []
        )

    def region_interaction_snapshot(
        self, session_id: str, contact_id: str, map_id: str, region_id: str
    ) -> dict[str, Any]:
        with self._lock:
            _session, campaign, _document, person, region = self._region_player_context(
                session_id, contact_id, map_id, region_id
            )
            behavior = str(region.get("behavior_type", "area") or "area")
            character_id = str(person["record_id"])
            day = self._game_day(campaign)
            state = campaign["game_state"].get("region_interactions", {}) or {}
            unlocked = self._secret_is_revealed(
                campaign, region_id, character_id
            )
            attempted_region = any(
                str(item.get("character_id")) == character_id
                and str(item.get("region_id")) == region_id
                and str(item.get("game_day")) == day
                and str(item.get("mode_id")) != "__gate__"
                for item in state.get("attempts", []) or []
            )
            attempted_mode_ids = {
                str(item.get("mode_id", ""))
                for item in state.get("attempts", []) or []
                if str(item.get("character_id", "")) == character_id
                and str(item.get("region_id", "")) == region_id
                and str(item.get("game_day", "")) == day
            }
            if behavior == "secret" and not unlocked:
                return {
                    "kind": "secret", "map_id": map_id, "region_id": region_id,
                    "title": "Search", "unlocked": False,
                    "gate_already_attempted": "__gate__" in attempted_mode_ids,
                }
            if behavior in {"secret", "library", "storeroom"}:
                database = self.shared_store.load("db.json").data
                return {
                    "kind": "search", "map_id": map_id, "region_id": region_id,
                    "title": str(region.get("name") or "Search"), "unlocked": True,
                    "modes": [
                        {
                            "record_id": str(mode["record_id"]),
                            "name": str(mode["name"]),
                            "skill": str(mode["skill"]),
                            "extraction_methods": self._extraction_methods_for_mode(
                                region, mode, database
                            ),
                            "attempted_today": attempted_region or str(mode["record_id"]) in attempted_mode_ids,
                        }
                        for mode in region.get("search_modes", []) or []
                    ],
                }
            if behavior == "shop":
                return self._shop_snapshot(campaign, region, person, map_id)
            raise ValueError("This region has no player interaction")

    @staticmethod
    def _contact_id_for_character(
        session: dict[str, Any], person_id: str
    ) -> str:
        player = next(
            (
                item for item in session.get("roster", []) or []
                if str(item.get("character_id", "") or "") == str(person_id)
            ),
            None,
        )
        if player is None:
            raise PermissionError(
                "This character is not linked to a player in this session"
            )
        return str(player.get("contact_id", "") or "")

    def admin_region_search_options(
        self, session_id: str, person_id: str
    ) -> dict[str, Any]:
        """Return searchable same-map regions for a session-linked character."""

        with self._lock:
            _wrapper, session = self._active(session_id)
            contact_id = self._contact_id_for_character(session, person_id)
            _campaign, document = self._campaign_document(session)
            person = next(
                (
                    item for item in document.get("people", []) or []
                    if str(item.get("record_id", "") or "") == str(person_id)
                ),
                None,
            )
            if person is None:
                raise KeyError("Unknown character")
            placement = normalize_person_board(person.get("board")).get("placement") or {}
            map_id = str(placement.get("map_id", "") or "")
            if not map_id:
                raise ValueError("This character is not currently on a map")
            map_record = self._campaign_map(document, map_id)
            regions: list[dict[str, Any]] = []
            for region in map_record.get("regions", []) or []:
                if str(region.get("behavior_type", "") or "") not in {
                    "secret", "library", "storeroom",
                }:
                    continue
                snapshot = self.region_interaction_snapshot(
                    session_id,
                    contact_id,
                    map_id,
                    str(region.get("record_id", "") or ""),
                )
                if snapshot.get("kind") == "search":
                    regions.append(snapshot)
            return {
                "person_id": str(person_id),
                "person_name": str(person.get("name") or "Character"),
                "map_id": map_id,
                "map_name": str(map_record.get("name") or "Current map"),
                "regions": regions,
            }

    def admin_search_region(
        self,
        session_id: str,
        person_id: str,
        map_id: str,
        region_id: str,
        mode_id: str,
        extraction_method_id: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            _wrapper, session = self._active(session_id)
            contact_id = self._contact_id_for_character(session, person_id)
        return self.search_region(
            session_id,
            contact_id,
            map_id,
            region_id,
            mode_id,
            extraction_method_id,
        )

    def attempt_secret_gate(
        self, session_id: str, contact_id: str, map_id: str, region_id: str
    ) -> dict[str, Any]:
        with self._lock:
            _session, campaign, _document, person, region = self._region_player_context(
                session_id, contact_id, map_id, region_id
            )
            if str(region.get("behavior_type")) != "secret":
                raise ValueError("That region is not a Secret")
            character_id = str(person["record_id"])
            day = self._game_day(campaign)
            ledger = campaign["game_state"].get("region_interactions", {}) or {}
            if any(
                str(item.get("character_id")) == character_id
                and str(item.get("region_id")) == region_id
                and str(item.get("mode_id")) == "__gate__"
                and str(item.get("game_day")) == day
                for item in ledger.get("attempts", []) or []
            ):
                raise ValueError("This Secret cannot be searched again until the next game day")
            sheet = self.character_sheet_for(session_id, contact_id) or {}
            skill = str(region.get("secret_skill", "") or "")
            skill_value = self._raw_skill(sheet, skill)
            die = random.SystemRandom().randint(1, 10)
            total = die + skill_value
            success = total >= int(region.get("secret_threshold", 0) or 0)

            def update(state: dict[str, Any]) -> None:
                interactions = state.setdefault("region_interactions", {})
                interactions.setdefault("attempts", []).append({
                    "record_id": str(uuid4()), "character_id": character_id,
                    "map_id": map_id, "region_id": region_id, "mode_id": "__gate__",
                    "game_day": day, "natural_roll": die,
                    "skill_value": skill_value, "total": total, "created_at": iso_utc(utc_now()),
                })
                if success:
                    interactions.setdefault("secret_unlocks", []).append({
                        "record_id": str(uuid4()), "character_id": character_id,
                        "map_id": map_id, "region_id": region_id, "game_day": day,
                        "created_at": iso_utc(utc_now()),
                    })

            self.campaign_repository.update_game_state(campaign["record_id"], update)
            name = str(sheet.get("character_name") or person.get("displayed_name") or "A player")
            return {
                "kind": "secret_gate_result", "success": success, "natural_roll": die,
                "skill": skill, "skill_value": skill_value, "total": total,
                "text": (
                    f"{name} searches for a secret with {skill}: {die} + {skill_value} = {total}. "
                    + ("Something hidden is revealed." if success else "They find nothing today.")
                ),
            }

    def _competency_entries(
        self, region: dict[str, Any], mode: dict[str, Any], sheet: dict[str, Any],
        database: dict[str, Any], extraction_method_id: str = ""
    ) -> list[dict[str, Any]]:
        known_proficiencies = {
            str(item.get("record_id", "")) for item in sheet.get("proficiencies", []) or []
        }
        known_recipe_records = [
            item for item in sheet.get("recipes", []) or [] if isinstance(item, dict)
        ]
        known_recipes = {str(item.get("record_id", "")) for item in known_recipe_records}
        known_ingredient_names = {
            str(ingredient.get("name", "") or "").strip().casefold()
            for recipe in known_recipe_records
            for ingredient in recipe.get("ingredients", []) or []
            if isinstance(ingredient, dict) and str(ingredient.get("name", "") or "").strip()
        }
        known_ingredient_names.update({
            str(alternative.get("name", "") or "").strip().casefold()
            for recipe in known_recipe_records
            for group in recipe.get("ingredient_requirements", []) or []
            if isinstance(group, dict)
            for alternative in group.get("alternatives", []) or []
            if isinstance(alternative, dict)
            and str(alternative.get("name", "") or "").strip()
        })
        result: list[dict[str, Any]] = []
        for entry in region.get("contents", []) or []:
            if str(mode.get("record_id")) not in {
                str(value) for value in entry.get("search_mode_ids", []) or []
            }:
                continue
            try:
                reference = entry.get("reference", {})
                record = self._catalog_record(database, reference)
            except KeyError:
                continue
            methods = {
                str(value)
                for value in record.get("gathering_method_ids", []) or []
            }
            is_raw_material = (
                str(reference.get("collection", "")) == "raw_materials"
                or (
                    str(reference.get("collection", "")) == "general_items"
                    and str(record.get("type", "")) == "Raw Material"
                )
            )
            if is_raw_material:
                item_extraction_method = str(
                    record.get("searching_method_id", "") or ""
                )
                if not item_extraction_method and len(methods) == 1:
                    item_extraction_method = next(iter(methods))
                if (
                    not extraction_method_id
                    or item_extraction_method != extraction_method_id
                ):
                    continue
            elif methods and str(mode.get("gathering_method_id")) not in methods:
                continue
            required = {
                str(value.get("record_id") if isinstance(value, dict) else value)
                for value in record.get("required_proficiencies", []) or []
            }
            specialized = str(record.get("required_proficiency_id", "") or "")
            if specialized:
                required.add(specialized)
            collection = str(reference.get("collection", "") or "")
            if collection in {"creatures", "creature_parts"}:
                if collection == "creatures":
                    creature = record
                else:
                    parent_id = str(reference.get("parent_record_id", "") or "")
                    creature = next(
                        (item for item in database.get("creatures", []) or []
                         if str(item.get("record_id", "")) == parent_id), {}
                    )
                awareness_id = str(creature.get("awareness_proficiency_id", "") or "")
                if awareness_id:
                    required.add(awareness_id)
            required.discard("")
            if not required.issubset(known_proficiencies):
                continue
            skill_name = str(mode.get("skill", "") or "").casefold()
            recipe_ids = {
                str(value.get("record_id") if isinstance(value, dict) else value)
                for value in record.get("recipe_ids", []) or []
            }
            if skill_name in {"potions", "artificing"}:
                explicitly_known = bool(recipe_ids.intersection(known_recipes))
                name_is_known_ingredient = (
                    str(record.get("name") or record.get("title") or "")
                    .strip().casefold() in known_ingredient_names
                )
                if not explicitly_known and not name_is_known_ingredient:
                    continue
            enriched = deepcopy(entry)
            enriched["catalog"] = record
            result.append(enriched)
        return result

    def _extraction_methods_for_mode(
        self,
        region: dict[str, Any],
        mode: dict[str, Any],
        database: dict[str, Any],
    ) -> list[dict[str, str]]:
        method_ids: set[str] = set()
        mode_id = str(mode.get("record_id", "") or "")
        for entry in region.get("contents", []) or []:
            if mode_id not in {
                str(value)
                for value in entry.get("search_mode_ids", []) or []
            }:
                continue
            reference = entry.get("reference", {}) or {}
            try:
                record = self._catalog_record(database, reference)
            except KeyError:
                continue
            if not (
                str(reference.get("collection", "")) == "raw_materials"
                or (
                    str(reference.get("collection", "")) == "general_items"
                    and str(record.get("type", "")) == "Raw Material"
                )
            ):
                continue
            extraction_method_id = str(
                record.get("searching_method_id", "") or ""
            )
            legacy_methods = {
                str(value)
                for value in record.get("gathering_method_ids", []) or []
                if str(value)
            }
            if not extraction_method_id and len(legacy_methods) == 1:
                extraction_method_id = next(iter(legacy_methods))
            if extraction_method_id:
                method_ids.add(extraction_method_id)
        methods_by_id = {
            str(record.get("record_id", "")): record
            for record in database.get("gathering_methods", []) or []
        }
        return [
            {
                "record_id": method_id,
                "name": str(
                    methods_by_id.get(method_id, {}).get("name")
                    or method_id
                ),
            }
            for method_id in sorted(
                method_ids,
                key=lambda value: str(
                    methods_by_id.get(value, {}).get("name") or value
                ).casefold(),
            )
        ]

    @staticmethod
    def _inventory_add(
        person_state: dict[str, Any], reference: dict[str, Any], record: dict[str, Any],
        quantity: int, *, source: str
    ) -> None:
        stacks = person_state.setdefault("campaign_inventory", [])
        collection = str(reference.get("collection", "") or "")
        record_id = str(reference.get("record_id", "") or "")
        stack = next(
            (item for item in stacks
             if str(item.get("definition_collection", "")) == collection
             and str(item.get("definition_record_id", "")) == record_id), None
        )
        if stack is not None:
            stack["quantity"] = int(stack.get("quantity", 0) or 0) + int(quantity)
            return
        stacks.append({
            "record_id": str(uuid4()), "item_id": record_id,
            "part_id": record_id if collection.endswith("_parts") else "",
            "name": str(record.get("name") or record.get("title") or "Found item"),
            "category": collection.replace("_", " ").title(), "quantity": int(quantity),
            "source_creature_id": "", "source_species_id": "",
            "acquired_at": iso_utc(utc_now()), "definition_collection": collection,
            "definition_record_id": record_id,
            "description": str(record.get("description", "") or "")[:4000],
            "method": source,
        })

    def search_region(
        self, session_id: str, contact_id: str, map_id: str, region_id: str,
        mode_id: str, extraction_method_id: str = ""
    ) -> dict[str, Any]:
        with self._lock:
            _session, campaign, document, person, region = self._region_player_context(
                session_id, contact_id, map_id, region_id
            )
            behavior = str(region.get("behavior_type", "") or "")
            if behavior not in {"secret", "library", "storeroom"}:
                raise ValueError("That region cannot be searched")
            character_id = str(person["record_id"])
            day = self._game_day(campaign)
            interaction_state = campaign["game_state"].get("region_interactions", {}) or {}
            if behavior == "secret" and not self._secret_is_revealed(
                campaign, region_id, character_id
            ):
                raise PermissionError("This Secret has not been found today")
            if any(
                str(item.get("character_id")) == character_id
                and str(item.get("region_id")) == region_id
                and str(item.get("mode_id")) != "__gate__"
                and str(item.get("game_day")) == day
                for item in interaction_state.get("attempts", []) or []
            ):
                raise ValueError("This region was already searched today")
            mode = next(
                (item for item in region.get("search_modes", []) or []
                 if str(item.get("record_id")) == mode_id), None
            )
            if mode is None:
                raise KeyError("Unknown search mode")
            sheet = self.character_sheet_for(session_id, contact_id) or {}
            database = self.shared_store.load("db.json").data
            extraction_methods = self._extraction_methods_for_mode(
                region, mode, database
            )
            extraction_method_ids = {
                str(item["record_id"]) for item in extraction_methods
            }
            extraction_method_id = str(extraction_method_id or "")
            if extraction_method_ids and not extraction_method_id:
                raise ValueError(
                    "Select a Searching Method before searching."
                )
            if (
                extraction_method_id
                and extraction_method_id not in extraction_method_ids
            ):
                raise ValueError(
                    "That Searching Method is not available here."
                )
            entries = self._competency_entries(
                region,
                mode,
                sheet,
                database,
                extraction_method_id,
            )
            depletion = interaction_state.get("source_depletion", {}) or {}

            def available(entry: dict[str, Any]) -> int | None:
                if not bool(entry.get("depletable", False)):
                    return None
                record = entry.get("catalog", {})
                initial = max(1, int(record.get("default_source_quantity", 1) or 1))
                used = int(depletion.get(f"{region_id}:{entry['record_id']}", 0) or 0)
                return max(0, initial - used)

            skill_name = str(mode.get("skill", "") or "")
            skill_value = self._raw_skill(sheet, skill_name)
            outcome = draw_loot(entries, skill_value, available_quantity=available)
            by_id = {str(item["record_id"]): item for item in entries}
            awarded_names: list[str] = []
            destroyed_name = ""
            destroyed_creature = False

            def update(state: dict[str, Any]) -> None:
                interactions = state.setdefault("region_interactions", {})
                interactions.setdefault("attempts", []).append({
                    "record_id": str(uuid4()), "character_id": character_id,
                    "map_id": map_id, "region_id": region_id, "mode_id": mode_id,
                    "extraction_method_id": extraction_method_id,
                    "game_day": day, "natural_roll": outcome.natural_roll,
                    "skill_value": skill_value, "total": outcome.total,
                    "created_at": iso_utc(utc_now()),
                })
                depletion_state = interactions.setdefault("source_depletion", {})
                person_state = state.setdefault("people", {}).setdefault(character_id, {})
                for entry_id in outcome.awarded_ids:
                    entry = by_id[entry_id]
                    reference = entry["reference"]
                    record = entry["catalog"]
                    name = str(record.get("name") or record.get("title") or "Something")
                    awarded_names.append(name)
                    if bool(entry.get("depletable", False)):
                        key = f"{region_id}:{entry_id}"
                        depletion_state[key] = int(depletion_state.get(key, 0) or 0) + 1
                    if str(reference.get("collection")) == "creatures":
                        creatures = state.setdefault("creatures", {})
                        existing = next(
                            (item for item in creatures.values()
                             if str(item.get("species_record_id")) == str(reference.get("record_id"))
                             and str((item.get("placement") or {}).get("map_id")) == map_id
                             and str(item.get("visibility", "headmaster")) == "headmaster"), None
                        )
                        if existing is not None:
                            existing["visibility"] = "players"
                        else:
                            counters = state.setdefault("creature_counters", {})
                            species_id = str(reference["record_id"])
                            counter = int(counters.get(species_id, 0) or 0) + 1
                            counters[species_id] = counter
                            points = region.get("points", []) or []
                            x = sum(float(point["x"]) for point in points) / len(points)
                            y = sum(float(point["y"]) for point in points) / len(points)
                            map_record = self._campaign_map(document, map_id)
                            creature = generate_creature_instance(record, counter, {
                                "location_id": str(map_record.get("location_id", "")),
                                "floor_id": str(map_record.get("floor_id", "") or ""),
                                "map_id": map_id, "x": x, "y": y,
                            })
                            creature["visibility"] = "players"
                            creatures[creature["record_id"]] = creature
                    else:
                        self._inventory_add(person_state, reference, record, 1, source=str(region.get("name") or "Search"))
                if outcome.destroyed_id:
                    entry = by_id[outcome.destroyed_id]
                    record = entry["catalog"]
                    nonlocal destroyed_name, destroyed_creature
                    destroyed_name = str(record.get("name") or record.get("title") or "Something")
                    reference = entry.get("reference", {})
                    if str(reference.get("collection", "")) == "creatures":
                        creatures = state.setdefault("creatures", {})
                        escaped_id = next(
                            (
                                instance_id for instance_id, instance in creatures.items()
                                if str(instance.get("species_record_id", ""))
                                == str(reference.get("record_id", ""))
                                and str((instance.get("placement") or {}).get("map_id", "")) == map_id
                                and str(instance.get("visibility", "headmaster")) == "headmaster"
                            ),
                            "",
                        )
                        if escaped_id:
                            creatures.pop(escaped_id, None)
                        destroyed_creature = True
                    if bool(entry.get("depletable", False)):
                        key = f"{region_id}:{outcome.destroyed_id}"
                        depletion_state[key] = int(depletion_state.get(key, 0) or 0) + 1
                    interactions.setdefault("natural_one_losses", []).append({
                        "record_id": str(uuid4()), "character_id": character_id,
                        "region_id": region_id, "content_entry_id": outcome.destroyed_id,
                        "name": destroyed_name, "game_day": day,
                        "created_at": iso_utc(utc_now()),
                    })

            self.campaign_repository.update_game_state(campaign["record_id"], update)
            character_name = str(sheet.get("character_name") or person.get("displayed_name") or "A player")
            extraction_method_name = next(
                (
                    str(item.get("name", ""))
                    for item in extraction_methods
                    if str(item.get("record_id", ""))
                    == extraction_method_id
                ),
                "",
            )
            if destroyed_name:
                detail = (
                    f"They find {destroyed_name}, but it escapes."
                    if destroyed_creature
                    else f"They find {destroyed_name}, but destroy or lose it."
                )
            elif awarded_names:
                detail = "They find " + ", ".join(awarded_names) + "."
            else:
                detail = "They find nothing."
            return {
                "kind": "region_search_result", "natural_roll": outcome.natural_roll,
                "skill": skill_name, "skill_value": skill_value, "total": outcome.total,
                "extraction_method_id": extraction_method_id,
                "extraction_method": extraction_method_name,
                "awarded": awarded_names, "destroyed": destroyed_name,
                "loot_points_remaining": outcome.points_remaining,
                "text": (
                    f"{character_name} searches using {skill_name}"
                    + (
                        f" and {extraction_method_name}"
                        if extraction_method_name else ""
                    )
                    + f": {outcome.natural_roll} + {skill_value} = {outcome.total}. {detail}"
                ),
            }

    def _shop_snapshot(
        self, campaign: dict[str, Any], region: dict[str, Any], person: dict[str, Any],
        map_id: str
    ) -> dict[str, Any]:
        database = self.shared_store.load("db.json").data
        sales = (campaign["game_state"].get("region_interactions", {}) or {}).get("shop_window_sales", {}) or {}
        character_id = str(person["record_id"])
        person_state = campaign["game_state"].get("people", {}).get(character_id, {}) or {}
        balance = int(person_state.get("currency_knuts", 0) or 0)
        current = str(campaign["game_state"]["current_game_datetime"])
        listings: list[dict[str, Any]] = []
        for listing in region.get("shop_listings", []) or []:
            try:
                record = self._catalog_record(database, listing.get("reference", {}))
            except KeyError:
                continue
            window = shop_window(region, listing, current)
            frequency = str(listing.get("frequency", "always"))
            quantity = None if frequency == "always" else max(1, int(record.get("default_stock_quantity", record.get("default_source_quantity", 1)) or 1))
            sold = int(sales.get(f"{region['record_id']}:{listing['record_id']}:{window['window_id']}", 0) or 0)
            remaining = None if quantity is None else max(0, quantity - sold)
            available = bool(window["available"] and (remaining is None or remaining > 0))
            price = int(listing.get("price_knuts", 9_999_999) or 0)
            listings.append({
                "record_id": str(listing["record_id"]),
                "name": str(record.get("name") or record.get("title") or "Item"),
                "description": str(record.get("description", "") or "")[:1000],
                "price_knuts": price, "frequency": frequency,
                "available": available, "remaining": remaining,
                "affordable": available and balance >= price,
            })
        return {
            "kind": "shop", "map_id": map_id, "region_id": str(region["record_id"]),
            "title": str(region.get("name") or "Shop"), "balance_knuts": balance,
            "listings": listings,
        }

    def purchase_shop_listing(
        self, session_id: str, contact_id: str, map_id: str, region_id: str,
        listing_id: str
    ) -> dict[str, Any]:
        with self._lock:
            _session, campaign, _document, person, region = self._region_player_context(
                session_id, contact_id, map_id, region_id
            )
            if str(region.get("behavior_type")) != "shop":
                raise ValueError("That region is not a shop")
            listing = next(
                (item for item in region.get("shop_listings", []) or []
                 if str(item.get("record_id")) == listing_id), None
            )
            if listing is None:
                raise KeyError("Unknown shop listing")
            database = self.shared_store.load("db.json").data
            record = self._catalog_record(database, listing["reference"])
            window = shop_window(region, listing, str(campaign["game_state"]["current_game_datetime"]))
            if not window["available"]:
                raise ValueError("That listing is not currently in stock")
            character_id = str(person["record_id"])
            price = int(listing.get("price_knuts", 9_999_999) or 0)
            frequency = str(listing.get("frequency", "always"))
            sales_key = f"{region_id}:{listing_id}:{window['window_id']}"
            result_balance = 0

            def update(state: dict[str, Any]) -> None:
                nonlocal result_balance
                interactions = state.setdefault("region_interactions", {})
                sales = interactions.setdefault("shop_window_sales", {})
                if frequency != "always":
                    authored = max(1, int(record.get("default_stock_quantity", record.get("default_source_quantity", 1)) or 1))
                    if int(sales.get(sales_key, 0) or 0) >= authored:
                        raise ValueError("That listing has sold out")
                person_state = state.setdefault("people", {}).setdefault(character_id, {})
                balance = int(person_state.get("currency_knuts", 0) or 0)
                if balance < price:
                    raise ValueError("The character cannot afford that item")
                person_state["currency_knuts"] = balance - price
                result_balance = balance - price
                if frequency != "always":
                    sales[sales_key] = int(sales.get(sales_key, 0) or 0) + 1
                self._inventory_add(person_state, listing["reference"], record, 1, source=str(region.get("name") or "Shop"))
                interactions.setdefault("purchases", []).append({
                    "record_id": str(uuid4()), "character_id": character_id,
                    "map_id": map_id, "region_id": region_id, "listing_id": listing_id,
                    "definition_collection": str(listing["reference"].get("collection", "")),
                    "definition_record_id": str(listing["reference"].get("record_id", "")),
                    "price_knuts": price, "game_datetime": str(state["current_game_datetime"]),
                    "created_at": iso_utc(utc_now()),
                })

            self.campaign_repository.update_game_state(campaign["record_id"], update)
            item_name = str(record.get("name") or record.get("title") or "an item")
            character_name = str(person.get("displayed_name") or "A player")
            return {
                "kind": "shop_purchase_result", "item_name": item_name,
                "price_knuts": price, "balance_knuts": result_balance,
                "text": f"{character_name} buys {item_name} for {price} Knuts.",
            }

    def adjust_person_currency(
        self, session_id: str, person_id: str, change_knuts: int
    ) -> dict[str, Any]:
        """Adjust a campaign character's balance from Headmaster-only controls."""

        change = int(change_knuts)
        with self._lock:
            session = self._board_context(session_id)
            campaign, document = self._campaign_document(session)
            if not any(
                str(person.get("record_id", "")) == person_id
                for person in document.get("people", [])
                if isinstance(person, dict)
            ):
                raise KeyError("Unknown person")
            result_balance = 0

            def update(state: dict[str, Any]) -> None:
                nonlocal result_balance
                person_state = state.setdefault("people", {}).setdefault(person_id, {})
                current = max(0, int(person_state.get("currency_knuts", 0) or 0))
                result_balance = current + change
                if result_balance < 0:
                    raise ValueError("That adjustment would make the balance negative")
                person_state["currency_knuts"] = result_balance

            self.campaign_repository.update_game_state(campaign["record_id"], update)
            return {"person_id": person_id, "balance_knuts": result_balance}

    def roll_character_action(
        self,
        session_id: str,
        contact_id: str,
        roll_type: str,
        target_id: str,
    ) -> dict[str, Any]:
        if str(roll_type or "").strip().casefold() == "recipe":
            raise PermissionError(
                "Recipe attempts require confirmation before ingredients are used"
            )
        with self._lock:
            controlled = self.controlled_character_ids(session_id, contact_id)
            wrapper, session = self._active(session_id)
            player = self._player(session, contact_id)
            character_id = str(player.get("character_id", "") or "")
            if not character_id or character_id not in controlled:
                raise PermissionError("This player does not control a linked character")
            campaign_id = str(session.get("campaign_id", "") or "")
            campaign = self.campaign_repository.get(campaign_id) if campaign_id else None
            if campaign and self._roll_consumes_battle_action(roll_type):
                self._assert_battle_action_available(
                    campaign["game_state"], "person", character_id
                )
            sheet = self.character_sheet_for(session_id, contact_id)
            if sheet is None:
                raise PermissionError("No World Builder character is linked to this player")
            result = perform_character_roll(sheet, roll_type, target_id)
            if campaign and self._roll_consumes_battle_action(roll_type):
                self._commit_battle_action(
                    campaign_id, "person", character_id,
                    str(result.get("text") or result.get("target_name") or "Action completed"),
                )
            return result

    def attempt_character_recipe(
        self,
        session_id: str,
        contact_id: str,
        target_id: str,
    ) -> dict[str, Any]:
        """Consume a confirmed recipe's ingredients, then make its roll."""

        controlled = self.controlled_character_ids(session_id, contact_id)
        with self._lock:
            _wrapper, session = self._active(session_id)
            player = self._player(session, contact_id)
            character_id = str(player.get("character_id", "") or "")
            if not character_id or character_id not in controlled:
                raise PermissionError("This player does not control a linked character")
            campaign_id = str(session.get("campaign_id", "") or "")
            if not campaign_id:
                raise PermissionError("This session is not linked to a campaign")

            campaign_for_turn = self.campaign_repository.get(campaign_id)
            self._assert_battle_action_available(
                campaign_for_turn["game_state"], "person", character_id
            )

            sheet = self.character_sheet_for(session_id, contact_id)
            if sheet is None:
                raise PermissionError("No World Builder character is linked to this player")
            recipe = next(
                (
                    item for item in sheet.get("recipes", []) or []
                    if isinstance(item, dict)
                    and str(item.get("record_id", "")) == str(target_id)
                ),
                None,
            )
            if recipe is None:
                raise PermissionError("This character does not know that recipe")
            requirements = recipe.get("requirements", {}) or {}
            missing = [str(item) for item in requirements.get("missing", []) or []]
            if not requirements.get("ready", False):
                raise PermissionError(
                    "Missing recipe requirements: " + ", ".join(missing)
                )
            consumption = requirements.get("consumption", {}) or {}
            if not isinstance(consumption, dict):
                raise ValueError("Invalid recipe consumption plan")

            def consume(state: dict[str, Any]) -> None:
                person_state = state.setdefault("people", {}).setdefault(
                    character_id, {}
                )
                already = person_state.setdefault("consumed_inventory", {})
                for item_id, raw_quantity in consumption.items():
                    quantity = float(raw_quantity)
                    stacks = person_state.setdefault("campaign_inventory", [])
                    stack = next(
                        (
                            item for item in stacks
                            if str(item.get("record_id", "")) == str(item_id)
                        ),
                        None,
                    )
                    if stack is not None:
                        remaining = float(stack.get("quantity", 0) or 0) - quantity
                        if remaining < 0:
                            raise ValueError("Campaign inventory changed before consumption")
                        if remaining == 0:
                            stacks.remove(stack)
                        else:
                            stack["quantity"] = int(remaining) if remaining.is_integer() else remaining
                    else:
                        already[item_id] = float(already.get(item_id, 0) or 0) + quantity

            # Consumption is committed before the die is rolled. A failed attempt
            # therefore uses the same ingredients as a successful one.
            if consumption:
                self.campaign_repository.update_game_state(campaign_id, consume)
            required_spell_rolls = []
            for spell_group in requirements.get("spells", []) or []:
                spell_id = str(spell_group.get("selected_record_id", "") or "")
                if not spell_id:
                    continue
                required_spell_rolls.append(
                    perform_character_roll(sheet, "spell", spell_id)
                )
            failed_spell = next(
                (roll for roll in required_spell_rolls if roll.get("success") is False),
                None,
            )
            if failed_spell is None:
                result = perform_character_roll(sheet, "recipe", target_id)
            else:
                result = deepcopy(failed_spell)
                result.update({
                    "action_type": "recipe",
                    "target_id": target_id,
                    "target_name": str(recipe.get("name") or "Recipe"),
                    "text": (
                        f"{sheet.get('character_name', 'The character')} attempts "
                        f"{recipe.get('name', 'a recipe')}, but the required "
                        f"{failed_spell.get('target_name', 'spell')} fails."
                    ),
                })
            result["required_spell_rolls"] = required_spell_rolls
            result["consumed_ingredients"] = deepcopy(
                requirements.get("ingredients", []) or []
            )
            result["required_vessel"] = deepcopy(requirements.get("vessel"))
            result["required_vessels"] = deepcopy(
                requirements.get("vessels", []) or []
            )
            result["required_proficiencies"] = deepcopy(
                requirements.get("proficiencies", []) or []
            )
            result["required_spells"] = deepcopy(
                requirements.get("spells", []) or []
            )
            output_item = requirements.get("output_item")
            output_quantity = int(requirements.get("output_quantity", 1) or 1)
            if result.get("success") is True and isinstance(output_item, dict):
                def award(state: dict[str, Any]) -> None:
                    person_state = state.setdefault("people", {}).setdefault(
                        character_id, {}
                    )
                    self._inventory_add(
                        person_state,
                        output_item,
                        output_item,
                        output_quantity,
                        source=str(recipe.get("name") or "Recipe"),
                    )

                self.campaign_repository.update_game_state(campaign_id, award)
                result["recipe_output"] = {
                    **deepcopy(output_item), "quantity": output_quantity,
                }
            self._commit_battle_action(
                campaign_id, "person", character_id,
                str(result.get("text") or recipe.get("name") or "Recipe attempted"),
            )
            return result

    def update_character_equipment(
        self, session_id: str, contact_id: str, slot: str, item_id: str,
    ) -> dict[str, Any]:
        slot = str(slot or "").strip()
        if slot not in {"focus", "accessory_1", "accessory_2", "flyable"}:
            raise ValueError("Unknown equipment slot")
        with self._lock:
            _wrapper, session = self._active(session_id)
            player = self._player(session, contact_id)
            character_id = str(player.get("character_id", "") or "")
            campaign_id = str(session.get("campaign_id", "") or "")
            if not character_id or not campaign_id:
                raise PermissionError("A linked character and campaign are required")
            sheet = self.character_sheet_for(session_id, contact_id)
            inventory = sheet.get("inventory", []) if sheet else []
            item = next((entry for entry in inventory if str(entry.get("record_id", "")) == item_id), None) if item_id else None
            if item_id and item is None:
                raise PermissionError("That item is not in this character's inventory")
            expected = (
                "focus" if slot == "focus"
                else "flyable" if slot == "flyable"
                else "accessory"
            )
            if item is not None and str(item.get("equipment_slot_type", "")) != expected:
                raise ValueError(f"That item cannot occupy the {slot.replace('_', ' ')} slot")
            campaign = self.campaign_repository.get(campaign_id)
            person_state = (campaign.get("game_state", {}).get("people", {}) or {}).get(character_id, {})
            if person_state.get("battle"):
                details = {
                    "session_id": session_id, "contact_id": contact_id,
                    "person_id": character_id, "slot": slot, "item_id": item_id,
                    "item_name": str((item or {}).get("name", "Unequip")),
                    "request_summary": f"{sheet.get('character_name', 'Character')} wants to change {slot.replace('_', ' ')} during battle",
                }
                request = self.campaign_repository.add_request(campaign_id, "equipment_change", details)
                return {"status": "pending", "request": request}

            flight_roll: dict[str, Any] | None = None
            if slot == "flyable" and item is not None:
                try:
                    threshold = int(item.get("flight_threshold"))
                except (TypeError, ValueError) as error:
                    raise ValueError(
                        "That flyable item does not have a valid Flying threshold"
                    ) from error
                flight_roll = perform_character_roll(sheet, "skill", "Flying")
                natural = int((flight_roll.get("dice") or [0])[0] or 0)
                success = natural != 1 and int(flight_roll.get("total", 0) or 0) >= threshold
                critical = (
                    "failure" if natural == 1
                    else "success" if natural == 10 and success
                    else ""
                )
                character_name = str(sheet.get("character_name") or "A character")
                item_name = str(item.get("name") or "a flyable item")
                flight_roll.update({
                    "action_type": "flyable",
                    "target_id": str(item.get("record_id") or ""),
                    "target_name": item_name,
                    "threshold": threshold,
                    "success": success,
                    "critical": critical,
                    "outcome": (
                        "critical_success" if critical == "success"
                        else "critical_failure" if critical == "failure"
                        else "success" if success else "failure"
                    ),
                    "text": (
                        f"{character_name} gets airborne on {item_name} "
                        f"with a Flying total of {flight_roll.get('total')} against {threshold}."
                        if success else
                        f"{character_name} fails to get airborne on {item_name} "
                        f"with a Flying total of {flight_roll.get('total')} against {threshold}."
                    ),
                })
                if not success:
                    return {
                        "status": "failed", "slot": slot,
                        "item_id": item_id,
                        "airborne": bool(person_state.get("airborne", False)),
                        "roll": flight_roll, "text": flight_roll["text"],
                    }

            def update(state: dict[str, Any]) -> None:
                person = state.setdefault("people", {}).setdefault(character_id, {})
                equipment = person.setdefault("equipment", {})
                equipment[slot] = item_id
                if slot == "flyable":
                    person["airborne"] = bool(item_id)
                if item_id:
                    for other_slot, equipped_id in list(equipment.items()):
                        if other_slot != slot and equipped_id == item_id:
                            equipment[other_slot] = ""

            self.campaign_repository.update_game_state(campaign_id, update)
            result = {
                "status": "equipped" if item_id else "unequipped",
                "slot": slot,
                "item_id": item_id,
                "airborne": bool(item_id) if slot == "flyable" else bool(person_state.get("airborne", False)),
            }
            if flight_roll is not None:
                result["roll"] = flight_roll
                result["text"] = flight_roll["text"]
            return result

    def use_inventory_item(
        self, session_id: str, contact_id: str, item_id: str, action_id: str,
    ) -> dict[str, Any]:
        """Perform one explicitly configured item action; there is no generic use."""

        with self._lock:
            _wrapper, session = self._active(session_id)
            player = self._player(session, contact_id)
            character_id = str(player.get("character_id", "") or "")
            campaign_id = str(session.get("campaign_id", "") or "")
            if not character_id or not campaign_id:
                raise PermissionError("A linked character and campaign are required")
            sheet = self.character_sheet_for(session_id, contact_id)
            item = next(
                (entry for entry in (sheet or {}).get("inventory", []) if str(entry.get("record_id", "")) == item_id),
                None,
            )
            if item is None:
                raise PermissionError("That item is not in this character's inventory")
            actions = [entry for entry in item.get("actions", []) or [] if isinstance(entry, dict)]
            action = next(
                (entry for entry in actions if str(entry.get("record_id") or entry.get("action_id") or "") == action_id),
                None,
            )
            if action is None:
                raise PermissionError("That item has no such structured action")
            action_type = str(action.get("action_type", "") or "").casefold()
            if action_type not in {"roll", "message", "consume", "potion"}:
                raise ValueError("That item action is not supported")
            if str(action.get("activation_mode", "click") or "click").casefold() != "click":
                raise PermissionError("That item effect is passive and cannot be clicked")
            result: dict[str, Any] = {
                "activity_type": "item_action", "item_id": item_id,
                "item_name": str(item.get("name") or "Item"),
                "action_id": action_id, "action_name": str(action.get("name") or "Use"),
            }
            if action_type == "roll":
                roll_type = str(action.get("roll_type") or "skill")
                target_id = str(action.get("target_id") or action.get("target") or "")
                if not target_id:
                    raise ValueError("This item roll is missing its target")
                roll_sheet = sheet
                if roll_type in {"spell", "proficiency"}:
                    sheet_collection = (
                        "spells" if roll_type == "spell" else "proficiencies"
                    )
                    known = any(
                        str(entry.get("record_id", "")) == target_id
                        for entry in sheet.get(sheet_collection, []) or []
                        if isinstance(entry, dict)
                    )
                    if not known:
                        database = self.shared_store.load("db.json").data
                        source = next(
                            (
                                entry
                                for entry in database.get(sheet_collection, []) or []
                                if isinstance(entry, dict)
                                and str(entry.get("record_id", "")) == target_id
                            ),
                            None,
                        )
                        if source is None:
                            raise KeyError("That linked item effect no longer exists")
                        roll_sheet = deepcopy(sheet)
                        roll_sheet.setdefault(sheet_collection, []).append(
                            deepcopy(source)
                        )
                result["roll"] = perform_character_roll(
                    roll_sheet, roll_type, target_id
                )
                result["text"] = str(result["roll"].get("text") or "An item action was rolled.")
            elif action_type == "potion":
                target_id = str(action.get("target_id", "") or "")
                collection = str(
                    action.get("target_collection", "potions") or "potions"
                )
                if collection not in {"potions", "preparations"} or not target_id:
                    raise ValueError("This item potion effect is incomplete")
                database = self.shared_store.load("db.json").data
                potion = next(
                    (
                        entry for entry in database.get(collection, []) or []
                        if isinstance(entry, dict)
                        and str(entry.get("record_id", "")) == target_id
                    ),
                    None,
                )
                if potion is None:
                    raise KeyError("That linked potion effect no longer exists")
                effect_text = str(
                    potion.get("raw_effect")
                    or potion.get("effect")
                    or potion.get("description")
                    or "The potion takes effect."
                )[:4000]
                character_name = str(sheet.get("character_name") or "A character")
                result["effect"] = {
                    "record_id": target_id,
                    "collection": collection,
                    "name": str(potion.get("name") or action.get("name") or "Potion"),
                    "description": effect_text,
                    "target_scope": str(
                        action.get("target_scope")
                        or potion.get("target_scope")
                        or "self"
                    ),
                }
                result["text"] = (
                    f"{character_name} uses {item.get('name', 'an item')}. "
                    f"{effect_text}"
                )
            else:
                result["text"] = str(
                    action.get("message")
                    or f"{sheet.get('character_name', 'A character')} uses {item.get('name', 'an item')}."
                )[:4000]
            consume_quantity = int(action.get("consume_quantity", 1 if action_type == "consume" else 0) or 0)
            if consume_quantity > 0:
                def consume(state: dict[str, Any]) -> None:
                    person = state.setdefault("people", {}).setdefault(character_id, {})
                    stack = next(
                        (entry for entry in person.setdefault("campaign_inventory", []) if str(entry.get("record_id")) == item_id),
                        None,
                    )
                    if stack is not None:
                        remaining = int(stack.get("quantity", 0) or 0) - consume_quantity
                        if remaining < 0:
                            raise ValueError("There is not enough of that item")
                        if remaining:
                            stack["quantity"] = remaining
                        else:
                            person["campaign_inventory"].remove(stack)
                    else:
                        consumed = person.setdefault("consumed_inventory", {})
                        consumed[item_id] = int(consumed.get(item_id, 0) or 0) + consume_quantity
                self.campaign_repository.update_game_state(campaign_id, consume)
                result["consumed_quantity"] = consume_quantity
            return result

    def add_shared_catalog_tag(
        self, session_id: str, contact_id: str, collection: str,
        target_record_id: str, name: str,
    ) -> dict[str, Any]:
        allowed = {"spells", "proficiencies", "recipes", "potions", "preparations", "foods_and_drinks"}
        collection = str(collection or "").strip()
        target_record_id = str(target_record_id or "").strip()
        shown_name = re.sub(r"\s+", " ", str(name or "").strip())[:100]
        if collection not in allowed or not target_record_id or not shown_name:
            raise ValueError("Choose a valid catalog record and tag name")
        with self._lock:
            _wrapper, session = self._active(session_id)
            self._player(session, contact_id)
            campaign_id = str(session.get("campaign_id", "") or "")
            database = self.shared_store.load("db.json").data
            if not any(str(item.get("record_id", "")) == target_record_id for item in database.get(collection, []) or []):
                raise KeyError("Unknown catalog record")
            result: dict[str, Any] = {}

            def update(campaign: dict[str, Any]) -> None:
                nonlocal result
                normalized_name = shown_name.casefold()
                tag = next((item for item in campaign.setdefault("shared_tags", []) if item.get("normalized_name") == normalized_name), None)
                if tag is None:
                    tag = {
                        "record_id": str(uuid4()), "name": shown_name,
                        "normalized_name": normalized_name,
                        "created_by_player_id": contact_id,
                        "created_at": iso_utc(utc_now()),
                    }
                    campaign["shared_tags"].append(tag)
                exists = any(
                    item.get("collection") == collection
                    and item.get("target_record_id") == target_record_id
                    and item.get("tag_id") == tag["record_id"]
                    for item in campaign.setdefault("tag_assignments", [])
                )
                if not exists:
                    campaign["tag_assignments"].append({
                        "record_id": str(uuid4()), "collection": collection,
                        "target_record_id": target_record_id, "tag_id": tag["record_id"],
                        "created_by_player_id": contact_id, "created_at": iso_utc(utc_now()),
                    })
                result = deepcopy(tag)

            self.campaign_repository.update_campaign(campaign_id, update)
            return result

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
                elif action == "ground":
                    equipment = person.setdefault("equipment", {})
                    removed_item_id = str(equipment.get("flyable", "") or "")
                    equipment["flyable"] = ""
                    person["airborne"] = False
                    result = {
                        "airborne": False,
                        "removed_item_id": removed_item_id,
                    }
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

            updated_campaign = self.campaign_repository.update_game_state(
                campaign["record_id"], update
            )
            game_datetime = str(
                updated_campaign["game_state"]["current_game_datetime"]
            )
            event_details = {
                "person_ids": [person_id],
                "source": "game-board",
            }
            if action == "add_wound":
                event_details.update({
                    "wound_id": result["record_id"],
                    "severity": result["severity"],
                    "description": result["note"],
                })
            elif action in {"enter_battle", "leave_battle"}:
                event_details["battle"] = deepcopy(result)
            elif action == "ground":
                event_details.update(deepcopy(result))
            else:
                event_details.update({
                    "note_id": result["record_id"],
                    "description": result["text"],
                })
            event_date, event_time = game_datetime.split("T", 1)
            self.campaign_repository.add_event(
                campaign["record_id"],
                action,
                event_date,
                event_time=event_time,
                details=event_details,
            )
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
            campaign_id = str(session.get("campaign_id", "") or "")
            if not campaign_id:
                raise ValueError("This session is not linked to a campaign")
            world = self._world_document()
            map_record = next(
                (
                    item for item in self.world_board._location_maps(world)
                    if str(item.get("record_id", "")) == map_id
                ),
                None,
            )
            if map_record is None:
                raise KeyError("That map is not assigned to a location or floor")
            person = next(
                (item for item in world.get("people", []) if item.get("record_id") == person_id),
                None,
            )
            if person is None:
                raise KeyError("Unknown person")
            placement = {
                "location_id": str(map_record["location_id"]),
                "floor_id": str(map_record.get("floor_id", "") or ""),
                "map_id": str(map_id),
                "x": max(0.0, min(1.0, float(x))),
                "y": max(0.0, min(1.0, float(y))),
            }

            def update(state: dict[str, Any]) -> None:
                people = state.setdefault("people", {})
                existing = people.get(person_id)
                if not isinstance(existing, dict):
                    existing = self.campaign_repository._person_state(
                        normalize_person_board(person.get("board"))
                    )
                existing["placement"] = deepcopy(placement)
                people[person_id] = existing
                followers = [
                    item for item in (state.get("creatures", {}) or {}).values()
                    if isinstance(item, dict)
                    and str(item.get("related_character_id", "")) == person_id
                    and str(item.get("relationship_state", "")) == "lured"
                    and str(item.get("life_state", "alive")) == "alive"
                ]
                for index, follower in enumerate(followers):
                    angle = (index % 8) * (math.pi / 4.0)
                    radius = 0.012 + (index // 8) * 0.008
                    follower["placement"] = {
                        "location_id": placement["location_id"],
                        "floor_id": placement["floor_id"],
                        "map_id": map_id,
                        "x": max(0.005, min(0.995, placement["x"] + math.cos(angle) * radius)),
                        "y": max(0.005, min(0.995, placement["y"] + math.sin(angle) * radius)),
                    }
                retained_groups = []
                for group in state.get("groups", []) or []:
                    if str(group.get("location_id", "")) != placement["location_id"]:
                        group["members"] = [
                            member for member in group.get("members", []) or []
                            if not (
                                str(member.get("actor_type", "")) == "person"
                                and str(member.get("actor_id", "")) == person_id
                            )
                        ]
                    if len(group.get("members", []) or []) >= 2:
                        retained_groups.append(group)
                state["groups"] = retained_groups

            self.campaign_repository.update_game_state(campaign_id, update)
            return deepcopy(placement)

    def place_person_on_map(
        self,
        session_id: str,
        person_id: str,
        map_id: str,
        x: float = 0.5,
        y: float = 0.5,
        *,
        confirm_move: bool = False,
    ) -> dict[str, Any]:
        """Place any world character, confirming an inter-map move first."""

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
            board = normalize_person_board(person.get("board"))
            previous = board.get("placement")
            if previous and str(previous.get("map_id", "")) == map_id:
                return {
                    "placed": False,
                    "already_on_map": True,
                    "person_id": person_id,
                    "person_name": str(person.get("displayed_name", "") or "Character"),
                    "placement": deepcopy(previous),
                }
            if previous and not confirm_move:
                previous_map = next(
                    (
                        item for item in document.get("maps", [])
                        if str(item.get("record_id", "")) == str(previous.get("map_id", ""))
                    ),
                    {},
                )
                return {
                    "requires_confirmation": True,
                    "person_id": person_id,
                    "person_name": str(person.get("displayed_name", "") or "Character"),
                    "current_map_id": str(previous.get("map_id", "")),
                    "current_map_name": str(previous_map.get("name", "") or "another map"),
                }

            occupied = []
            for other in document.get("people", []):
                if not isinstance(other, dict) or other is person:
                    continue
                placement = normalize_person_board(other.get("board")).get("placement")
                if placement and str(placement.get("map_id", "")) == map_id:
                    occupied.append((float(placement["x"]), float(placement["y"])))
            spacing = max(
                0.006,
                float(target.get("token_scale", DEFAULT_MAP_TOKEN_SCALE)) * 1.15,
            )
            requested = (
                max(0.005, min(0.995, float(x))),
                max(0.005, min(0.995, float(y))),
            )
            candidates = [requested]
            for ring in range(1, 7):
                radius = spacing * ring
                for index in range(max(8, ring * 8)):
                    angle = (2.0 * math.pi * index) / max(8, ring * 8)
                    candidates.append((
                        max(0.005, min(0.995, requested[0] + math.cos(angle) * radius)),
                        max(0.005, min(0.995, requested[1] + math.sin(angle) * radius)),
                    ))
            px, py = next(
                (
                    point for point in candidates
                    if all(
                        math.hypot(point[0] - ox, point[1] - oy) >= spacing
                        for ox, oy in occupied
                    )
                ),
                candidates[-1],
            )
            board["placement"] = {
                "location_id": str(target["location_id"]),
                "floor_id": str(target.get("floor_id", "") or ""),
                "map_id": map_id,
                "x": px,
                "y": py,
            }
            person["board"] = board
            self.world_board._remove_from_incompatible_groups(
                document, person_id, board["placement"]["location_id"]
            )
            self._persist_campaign_document(campaign["record_id"], document)

            contact_ids = [
                str(player.get("contact_id", ""))
                for player in session.get("roster", [])
                if str(player.get("character_id", "") or "") == person_id
            ]
            if contact_ids:
                camera = {
                    "zoom": float(normalize_zoom_profile(target.get("zoom_profile")).get("default_zoom", 1.0)),
                    "center_x": px,
                    "center_y": py,
                }

                def update(state: dict[str, Any]) -> None:
                    loaded = state.setdefault("loaded_map_ids", [])
                    if map_id not in loaded:
                        loaded.append(map_id)
                    map_state = state.setdefault("maps", {}).setdefault(map_id, {})
                    cameras = map_state.setdefault("player_cameras", {})
                    active_maps = state.setdefault("player_active_map_ids", {})
                    for contact_id in contact_ids:
                        cameras[contact_id] = deepcopy(camera)
                        active_maps[contact_id] = map_id

                self.campaign_repository.update_game_state(campaign["record_id"], update)
            return {
                "placed": True,
                "person_id": person_id,
                "person_name": str(person.get("displayed_name", "") or "Character"),
                "placement": deepcopy(board["placement"]),
                "moved_from_another_map": bool(previous),
            }

    def create_quick_character(
        self,
        session_id: str,
        map_id: str,
        name: str,
        age: int,
        development_strategy: str = "random",
        player_character: bool = False,
    ) -> dict[str, Any]:
        """Create a lightweight World Builder person and progress their youth."""

        clean_name = " ".join(str(name or "").split())
        if not clean_name:
            raise ValueError("Character name is required")
        age = int(age)
        if not 0 <= age <= 1000:
            raise ValueError("Rough age must be between 0 and 1000")
        with self._lock:
            session = self._board_context(session_id)
            current = normalize_game_datetime(
                str(session.get("game_datetime", "") or ""),
                str(session.get("event_date", "") or date.today().isoformat()),
            )
            current_year = int(GAME_DATETIME.fullmatch(current).group("year"))
            source_directory = Path(__file__).resolve().parents[2] / "apps" / "world-builder" / "source"
            source_text = str(source_directory)
            if source_text not in sys.path:
                sys.path.insert(0, source_text)
            data_directory = (
                Path(self.shared_store.data_directory)
                if self.shared_store.data_directory is not None
                else Path(__file__).resolve().parents[2] / "data"
            )
            os.environ.setdefault(
                "HEADMASTERS_SCROLL_DATA_DIRECTORY",
                str(data_directory),
            )
            from mage_maker.core.database import JsonDatabase
            from mage_maker.core.controller import PeopleController
            from mage_maker.core.dates import historical_year_shift
            from mage_maker.sections.development.characteristics import randomized_characteristics
            from mage_maker.sections.development.initial_bonuses import initialize_initial_bonuses
            from mage_maker.sections.development.initial_values import initialize_parental_values
            from mage_maker.sections.development.models import (
                DEVELOPMENT_SCHEMA_OPTIONS,
                randomized_development_plan,
            )
            from mage_maker.sections.development.school_years import ensure_school_year_records

            strategy = str(development_strategy or "random").strip()
            if strategy.casefold() == "random":
                plan = randomized_development_plan()
            else:
                matches = {
                    option.casefold(): option for option in DEVELOPMENT_SCHEMA_OPTIONS
                }
                selected = matches.get(strategy.casefold())
                if selected is None:
                    raise ValueError("Unknown development strategy")
                plan = randomized_development_plan(selected_schema=selected)
            birth_year = historical_year_shift(current_year, -age) if age else current_year
            visible_school_years = min(7, max(0, age - 10))
            plan["school_started"] = visible_school_years > 0
            plan["academic_years_advanced"] = (
                7 if age >= 18 else max(0, visible_school_years - 1)
            )
            db = JsonDatabase(data_directory / "world.json")
            # Use this service's store explicitly.  This is important for
            # portable installs and temporary/test data directories, and it
            # retains the shared revision-aware save contract.
            db.shared_store = self.shared_store
            db.load()
            controller = PeopleController(db)
            draft = {
                "displayed_name": clean_name,
                "birth_year": birth_year,
                "birth_month": None,
                "birth_day": None,
                "player_character": bool(player_character),
                "blood_status": "Pureblood",
                "developmental_environment": "Magical",
                "development_plan": plan,
                "unfinished": True,
            }
            draft["parental_values"] = initialize_parental_values(draft, db.list_people())
            draft["initial_bonuses"] = initialize_initial_bonuses(draft, plan)
            draft["characteristics"] = randomized_characteristics()
            rules = self.shared_store.load("db.json").data
            plan["school_years"] = ensure_school_year_records(
                [],
                visible_school_years,
                plan,
                books=rules.get("books", []),
                spells=rules.get("spells", []),
                proficiencies=rules.get("proficiencies", []),
                school_name="",
                initial_characteristics=draft["characteristics"],
                manage_books=True,
                schools=rules.get("schools", []),
            )
            draft["development_plan"] = plan
            created = controller.create_person(draft)
            placement = self.place_person_on_map(
                session_id,
                str(created["record_id"]),
                map_id,
                0.5,
                0.5,
                confirm_move=True,
            )
            return {
                "character": {
                    "id": str(created["record_id"]),
                    "name": str(created["displayed_name"]),
                    "birth_year": created.get("birth_year"),
                    "development_strategy": plan.get("schema"),
                    "development_years": visible_school_years,
                },
                "placement": placement.get("placement"),
            }

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

    def activate_player_character_map(
        self,
        session_id: str,
        contact_id: str,
        person_id: str,
    ) -> dict[str, Any] | None:
        """Place a linked character and make its map the player's live view."""

        with self._lock:
            placement = self.ensure_person_placement(session_id, person_id)
            if not placement:
                return None
            _wrapper, session = self._active(session_id)
            campaign, document = self._campaign_document(session)
            target = self._campaign_map(document, str(placement["map_id"]))
            map_id = str(target["record_id"])
            profile = normalize_zoom_profile(target.get("zoom_profile"))
            camera = {
                "zoom": float(profile.get("default_zoom", 1.0)),
                "center_x": float(placement["x"]),
                "center_y": float(placement["y"]),
            }

            def update(state: dict[str, Any]) -> None:
                loaded = state.setdefault("loaded_map_ids", [])
                if map_id not in loaded:
                    loaded.append(map_id)
                state.setdefault("player_active_map_ids", {})[contact_id] = map_id
                map_state = state.setdefault("maps", {}).setdefault(map_id, {})
                map_state.setdefault("player_cameras", {})[contact_id] = deepcopy(camera)

            self.campaign_repository.update_game_state(campaign["record_id"], update)
            return {"placement": deepcopy(placement), "camera": camera}

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
        return self.world_board._location_maps(self._world_document())

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
            behavior = str((region or {}).get("behavior_type", "") or "")
            revealed_secret_passage = bool(
                region
                and behavior == "secret"
                and region.get("secret_passage", False)
                and self._secret_is_revealed(campaign, region_id, person_id)
            )
            if region is None or not (
                behavior == "travel" or revealed_secret_passage
            ):
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

    def set_secret_revealed(
        self,
        session_id: str,
        map_id: str,
        region_id: str,
        revealed: bool,
    ) -> dict[str, Any]:
        """Reveal or conceal one authored Secret for every campaign player."""

        with self._lock:
            session = self._board_context(session_id)
            campaign, document = self._campaign_document(session)
            map_record = self._campaign_map(document, map_id)
            region = next(
                (
                    item
                    for item in map_record.get("regions", []) or []
                    if str(item.get("record_id", "") or "") == region_id
                ),
                None,
            )
            if region is None or str(
                region.get("behavior_type", "") or ""
            ) != "secret":
                raise ValueError("That map area is not a Secret")

            def update(state: dict[str, Any]) -> None:
                interactions = state.setdefault("region_interactions", {})
                records = [
                    item
                    for item in interactions.setdefault(
                        "revealed_secrets", []
                    )
                    if str(item.get("region_id", "") or "") != region_id
                ]
                if revealed:
                    records.append(
                        {
                            "record_id": str(uuid4()),
                            "map_id": map_id,
                            "region_id": region_id,
                            "created_at": iso_utc(utc_now()),
                        }
                    )
                interactions["revealed_secrets"] = records

            self.campaign_repository.update_game_state(
                campaign["record_id"], update
            )
            return {
                "map_id": map_id,
                "region_id": region_id,
                "name": str(region.get("name", "") or "Secret"),
                "secret_passage": bool(
                    region.get("secret_passage", False)
                ),
                "revealed": bool(revealed),
            }

    def create_board_group(
        self,
        session_id: str,
        name: str,
        location_id: str,
        person_ids: list[str],
        color: str = "#b0b0b0",
    ) -> dict[str, Any]:
        with self._lock:
            session = self._board_context(session_id)
            campaign, document = self._campaign_document(session)
            if len(set(person_ids)) < 1:
                raise ValueError("A board group requires at least one person")
            people = {str(item.get("record_id")): item for item in document.get("people", [])}
            for person_id in person_ids:
                placement = normalize_person_board(people.get(person_id, {}).get("board")).get("placement") if person_id in people else None
                if person_id not in people or not placement or placement["location_id"] != location_id:
                    raise ValueError("Every group member must be a person at this location")
            # Assigning a group is a replacement operation.  Remove the chosen
            # people from their old groups first instead of rejecting a normal
            # "change group" action.
            selected_ids = set(person_ids)
            for group in document.get("board_groups", []):
                group["members"] = [
                    member for member in group.get("members", [])
                    if not (
                        member.get("actor_type", "person") == "person"
                        and member.get("actor_id") in selected_ids
                    )
                ]
            document["board_groups"] = [
                group for group in document.get("board_groups", [])
                if len(group.get("members", [])) >= 2
            ]
            now = iso_utc(utc_now())
            group_data = {
                "record_id": str(uuid4()),
                "name": str(name or "").strip(),
                "location_id": str(location_id),
                "color": str(color or "#b0b0b0").strip().lower(),
                "members": [
                    {"record_id": str(uuid4()), "actor_type": "person", "actor_id": person_id}
                    for person_id in person_ids
                ],
                "created_at": now,
                "last_updated": now,
            }
            # The canonical group contract historically required two members.
            # A one-person group is useful for preconfiguring presentation; it
            # is retained as a campaign group and becomes canonical as soon as
            # another member joins.
            group = normalize_group(group_data) if len(person_ids) >= 2 else group_data
            document.setdefault("board_groups", []).append(group)
            self._persist_campaign_document(campaign["record_id"], document)
            return deepcopy(group)

    def create_board_faction(
        self,
        session_id: str,
        person_id: str,
        name: str,
        color: str,
    ) -> dict[str, Any]:
        """Create a world faction and join the character on the game date."""

        normalized_name = str(name or "").strip()
        normalized_color = str(color or "#808080").strip().lower()
        if not normalized_name:
            raise ValueError("Faction name is required")
        if not re.fullmatch(r"#[0-9a-f]{6}", normalized_color):
            raise ValueError("Faction color must use #RRGGBB")
        with self._lock:
            session = self._board_context(session_id)
            campaign, _document = self._campaign_document(session)
            world_session = self.shared_store.load("world.json")
            if not any(str(person.get("record_id", "")) == person_id for person in world_session.data.get("people", [])):
                raise KeyError("Unknown person")
            game_datetime = str(campaign["game_state"]["current_game_datetime"])
            event_date, _, event_time = game_datetime.partition("T")
            event_time = event_time.replace(":", "")[:4]
            existing = next(
                (
                    item for item in world_session.data.get("organizations", [])
                    if isinstance(item, dict)
                    and item.get("is_faction")
                    and str(item.get("name", "")).strip().casefold() == normalized_name.casefold()
                ),
                None,
            )
            faction_id = str((existing or {}).get("record_id", "") or str(uuid4()))
            if existing is None:
                world_session.data.setdefault("organizations", []).append({
                    "record_id": faction_id,
                    "name": normalized_name,
                    "organization_type": "Faction",
                    "parent_organization_id": "",
                    "is_faction": True,
                    "faction_color": normalized_color,
                    "events": [{
                        "record_id": "organization-founding",
                        "event_type": "founding",
                        "title": "Founding",
                        "date": event_date,
                        "time": "",
                        "year": int(re.match(r"^-?\d+", event_date).group()),
                        "description": "",
                        "person_ids": [],
                        "item_ids": [],
                        "item_link_types": {},
                        "item_new_owners": {},
                        "eminence_person_ids": [],
                        "eminence_skills": {},
                    }],
                    "jobs": [],
                })
            else:
                # A faction is a shared world organization. Changing its
                # color changes the one faction record for every character,
                # rather than creating a person-specific presentation value.
                existing["faction_color"] = normalized_color
            if faction_id not in active_faction_ids(world_session.data, person_id, game_datetime):
                world_session.data.setdefault("events", []).append({
                    "record_id": str(uuid4()),
                    "event_type": "joined_faction",
                    "title": f"Joined {normalized_name}",
                    "date": event_date,
                    "time": event_time,
                    "description": "",
                    "person_ids": [person_id],
                    "organization_id": faction_id,
                    "organization_name": normalized_name,
                })
            outcome = self.shared_store.save(world_session, "game-board")
            if not outcome.saved:
                raise RuntimeError("World Builder data changed; refresh and try again")
            refreshed_session = self._board_context(session_id)
            refreshed_campaign, refreshed_document = self._campaign_document(refreshed_session)
            person = next(
                item for item in refreshed_document.get("people", [])
                if str(item.get("record_id", "")) == person_id
            )
            board = normalize_person_board(person.get("board"))
            board["faction_organization_id"] = faction_id
            person["board"] = board
            self._persist_campaign_document(refreshed_campaign["record_id"], refreshed_document)
            return {
                "organization_id": faction_id,
                "name": normalized_name,
                "color": normalized_color,
            }

    def update_board_faction_color(
        self,
        session_id: str,
        organization_id: str,
        color: str,
    ) -> dict[str, Any]:
        """Change the shared color of an existing world faction."""

        normalized_color = str(color or "").strip().lower()
        if not re.fullmatch(r"#[0-9a-f]{6}", normalized_color):
            raise ValueError("Faction color must use #RRGGBB")
        with self._lock:
            self._board_context(session_id)
            world_session = self.shared_store.load("world.json")
            faction = next(
                (
                    item for item in world_session.data.get("organizations", [])
                    if isinstance(item, dict)
                    and item.get("is_faction")
                    and str(item.get("record_id", "")) == organization_id
                ),
                None,
            )
            if faction is None:
                raise KeyError("Unknown faction")
            faction["faction_color"] = normalized_color
            outcome = self.shared_store.save(world_session, "game-board")
            if not outcome.saved:
                raise RuntimeError("World Builder data changed; refresh and try again")
            return {
                "organization_id": organization_id,
                "name": str(faction.get("name") or organization_id),
                "color": normalized_color,
            }

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
        contact_id: str | None = None,
    ) -> tuple[Any, str]:
        snapshot = (
            self.board_snapshot(
                session_id,
                for_players=True,
                contact_id=contact_id,
            )
            if contact_id
            else self.board_snapshot(session_id, for_players=True)
        )
        # A test/legacy snapshot may still carry a sheet. Production player
        # snapshots no longer do, so build it lazily only for assets whose
        # authorization genuinely depends on private character knowledge.
        sheet: dict[str, Any] | None = snapshot.get("character_sheet")
        if asset_id.startswith("book-cover:"):
            if sheet is None and contact_id:
                sheet = self.character_sheet_for(session_id, str(contact_id))
            authorized_cover_ids = {
                str(book.get("cover_asset_id") or "")
                for book in (sheet or {}).get("books", []) or []
                if isinstance(book, dict)
            }
            if asset_id not in authorized_cover_ids:
                raise PermissionError("That book cover is not available to this session")
            slug = asset_id.removeprefix("book-cover:")
            filename = BOOK_COVER_FILES.get(slug)
            if not filename:
                raise PermissionError("That book cover is not available")
            cover = BOOK_COVER_DIRECTORY / filename
            if not cover.is_file():
                raise FileNotFoundError(filename)
            return cover, "image/png"
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
        if sheet is None:
            sheet = self.character_sheet_for(session_id, str(contact_id or ""))
        portrait_id = str(
            ((sheet or {}).get("overview") or {}).get("portrait_asset_id", "")
            or ""
        )
        if portrait_id == asset_id:
            character_id = str((sheet or {}).get("character_id", "") or "")
            person = next(
                (
                    item for item in world.get("people", [])
                    if str(item.get("record_id", "")) == character_id
                ),
                None,
            )
            portrait = ((person or {}).get("board") or {}).get("portrait")
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
        activity: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        text = text.strip()
        if not text:
            raise ValueError("Chat messages cannot be empty")
        if len(text) > 500:
            raise ValueError("Chat messages are limited to 500 characters")
        if sender_role not in {"player", "headmaster", "system", "creature"}:
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
            if activity is not None:
                # Calculation details contain no hidden records and allow the
                # UI to show a concise sentence with an expandable audit.
                message["activity"] = deepcopy(activity)
            chat = session.setdefault("chat", [])
            chat.append(message)
            del chat[:-100]
            self.repository.save_active(wrapper)
            return deepcopy(message)

    def chat_message_for_viewer(
        self, message: dict[str, Any], session_id: str, contact_id: str
    ) -> dict[str, Any]:
        """Redact creature identity independently for one admitted player."""

        shown = deepcopy(message)
        activity = shown.get("activity")
        if not isinstance(activity, dict) or activity.get("activity_type") not in {
            "creature_action", "creature_harvest"
        }:
            return shown
        proficiency_id = str(activity.get("awareness_proficiency_id", "") or "")
        sheet = self.character_sheet_for(session_id, contact_id) or {}
        known = proficiency_id in {
            str(item.get("record_id", "") or "")
            for item in sheet.get("proficiencies", []) or []
            if isinstance(item, dict)
        }
        species_name = str(activity.get("species_name") or "Creature")
        viewer_name = species_name if known else "Unknown creature"
        if activity.get("activity_type") == "creature_action":
            action_name = str(activity.get("name") or "an action")
            roll = int(activity.get("roll", 0) or 0)
            shown["text"] = f"{viewer_name} uses {action_name} and rolls {roll}."
            shown["sender_name"] = viewer_name
        elif not known:
            shown["text"] = str(shown.get("text", "")).replace(
                species_name, "an unknown creature"
            )
        activity.pop("species_name", None)
        activity.pop("awareness_proficiency_id", None)
        activity.pop("internal_label", None)
        return shown

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
