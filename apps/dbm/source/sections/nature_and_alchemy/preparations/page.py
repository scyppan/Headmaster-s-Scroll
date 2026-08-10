from sections.nature_and_alchemy.potions.editor_page import (
    AlchemyFormulaPage,
)
from sections.nature_and_alchemy.preparations.controller import (
    PreparationController,
)
from sections.nature_and_alchemy.preparations.record_form import (
    PreparationForm,
)


class PreparationsPage(AlchemyFormulaPage):
    def __init__(self, parent, database):
        super().__init__(
            parent,
            database,
            "preparations",
            "Preparations",
            "preparation",
            controller_class=PreparationController,
            form_class=PreparationForm,
        )
