from core.section_definition import SectionDefinition
from .page import CreaturePartsPage


SECTION = SectionDefinition(
    key="creature_parts",
    title="Creature Parts",
    order=120,
    page_class=CreaturePartsPage,
    visible=False,
)
