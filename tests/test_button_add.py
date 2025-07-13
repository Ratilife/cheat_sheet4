from tests.mock_models import MockButtonModel
from srs.start_panel.view_models.view_model import ButtonViewModel


def test_button_add():
    model = MockButtonModel()
    view_model = ButtonViewModel(model)

    view_model.add_button("New", "/new/path")  #Изменить путь
    assert len(view_model.get_buttons()) == 2