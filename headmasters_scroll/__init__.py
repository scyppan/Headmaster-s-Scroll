"""Shared foundation for the Headmaster's Scroll application suite."""

from .models import Conflict, DataSession, SaveOutcome
from .store import SharedJsonStore

__all__ = ["Conflict", "DataSession", "SaveOutcome", "SharedJsonStore"]

