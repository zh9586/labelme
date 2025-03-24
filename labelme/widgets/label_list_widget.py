from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QStyle


# https://stackoverflow.com/a/2039745/4158863
class HTMLDelegate(QtWidgets.QStyledItemDelegate):
    # QStyledItemDelegate，它用于在 Qt 的视图控件中自定义绘制列表项的显示方式，尤其是当列表项的文本包含 HTML 内容时。
    def __init__(self, parent=None):
        super(HTMLDelegate, self).__init__()
        self.doc = QtGui.QTextDocument(self)  # QTextDocument 是 Qt 中用于处理和显示富文本的类，它支持 HTML 格式的文本。

    def paint(self, painter, option, index):  # 用于绘制的绘图设备; 绘制项的样式选项（如大小、颜色等）;该项在模型中的索引
        painter.save()  # 保存当前绘图状态，以便稍后恢复。

        options = QtWidgets.QStyleOptionViewItem(option)

        self.initStyleOption(options, index)
        self.doc.setHtml(options.text)
        options.text = ""  # 将 options 对象中的文本设置为空，因为我们已经将文本传递给 QTextDocument 进行渲染。

        style = (
            QtWidgets.QApplication.style()  # todo 暂时先不看
            if options.widget is None
            else options.widget.style()
        )
        style.drawControl(QStyle.CE_ItemViewItem, options, painter)

        ctx = QtGui.QAbstractTextDocumentLayout.PaintContext()

        if option.state & QStyle.State_Selected:
            ctx.palette.setColor(
                QPalette.Text,
                option.palette.color(QPalette.Active, QPalette.HighlightedText),
            )
        else:
            ctx.palette.setColor(
                QPalette.Text,
                option.palette.color(QPalette.Active, QPalette.Text),
            )

        textRect = style.subElementRect(QStyle.SE_ItemViewItemText, options)

        if index.column() != 0:
            textRect.adjust(5, 0, 0, 0)

        thefuckyourshitup_constant = 4
        margin = (option.rect.height() - options.fontMetrics.height()) // 2
        margin = margin - thefuckyourshitup_constant
        textRect.setTop(textRect.top() + margin)

        painter.translate(textRect.topLeft())
        painter.setClipRect(textRect.translated(-textRect.topLeft()))
        self.doc.documentLayout().draw(painter, ctx)

        painter.restore()

    def sizeHint(self, option, index):
        thefuckyourshitup_constant = 4
        return QtCore.QSize(
            int(self.doc.idealWidth()),
            int(self.doc.size().height() - thefuckyourshitup_constant),
        )


class LabelListWidgetItem(QtGui.QStandardItem):
    # QtGui.QStandardItem 用来表示一个项的数据。它是 QAbstractItemModel 中的数据表示单元。
    def __init__(self, text=None, shape=None):  # text 是项的显示文本，shape 是与项相关联的形状数据。
        super(LabelListWidgetItem, self).__init__()
        self.setText(text or "")
        self.setShape(shape)

        self.setCheckable(True)  # 设置该项为可勾选状态
        self.setCheckState(Qt.Checked)  # 设置项的勾选状态为“已勾选”。
        self.setEditable(False)  # 设置该项为不可编辑状态，用户无法更改该项的文本。
        self.setTextAlignment(Qt.AlignBottom)  # 设置文本的对齐方式为底部对齐。

    def clone(self):
        return LabelListWidgetItem(self.text(), self.shape())  # 重载了该方法，本身返回的是QStandardItem

    def setShape(self, shape):
        self.setData(shape, Qt.UserRole)

    def shape(self):
        return self.data(Qt.UserRole)

    def __hash__(self):
        return id(self)

    def __repr__(self):
        return '{}("{}")'.format(self.__class__.__name__, self.text())


class StandardItemModel(QtGui.QStandardItemModel):
    # QtGui.QStandardItemModel 用于管理和存储项（Item）数据，每个项可以是一个独立的数据单元，通常与视图控件的行、列和层级结构相对应。它主要用于提供一个统一的接口来管理这些数据，并支持增、删、改、查等操作。
    itemDropped = QtCore.pyqtSignal()

    def removeRows(self, *args, **kwargs):  # 重写了该方法。
        ret = super().removeRows(*args, **kwargs)
        self.itemDropped.emit()  # 当删除行时，不仅用父类方法中进行删除，而且发射一个信号，通知其他部分有一行数据已经被删除。
        return ret


