from srs.start_panel.models.model  import IButtonModel, ButtonModel
from typing import List

class MockButtonModel(IButtonModel):
    """Тестовая модель, заменяющая реальную"""
    def __init__(self):
        self._buttons = [ButtonModel("Test", "/test/path")] #Изменить путь

    def get_buttons(self) -> List[ButtonModel]:
        return self._buttons

    def add_button(self, name: str, path: str):
        self._buttons.append(ButtonModel(name, path))

