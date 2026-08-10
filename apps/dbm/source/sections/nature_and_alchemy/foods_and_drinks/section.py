from core.section_definition import SectionDefinition
from .page import FoodsAndDrinksPage


SECTION = SectionDefinition(
    key="foods_and_drinks",
    title="Foods & Drinks",
    order=170,
    page_class=FoodsAndDrinksPage,
)
