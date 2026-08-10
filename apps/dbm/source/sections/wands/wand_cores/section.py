from core.section_definition import SectionDefinition
from .page import WandCoresPage


SECTION = SectionDefinition(
    key="wand_cores",
    title="Wand Cores",
    order=40,
    page_class=WandCoresPage,
    visible=False,
)
