from __future__ import annotations

from typing import Final

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt


class ToolBar(QtWidgets.QToolBar):
    ACTION_KEY: Final = "labelme-toolbar-action-key"
    DRAG_MIME: Final = "application/x-labelme-toolbar-action"

    def __init__(
        self,
        *,
        title: str,
        name: str | None = None,
        actions: list[QtGui.QAction],
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
        button_style: Qt.ToolButtonStyle = Qt.ToolButtonStyle.ToolButtonTextUnderIcon,
        font_base: QtGui.QFont | None = None,
        overflow_label: str | None = None,
    ) -> None:
        OBJECT_NAME_SUFFIX: Final = "ToolBar"
        FONT_SCALE_FACTOR: Final = 0.8
        VERTICAL_SEPARATOR_STYLE: Final = (
            "QToolBar::separator { height: 1px; background: palette(mid); "
            "margin: 2px 4px; }"
        )

        super().__init__(title)
        self._drag_start: QtCore.QPoint | None = None
        self._drag_button: QtWidgets.QToolButton | None = None
        self._default_actions = tuple(actions)
        # The object name keys saved window state, so it must not change with
        # the translated title.
        self.setObjectName((name or title) + OBJECT_NAME_SUFFIX)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setMovable(True)
        self.setFloatable(True)
        self.setAllowedAreas(Qt.ToolBarArea.AllToolBarAreas)
        self.setAcceptDrops(True)
        self.setOrientation(orientation)
        self.setToolButtonStyle(button_style)
        overflow = self.findChild(QtWidgets.QToolButton, "qt_toolbar_ext_button")
        if overflow is not None:
            overflow.setAccessibleName(overflow_label or self.tr("More actions"))

        layout = self.layout()
        if layout is not None:
            layout.setSpacing(0)
            layout.setContentsMargins(0, 0, 0, 0)

        if font_base is not None:
            scaled_font = QtGui.QFont(font_base)
            scaled_font.setPointSizeF(font_base.pointSizeF() * FONT_SCALE_FACTOR)
            self.setFont(scaled_font)

        self._vertical_separator_style = VERTICAL_SEPARATOR_STYLE
        self._drop_marker = QtWidgets.QFrame(self)
        self._drop_marker.setStyleSheet("background: palette(highlight);")
        self._drop_marker.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._drop_marker.hide()
        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._refresh_buttons)
        self.orientationChanged.connect(self._refresh_buttons)

        for index, action in enumerate(actions):
            action.setProperty(self.ACTION_KEY, f"{self.objectName()}/{index}")
            self.addAction(action)

        self._refresh_buttons()

    @property
    def default_actions(self) -> tuple[QtGui.QAction, ...]:
        return self._default_actions

    def actionEvent(self, event: QtGui.QActionEvent, /) -> None:
        super().actionEvent(event)
        # Qt may not have created the new action's button until this event returns.
        if hasattr(self, "_refresh_timer"):
            self._refresh_timer.start(0)

    def _refresh_buttons(self) -> None:
        vertical = self.orientation() == Qt.Orientation.Vertical
        self.setStyleSheet(self._vertical_separator_style if vertical else "")
        for action in self.actions():
            button = self.widgetForAction(action)
            if isinstance(button, QtWidgets.QToolButton):
                button.setMinimumWidth(0)
                button.installEventFilter(self)
        if vertical:
            self._equalize_button_widths()

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent, /) -> bool:
        if isinstance(watched, QtWidgets.QToolButton) and isinstance(
            event, QtGui.QMouseEvent
        ):
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                self._drag_button = watched
                self._drag_start = (
                    event.position().toPoint()
                    if event.button() == Qt.MouseButton.LeftButton
                    else None
                )
            elif event.type() == QtCore.QEvent.Type.MouseButtonRelease:
                self._drag_start = None
                self._drag_button = None
            elif (
                event.type() == QtCore.QEvent.Type.MouseMove
                and self._drag_start is not None
                and watched is self._drag_button
                and event.buttons() & Qt.MouseButton.LeftButton
                and (event.position().toPoint() - self._drag_start).manhattanLength()
                >= QtWidgets.QApplication.startDragDistance()
            ):
                action = watched.defaultAction()
                self._drag_start = None
                self._drag_button = None
                if action is not None and not isinstance(
                    action, QtWidgets.QWidgetAction
                ):
                    # Clearing the down state before starting the native drag prevents
                    # release from activating Open/Delete or switching drawing mode.
                    watched.setDown(False)
                    drag = QtGui.QDrag(self)
                    drag.setMimeData(self.mime_for_action(action))
                    drag.setPixmap(watched.grab())
                    drag.exec(Qt.DropAction.MoveAction)
                    drag.deleteLater()
                    return True
        return super().eventFilter(watched, event)

    @classmethod
    def mime_for_action(cls, action: QtGui.QAction, /) -> QtCore.QMimeData:
        mime = QtCore.QMimeData()
        mime.setData(cls.DRAG_MIME, str(id(action)).encode("ascii"))
        return mime

    def _drag_source(
        self, mime: QtCore.QMimeData, /
    ) -> tuple[ToolBar, QtGui.QAction] | None:
        if not mime.hasFormat(self.DRAG_MIME):
            return None
        key = mime.data(self.DRAG_MIME).data()
        root: QtWidgets.QWidget = self
        while (parent := root.parentWidget()) is not None:
            root = parent
        toolbars = root.findChildren(ToolBar)
        if self not in toolbars:
            toolbars.append(self)
        for toolbar in toolbars:
            for action in toolbar.actions():
                if (
                    key == str(id(action)).encode("ascii")
                    and not action.isSeparator()
                    and not isinstance(action, QtWidgets.QWidgetAction)
                ):
                    return toolbar, action
        return None

    def _action_before(self, position: QtCore.QPoint, /) -> QtGui.QAction | None:
        vertical = self.orientation() == Qt.Orientation.Vertical
        for action in self.actions():
            rect = self.actionGeometry(action)
            if not action.isVisible() or not rect.isValid():
                continue
            if vertical:
                before = position.y() < rect.center().y()
            elif self.isRightToLeft():
                before = position.x() > rect.center().x()
            else:
                before = position.x() < rect.center().x()
            if before:
                return action
        return None

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent, /) -> None:
        if self._drag_source(event.mimeData()) is None:
            event.ignore()
            return
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent, /) -> None:
        if self._drag_source(event.mimeData()) is None:
            event.ignore()
            return
        before = self._action_before(event.position().toPoint())
        rect = self.actionGeometry(before) if before is not None else self.rect()
        MARKER_WIDTH: Final = 2
        if self.orientation() == Qt.Orientation.Vertical:
            y = rect.top() if before is not None else rect.bottom() - MARKER_WIDTH
            self._drop_marker.setGeometry(0, y, self.width(), MARKER_WIDTH)
        else:
            if self.isRightToLeft():
                x = rect.right() - MARKER_WIDTH if before is not None else rect.left()
            else:
                x = rect.left() if before is not None else rect.right() - MARKER_WIDTH
            self._drop_marker.setGeometry(x, 0, MARKER_WIDTH, self.height())
        self._drop_marker.raise_()
        self._drop_marker.show()
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def dragLeaveEvent(self, event: QtGui.QDragLeaveEvent, /) -> None:
        self._drop_marker.hide()
        event.accept()

    def dropEvent(self, event: QtGui.QDropEvent, /) -> None:
        self._drop_marker.hide()
        source = self._drag_source(event.mimeData())
        if source is None:
            event.ignore()
            return
        toolbar, action = source
        before = self._action_before(event.position().toPoint())
        if action is not before:
            toolbar.removeAction(action)
            if before is None:
                self.addAction(action)
            else:
                self.insertAction(before, action)
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def _equalize_button_widths(self) -> None:
        buttons = [
            button
            for action in self.actions()
            if isinstance(
                (button := self.widgetForAction(action)), QtWidgets.QToolButton
            )
        ]
        if not buttons:
            return
        max_width = max(b.sizeHint().width() for b in buttons)
        for button in buttons:
            button.setMinimumWidth(max_width)
