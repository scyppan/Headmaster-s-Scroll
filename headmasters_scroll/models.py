from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass
class DataSession:
    filename: str
    path: Path
    base_data: dict[str, Any]
    data: dict[str, Any]
    loaded_revision: str

    def reset_to(self, value: dict[str, Any], revision: str) -> None:
        self.base_data = deepcopy(value)
        self.data = deepcopy(value)
        self.loaded_revision = revision


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
