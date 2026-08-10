from shared.widgets import SearchableRecordList


class AccessoryList(SearchableRecordList):
    def __init__(self, parent, selection_command):
        super().__init__(
            parent,
            selection_command=selection_command,
            heading_text="All Accessories",
            item_word="accessories",
            unnamed_label="Unnamed accessory",
        )
