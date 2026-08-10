from core.section_definition import SectionDefinition
from .page import ProficienciesPage


SECTION = SectionDefinition(
    key="proficiencies",
    title="Proficiencies",
    order=200,
    page_class=ProficienciesPage,
)
