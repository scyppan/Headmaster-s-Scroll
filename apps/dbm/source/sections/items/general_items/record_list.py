from shared.widgets import SearchableRecordList


class GeneralItemList(SearchableRecordList):
    def __init__(self, parent, selection_command):
        super().__init__(
            parent,
            selection_command=selection_command,
            heading_text="All General Items",
            item_word="general items",
            unnamed_label="Unnamed general item",
        )
