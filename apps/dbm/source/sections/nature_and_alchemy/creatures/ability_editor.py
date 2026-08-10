from sections.nature_and_alchemy.creatures.attack_editor import AttackEditor


class AbilityEditor(AttackEditor):
    def __init__(self, parent, change_command):
        super().__init__(parent, change_command, list_height=4)
        self.configure(text="Abilities")
        self.add_button.set_text("Add Ability")
        self.add_button.command = self.add_ability
        self.name_field.label.configure(text="Ability Name")
        self.roll_field.label.configure(text="Ability Roll")
        self.description_field.label.configure(text="Ability Description")
        self.refresh_list()

    def set_abilities(self, abilities):
        self.set_attacks(abilities)

    def get_abilities(self):
        try:
            return self.get_attacks()
        except ValueError as error:
            raise ValueError(str(error).replace("attack", "ability")) from None

    def add_ability(self):
        self.add_attack()
        self.attacks[self.selected_index]["name"] = "New Ability"
        self.name_field.set_value("New Ability")
        self.refresh_list()

    def refresh_list(self):
        super().refresh_list()
        self.count_label.configure(text=f"{len(self.attacks)} abilities")
