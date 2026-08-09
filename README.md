# Headmaster's Scroll

Headmaster's Scroll is the local home for Charms Check desktop applications. The canonical JSON files live in `data/`; applications live in `apps/` and use the shared `headmasters_scroll` package to load and save them safely.

## Run the home screen

```powershell
python main.py
```

Mage Maker and DBM are registered as disabled placeholders for the foundation release.

## Shared data API

```python
from headmasters_scroll import SharedJsonStore

store = SharedJsonStore()
session = store.load("world.json")
session.data["people"][0]["notes"] = "Updated locally"
result = store.save(session, app_id="mage-maker")
```

If `result.status == "conflicts"`, present `result.conflicts` as line items. Map each `conflict_id` to `"app"` or `"disk"`, then call `save_with_resolutions` with `result.disk_revision`. A changed disk revision causes a fresh comparison instead of overwriting newer work.

App manifests are stored at `apps/<app-id>/app.json`. Enabled apps require an entry command and are launched in a separate process. App-specific preferences use `Preferences(app_id)` and are written beneath the ignored `runtime/preferences/` directory.

## Tests

```powershell
python -m unittest discover -s tests -v
```
