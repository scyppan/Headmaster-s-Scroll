# Charms Check Game Board Weblink

This is the player-facing WordPress client for Headmaster's Scroll Game Board. Its file structure sits beside Game Board, DBM, and Mage Maker, but it has no local launcher manifest and does not appear as a Headmaster's Scroll tile. Its published browser assets contain no contacts, session state, credentials, or canonical game data.

## Project layout

- `wordpress.html` — paste this root-level loader into a WordPress Custom HTML block.
- `css/game-board.css` — the parchment presentation.
- `js/game-board.js` — invitations, approval polling, WebSocket connection, heartbeats, announcements, and acknowledgements.
- `index.html` — local visual preview. Add `?preview=waiting` or `?preview=denied` to preview those states.

## First publication

1. Publish Headmaster's Scroll and tag the release as `v0.2.0`.
2. Confirm the Weblink assets are present under `apps/charms-check-game-board-weblink/` in that tag.
3. In `wordpress.html`, replace `https://game.example.com` with the stable HTTPS hostname for the named Cloudflare Tunnel.
4. Paste the complete contents of `wordpress.html` into the WordPress page's Custom HTML block.
5. Configure Headmaster's Scroll with that exact WordPress origin and player page URL.

The loader uses this pinned CDN root:

```text
https://cdn.jsdelivr.net/gh/scyppan/Headmaster-s-Scroll@v0.2.0/apps/charms-check-game-board-weblink/
```

For later releases, create a new Git tag and change only `VERSION` in `wordpress.html`. A release tag is preferred to `main` because the files for an invitation session remain stable and cacheable.

## Security boundary

The invitation remains in the URL fragment, so it is not sent to WordPress during the page request. The client removes it from the address bar after reading it and keeps it only in the browser session. The Weblink never requests Headmaster dashboard routes or shared JSON data; it communicates only with the public admissions and session endpoints.
