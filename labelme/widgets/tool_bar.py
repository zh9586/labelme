from PyQt5 import QtCore
from PyQt5 import QtWidgets


class ToolBar(QtWidgets.QToolBar):  # 它就是工具栏一个按钮的抽象
    def __init__(self, title):
        super(ToolBar, self).__init__(title)
        layout = self.layout()  # 默认是QBoxLayout风格的布局，可以QVBoxLayout/QHBoxLayout
        m = (0, 0, 0, 0)
        layout.setSpacing(0)  # 设置控件之间的间距为 0
        layout.setContentsMargins(*m)  # 设置工具栏内部的边距
        self.setContentsMargins(*m)  # 设置整个工具栏相对于窗口的边距
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.FramelessWindowHint)  # 就是按位进行设置，窗口的标志，一个窗口有多个标志，比如显示系统菜单？有无标识栏等。
        # self.windowFlags()窗口的标志是一系列；QtCore.Qt.FramelessWindowHint 去掉窗口的边框；self.setWindowFlags(...) 重新应用窗口标志，使工具栏变得无边框。

    def addAction(self, action):
        if isinstance(action, QtWidgets.QWidgetAction):
            return super(ToolBar, self).addAction(action)
        btn = QtWidgets.QToolButton()  # 专门用于工具栏的按钮，比普通 QPushButton 更适合工具栏
        btn.setDefaultAction(action)  # 让 btn 继承 action 的行为，比如点击事件、文本、图标等
        btn.setToolButtonStyle(self.toolButtonStyle())  # 让按钮的 ToolButtonStyle 继承自 ToolBar 本身的 ToolButtonStyle，确保所有按钮的风格一致。
        self.addWidget(btn)  # self.addWidget(btn) 直接把 QToolButton 加入 QToolBar。也就是直接把按钮加到工具栏。

        # center align
        for i in range(self.layout().count()):  # 获取工具栏里的所有控件数量。并遍历。
            if isinstance(self.layout().itemAt(i).widget(), QtWidgets.QToolButton):   # 获取第 i 个控件，并判断是否是 QToolButton
                self.layout().itemAt(i).setAlignment(QtCore.Qt.AlignCenter)  # 如果是 QToolButton，就让它 setAlignment(QtCore.Qt.AlignCenter)，让按钮居中显示
