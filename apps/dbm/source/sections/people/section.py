from core.section_definition import SectionDefinition
from .page import PeoplePage


SECTION = SectionDefinition(
    key="people",
    title="People",
    order=10,
    page_class=PeoplePage,
    visible=False,
)
