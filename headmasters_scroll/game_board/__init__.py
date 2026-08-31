"""Game Board session hosting, admission, and monitoring."""

ADMIN_API_REVISION = "actor-creation-v5"

from .service import GameBoardService
from .storage import GameBoardRepository

__all__ = ["ADMIN_API_REVISION", "GameBoardRepository", "GameBoardService"]
