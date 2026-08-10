from core.section_definition import SectionDefinition
from .page import PlantPartsPage


SECTION = SectionDefinition(
    key="plant_parts",
    title="Plant Parts",
    order=140,
    page_class=PlantPartsPage,
    visible=False,
)
