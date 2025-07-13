import sys
from PySide6.QtWidgets import QApplication
from srs.start_panel.views.view import MainWindow
from srs.start_panel.view_models.view_model import ButtonViewModel
from srs.start_panel.models.model import ButtonListModel

def start():
    app = QApplication([])

    # Создаем Model
    model = ButtonListModel()

    # Создаем ViewModel и передаем ей Model
    view_model = ButtonViewModel(model)

    # Создаем View и передаем ему ViewModel
    window = MainWindow(view_model)
    window.show()

    sys.exit(app.exec())

if __name__ == '__main__':
    start()


