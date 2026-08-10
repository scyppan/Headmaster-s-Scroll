from shared.widgets import SearchableRecordList


class WandQualityList(SearchableRecordList):
    def __init__(self, parent, selection_command):
        super().__init__(
            parent,
            selection_command=selection_command,
            heading_text="All Qualities",
            item_word="qualities",
            unnamed_label="Unnamed quality",
        )

