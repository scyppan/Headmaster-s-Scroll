from core.section_definition import SectionDefinition
from .page import GeneralItemsPage


SECTION = SectionDefinition(
    key="general_items",
    title="General Items",
    order=100,
    page_class=GeneralItemsPage,
)
