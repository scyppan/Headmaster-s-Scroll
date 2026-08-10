from core.section_definition import SectionDefinition
from .page import PotionsPage


SECTION = SectionDefinition(
    key="potions",
    title="Potions & Preparations",
    order=160,
    page_class=PotionsPage,
)
