from core.section_definition import SectionDefinition
from .page import SpellsPage


SECTION = SectionDefinition(
    key="spells",
    title="Spells",
    order=210,
    page_class=SpellsPage,
)
