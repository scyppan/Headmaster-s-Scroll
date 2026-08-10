from shared.widgets import SearchableRecordList


class WandWoodList(SearchableRecordList):
    def __init__(self, parent, selection_command):
        super().__init__(
            parent,
            selection_command=selection_command,
            heading_text="All Woods",
            item_word="woods",
            unnamed_label="Unnamed wood",
        )
