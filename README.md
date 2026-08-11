# Headmaster's Scroll

Headmaster's Scroll is the local home for Charms Check desktop applications. The canonical JSON files live in `data/`; applications live in `apps/` and use the shared `headmasters_scroll` package to load and save them safely.

Project-wide record-selection, canvas, and toolbar requirements are documented in [`docs/INTERFACE_CONVENTIONS.md`](docs/INTERFACE_CONVENTIONS.md).

## Run the home screen

```powershell
python main.py
```

The Scroll launches Game Board, World Builder, DBM, and Mapper as separate native Python applications. Game Board starts its local communication service automatically. See `apps/game-board/README.md` for Gmail, WordPress, free Tailscale Funnel, and setup instructions.

## Private portraits and maps

World Builder converts imported character portraits to 512×512 WebP files. Mapper imports map images without embedding them in JSON. Both kinds of image live under the Git-ignored `data/assets/` directory; `world.json` contains only stable asset IDs, hashes, dimensions, and media metadata.

These images are intentionally not published to GitHub. Back up `data/assets/` separately alongside the canonical JSON backups. During a game, the player service exposes only images visible to that admitted connection using a temporary credential that expires on disconnect, revocation, expiration, or session end.

## Mapper polygon editor

Mapper accepts PNG, JPEG, WebP, and SVG base maps. SVG imports are safely rendered to bounded PNG files; the source SVG is not copied into the project. Select **Draw Polygon**, click each corner, and press Enter or double-click to complete a shape. Escape cancels an unfinished shape. The right panel stores its free-text Type, fixed Behavior, hover text, and optional Travel destination. Middle-drag pans, the mouse wheel zooms around the cursor, and **Fit Map** restores the full-map view.

Only completed polygons are saved. They remain Headmaster-only authoring data until interactive Game Board behavior is implemented.

## Shared data API

```python
from headmasters_scroll import SharedJsonStore

store = SharedJsonStore()
session = store.load("world.json")
session.data["people"][0]["notes"] = "Updated locally"
result = store.save(session, app_id="world-builder")
```

If `result.status == "conflicts"`, present `result.conflicts` as line items. Map each `conflict_id` to `"app"` or `"disk"`, then call `save_with_resolutions` with `result.disk_revision`. A changed disk revision causes a fresh comparison instead of overwriting newer work.

App manifests are stored at `apps/<app-id>/app.json`. Enabled apps require an entry command and are launched in a separate process. App-specific preferences use `Preferences(app_id)` and are written beneath the ignored `runtime/preferences/` directory.

## Tests

```powershell
python -m pytest -q tests
```

Install Game Board's optional server and Gmail dependencies before running its API integration tests:

```powershell
python -m pip install -e ".[game-board]"
```
