from shared.widgets import SearchableRecordList


class WandCoreList(SearchableRecordList):
    def __init__(self, parent, selection_command):
        super().__init__(
            parent,
            selection_command=selection_command,
            heading_text="All Cores",
            item_word="cores",
            unnamed_label="Unnamed core",
        )
