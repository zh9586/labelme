import collections
from typing import Optional

import imgviz
from loguru import logger
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

import osam
import numpy as np
from labelme._automation import polygon_from_mask
import labelme.utils
from labelme.shape import Shape

# TODO(unknown):
# - [maybe] Find optimal epsilon value.


CURSOR_DEFAULT = QtCore.Qt.ArrowCursor  # type: ignore[attr-defined]  # 普通箭头光标
CURSOR_POINT = QtCore.Qt.PointingHandCursor  # type: ignore[attr-defined]  # 手指光标，通常用于链接可点击
CURSOR_DRAW = QtCore.Qt.CrossCursor  # type: ignore[attr-defined] # 十字光标，通常用于绘图
CURSOR_MOVE = QtCore.Qt.ClosedHandCursor  # type: ignore[attr-defined]  # 闭合的手，表示拖动中
CURSOR_GRAB = QtCore.Qt.OpenHandCursor  # type: ignore[attr-defined]  # 张开的手，表示可以抓取

MOVE_SPEED = 5.0  # 鼠标更新步长为5个像素。


class Canvas(QtWidgets.QWidget):  # QGraphicsView 本身只是一个视图，它显示的是 QGraphicsScene 中的 items。
    # 每个信号都可以在类中被 emit() 发射，然后外部用 connect() 绑定槽函数。
    zoomRequest = QtCore.pyqtSignal(int, QtCore.QPoint)  # 请求缩放，参数可能是缩放比例和鼠标位置
    scrollRequest = QtCore.pyqtSignal(int, int)  # 请求滚动，两个参数可能表示水平和垂直滚动量。
    newShape = QtCore.pyqtSignal()  # 新建形状事件。
    selectionChanged = QtCore.pyqtSignal(list)  #  当前选中形状变化，传入选中形状列表
    shapeMoved = QtCore.pyqtSignal()  # 形状被移动
    drawingPolygon = QtCore.pyqtSignal(bool)  #  是否正在绘制多边形
    vertexSelected = QtCore.pyqtSignal(bool)  # 是否选中顶点。
    mouseMoved = QtCore.pyqtSignal(QtCore.QPointF)  # 鼠标移动事件，QPointF 是浮点坐标

    CREATE, EDIT = 0, 1  # 两种模式，创建模式 和编辑模式

    # polygon, rectangle, line, or point
    _createMode = "polygon"  # 默认创建多边形，也就是创建模式下的子任务

    _fill_drawing = False  # 控制绘制形状时是否填充颜色。

    def __init__(self, *args, **kwargs):
        self.epsilon = kwargs.pop("epsilon", 10.0)  # 控制形状精度或容差，例如鼠标点击与顶点距离的判定。10.0是取不到时的默认值。
        self.double_click = kwargs.pop("double_click", "close")  # 配置双击行为，"close"：双击关闭多边形；None：不触发关闭。
        if self.double_click not in [None, "close"]:
            raise ValueError(
                "Unexpected value for double_click event: {}".format(self.double_click)
            )
        self.num_backups = kwargs.pop("num_backups", 10)  # num_backups 表示形状的最大备份数，用于 撤销操作。
        self._crosshair = kwargs.pop(  # _crosshair 控制 鼠标十字准星 是否在不同模式下启用
            "crosshair",
            {
                "polygon": False,
                "rectangle": True,
                "circle": False,
                "line": False,
                "point": False,
                "linestrip": False,
                "ai_polygon": False,
                "ai_mask": False,
            },
        )
        super(Canvas, self).__init__(*args, **kwargs)  # 初始化 QWidget todo 1
        # Initialise local state.
        self.mode = self.EDIT  # 当前模式，默认编辑
        self.shapes = []  # 当前画布上的所有形状列表
        self.shapesBackups = []  # 用于撤销shapes
        self.current = None  # 当前正在编辑的形状。
        self.selectedShapes = []  # save the selected shapes here  # 当前选中的形状。
        self.selectedShapesCopy = []
        # self.line represents:
        #   - createMode == 'polygon': edge from last point to current
        #   - createMode == 'rectangle': diagonal line of the rectangle
        #   - createMode == 'line': the line
        #   - createMode == 'point': the point
        self.line = Shape()  # 临时线条对象，表示不同模式下的边、对角线等
        self.prevPoint = QtCore.QPoint()  # 记录上一次鼠标点击位置。
        self.prevMovePoint = QtCore.QPoint()  # 记录上一次鼠标移动位置。
        self.offsets = QtCore.QPoint(), QtCore.QPoint()  # 拖动框时的偏移量。
        self.scale = 1.0  # 控制画布缩放比例，默认为 1.0（原始大小）。
        self.pixmap = QtGui.QPixmap()  # 用于存储背景图像，例如加载一张图片进行标注
        self.visible = {}  # 存储哪些元素可见
        self._hideBackround = False  # 控制 是否隐藏背景
        self.hideBackround = False  # 控制 是否隐藏背景
        self.hShape = None  # 当前被高亮显示的形状对象
        self.prevhShape = None  # 上一次高亮的形状， 主要用于 刷新绘制，避免每次重绘整个画布，只更新高亮变化的形状
        self.hVertex = None  # 当前高亮的顶点（vertex），通常鼠标悬停在某个顶点上时设置
        self.prevhVertex = None  # 上一次高亮的顶点，用于优化绘制和交互。
        self.hEdge = None  # 当前高亮的边
        self.prevhEdge = None  # 上一次高亮的边
        self.movingShape = False  # 是否正在拖动某个形状
        self.snapping = True  # 是否启用吸附功能， 启用时，绘制或移动形状会自动对齐到网格或附近顶点。
        self.hShapeIsSelected = False  # 当前高亮形状是否已经被选中， 有些操作只对选中形状有效，比如拖动、删除、修改属性，用于区分“仅高亮”和“已选中”的状态
        self._painter = QtGui.QPainter()  # QPainter 是 PyQt/PySide 绘图核心对象。 用于在 QWidget 或 QPixmap 上绘制, 形状,高亮效果等。 todo
        self._cursor = CURSOR_DEFAULT  # 当前光标，默认箭头。
        # Menus:
        # 0: right-click without selection and dragging of shapes
        # 1: right-click with selection and dragging of shapes
        self.menus = (QtWidgets.QMenu(), QtWidgets.QMenu())  # 保存两个菜单
        # Set widget options.
        self.setMouseTracking(True)  # 默认情况下，QWidget 只有在鼠标按下时才会触发 mouseMoveEvent, 设为 True 后，即使鼠标只是移动，也会持续触发 mouseMoveEvent.
        self.setFocusPolicy(QtCore.Qt.WheelFocus)  # 决定这个控件是否能接收键盘事件。

        self._sam: Optional[osam.types.Model] = None
        self._sam_embedding: collections.OrderedDict[
            bytes, osam.types.ImageEmbedding
        ] = collections.OrderedDict()

    def fillDrawing(self):
        return self._fill_drawing

    def setFillDrawing(self, value):
        self._fill_drawing = value

    @property  # 这时你可以通过 obj.createMode 来访问，但不能直接赋值（写入）obj.createMode = x
    def createMode(self):  # 就是判断以什么方式进行画框；
        return self._createMode

    @createMode.setter  # 为了支持赋值操作，你需要写一个 setter 方法，用 @属性名.setter 装饰，就可以，obj.createMode = True
    def createMode(self, value):
        if value not in [
            "polygon",
            "rectangle",
            "circle",
            "line",
            "point",
            "linestrip",
            "ai_polygon",
            "ai_mask",
        ]:
            raise ValueError("Unsupported createMode: %s" % value)
        self._createMode = value

    def _compute_and_cache_image_embedding(self) -> None:
        if self._sam is None:
            logger.warning("SAM model is not set yet")
            return

        sam: osam.types.Model = self._sam  # sam模型；

        image: np.ndarray = labelme.utils.img_qt_to_arr(self.pixmap.toImage())  # 转化成numpy类型
        if image.tobytes() in self._sam_embedding:
            return

        logger.debug("Computing image embeddings for model {!r}", sam.name)
        self._sam_embedding[image.tobytes()] = sam.encode_image(
            image=imgviz.asrgb(image)  # 将编码向量保存。
        )

    def initializeAiModel(self, model_name):
        if self.pixmap is None:  # self.pixmap就是所加载的图像
            logger.warning("Pixmap is not set yet")
            return

        if self._sam is None or self._sam.name != model_name:
            logger.debug("Initializing AI model {!r}", model_name)
            self._sam = osam.apis.get_model_type_by_name(model_name)()  # 动态获取并实例化对应模型，赋值给self._sam
            self._sam_embedding.clear()  # 清空之前缓存的所有图像 embedding，因为模型换了，之前缓存的 embedding 可能不适用。

        self._compute_and_cache_image_embedding()  # 编码缓存。

    def storeShapes(self):
        shapesBackup = []
        for shape in self.shapes:  # 就是把shape拷贝了 一份
            shapesBackup.append(shape.copy())
        if len(self.shapesBackups) > self.num_backups:  # 如果self.shapesBackups长度超了，就只取最后的self.num_backups + 1。
            self.shapesBackups = self.shapesBackups[-self.num_backups - 1:]
        self.shapesBackups.append(shapesBackup)  # 把复制的shapes放到self.shapesBackups，

    @property
    def isShapeRestorable(self):  # 判断能否撤销。
        # We save the state AFTER each edit (not before) so for an
        # edit to be undoable, we expect the CURRENT and the PREVIOUS state
        # to be in the undo stack.
        if len(self.shapesBackups) < 2:  # 要撤销一次，需要栈里至少有 “当前状态” 和 “上一个状态”
            return False
        return True

    def restoreShape(self):  # 就是恢复前一次的shape
        # This does _part_ of the job of restoring shapes.
        # The complete process is also done in app.py::undoShapeEdit
        # and app.py::loadShapes and our own Canvas::loadShapes function.
        if not self.isShapeRestorable:
            return
        self.shapesBackups.pop()  # latest

        # The application will eventually call Canvas.loadShapes which will
        # push this right back onto the stack.
        shapesBackup = self.shapesBackups.pop()  # 之前的shape,当前的在前一次已经弹出了。
        self.shapes = shapesBackup  # 把 shapes 恢复成这个版本
        self.selectedShapes = []  # 清空当前选中
        for shape in self.shapes:
            shape.selected = False  # 所有 shape 取消选中
        self.update()  # 更新画布

    def enterEvent(self, ev):  # 鼠标进入画布，改成指定光标
        self.overrideCursor(self._cursor)

    def leaveEvent(self, ev):
        self.unHighlight()  # 鼠标离开时取消高亮
        self.restoreCursor()  # 恢复默认光标

    def focusOutEvent(self, ev):
        self.restoreCursor()  # 画布失去焦点时恢复光标;当你点击某个 QWidget（比如画布），它就获得焦点,如果你点了别的地方（比如菜单栏、另一个窗口），画布就失去焦点。

    def isVisible(self, shape):  # 判断某个 shape（标注框、物体）当前是否可见
        return self.visible.get(shape, True)

    def drawing(self):  # 判断当前是在 创建模式 还是 编辑模式
        return self.mode == self.CREATE

    def editing(self):  # 判断当前是在 创建模式 还是 编辑模式
        return self.mode == self.EDIT

    def setEditing(self, value=True):  # 在 创建模式 和 编辑模式 之间切换
        self.mode = self.EDIT if value else self.CREATE
        if self.mode == self.EDIT:
            # CREATE -> EDIT
            self.repaint()  # clear crosshair
        else:
            # EDIT -> CREATE
            self.unHighlight()
            self.deSelectShape()

    def unHighlight(self):  # 鼠标离开目标物体时，把它的高亮状态去掉，并记下我刚才指着哪个物体/顶点/边
        if self.hShape:
            self.hShape.highlightClear()
            self.update()
        self.prevhShape = self.hShape  # 当前鼠标悬停的图形
        self.prevhVertex = self.hVertex  # 当前鼠标悬停的顶点
        self.prevhEdge = self.hEdge  # 当前鼠标悬停的边
        self.hShape = self.hVertex = self.hEdge = None

    def selectedVertex(self):  # 是否选中点
        return self.hVertex is not None

    def selectedEdge(self):  # 是否选中边
        return self.hEdge is not None

    def mouseMoveEvent(self, ev):
        """Update line with last point and current coordinates."""
        try:
            pos = self.transformPos(ev.localPos())
        except AttributeError:
            return

        self.mouseMoved.emit(pos)

        self.prevMovePoint = pos
        self.restoreCursor()

        is_shift_pressed = ev.modifiers() & QtCore.Qt.ShiftModifier

        # Polygon drawing.
        if self.drawing():
            if self.createMode in ["ai_polygon", "ai_mask"]:
                self.line.shape_type = "points"
            else:
                self.line.shape_type = self.createMode

            self.overrideCursor(CURSOR_DRAW)
            if not self.current:
                self.repaint()  # draw crosshair
                return

            if self.outOfPixmap(pos):
                # Don't allow the user to draw outside the pixmap.
                # Project the point to the pixmap's edges.
                pos = self.intersectionPoint(self.current[-1], pos)
            elif (
                self.snapping
                and len(self.current) > 1
                and self.createMode == "polygon"
                and self.closeEnough(pos, self.current[0])
            ):
                # Attract line to starting point and
                # colorise to alert the user.
                pos = self.current[0]
                self.overrideCursor(CURSOR_POINT)
                self.current.highlightVertex(0, Shape.NEAR_VERTEX)
            if self.createMode in ["polygon", "linestrip"]:
                self.line.points = [self.current[-1], pos]
                self.line.point_labels = [1, 1]
            elif self.createMode in ["ai_polygon", "ai_mask"]:
                self.line.points = [self.current.points[-1], pos]
                self.line.point_labels = [
                    self.current.point_labels[-1],
                    0 if is_shift_pressed else 1,
                ]
            elif self.createMode == "rectangle":
                self.line.points = [self.current[0], pos]
                self.line.point_labels = [1, 1]
                self.line.close()
            elif self.createMode == "circle":
                self.line.points = [self.current[0], pos]
                self.line.point_labels = [1, 1]
                self.line.shape_type = "circle"
            elif self.createMode == "line":
                self.line.points = [self.current[0], pos]
                self.line.point_labels = [1, 1]
                self.line.close()
            elif self.createMode == "point":
                self.line.points = [self.current[0]]
                self.line.point_labels = [1]
                self.line.close()
            assert len(self.line.points) == len(self.line.point_labels)
            self.repaint()
            self.current.highlightClear()
            return

        # Polygon copy moving.
        if QtCore.Qt.RightButton & ev.buttons():
            if self.selectedShapesCopy and self.prevPoint:
                self.overrideCursor(CURSOR_MOVE)
                self.boundedMoveShapes(self.selectedShapesCopy, pos)
                self.repaint()
            elif self.selectedShapes:
                self.selectedShapesCopy = [s.copy() for s in self.selectedShapes]
                self.repaint()
            return

        # Polygon/Vertex moving.
        if QtCore.Qt.LeftButton & ev.buttons():
            if self.selectedVertex():
                self.boundedMoveVertex(pos)
                self.repaint()
                self.movingShape = True
            elif self.selectedShapes and self.prevPoint:
                self.overrideCursor(CURSOR_MOVE)
                self.boundedMoveShapes(self.selectedShapes, pos)
                self.repaint()
                self.movingShape = True
            return

        # Just hovering over the canvas, 2 possibilities:
        # - Highlight shapes
        # - Highlight vertex
        # Update shape/vertex fill and tooltip value accordingly.
        self.setToolTip(self.tr("Image"))
        for shape in reversed([s for s in self.shapes if self.isVisible(s)]):
            # Look for a nearby vertex to highlight. If that fails,
            # check if we happen to be inside a shape.
            index = shape.nearestVertex(pos, self.epsilon)
            index_edge = shape.nearestEdge(pos, self.epsilon)
            if index is not None:
                if self.selectedVertex():
                    self.hShape.highlightClear()
                self.prevhVertex = self.hVertex = index
                self.prevhShape = self.hShape = shape
                self.prevhEdge = self.hEdge
                self.hEdge = None
                shape.highlightVertex(index, shape.MOVE_VERTEX)
                self.overrideCursor(CURSOR_POINT)
                self.setToolTip(
                    self.tr(
                        "Click & Drag to move point\n"
                        "ALT + SHIFT + Click to delete point"
                    )
                )
                self.setStatusTip(self.toolTip())
                self.update()
                break
            elif index_edge is not None and shape.canAddPoint():
                if self.selectedVertex():
                    self.hShape.highlightClear()
                self.prevhVertex = self.hVertex
                self.hVertex = None
                self.prevhShape = self.hShape = shape
                self.prevhEdge = self.hEdge = index_edge
                self.overrideCursor(CURSOR_POINT)
                self.setToolTip(self.tr("ALT + Click to create point"))
                self.setStatusTip(self.toolTip())
                self.update()
                break
            elif shape.containsPoint(pos):
                if self.selectedVertex():
                    self.hShape.highlightClear()
                self.prevhVertex = self.hVertex
                self.hVertex = None
                self.prevhShape = self.hShape = shape
                self.prevhEdge = self.hEdge
                self.hEdge = None
                self.setToolTip(
                    self.tr("Click & drag to move shape '%s'") % shape.label
                )
                self.setStatusTip(self.toolTip())
                self.overrideCursor(CURSOR_GRAB)
                self.update()
                break
        else:  # Nothing found, clear highlights, reset state.
            self.unHighlight()
        self.vertexSelected.emit(self.hVertex is not None)

    def addPointToEdge(self):  # 在边上插入一个新顶点
        shape = self.prevhShape
        index = self.prevhEdge
        point = self.prevMovePoint
        if shape is None or index is None or point is None:
            return
        shape.insertPoint(index, point)
        shape.highlightVertex(index, shape.MOVE_VERTEX)
        self.hShape = shape
        self.hVertex = index
        self.hEdge = None
        self.movingShape = True

    def removeSelectedPoint(self):  # 删除当前选中的顶点
        shape = self.prevhShape
        index = self.prevhVertex
        if shape is None or index is None:
            return
        shape.removePoint(index)
        shape.highlightClear()
        self.hShape = shape
        self.prevhVertex = None
        self.movingShape = True  # Save changes

    def mousePressEvent(self, ev):
        pos = self.transformPos(ev.localPos())

        is_shift_pressed = ev.modifiers() & QtCore.Qt.ShiftModifier

        if ev.button() == QtCore.Qt.LeftButton:
            if self.drawing():
                if self.current:
                    # Add point to existing shape.
                    if self.createMode == "polygon":
                        self.current.addPoint(self.line[1])
                        self.line[0] = self.current[-1]
                        if self.current.isClosed():
                            self.finalise()
                    elif self.createMode in ["rectangle", "circle", "line"]:
                        assert len(self.current.points) == 1
                        self.current.points = self.line.points
                        self.finalise()
                    elif self.createMode == "linestrip":
                        self.current.addPoint(self.line[1])
                        self.line[0] = self.current[-1]
                        if int(ev.modifiers()) == QtCore.Qt.ControlModifier:
                            self.finalise()
                    elif self.createMode in ["ai_polygon", "ai_mask"]:
                        self.current.addPoint(
                            self.line.points[1],
                            label=self.line.point_labels[1],
                        )
                        self.line.points[0] = self.current.points[-1]
                        self.line.point_labels[0] = self.current.point_labels[-1]
                        if ev.modifiers() & QtCore.Qt.ControlModifier:
                            self.finalise()
                elif not self.outOfPixmap(pos):
                    # Create new shape.
                    self.current = Shape(
                        shape_type="points"
                        if self.createMode in ["ai_polygon", "ai_mask"]
                        else self.createMode
                    )
                    self.current.addPoint(pos, label=0 if is_shift_pressed else 1)
                    if self.createMode == "point":
                        self.finalise()
                    elif (
                        self.createMode in ["ai_polygon", "ai_mask"]
                        and ev.modifiers() & QtCore.Qt.ControlModifier
                    ):
                        self.finalise()
                    else:
                        if self.createMode == "circle":
                            self.current.shape_type = "circle"
                        self.line.points = [pos, pos]
                        if (
                            self.createMode in ["ai_polygon", "ai_mask"]
                            and is_shift_pressed
                        ):
                            self.line.point_labels = [0, 0]
                        else:
                            self.line.point_labels = [1, 1]
                        self.setHiding()
                        self.drawingPolygon.emit(True)
                        self.update()
            elif self.editing():
                if self.selectedEdge() and ev.modifiers() == QtCore.Qt.AltModifier:
                    self.addPointToEdge()
                elif self.selectedVertex() and ev.modifiers() == (
                    QtCore.Qt.AltModifier | QtCore.Qt.ShiftModifier
                ):
                    self.removeSelectedPoint()

                group_mode = int(ev.modifiers()) == QtCore.Qt.ControlModifier
                self.selectShapePoint(pos, multiple_selection_mode=group_mode)
                self.prevPoint = pos
                self.repaint()
        elif ev.button() == QtCore.Qt.RightButton and self.editing():
            group_mode = int(ev.modifiers()) == QtCore.Qt.ControlModifier
            if not self.selectedShapes or (
                self.hShape is not None and self.hShape not in self.selectedShapes
            ):
                self.selectShapePoint(pos, multiple_selection_mode=group_mode)
                self.repaint()
            self.prevPoint = pos

    def mouseReleaseEvent(self, ev):
        if ev.button() == QtCore.Qt.RightButton:
            menu = self.menus[len(self.selectedShapesCopy) > 0]
            self.restoreCursor()
            if not menu.exec_(self.mapToGlobal(ev.pos())) and self.selectedShapesCopy:
                # Cancel the move by deleting the shadow copy.
                self.selectedShapesCopy = []
                self.repaint()
        elif ev.button() == QtCore.Qt.LeftButton:
            if self.editing():
                if (
                    self.hShape is not None
                    and self.hShapeIsSelected
                    and not self.movingShape
                ):
                    self.selectionChanged.emit(
                        [x for x in self.selectedShapes if x != self.hShape]
                    )

        if self.movingShape and self.hShape:
            index = self.shapes.index(self.hShape)
            if self.shapesBackups[-1][index].points != self.shapes[index].points:
                self.storeShapes()
                self.shapeMoved.emit()

            self.movingShape = False

    def endMove(self, copy):  # 这个函数处理用户拖动或移动选中形状后的“结束动作”。
        assert self.selectedShapes and self.selectedShapesCopy
        assert len(self.selectedShapesCopy) == len(self.selectedShapes)
        if copy:  # 参数表示是复制拖动还是直接移动
            for i, shape in enumerate(self.selectedShapesCopy):
                self.shapes.append(shape)
                self.selectedShapes[i].selected = False
                self.selectedShapes[i] = shape
        else:
            for i, shape in enumerate(self.selectedShapesCopy):
                self.selectedShapes[i].points = shape.points
        self.selectedShapesCopy = []
        self.repaint()
        self.storeShapes()
        return True

    def hideBackroundShapes(self, value): # 隐藏背景shape
        self.hideBackround = value
        if self.selectedShapes:
            # Only hide other shapes if there is a current selection. 只有当前有选中形状时才隐藏其他背景形状，
            # Otherwise the user will not be able to select a shape. 避免没有选中时用户无法选择形状
            self.setHiding(True)
            self.update()

    def setHiding(self, enable=True):  # 控制内部变量 _hideBackround，是否真正执行隐藏背景形状的逻辑,只有enable=True时，才使用self.hideBackround的值决定是否隐藏；否则一定不隐藏
        self._hideBackround = self.hideBackround if enable else False

    def canCloseShape(self):
        return self.drawing() and (
                (self.current and len(self.current) > 2)
                or self.createMode in ["ai_polygon", "ai_mask"]
        )  # 绘制模型，有shape，且当前点数大于2， 或者用ai创建的。


    def mouseDoubleClickEvent(self, ev):
        if self.double_click != "close":
            return

        if (
            self.createMode == "polygon" and self.canCloseShape()
        ) or self.createMode in ["ai_polygon", "ai_mask"]:
            self.finalise()

    def selectShapes(self, shapes):
        self.setHiding()
        self.selectionChanged.emit(shapes)
        self.update()

    def selectShapePoint(self, point, multiple_selection_mode):
        """Select the first shape created which contains this point."""
        if self.selectedVertex():  # A vertex is marked for selection.
            index, shape = self.hVertex, self.hShape
            shape.highlightVertex(index, shape.MOVE_VERTEX)
        else:
            for shape in reversed(self.shapes):
                if self.isVisible(shape) and shape.containsPoint(point):
                    self.setHiding()
                    if shape not in self.selectedShapes:
                        if multiple_selection_mode:
                            self.selectionChanged.emit(self.selectedShapes + [shape])
                        else:
                            self.selectionChanged.emit([shape])
                        self.hShapeIsSelected = False
                    else:
                        self.hShapeIsSelected = True
                    self.calculateOffsets(point)
                    return
        self.deSelectShape()

    def calculateOffsets(self, point):
        left = self.pixmap.width() - 1
        right = 0
        top = self.pixmap.height() - 1
        bottom = 0
        for s in self.selectedShapes:
            rect = s.boundingRect()
            if rect.left() < left:
                left = rect.left()
            if rect.right() > right:
                right = rect.right()
            if rect.top() < top:
                top = rect.top()
            if rect.bottom() > bottom:
                bottom = rect.bottom()

        x1 = left - point.x()
        y1 = top - point.y()
        x2 = right - point.x()
        y2 = bottom - point.y()
        self.offsets = QtCore.QPointF(x1, y1), QtCore.QPointF(x2, y2)

    def boundedMoveVertex(self, pos):
        index, shape = self.hVertex, self.hShape
        point = shape[index]
        if self.outOfPixmap(pos):
            pos = self.intersectionPoint(point, pos)
        shape.moveVertexBy(index, pos - point)

    def boundedMoveShapes(self, shapes, pos):
        if self.outOfPixmap(pos):
            return False  # No need to move
        o1 = pos + self.offsets[0]
        if self.outOfPixmap(o1):
            pos -= QtCore.QPointF(min(0, o1.x()), min(0, o1.y()))
        o2 = pos + self.offsets[1]
        if self.outOfPixmap(o2):
            pos += QtCore.QPointF(
                min(0, self.pixmap.width() - o2.x()),
                min(0, self.pixmap.height() - o2.y()),
            )
        # XXX: The next line tracks the new position of the cursor
        # relative to the shape, but also results in making it
        # a bit "shaky" when nearing the border and allows it to
        # go outside of the shape's area for some reason.
        # self.calculateOffsets(self.selectedShapes, pos)
        dp = pos - self.prevPoint
        if dp:
            for shape in shapes:
                shape.moveBy(dp)
            self.prevPoint = pos
            return True
        return False

    def deSelectShape(self):
        if self.selectedShapes:
            self.setHiding(False)
            self.selectionChanged.emit([])
            self.hShapeIsSelected = False
            self.update()

    def deleteSelected(self):
        deleted_shapes = []
        if self.selectedShapes:
            for shape in self.selectedShapes:
                self.shapes.remove(shape)
                deleted_shapes.append(shape)
            self.storeShapes()
            self.selectedShapes = []
            self.update()
        return deleted_shapes

    def deleteShape(self, shape):
        if shape in self.selectedShapes:
            self.selectedShapes.remove(shape)
        if shape in self.shapes:
            self.shapes.remove(shape)
        self.storeShapes()
        self.update()

    def paintEvent(self, event: Optional[QtGui.QPaintEvent]) -> None:
        if not self.pixmap:
            return super(Canvas, self).paintEvent(event)  # 如果 self.pixmap 为 None 或空，就调用父类默认绘制方法。避免空图像导致绘制错误。

        p = self._painter  # 获取一个 QPainter 对象 p 用于绘制
        p.begin(self)  # 开始在当前 Canvas 上绘制
        p.setRenderHint(QtGui.QPainter.Antialiasing)  # 设置抗锯齿和高质量渲染，确保绘制线条和平滑缩放图片时效果更好。
        p.setRenderHint(QtGui.QPainter.HighQualityAntialiasing)
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

        p.scale(self.scale, self.scale)  # 按当前缩放比例缩放绘制内容
        p.translate(self.offsetToCenter())  # 平移坐标系，将内容中心对齐到视图中心

        p.drawPixmap(0, 0, self.pixmap)  # 在 (0,0) 绘制 self.pixmap, 此时图像会根据上面的 scale 和 translate 调整位置和大小。

        p.scale(1 / self.scale, 1 / self.scale)  # 将缩放比例恢复到 1:1，用于后续绘制不受缩放影响的内容，例如 UI 标记或十字准线。

        # draw crosshair  # 绘制十字准线
        if (
            self._crosshair[self._createMode]
            and self.drawing()
            and self.prevMovePoint
            and not self.outOfPixmap(self.prevMovePoint)
        ):
            p.setPen(QtGui.QColor(0, 0, 0))
            p.drawLine(
                0,
                int(self.prevMovePoint.y() * self.scale),
                self.width() - 1,
                int(self.prevMovePoint.y() * self.scale),
            )
            p.drawLine(
                int(self.prevMovePoint.x() * self.scale),
                0,
                int(self.prevMovePoint.x() * self.scale),
                self.height() - 1,
            )

        Shape.scale = self.scale  # 绘制已有形状,可能有标签就绘制上去。
        for shape in self.shapes:
            if (shape.selected or not self._hideBackround) and self.isVisible(shape):
                shape.fill = shape.selected or shape == self.hShape
                shape.paint(p)
        if self.current:  # 绘制当前正在绘制的形状
            self.current.paint(p)
            assert len(self.line.points) == len(self.line.point_labels)
            self.line.paint(p)
        if self.selectedShapesCopy:  # 绘制选中的复制形状，复制shape其实就是另外绘制一个shape
            for s in self.selectedShapesCopy:
                s.paint(p)

        if not self.current:  # 处理多边形绘制
            p.end()
            return

        if (
            self.createMode == "polygon"
            and self.fillDrawing()
            and len(self.current.points) >= 2
        ):
            drawing_shape = self.current.copy()
            if drawing_shape.fill_color.getRgb()[3] == 0:
                logger.warning(
                    "fill_drawing=true, but fill_color is transparent,"
                    " so forcing to be opaque."
                )
                drawing_shape.fill_color.setAlpha(64)
            drawing_shape.addPoint(self.line[1])

        if self.createMode not in ["ai_polygon", "ai_mask"]:  # 处理 AI 辅助绘制
            p.end()
            return

        drawing_shape = self.current.copy()
        drawing_shape.addPoint(
            point=self.line.points[1],
            label=self.line.point_labels[1],
        )
        if self.createMode in ["ai_polygon", "ai_mask"]:
            if self._sam is None:
                logger.warning("SAM model is not set yet")
                p.end()
                return
            _update_shape_with_sam(
                shape=drawing_shape,
                createMode=self.createMode,
                model_name=self._sam.name,
                image_embedding=self._sam_embedding[
                    labelme.utils.img_qt_to_arr(self.pixmap.toImage()).tobytes()
                ],
            )
        drawing_shape.fill = self.fillDrawing()
        drawing_shape.selected = True
        drawing_shape.paint(p)
        p.end()

    def transformPos(self, point):
        """Convert from widget-logical coordinates to painter-logical ones."""
        return point / self.scale - self.offsetToCenter()

    def offsetToCenter(self):
        s = self.scale
        area = super(Canvas, self).size()
        w, h = self.pixmap.width() * s, self.pixmap.height() * s
        aw, ah = area.width(), area.height()
        x = (aw - w) / (2 * s) if aw > w else 0
        y = (ah - h) / (2 * s) if ah > h else 0
        return QtCore.QPointF(x, y)

    def outOfPixmap(self, p):
        w, h = self.pixmap.width(), self.pixmap.height()
        return not (0 <= p.x() <= w - 1 and 0 <= p.y() <= h - 1)

    def finalise(self):
        assert self.current
        if self._sam:  # 5.8.0 bug
            _update_shape_with_sam(
                shape=self.current,
                createMode=self.createMode,
                model_name=self._sam.name,
                image_embedding=self._sam_embedding[
                    labelme.utils.img_qt_to_arr(self.pixmap.toImage()).tobytes()
                ],
            )
        self.current.close()

        self.shapes.append(self.current)
        self.storeShapes()
        self.current = None
        self.setHiding(False)
        self.newShape.emit()
        self.update()

    def closeEnough(self, p1, p2):
        # d = distance(p1 - p2)
        # m = (p1-p2).manhattanLength()
        # print "d %.2f, m %d, %.2f" % (d, m, d - m)
        # divide by scale to allow more precision when zoomed in
        return labelme.utils.distance(p1 - p2) < (self.epsilon / self.scale)

    def intersectionPoint(self, p1, p2):
        # Cycle through each image edge in clockwise fashion,
        # and find the one intersecting the current line segment.
        # http://paulbourke.net/geometry/lineline2d/
        size = self.pixmap.size()
        points = [
            (0, 0),
            (size.width() - 1, 0),
            (size.width() - 1, size.height() - 1),
            (0, size.height() - 1),
        ]
        # x1, y1 should be in the pixmap, x2, y2 should be out of the pixmap
        x1 = min(max(p1.x(), 0), size.width() - 1)
        y1 = min(max(p1.y(), 0), size.height() - 1)
        x2, y2 = p2.x(), p2.y()
        d, i, (x, y) = min(self.intersectingEdges((x1, y1), (x2, y2), points))
        x3, y3 = points[i]
        x4, y4 = points[(i + 1) % 4]
        if (x, y) == (x1, y1):
            # Handle cases where previous point is on one of the edges.
            if x3 == x4:
                return QtCore.QPointF(x3, min(max(0, y2), max(y3, y4)))
            else:  # y3 == y4
                return QtCore.QPointF(min(max(0, x2), max(x3, x4)), y3)
        return QtCore.QPointF(x, y)

    def intersectingEdges(self, point1, point2, points):
        """Find intersecting edges.

        For each edge formed by `points', yield the intersection
        with the line segment `(x1,y1) - (x2,y2)`, if it exists.
        Also return the distance of `(x2,y2)' to the middle of the
        edge along with its index, so that the one closest can be chosen.
        """
        (x1, y1) = point1
        (x2, y2) = point2
        for i in range(4):
            x3, y3 = points[i]
            x4, y4 = points[(i + 1) % 4]
            denom = (y4 - y3) * (x2 - x1) - (x4 - x3) * (y2 - y1)
            nua = (x4 - x3) * (y1 - y3) - (y4 - y3) * (x1 - x3)
            nub = (x2 - x1) * (y1 - y3) - (y2 - y1) * (x1 - x3)
            if denom == 0:
                # This covers two cases:
                #   nua == nub == 0: Coincident
                #   otherwise: Parallel
                continue
            ua, ub = nua / denom, nub / denom
            if 0 <= ua <= 1 and 0 <= ub <= 1:
                x = x1 + ua * (x2 - x1)
                y = y1 + ua * (y2 - y1)
                m = QtCore.QPointF((x3 + x4) / 2, (y3 + y4) / 2)
                d = labelme.utils.distance(m - QtCore.QPointF(x2, y2))
                yield d, i, (x, y)

    # These two, along with a call to adjustSize are required for the
    # scroll area.
    def sizeHint(self):
        return self.minimumSizeHint()

    def minimumSizeHint(self):
        if self.pixmap:
            return self.scale * self.pixmap.size()
        return super(Canvas, self).minimumSizeHint()

    def wheelEvent(self, ev):  # ev 是 QWheelEvent 对象，包含滚轮滚动的各种信息
        mods = ev.modifiers()  #  获取在滚轮滚动时按下的键盘修饰键; 返回的是一个标志位，可以用 QtCore.Qt.ControlModifier、QtCore.Qt.ShiftModifier 等进行判断。
        delta = ev.angleDelta()  # 获取滚轮滚动的增量（角度差）,返回一个 QPoint 对象, delta.x() 表示水平方向滚动量, delta.y() 表示垂直方向滚动量。
        if QtCore.Qt.ControlModifier == int(mods):  # 判断滚轮事件发生时是否按下了 Ctrl 键。
            # with Ctrl/Command key
            # zoom
            self.zoomRequest.emit(delta.y(), ev.pos())  # 当按下 Ctrl 键时，触发一个 自定义信号 zoomRequest, ev.pos()：事件发生时在 视图坐标中的位置
        else:  #  如果没有按下 Ctrl 键，认为是普通滚动
            # scroll
            self.scrollRequest.emit(delta.x(), QtCore.Qt.Horizontal)  # 触发 scrollRequest 信号，把滚动量和方向发送给信号的监听者
            self.scrollRequest.emit(delta.y(), QtCore.Qt.Vertical)
        ev.accept()  #　标记事件已被处理，不再传递给父类或默认事件处理。

    def moveByKeyboard(self, offset):
        if self.selectedShapes:
            self.boundedMoveShapes(self.selectedShapes, self.prevPoint + offset)
            self.repaint()
            self.movingShape = True

    def keyPressEvent(self, ev):
        modifiers = ev.modifiers()
        key = ev.key()
        if self.drawing():
            if key == QtCore.Qt.Key_Escape and self.current:
                self.current = None
                self.drawingPolygon.emit(False)
                self.update()
            elif key == QtCore.Qt.Key_Return and self.canCloseShape():
                self.finalise()
            elif modifiers == QtCore.Qt.AltModifier:
                self.snapping = False
        elif self.editing():
            if key == QtCore.Qt.Key_Up:
                self.moveByKeyboard(QtCore.QPointF(0.0, -MOVE_SPEED))
            elif key == QtCore.Qt.Key_Down:
                self.moveByKeyboard(QtCore.QPointF(0.0, MOVE_SPEED))
            elif key == QtCore.Qt.Key_Left:
                self.moveByKeyboard(QtCore.QPointF(-MOVE_SPEED, 0.0))
            elif key == QtCore.Qt.Key_Right:
                self.moveByKeyboard(QtCore.QPointF(MOVE_SPEED, 0.0))

    def keyReleaseEvent(self, ev):
        modifiers = ev.modifiers()
        if self.drawing():
            if int(modifiers) == 0:
                self.snapping = True
        elif self.editing():
            if self.movingShape and self.selectedShapes:
                index = self.shapes.index(self.selectedShapes[0])
                if self.shapesBackups[-1][index].points != self.shapes[index].points:
                    self.storeShapes()
                    self.shapeMoved.emit()

                self.movingShape = False

    def setLastLabel(self, text, flags):
        assert text
        self.shapes[-1].label = text
        self.shapes[-1].flags = flags
        self.shapesBackups.pop()
        self.storeShapes()
        return self.shapes[-1]

    def undoLastLine(self):
        assert self.shapes
        self.current = self.shapes.pop()
        self.current.setOpen()
        self.current.restoreShapeRaw()
        if self.createMode in ["polygon", "linestrip"]:
            self.line.points = [self.current[-1], self.current[0]]
        elif self.createMode in ["rectangle", "line", "circle"]:
            self.current.points = self.current.points[0:1]
        elif self.createMode == "point":
            self.current = None
        self.drawingPolygon.emit(True)

    def undoLastPoint(self):
        if not self.current or self.current.isClosed():
            return
        self.current.popPoint()
        if len(self.current) > 0:
            self.line[0] = self.current[-1]
        else:
            self.current = None
            self.drawingPolygon.emit(False)
        self.update()

    def loadPixmap(self, pixmap, clear_shapes=True):  # 将图像数据放到canvas的self.pixmap里
        self.pixmap = pixmap
        if self._sam:
            self._compute_and_cache_image_embedding()
        if clear_shapes:
            self.shapes = []
        self.update()

    def loadShapes(self, shapes, replace=True):
        if replace:
            self.shapes = list(shapes)
        else:
            self.shapes.extend(shapes)
        self.storeShapes()
        self.current = None
        self.hShape = None
        self.hVertex = None
        self.hEdge = None
        self.update()

    def setShapeVisible(self, shape, value):  # 用来设置某个shape（形状）是否可见。
        self.visible[shape] = value
        self.update()

    def overrideCursor(self, cursor):  # 用来临时改变鼠标光标
        self.restoreCursor()  # 先调用restoreCursor()，确保之前的光标设置被清除，防止累积叠加。
        self._cursor = cursor  # 保存当前设置的光标，方便后续管理或还原。
        QtWidgets.QApplication.setOverrideCursor(cursor)  # 通过应用级别设置鼠标光标覆盖，临时改变鼠标样式

    def restoreCursor(self):  # 方法用来恢复鼠标光标。
        QtWidgets.QApplication.restoreOverrideCursor()  # 调用Qt应用的函数，移除之前的鼠标光标覆盖，还原为默认或之前状态。

    def resetState(self):  # 用来重置控件或画布的状态。
        self.restoreCursor()  # 先恢复光标为默认，避免光标停留在特殊状态。
        self.pixmap = None  # 清除当前的图像（pixmap），通常表示清空画布或重置内容。
        self.shapesBackups = []  # 清空形状备份列表，重置历史记录或撤销栈。
        self.update()  # 刷新界面，触发重绘，保证重置后的界面状态正确显示。


