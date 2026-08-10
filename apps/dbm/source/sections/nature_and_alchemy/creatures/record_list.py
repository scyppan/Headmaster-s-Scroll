from shared.widgets import SearchableRecordList


class CreatureList(SearchableRecordList):
    def __init__(self, parent, selection_command):
        super().__init__(
            parent,
            selection_command=selection_command,
            heading_text="All Creatures",
            item_word="creatures",
            unnamed_label="Unnamed creature",
        )
