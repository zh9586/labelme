import os.path as osp
from math import sqrt

import numpy as np
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

here = osp.dirname(osp.abspath(__file__))


def newIcon(icon):
    icons_dir = osp.join(here, "../icons")
    return QtGui.QIcon(osp.join(":/", icons_dir, "%s.png" % icon))


def newButton(text, icon=None, slot=None):
    b = QtWidgets.QPushButton(text)
    if icon is not None:
        b.setIcon(newIcon(icon))
    if slot is not None:
        b.clicked.connect(slot)
    return b


def newAction(  # QAction 被添加到菜单栏或工具栏，那么鼠标点击它时，会自动触发 triggered 信号。action.trigger()  # 这相当于用户点击了这个 action
    parent,  # QAction 需要一个父对象，一般是 QMainWindow、QMenu、QToolBar 等
    text,  # 按钮的文本，比如 "Open File"
    slot=None,  # 绑定的槽函数（点击时触发的操作）
    shortcut=None,  # 快捷键，可以是 'Ctrl+O' 这样的字符串
    icon=None,  # 按钮图标，通常是资源文件路径
    tip=None,  # # 鼠标悬停提示
    checkable=False,  # # 是否是可勾选的 QAction
    enabled=True,  # 是否默认启用
    checked=False,  # 如果是可勾选的 QAction，是否默认勾选
):
    """Create a new action and assign callbacks, shortcuts, etc."""
    a = QtWidgets.QAction(text, parent)  # 动作触发，可以是点击菜单，也可以快捷键，或者手动触发action.trigger()，QAction 的触发（triggered 信号）本身不区分是左击、右击、单击还是双击。
    if icon is not None:
        a.setIconText(text.replace(" ", "\n"))
        a.setIcon(newIcon(icon))
    if shortcut is not None:
        if isinstance(shortcut, (list, tuple)):
            a.setShortcuts(shortcut)
        else:
            a.setShortcut(shortcut)
    if tip is not None:
        a.setToolTip(tip)
        a.setStatusTip(tip)
    if slot is not None:
        a.triggered.connect(slot)  # 当这个 QAction 被触发时（triggered 信号发出），就去执行你绑定的 slot（槽函数）。
    if checkable:
        a.setCheckable(True)
    a.setEnabled(enabled)  # 设置动作是否可用
    a.setChecked(checked)  # 设置动作的初始勾选状态
    return a


def addActions(widget, actions): # 其实是将菜单和action绑定起来。
    for action in actions:
        if action is None:
            widget.addSeparator()  # 增加分隔符
        elif isinstance(action, QtWidgets.QMenu):
            widget.addMenu(action)  # 菜单的action
        else:
            widget.addAction(action)  # 都是自己的方法去加。


def labelValidator():  # 确保用户输入的字符串不以空格或制表符开头，并且至少有一个字符。
    return QtGui.QRegExpValidator(QtCore.QRegExp(r"^[^ \t].+"), None)  # ^: 匹配字符串的开始。[^ \t]: 这个部分意思是匹配任何不是空格（' '）或制表符（\t）的字符。.+: 匹配至少一个字符


class struct(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)  # 是 Python 每个对象 内部的 字典，它存储了该对象的所有 实例属性。


def distance(p):
    return sqrt(p.x() * p.x() + p.y() * p.y())


def distancetoline(point, line):  # 计算一个点到一条线段的距离
    p1, p2 = line
    p1 = np.array([p1.x(), p1.y()])
    p2 = np.array([p2.x(), p2.y()])
    p3 = np.array([point.x(), point.y()])
    if np.dot((p3 - p1), (p2 - p1)) < 0:
        return np.linalg.norm(p3 - p1)
    if np.dot((p3 - p2), (p1 - p2)) < 0:
        return np.linalg.norm(p3 - p2)
    if np.linalg.norm(p2 - p1) == 0:
        return np.linalg.norm(p3 - p1)
    return np.linalg.norm(np.cross(p2 - p1, p1 - p3)) / np.linalg.norm(p2 - p1)


def fmtShortcut(text):  # 用于格式化快捷键文本的函数
    mod, key = text.split("+", 1)  # 将文本按 "+" 分割成两部分，修饰符和键
    return "<b>%s</b>+<b>%s</b>" % (mod, key)  # 返回加粗的 HTML 格式化文本
