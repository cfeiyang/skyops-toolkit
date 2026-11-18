"""Common section rail for the three desktop pages."""

from PySide6.QtWidgets import QButtonGroup, QStackedWidget, QVBoxLayout, QWidget

from stk_simulation.app.icons import action_button


class SectionStack(QStackedWidget):
    """Size parameter forms by the active section."""

    def sizeHint(self):
        page = self.currentWidget()
        return page.sizeHint() if page else super().sizeHint()

    def minimumSizeHint(self):
        page = self.currentWidget()
        return page.minimumSizeHint() if page else super().minimumSizeHint()

    def setCurrentIndex(self, index):
        super().setCurrentIndex(index)
        self.updateGeometry()


class SideNavigation(QWidget):
    def __init__(self, entries, stack, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(144)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self._buttons = QButtonGroup(self)
        for index, (title, artwork) in enumerate(entries):
            item = action_button(title, artwork)
            item.setObjectName("stepButton")
            item.setCheckable(True)
            self._buttons.addButton(item, index)
            layout.addWidget(item)
        layout.addStretch(1)
        self._buttons.idClicked.connect(stack.setCurrentIndex)
        stack.currentChanged.connect(self._select)
        self._select(stack.currentIndex())

    def _select(self, index):
        button = self._buttons.button(index)
        if button is not None:
            button.setChecked(True)

