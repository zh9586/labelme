from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt


class EscapableQListWidget(QtWidgets.QListWidget):
    def keyPressEvent(self, event):  # 是一个事件处理方法，用于捕捉键盘上的按键事件。每当用户按下键盘上的键时，keyPressEvent 会被触发。
        super(EscapableQListWidget, self).keyPressEvent(event)  # event 是传递给 keyPressEvent 的事件对象，其中包含了按键的信息，如按下的键、键的状态等。
        if event.key() == Qt.Key_Escape:
            self.clearSelection()
