from typing import Dict, List
from PySide6.QtCore import QObject, Signal
from srs.start_panel.models.model_delete_buttons import DeleteButtonsModel
from srs.start_panel.models.model import ButtonModel

class DeleteButtonsViewModel(QObject):
    def __init__(self, model):
        super().__init__()
        self._model = model  # Ссылка на ButtonListModel (model)
        self._delete_model = DeleteButtonsModel(model)  # Создаем DeleteButtonsModel (model_delete_buttons)
    # Сигнал для уведомления View об изменении данных
    buttonsUpdated = Signal()

    def get_buttons(self) -> List[ButtonModel]:
        """
        Возвращает список кнопок.
        """
        return self._model.get_buttons()

    def set_selected(self, name: str, selected: bool):
        """
        Устанавливает отметку для кнопки.
        """
        self._delete_model.set_selected(name, selected)
        self.buttonsUpdated.emit()

    def get_selected_buttons(self) -> List[str]:
        """
        Возвращает список имен кнопок, которые были отмечены для удаления.
        """
        return self._delete_model.get_selected_buttons()

    def get_selected_indices(self) -> List[int]:
        # Возвращает индексы выбранных кнопок, а не их имена
        selected_indices = []
        for i in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(i, 1)
            if checkbox.isChecked():
                selected_indices.append(i)
        return selected_indices
    def get_selected_buttons_index(self) -> List[str]:
        # возможно удалить
        return self._delete_model.get_selected_buttons_index()



    #описать метод на удаление 
    def remove_button_list(self,list):
        return self._model.remove_button_list(list)