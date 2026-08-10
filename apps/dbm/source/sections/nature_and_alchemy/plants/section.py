from core.section_definition import SectionDefinition
from .page import PlantsPage


SECTION = SectionDefinition(
    key="plants",
    title="Plants",
    order=130,
    page_class=PlantsPage,
)
