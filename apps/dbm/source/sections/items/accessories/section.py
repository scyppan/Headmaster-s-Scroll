from core.section_definition import SectionDefinition
from .page import AccessoriesPage


SECTION = SectionDefinition(
    key="accessories",
    title="Accessories",
    order=90,
    page_class=AccessoriesPage,
)
