from shared.widgets import SearchableRecordList


class WandMakerList(SearchableRecordList):
    def __init__(self, parent, selection_command):
        super().__init__(
            parent,
            selection_command=selection_command,
            heading_text="All Makers",
            item_word="makers",
            unnamed_label="Unnamed maker",
        )
