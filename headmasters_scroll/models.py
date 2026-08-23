from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass
class DataSession:
    filename: str
    path: Path
    base_data: dict[str, Any] | None
    data: dict[str, Any]
    loaded_revision: str
    base_snapshot: bytes | None = field(default=None, repr=False)
    loaded_fingerprint: tuple[int, int, int, int] | None = field(
        default=None,
        repr=False,
    )

    def merge_base(self) -> dict[str, Any]:
        """Return the immutable loaded document only when a merge needs it.

        Large files used to keep two complete dictionary trees in memory and
        deep-copy the newly committed tree after every save.  A serialized
        snapshot is both immutable and much smaller; the uncommon concurrent
        edit path pays the decoding cost only when it actually needs a
        three-way comparison.
        """
        if self.base_data is not None:
            return self.base_data
        if self.base_snapshot is None:
            raise RuntimeError("The data session has no merge base.")
        value = json.loads(self.base_snapshot)
        if not isinstance(value, dict):
            raise RuntimeError("The data session merge base is invalid.")
        return value

    def reset_to(
        self,
        value: dict[str, Any],
        revision: str,
        base_snapshot: bytes | None = None,
        loaded_fingerprint: tuple[int, int, int, int] | None = None,
    ) -> None:
        if base_snapshot is None:
            # Retain compatibility for manually constructed sessions while
            # the store itself always supplies the exact committed bytes.
            self.base_data = deepcopy(value)
            self.data = value
            self.base_snapshot = None
        else:
            self.base_data = None
            self.base_snapshot = base_snapshot
            # ``value`` is already this session's isolated editable document.
            # Keeping it avoids cloning the entire world after each commit.
            self.data = value
        self.loaded_revision = revision
        self.loaded_fingerprint = loaded_fingerprint


@dataclass(frozen=True)
class Conflict:
    conflict_id: str
    file: str
    collection: str
    record_id: str | None
    field_path: str
    loaded_value: Any
    app_value: Any
    disk_value: Any
    locator: tuple[Any, ...] = field(repr=False, compare=False)
    disk_missing: bool = field(default=False, repr=False, compare=False)


@dataclass
class SaveOutcome:
    status: Literal["saved", "conflicts"]
    revision_id: str | None = None
    conflicts: list[Conflict] = field(default_factory=list)
    disk_revision: str | None = None

    @property
    def saved(self) -> bool:
        return self.status == "saved"
