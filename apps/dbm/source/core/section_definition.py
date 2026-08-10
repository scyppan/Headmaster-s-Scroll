from dataclasses import dataclass


@dataclass(frozen=True)
class SectionDefinition:
    key: str
    title: str
    order: int
    page_class: type
    storage_key: str | None = None
    storage_type: str | None = "collection"
    visible: bool = True

    @property
    def database_key(self):
        return self.storage_key or self.key
