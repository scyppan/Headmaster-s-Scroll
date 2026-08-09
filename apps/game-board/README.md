# Game Board setup

Game Board is a native Python desktop app for the Headmaster. Its private controls are never served as a website. The player-facing service is separate, and the free Tailscale Funnel points only to that player port.

## Install the Python dependencies

From the Headmaster's Scroll repository:

```powershell
python -m pip install -e ".[game-board]"
```

## Open Game Board

Launch Headmaster's Scroll and select the **Game Board** tile. The Python window starts the local communication service automatically and provides native tabs for:

- players and email addresses;
- session creation and invitation sending;
- pending admission approval or denial;
- currently connected players and connection quality;
- announcements, revocation, pausing, and ending a session;
- WordPress, public connection, and Gmail settings.

Closing Game Board stops the communication service that its window started. It does not stop a separately started Tailscale Funnel command.

For diagnostics or headless use, the local service can still be started manually:

```powershell
python -m headmasters_scroll.game_board.server
```

## Configure Gmail

1. Create a Google Cloud project, enable the Gmail API, and configure the OAuth consent screen.
2. Create an OAuth client with application type **Desktop app**.
3. Download its JSON file to the repository as `credentials.json`. This path is ignored by Git.
4. Open the native Game Board window, complete **Connection Setup**, and select **Connect Gmail**.

Only the `gmail.send` scope is requested. The refresh token is stored in Windows Credential Manager rather than a project file.

## Configure the WordPress Weblink

The player interface lives in the sibling app folder `apps/charms-check-game-board-weblink/`. It has no launcher manifest, so it does not appear as a local tile. Its root-level `wordpress.html` is the loader intended for a WordPress Custom HTML block. JavaScript creates the player interface inside `<div id="gameboard">`.

1. Publish Headmaster's Scroll and create the release tag referenced by the Weblink loader.
2. Paste the complete contents of `apps/charms-check-game-board-weblink/wordpress.html` into a WordPress Custom HTML block.
3. Enter the published WordPress page URL, its exact origin, and the Tailscale Funnel URL under **Connection Setup** in the native app.

The existing WordPress signup and page-access system remains independent of Game Board.

## Start the free public connection

Open PowerShell as Administrator and run:

```powershell
tailscale funnel 8765
```

Tailscale forwards the public HTTPS hostname only to `http://127.0.0.1:8765`. Never expose port `8764`; that localhost-only port accepts the native app's private control requests.

Press `Ctrl+C` in the Funnel window to remove public access. **End Session** revokes invitations and disconnects players but intentionally leaves the manually managed Funnel command alone.
