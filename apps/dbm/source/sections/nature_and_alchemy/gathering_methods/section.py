from core.section_definition import SectionDefinition
from .page import GatheringMethodsPage


SECTION = SectionDefinition(
    key="gathering_methods",
    title="Searching Methods",
    order=128,
    page_class=GatheringMethodsPage,
    storage_type=None,
    visible=False,
)
