from core.section_definition import SectionDefinition
from .page import BookshelvesPage


SECTION = SectionDefinition(
    key="bookshelves",
    title="Bookshelves",
    order=190,
    page_class=BookshelvesPage,
)