def _update_shape_with_sam(
    shape: Shape,
    createMode: str,
    model_name: str,
    image_embedding: osam.types.ImageEmbedding,
) -> None:
    if createMode not in ["ai_polygon", "ai_mask"]:
        raise ValueError(
            f"createMode must be 'ai_polygon' or 'ai_mask', not {createMode}"
        )

    response: osam.types.GenerateResponse = osam.apis.generate(  # 调用 osam.apis.generate() 进行 AI 形状生成
        osam.types.GenerateRequest(  # 这个类用于构造 API 请求　
            model=model_name,
            image_embedding=image_embedding,
            prompt=osam.types.Prompt(
                points=[[point.x(), point.y()] for point in shape.points],
                point_labels=shape.point_labels,
            ),
        )
    )
    if not response.annotations:  # 可能是列表，包含{mask:, bounding_box}
        logger.warning("No annotations returned by model {!r}", model_name)
        return

    if createMode == "ai_mask":
        y1: int
        x1: int
        y2: int
        x2: int
        if response.annotations[0].bounding_box is None:  # 拿到边界框，有了直接拿，没得用掩码算。
            y1, x1, y2, x2 = imgviz.instances.mask_to_bbox(
                [response.annotations[0].mask]
            )[0].astype(int)
        else:
            y1 = response.annotations[0].bounding_box.ymin
            x1 = response.annotations[0].bounding_box.xmin
            y2 = response.annotations[0].bounding_box.ymax
            x2 = response.annotations[0].bounding_box.xmax
        shape.setShapeRefined(
            shape_type="mask",
            points=[QtCore.QPointF(x1, y1), QtCore.QPointF(x2, y2)],
            point_labels=[1, 1],
            mask=response.annotations[0].mask[y1 : y2 + 1, x1 : x2 + 1],
        )
    elif createMode == "ai_polygon":
        points = polygon_from_mask.compute_polygon_from_mask(
            mask=response.annotations[0].mask
        )  # 从掩码生成多边形，因为sam生成的就是掩码。
        if len(points) < 2:  # 不构成封闭区域。
            return
        shape.setShapeRefined(
            shape_type="polygon",
            points=[QtCore.QPointF(point[0], point[1]) for point in points],
            point_labels=[1] * len(points),
        )  # 它用于将当前形状更新为多边形（polygon），并将相应的点坐标和标签赋给它。
