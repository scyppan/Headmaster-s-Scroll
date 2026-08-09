# Free public connection with Tailscale Funnel

The Game Board uses Tailscale Funnel as its free public bridge. Players connect through the public HTTPS address printed by Tailscale; they do not install Tailscale or join the private tailnet.

## One-time setup

1. Install Tailscale for Windows.
2. Sign in with a personal Gmail, Apple, or personal GitHub account.
3. Stay on the **Personal — $0 free forever** plan. Do not enter payment information or upgrade.
4. When the first Funnel command opens the approval page, approve Funnel for this computer.

## Start the public connection

Open the native Game Board app first. Then open PowerShell as Administrator and run:

```powershell
tailscale funnel 8765
```

The output looks like this:

```text
Available on the internet:
https://your-computer.your-tailnet.ts.net

|-- / proxy http://127.0.0.1:8765
```

Copy the HTTPS address into **Connection Setup** in the native Game Board app and into `apps/charms-check-game-board-weblink/wordpress.html` as `API_BASE`.

## Stop public access

Press `Ctrl+C` in the Funnel window. Because this setup deliberately runs in the foreground, closing that command stops the public connection rather than silently leaving it enabled after a reboot.

Never Funnel port `8764`. It is the localhost-only control API used by the native Python app.
