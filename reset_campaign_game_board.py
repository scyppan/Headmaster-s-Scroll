"""Audit or reset the Game Board state for exactly one campaign.

The command is a dry run unless ``--apply`` is supplied.  Applied resets use
the shared JSON store so the previous ``campaign.json`` revision is preserved
in its timestamped backup directory before the atomic replacement.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from headmasters_scroll.campaigns import CampaignRepository  # noqa: E402
from headmasters_scroll.store import SharedJsonStore  # noqa: E402


def _target_campaign(
    campaigns: list[dict],
    *,
    campaign_id: str = "",
    campaign_name: str = "",
) -> dict:
    if campaign_id:
        matches = [item for item in campaigns if item["record_id"] == campaign_id]
    else:
        matches = [item for item in campaigns if item["name"] == campaign_name]
    if not matches:
        raise ValueError("No campaign exactly matched the requested target")
    if len(matches) != 1:
        raise ValueError("The requested target matched more than one campaign; use its ID")
    return matches[0]


def _summary(campaign: dict) -> dict:
    state = campaign["game_state"]
    return {
        "campaign_id": campaign["record_id"],
        "campaign_name": campaign["name"],
        "current_game_datetime": state["current_game_datetime"],
        "initialized": state["initialized"],
        "loaded_maps": len(state["loaded_map_ids"]),
        "saved_map_states": len(state["maps"]),
        "saved_people": len(state["people"]),
        "saved_creatures": len(state["creatures"]),
        "saved_groups": len(state["groups"]),
        "saved_battles": len(state["battles"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset exactly one campaign's Game Board without changing its clock."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--campaign-id")
    target.add_argument("--campaign-name")
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()

    repository = CampaignRepository(SharedJsonStore(ROOT / "data"))
    campaign = _target_campaign(
        repository.list(),
        campaign_id=str(arguments.campaign_id or ""),
        campaign_name=str(arguments.campaign_name or ""),
    )
    print(json.dumps({"before": _summary(campaign)}, indent=2))
    if not arguments.apply:
        print("Audit only; no files changed.")
        return

    reset = repository.reset_game_state(campaign["record_id"])
    print(json.dumps({"after": _summary(reset)}, indent=2))
    print("Applied. The shared store created a recoverable timestamped backup.")


if __name__ == "__main__":
    main()
