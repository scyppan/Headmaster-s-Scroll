__all__ = (
    "EventController",
    "EventEditor",
    "WorldEventController",
)


def __getattr__(name):
    if name in ("EventController", "WorldEventController"):
        from mage_maker.sections.events.controller import (
            EventController,
            WorldEventController,
        )

        return (
            EventController
            if name == "EventController"
            else WorldEventController
        )

    if name == "EventEditor":
        from mage_maker.sections.events.editor import EventEditor

        return EventEditor

    raise AttributeError(name)
