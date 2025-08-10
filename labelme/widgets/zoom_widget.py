from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets


class ZoomWidget(QtWidgets.QSpinBox):  # 其实就是显示缩放比例的敞口。
    def __init__(self, value=100):
        super(ZoomWidget, self).__init__()
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)  # 关闭增减按钮
        self.setRange(1, 1000)  # 缩放比例从1~1000
        self.setSuffix(" %")  # 在数字后面自动显示后缀字符串 " %"，比如显示为 100 %，更直观表示是百分比
        self.setValue(value)  # 设置初始值为传入的参数 value，默认是 100
        self.setToolTip("Zoom Level")  # 设置鼠标悬停时显示的提示文本 "Zoom Level"，告诉用户这是“缩放级别”。
        self.setStatusTip(self.toolTip())  # 设置状态栏提示文本，和工具提示一样，通常在窗口底部状态栏显示，方便用户理解控件用途。
        self.setAlignment(QtCore.Qt.AlignCenter)  # 设置数字文本居中对齐，使显示更美观。

    def minimumSizeHint(self):  # 返回控件的最小推荐大小。
        height = super(ZoomWidget, self).minimumSizeHint().height()  # 调用父类的 minimumSizeHint() 方法，获取默认建议的高度。
        fm = QtGui.QFontMetrics(self.font())  # 获取当前字体的度量信息，用来测量文本宽度。
        width = fm.width(str(self.maximum()))  # 计算最大值（1000）对应字符串宽度，即测量“1000”这个文本需要多宽
        return QtCore.QSize(width, height)  # 返回一个 QSize 对象，表示控件最小宽度为最大数字宽度，高度为默认高度。
