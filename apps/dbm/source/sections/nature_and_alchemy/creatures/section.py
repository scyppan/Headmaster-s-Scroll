from core.section_definition import SectionDefinition
from .page import CreaturesPage


SECTION = SectionDefinition(
    key="creatures",
    title="Creatures",
    order=110,
    page_class=CreaturesPage,
)
