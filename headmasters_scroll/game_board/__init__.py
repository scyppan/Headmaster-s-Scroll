"""Game Board session hosting, admission, and monitoring."""

ADMIN_API_REVISION = "session-recovery-v1"

from .service import GameBoardService
from .storage import GameBoardRepository

__all__ = ["ADMIN_API_REVISION", "GameBoardRepository", "GameBoardService"]
