# Game Board setup

Game Board has a private headmaster dashboard and a separate player-facing service. The Cloudflare tunnel must point only to the player port.

## 1. Install the Python dependencies

From the Headmaster's Scroll repository:

```powershell
python -m pip install -e ".[game-board]"
```

## 2. Configure Gmail

1. Create a Google Cloud project, enable the Gmail API, and configure the OAuth consent screen.
2. Create an OAuth client with application type **Desktop app**.
3. Download its JSON file to the repository as `credentials.json`. This path is ignored by Git.
4. Start the server, open the private dashboard URL it prints, complete Connection Setup, and select **Connect Gmail**.

Only the `gmail.send` scope is requested. The refresh token is stored in Windows Credential Manager rather than a project file.

## 3. Configure the WordPress Weblink

The player interface is maintained in the sibling app folder `apps/charms-check-game-board-weblink/`. It has no launcher manifest, so it does not appear as a local tile. Its root-level `wordpress.html` is the small loader intended for the WordPress Custom HTML block.

1. Publish Headmaster's Scroll and create the release tag referenced by the Weblink loader.
2. In `apps/charms-check-game-board-weblink/wordpress.html`, replace `https://game.example.com` with the named Cloudflare hostname.
3. Paste the complete contents of that `wordpress.html` into a WordPress Custom HTML block.
4. Enter the published WordPress page URL, its exact origin, and the Cloudflare API URL in the headmaster dashboard.

The existing WordPress signup and page-access system remains independent of Game Board.

## 4. Configure the named Cloudflare Tunnel

Create a named tunnel and public hostname in Cloudflare. Use `cloudflared.example.yml` as a guide. Its only ingress target must be:

```text
http://127.0.0.1:8765
```

Do not expose port `8764`; it contains the private headmaster dashboard.

## 5. Start a game day

Start the two processes in separate terminals:

```powershell
python -m headmasters_scroll.game_board.server
cloudflared tunnel run YOUR_TUNNEL_NAME
```

The Python command prints the private dashboard URL, including its local access key. The Headmaster's Scroll Game Board tile opens the same URL while the server is running.

Use `Ctrl+C` in each terminal to stop its process. **End session** revokes invitations and disconnects players, but intentionally does not stop either manually managed process.