class LabelListWidget(QtWidgets.QListView):
    itemDoubleClicked = QtCore.pyqtSignal(LabelListWidgetItem)  # 双击信号，双击文件名，就显示相应的图像。
    itemSelectionChanged = QtCore.pyqtSignal(list, list)  # 被选中的项列表和被取消选中的项列表，表示列表中的选择发生了变化。itemSelectionChanged 是一个可以发出两个 list 类型参数的信号。

    def __init__(self):
        super(LabelListWidget, self).__init__()  # 调用父类 QListView 的构造函数，初始化 QListView 小部件
        self._selectedItems = []

        self.setWindowFlags(Qt.Window)  # 设置 LabelListWidget 小部件的窗口标志，使其表现得像一个独立的窗口。
        self.setModel(StandardItemModel())  # 设置视图的小部件模型为StandardItemModel, 用于管理视图项的数据。
        self.model().setItemPrototype(LabelListWidgetItem())  # 设置模型的原型项为LabelListWidgetItem，即每个列表项将使用该类型的项。
        self.setItemDelegate(HTMLDelegate())  # 设置视图的委托为 HTMLDelegate，使得项能够支持 HTML 格式的文本显示。
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)  # 设置选择模式为扩展选择（可以多选），允许用户选择多个项。
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)  # 设置拖放模式为内部移动（允许在同一视图中拖动项）。
        self.setDefaultDropAction(Qt.MoveAction)  # 设置默认的拖放操作为移动（当用户拖动项时，默认执行“移动”操作）。

        self.doubleClicked.connect(self.itemDoubleClickedEvent)  # 当用户双击某项时触发该槽self.itemDoubleClickedEvent
        self.selectionModel().selectionChanged.connect(self.itemSelectionChangedEvent)  # 当选择发生变化时触发该槽

    def __len__(self):
        return self.model().rowCount()

    def __getitem__(self, i):
        return self.model().item(i)

    def __iter__(self):
        for i in range(len(self)):
            yield self[i]

    @property
    def itemDropped(self):
        return self.model().itemDropped  # 返回模型的 itemDropped 信号，表示项被拖动到新位置。这里的 "项" 具体来说是 LabelListWidgetItem 类型的元素。

    @property
    def itemChanged(self):
        return self.model().itemChanged  # 表示项的内容发生了变化。

    def itemSelectionChangedEvent(self, selected, deselected):
        selected = [self.model().itemFromIndex(i) for i in selected.indexes()]
        deselected = [self.model().itemFromIndex(i) for i in deselected.indexes()]
        self.itemSelectionChanged.emit(selected, deselected)  # 信号带两个list参数被发射出去。

    def itemDoubleClickedEvent(self, index):
        self.itemDoubleClicked.emit(self.model().itemFromIndex(index))

    def selectedItems(self):
        return [self.model().itemFromIndex(i) for i in self.selectedIndexes()]  # 获取已选择项

    def scrollToItem(self, item):
        self.scrollTo(self.model().indexFromItem(item))  # 滚动视图，使指定的 item 可见。

    def addItem(self, item):
        if not isinstance(item, LabelListWidgetItem):
            raise TypeError("item must be LabelListWidgetItem")
        self.model().setItem(self.model().rowCount(), 0, item)
        item.setSizeHint(self.itemDelegate().sizeHint(None, None))

    def removeItem(self, item):
        index = self.model().indexFromItem(item)
        self.model().removeRows(index.row(), 1)

    def selectItem(self, item):
        index = self.model().indexFromItem(item)
        self.selectionModel().select(index, QtCore.QItemSelectionModel.Select)

    def findItemByShape(self, shape):  # todo 这里的shape是什么？
        for row in range(self.model().rowCount()):
            item = self.model().item(row, 0)
            if item.shape() == shape:
                return item
        raise ValueError("cannot find shape: {}".format(shape))

    def clear(self):
        self.model().clear()  # 清除视图中的所有项。通过调用模型的 clear() 方法来清除数据。
