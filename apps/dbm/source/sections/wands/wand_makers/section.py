from core.section_definition import SectionDefinition
from .page import WandMakersPage


SECTION = SectionDefinition(
    key="wand_makers",
    title="Wand Makers",
    order=60,
    page_class=WandMakersPage,
    visible=False,
)
