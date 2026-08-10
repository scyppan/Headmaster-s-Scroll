from core.section_definition import SectionDefinition
from sections.wands.workspace import WandWorkspacePage


SECTION = SectionDefinition(
    key="wands",
    title="Wands",
    order=30,
    page_class=WandWorkspacePage,
)
