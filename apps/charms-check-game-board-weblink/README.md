# Charms Check Game Board Weblink

This is the player-facing WordPress client for Headmaster's Scroll Game Board. Its file structure sits beside Game Board, DBM, and Mage Maker, but it has no local launcher manifest and does not appear as a Headmaster's Scroll tile. Its published browser assets contain no contacts, session state, credentials, or canonical game data.

## Project layout

- `wordpress.html` — JavaScript-only loader for the WordPress Head Scripts field. That field supplies the surrounding `<script>` element.
- `css/game-board.css` — the parchment presentation.
- `js/game-board.js` — creates the complete player GUI inside the canonical `#gameboard` container and handles invitations, approval polling, WebSocket connection, heartbeats, announcements, and acknowledgements. The mount ID is not configurable.
- `index.html` — local visual preview. Add `?preview=waiting` or `?preview=denied` to preview those states.

## WordPress placement

Place this container on the Game Board page:

```html
<div id="gameboard"></div>
```

Paste the complete contents of `wordpress.html` into the site's **Head Scripts** field. Do not include another `<script>` element or the `<div>` in that field; WordPress already wraps the field in `<script>`.

## Version naming

Release names use `<stage>YY.M.D.NNN`:

- `a` for alpha releases, such as `a26.8.9.002`;
- `b` for beta releases;
- `v` for incremental full releases;
- `NNN` is the three-digit release increment for that date.

Set `VERSION` in `wordpress.html` to the release being prepared, commit the files, and then create the matching Git tag and GitHub release. Do not point WordPress at that version until the tag is publicly available.

The current loader uses this pinned CDN root:

```text
https://cdn.jsdelivr.net/gh/scyppan/Headmaster-s-Scroll@a26.8.9.004/apps/charms-check-game-board-weblink/
```

## Security boundary

The invitation remains in the URL fragment, so it is not sent to WordPress during the page request. The client removes it from the address bar after reading it and keeps it only in the browser session. The Weblink never requests Headmaster control routes or shared JSON data; it communicates only with the public admissions and session endpoints.
