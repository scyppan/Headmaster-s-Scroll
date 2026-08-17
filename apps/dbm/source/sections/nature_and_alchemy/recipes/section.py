from core.section_definition import SectionDefinition
from .page import RecipesPage


SECTION = SectionDefinition(
    key="recipes",
    title="Recipes",
    order=165,
    page_class=RecipesPage,
)
