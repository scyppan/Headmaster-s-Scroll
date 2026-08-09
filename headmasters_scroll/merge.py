from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .models import Conflict


MISSING = object()


@dataclass
class MergeResult:
    data: dict[str, Any]
    conflicts: list[Conflict]


def _public(value: Any) -> Any:
    return None if value is MISSING else deepcopy(value)


def _copy(value: Any) -> Any:
    return MISSING if value is MISSING else deepcopy(value)


def _same(left: Any, right: Any) -> bool:
    if left is MISSING or right is MISSING:
        return left is right
    return left == right


def _record_list(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, dict) and isinstance(item.get("record_id"), str)
        for item in value
    )


def _conflict_id(filename: str, collection: str, record_id: str | None, field_path: str) -> str:
    return "|".join((filename, collection, record_id or "-", field_path or "<record>"))


def _merge_atomic(base: Any, app: Any, disk: Any, *, filename: str, collection: str,
                  record_id: str | None, field_path: str, locator: tuple[Any, ...],
                  conflicts: list[Conflict]) -> Any:
    if _same(app, disk):
        return _copy(app)
    if _same(app, base):
        return _copy(disk)
    if _same(disk, base):
        return _copy(app)
    conflicts.append(Conflict(
        _conflict_id(filename, collection, record_id, field_path), filename,
        collection, record_id, field_path, _public(base), _public(app),
        _public(disk), locator, disk is MISSING,
    ))
    return _copy(app)


def _merge_record(base: Any, app: dict[str, Any], disk: dict[str, Any], *, filename: str,
                  collection: str, record_id: str, locator: tuple[Any, ...],
                  conflicts: list[Conflict]) -> dict[str, Any]:
    base_dict = base if isinstance(base, dict) else {}
    result: dict[str, Any] = {}
    for key in sorted(set(base_dict) | set(app) | set(disk)):
        b, a, d = base_dict.get(key, MISSING), app.get(key, MISSING), disk.get(key, MISSING)
        item_locator = locator + (key,)
        if _record_list(a) and _record_list(d) and (b is MISSING or _record_list(b)):
            value = _merge_record_lists(
                [] if b is MISSING else b, a, d, filename=filename,
                collection=collection, parent_record_id=record_id, field_path=key,
                locator=item_locator, conflicts=conflicts,
            )
        else:
            value = _merge_atomic(
                b, a, d, filename=filename, collection=collection,
                record_id=record_id, field_path=key, locator=item_locator,
                conflicts=conflicts,
            )
        if value is not MISSING:
            result[key] = value
    return result


def _merge_record_lists(base: list[dict[str, Any]], app: list[dict[str, Any]],
                        disk: list[dict[str, Any]], *, filename: str, collection: str,
                        locator: tuple[Any, ...], conflicts: list[Conflict],
                        parent_record_id: str | None = None,
                        field_path: str = "") -> list[dict[str, Any]]:
    base_map = {item["record_id"]: item for item in base}
    app_map = {item["record_id"]: item for item in app}
    disk_map = {item["record_id"]: item for item in disk}
    order = list(dict.fromkeys([*(item["record_id"] for item in disk), *(item["record_id"] for item in app)]))
    output: list[dict[str, Any]] = []
    for item_id in order:
        b, a, d = base_map.get(item_id, MISSING), app_map.get(item_id, MISSING), disk_map.get(item_id, MISSING)
        item_locator = locator + (("record_id", item_id),)
        display_id = f"{parent_record_id}/{item_id}" if parent_record_id else item_id
        if a is MISSING and d is MISSING:
            continue
        if a is MISSING:
            if b is not MISSING and _same(d, b):
                continue
            output.append(deepcopy(d))  # an edit wins over a concurrent deletion
            continue
        if d is MISSING:
            if b is not MISSING and _same(a, b):
                continue
            output.append(deepcopy(a))
            continue
        if _same(a, d):
            output.append(deepcopy(a))
        elif b is not MISSING and _same(a, b):
            output.append(deepcopy(d))
        elif b is not MISSING and _same(d, b):
            output.append(deepcopy(a))
        else:
            output.append(_merge_record(
                b, a, d, filename=filename, collection=collection,
                record_id=display_id, locator=item_locator, conflicts=conflicts,
            ))
    return output


def merge_documents(filename: str, base: dict[str, Any], app: dict[str, Any],
                    disk: dict[str, Any]) -> MergeResult:
    conflicts: list[Conflict] = []
    merged: dict[str, Any] = {}
    for key in sorted(set(base) | set(app) | set(disk)):
        if key == "_headmasters_scroll":
            merged[key] = deepcopy(disk[key])
            continue
        b, a, d = base.get(key, MISSING), app.get(key, MISSING), disk.get(key, MISSING)
        if _record_list(a) and _record_list(d) and (b is MISSING or _record_list(b)):
            value = _merge_record_lists(
                [] if b is MISSING else b, a, d, filename=filename,
                collection=key, locator=(key,), conflicts=conflicts,
            )
        else:
            value = _merge_atomic(
                b, a, d, filename=filename, collection=key, record_id=None,
                field_path=key, locator=(key,), conflicts=conflicts,
            )
        if value is not MISSING:
            merged[key] = value
    return MergeResult(merged, conflicts)


def apply_disk_resolution(document: dict[str, Any], conflict: Conflict) -> None:
    current: Any = document
    for token in conflict.locator[:-1]:
        if isinstance(token, tuple) and token[0] == "record_id":
            current = next(item for item in current if item.get("record_id") == token[1])
        else:
            current = current[token]
    final = conflict.locator[-1]
    if conflict.disk_missing:
        current.pop(final, None)
    else:
        current[final] = deepcopy(conflict.disk_value)
