__all__ = ("LocationController",)


def __getattr__(name):
    if name == "LocationController":
        from mage_maker.sections.locations.controller import (
            LocationController,
        )

        return LocationController

    raise AttributeError(name)
