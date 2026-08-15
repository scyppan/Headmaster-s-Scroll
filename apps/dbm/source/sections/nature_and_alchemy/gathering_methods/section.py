from core.section_definition import SectionDefinition
from .page import GatheringMethodsPage


SECTION = SectionDefinition(
    key="gathering_methods",
    title="Gathering & Stock",
    order=128,
    page_class=GatheringMethodsPage,
    storage_type=None,
)
