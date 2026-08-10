from core.section_definition import SectionDefinition
from .page import SchoolsPage


SECTION = SectionDefinition(
    key="schools",
    title="Schools",
    order=20,
    page_class=SchoolsPage,
)
