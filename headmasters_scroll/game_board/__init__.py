"""Game Board session hosting, admission, and monitoring."""

ADMIN_API_REVISION = "campaign-actors-v3"

from .service import GameBoardService
from .storage import GameBoardRepository

__all__ = ["ADMIN_API_REVISION", "GameBoardRepository", "GameBoardService"]
