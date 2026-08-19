"""Audit or compact redundant campaign person-state snapshots.

Campaign actor state is an overlay on the World Builder person.  Fields equal
to the documented defaults are implicit and are reconstructed by the campaign
normalizer at read time.  This keeps thousands of unchanged people out of each
campaign while retaining every placement, wound, inventory item, reveal, note,
equipment choice, currency balance, and battle participant.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from headmasters_scroll.campaigns import (  # noqa: E402
    compact_campaign_document_for_storage,
    normalize_campaign,
)
from headmasters_scroll.store import SharedJsonStore  # noqa: E402


def encoded_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def build_report(source: dict, compacted: dict) -> dict:
    campaigns_before = source.get("campaigns", []) or []
    campaigns_after = compacted.get("campaigns", []) or []
    rows = []
    for before, after in zip(campaigns_before, campaigns_after, strict=False):
        before_people = (before.get("game_state", {}) or {}).get("people", {}) or {}
        after_people = (after.get("game_state", {}) or {}).get("people", {}) or {}
        rows.append({
            "campaign_id": str(before.get("record_id", "") or ""),
            "campaign_name": str(before.get("name", "") or ""),
            "person_snapshots_before": len(before_people),
            "person_overlays_after": len(after_people),
            "default_snapshots_removed": len(before_people) - len(after_people),
        })
    before_bytes = encoded_size(source)
    after_bytes = encoded_size(compacted)
    return {
        "campaigns": rows,
        "bytes_before": before_bytes,
        "bytes_after": after_bytes,
        "bytes_removed": before_bytes - after_bytes,
        "percent_removed": round(
            ((before_bytes - after_bytes) / before_bytes * 100) if before_bytes else 0,
            2,
        ),
    }


def verify(source: dict, compacted: dict) -> None:
    source_campaigns = source.get("campaigns", []) or []
    compact_campaigns = compacted.get("campaigns", []) or []
    if len(source_campaigns) != len(compact_campaigns):
        raise ValueError("Campaign count changed during overlay compaction")
    for source_campaign, stored_campaign in zip(
        source_campaigns, compact_campaigns, strict=False
    ):
        before = normalize_campaign(deepcopy(source_campaign))
        after = normalize_campaign(deepcopy(stored_campaign))
        stored_people = after["game_state"]["people"]
        for person_id, stored_state in stored_people.items():
            if stored_state != before["game_state"]["people"].get(person_id):
                raise ValueError(
                    f"Campaign overlay changed meaningful state for {person_id}"
                )
        before_ids = set(before["game_state"]["people"])
        removed_ids = before_ids - set(stored_people)
        for person_id in removed_ids:
            original = before["game_state"]["people"][person_id]
            trial = deepcopy(stored_campaign)
            trial["game_state"]["people"][person_id] = {}
            implicit = normalize_campaign(trial)["game_state"]["people"][person_id]
            if original != implicit:
                raise ValueError(
                    f"Campaign overlay would discard state for {person_id}"
                )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    store = SharedJsonStore(ROOT / "data")
    source = store.read_document("campaign.json")
    compacted = compact_campaign_document_for_storage(source)
    verify(source, compacted)
    report = build_report(source, compacted)
    print(json.dumps(report, indent=2))
    if not arguments.apply:
        print("Audit only; no files changed.")
        return
    session = store.load("campaign.json")
    session.data = compact_campaign_document_for_storage(session.data)
    verify(session.base_data, session.data)
    outcome = store.save(session, "campaign-normalizer")
    if not outcome.saved:
        raise RuntimeError("Campaign data changed during compaction; rerun the audit")
    print("Applied. The shared store created a recoverable timestamped backup.")


if __name__ == "__main__":
    main()
