from core.section_definition import SectionDefinition
from .page import PreparationsPage


SECTION = SectionDefinition(
    key="preparations",
    title="Preparations",
    order=150,
    page_class=PreparationsPage,
    visible=False,
)
