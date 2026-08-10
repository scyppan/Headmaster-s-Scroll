from shared.widgets import SearchableRecordList


class PlantList(SearchableRecordList):
    def __init__(self, parent, selection_command):
        super().__init__(
            parent,
            selection_command=selection_command,
            heading_text="All Plants",
            item_word="plants",
            unnamed_label="Unnamed plant",
        )
