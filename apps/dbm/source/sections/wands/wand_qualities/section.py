from core.section_definition import SectionDefinition
from .page import WandQualitiesPage


SECTION = SectionDefinition(
    key="wand_qualities",
    title="Wand Qualities",
    order=50,
    page_class=WandQualitiesPage,
    visible=False,
)
