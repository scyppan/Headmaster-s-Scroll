from core.section_definition import SectionDefinition
from .page import HoldableItemsPage


SECTION = SectionDefinition(
    key="holdable_items",
    title="Holdable Items",
    order=80,
    page_class=HoldableItemsPage,
)
