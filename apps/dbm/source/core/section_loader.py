import importlib
import pkgutil
from operator import attrgetter

import sections
from core.section_definition import SectionDefinition


def load_sections():
    discovered_sections = []

    for module_info in pkgutil.walk_packages(
        sections.__path__,
        prefix="sections.",
    ):
        if not module_info.name.endswith(".section"):
            continue

        section_module = importlib.import_module(module_info.name)
        section_definition = getattr(section_module, "SECTION", None)

        if not isinstance(section_definition, SectionDefinition):
            raise TypeError(
                f"{module_info.name} must expose a SectionDefinition named SECTION"
            )

        if section_definition.visible:
            discovered_sections.append(section_definition)

    discovered_sections.sort(key=attrgetter("order"))

    section_keys = [section.key for section in discovered_sections]
    section_titles = [section.title for section in discovered_sections]

    if len(section_keys) != len(set(section_keys)):
        raise ValueError("Every section must have a unique key")

    if len(section_titles) != len(set(section_titles)):
        raise ValueError("Every section must have a unique title")

    if not discovered_sections:
        raise RuntimeError("No application sections were discovered")

    return discovered_sections
