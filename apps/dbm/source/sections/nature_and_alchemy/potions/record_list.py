from shared.widgets import SearchableRecordList


class AlchemyFormulaList(SearchableRecordList):
    def __init__(
        self,
        parent,
        selection_command,
        heading_text,
        item_word,
        unnamed_label,
    ):
        super().__init__(
            parent,
            selection_command=selection_command,
            heading_text=heading_text,
            item_word=item_word,
            unnamed_label=unnamed_label,
        )
