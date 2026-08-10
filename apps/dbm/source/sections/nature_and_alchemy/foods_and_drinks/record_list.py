from shared.widgets import SearchableRecordList


class RecordList(SearchableRecordList):
    def __init__(self, parent, selection_command):
        super().__init__(
            parent,
            selection_command=selection_command,
            heading_text="All Items",
            item_word="items",
            unnamed_label="Unnamed record",
        )
