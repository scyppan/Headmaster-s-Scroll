from core.section_definition import SectionDefinition
from .page import BooksPage


SECTION = SectionDefinition(
    key="books",
    title="Books",
    order=180,
    page_class=BooksPage,
)
