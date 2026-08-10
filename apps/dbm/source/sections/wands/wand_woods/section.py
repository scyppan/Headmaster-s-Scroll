from core.section_definition import SectionDefinition
from .page import WandWoodsPage


SECTION = SectionDefinition(
    key="wand_woods",
    title="Wand Woods",
    order=30,
    page_class=WandWoodsPage,
    visible=False,
)
