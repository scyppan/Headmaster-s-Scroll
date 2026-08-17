from core.section_definition import SectionDefinition
from .page import RawMaterialsPage


SECTION = SectionDefinition(
    key="raw_materials",
    title="Raw Materials",
    order=105,
    page_class=RawMaterialsPage,
    visible=False,
)
