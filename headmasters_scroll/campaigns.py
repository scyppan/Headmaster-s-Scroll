from __future__ import annotations

import calendar
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from .store import SharedJsonStore


GAME_WORLD_DATE = re.compile(
    r"^(?P<year>-?[1-9]\d*)-(?P<month>\d{2})-(?P<day>\d{2})$"
)


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
    })
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

    def save_campaign(
        self,
        name: str,
        game_world_start_date: str,
        campaign_id: str | None = None,
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
