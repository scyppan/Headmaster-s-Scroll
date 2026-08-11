from __future__ import annotations

from .campaigns import CampaignRepository
from .game_board.storage import GameBoardRepository
from .store import SharedJsonStore


def main() -> None:
    store = SharedJsonStore()
    campaigns = CampaignRepository(store)
    world = store.load("world.json").data
    active = GameBoardRepository().active()
    current_times = {
        str(session.get("campaign_id")): str(session.get("game_datetime") or "")
        for session in active.get("sessions", [])
        if session.get("campaign_id")
    }
    results = [
        campaigns.ensure_game_state(
            campaign["record_id"],
            world,
            current_times.get(campaign["record_id"]) or None,
        )
        for campaign in campaigns.list()
    ]
    for campaign in results:
        state = campaign["game_state"]
        print(
            f"{campaign['name']}: initialized={state['initialized']}, "
            f"loaded_maps={len(state['loaded_map_ids'])}, "
            f"people={len(state['people'])}"
        )


if __name__ == "__main__":
    main()
