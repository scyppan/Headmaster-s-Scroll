from __future__ import annotations

import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from headmasters_scroll.game_board.storage import GameBoardRepository


def main() -> None:
    settings = GameBoardRepository().settings()
    base = f"http://{settings['admin_host']}:{settings['admin_port']}"
    try:
        urllib.request.urlopen(f"{base}/?key={settings['admin_key']}", timeout=1).close()
    except (OSError, urllib.error.URLError):
        raise SystemExit(
            "The Game Board server is not running. Start it with:\n"
            "python -m headmasters_scroll.game_board.server"
        )
    webbrowser.open(f"{base}/?key={settings['admin_key']}")


if __name__ == "__main__":
    main()

