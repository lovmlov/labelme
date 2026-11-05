from __future__ import annotations

import json

import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._widgets._tool_bar import ToolBar
from labelme._widgets._tool_bar_layout import restore_toolbar_actions
from labelme._widgets._tool_bar_layout import save_toolbar_actions


def _bar(*, qtbot: QtBot, name: str, labels: str = "ABC") -> ToolBar:
    toolbar = ToolBar(
        title=name,
        actions=[QtGui.QAction(label) for label in labels],
    )
    qtbot.addWidget(toolbar)
    toolbar.resize(600, 90)
    toolbar.show()
    return toolbar


def _drop(*, target: ToolBar, action: QtGui.QAction, position: QtCore.QPoint) -> bool:
    mime = ToolBar.mime_for_action(action)
    enter = QtGui.QDragEnterEvent(
        position,
        Qt.DropAction.MoveAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QtWidgets.QApplication.sendEvent(target, enter)
    move = QtGui.QDragMoveEvent(
        position,
        Qt.DropAction.MoveAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QtWidgets.QApplication.sendEvent(target, move)
    drop = QtGui.QDropEvent(
        QtCore.QPointF(position),
        Qt.DropAction.MoveAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QtWidgets.QApplication.sendEvent(target, drop)
    return enter.isAccepted() and move.isAccepted() and drop.isAccepted()


@pytest.mark.parametrize(
    "orientation", [Qt.Orientation.Horizontal, Qt.Orientation.Vertical]
)
def test_drop_reorders_buttons_without_activating(
    *, qtbot: QtBot, orientation: Qt.Orientation
) -> None:
    toolbar = _bar(qtbot=qtbot, name="Tools")
    toolbar.setOrientation(orientation)
    qtbot.wait(10)
    a, b, c = toolbar.actions()
    with qtbot.assertNotEmitted(c.triggered):
        assert _drop(
            target=toolbar, action=c, position=toolbar.actionGeometry(a).topLeft()
        )
    assert toolbar.actions() == [c, a, b]
    button = toolbar.widgetForAction(c)
    assert isinstance(button, QtWidgets.QToolButton)
    with qtbot.waitSignal(c.triggered):
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)


def test_button_drag_crosses_toolbars_and_preserves_menu_action(
    *, qtbot: QtBot
) -> None:
    window = QtWidgets.QMainWindow()
    qtbot.addWidget(window)
    source = _bar(qtbot=qtbot, name="Source")
    target = _bar(qtbot=qtbot, name="Target", labels="DE")
    window.addToolBar(source)
    window.addToolBar(Qt.ToolBarArea.LeftToolBarArea, target)
    action = source.actions()[0]
    menu = window.menuBar().addMenu("File")
    menu.addAction(action)
    window.show()
    qtbot.wait(10)
    assert _drop(target=target, action=action, position=QtCore.QPoint(1, 1))
    assert action not in source.actions()
    assert action in target.actions()
    assert menu.actions() == [action]
    assert window.menuWidget() is window.menuBar()
    assert window.menuBar().parentWidget() is window


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
def test_real_mouse_drag_does_not_trigger_action(
    *, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, cancel: bool, enabled: bool
) -> None:
    toolbar = _bar(qtbot=qtbot, name="Tools")
    a, b, c = toolbar.actions()
    a.setEnabled(enabled)
    button = toolbar.widgetForAction(a)
    assert isinstance(button, QtWidgets.QToolButton)
    started = []

    class TestDrag(QtGui.QDrag):
        def exec(self, *_args: object, **_kwargs: object) -> Qt.DropAction:
            started.append(True)
            if cancel:
                return Qt.DropAction.IgnoreAction
            assert _drop(
                target=toolbar,
                action=a,
                position=toolbar.actionGeometry(c).bottomRight() + QtCore.QPoint(20, 0),
            )
            return Qt.DropAction.MoveAction

    monkeypatch.setattr(QtGui, "QDrag", TestDrag)
    with qtbot.assertNotEmitted(a.triggered):
        qtbot.mousePress(button, Qt.MouseButton.LeftButton, pos=button.rect().center())
        pos = button.rect().center() + QtCore.QPoint(
            QtWidgets.QApplication.startDragDistance() + 5, 0
        )
        move = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseMove,
            QtCore.QPointF(pos),
            QtCore.QPointF(button.mapToGlobal(pos)),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QtWidgets.QApplication.sendEvent(button, move)
        qtbot.mouseRelease(toolbar, Qt.MouseButton.LeftButton)
    assert started
    assert toolbar.actions() == ([a, b, c] if cancel else [b, c, a])


def test_foreign_drag_cannot_change_toolbar(*, qtbot: QtBot) -> None:
    toolbar = _bar(qtbot=qtbot, name="Tools")
    original = toolbar.actions()
    other_window = _bar(qtbot=qtbot, name="Other")
    assert not _drop(
        target=toolbar, action=other_window.actions()[0], position=QtCore.QPoint()
    )
    assert toolbar.actions() == original


def test_orientation_change_releases_vertical_widths(*, qtbot: QtBot) -> None:
    toolbar = _bar(qtbot=qtbot, name="Tools")
    toolbar.setOrientation(Qt.Orientation.Vertical)
    qtbot.wait(10)
    buttons = [toolbar.widgetForAction(a) for a in toolbar.actions()]
    assert all(
        isinstance(b, QtWidgets.QToolButton) and b.minimumWidth() > 0 for b in buttons
    )
    toolbar.setOrientation(Qt.Orientation.Horizontal)
    qtbot.wait(10)
    assert all(
        isinstance(b, QtWidgets.QToolButton) and b.minimumWidth() == 0 for b in buttons
    )
    assert not toolbar.styleSheet()


def test_native_handle_drag_floats_toolbar(*, qtbot: QtBot) -> None:
    window = QtWidgets.QMainWindow()
    qtbot.addWidget(window)
    toolbar = _bar(qtbot=qtbot, name="Tools")
    window.addToolBar(toolbar)
    window.resize(800, 500)
    window.show()
    qtbot.wait(20)
    option = QtWidgets.QStyleOptionToolBar()
    toolbar.initStyleOption(option)
    handle = (
        toolbar.style()
        .subElementRect(QtWidgets.QStyle.SubElement.SE_ToolBarHandle, option, toolbar)
        .center()
    )
    qtbot.mousePress(toolbar, Qt.MouseButton.LeftButton, pos=handle)
    outside = window.mapToGlobal(window.rect().bottomRight() + QtCore.QPoint(50, 50))
    local = toolbar.mapFromGlobal(outside)
    move = QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseMove,
        QtCore.QPointF(local),
        QtCore.QPointF(outside),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QtWidgets.QApplication.sendEvent(toolbar, move)
    qtbot.mouseRelease(
        toolbar, Qt.MouseButton.LeftButton, pos=toolbar.mapFromGlobal(outside)
    )
    qtbot.wait(20)
    assert toolbar.isFloating()
    assert window.menuBar().parentWidget() is window
    target = _bar(qtbot=qtbot, name="Target", labels="DE")
    window.addToolBar(Qt.ToolBarArea.BottomToolBarArea, target)
    qtbot.wait(10)
    assert _drop(
        target=target, action=toolbar.actions()[0], position=QtCore.QPoint(1, 1)
    )


def test_save_restore_button_order_preserves_embedded_widget(*, qtbot: QtBot) -> None:
    toolbar = _bar(qtbot=qtbot, name="Tools")
    a, b, c = toolbar.actions()
    widget = QtWidgets.QLineEdit("AI prompt")
    widget_action = QtWidgets.QWidgetAction(toolbar)
    widget_action.setDefaultWidget(widget)
    # Construct a bar whose default layout includes the editable widget.
    other = ToolBar(title="Other", actions=[widget_action])
    qtbot.addWidget(other)
    bars = [toolbar, other]
    toolbar.removeAction(c)
    toolbar.insertAction(a, c)
    toolbar.removeAction(b)
    other.insertAction(widget_action, b)
    saved = save_toolbar_actions(toolbars=bars)
    restore_toolbar_actions(toolbars=bars)
    assert toolbar.actions() == [a, b, c]
    assert other.actions() == [widget_action]
    restore_toolbar_actions(toolbars=bars, state=saved)
    assert toolbar.actions() == [c, a]
    assert other.actions() == [b, widget_action]
    assert other.widgetForAction(widget_action) is widget
    assert widget.text() == "AI prompt"


@pytest.mark.parametrize(
    "corruption", ["json", "unknown", "duplicate", "missing", "anchor"]
)
def test_bad_saved_order_is_ignored_without_losing_actions(
    *, qtbot: QtBot, corruption: str
) -> None:
    separator = QtGui.QAction()
    separator.setSeparator(True)
    first = ToolBar(title="First", actions=[QtGui.QAction("A"), separator])
    second = _bar(qtbot=qtbot, name="Second", labels="B")
    qtbot.addWidget(first)
    original = [first.actions(), second.actions()]
    saved = json.loads(save_toolbar_actions(toolbars=[first, second]))
    if corruption == "unknown":
        saved["FirstToolBar"][0] = "unknown"
    elif corruption == "duplicate":
        saved["SecondToolBar"][0] = saved["FirstToolBar"][0]
    elif corruption == "missing":
        saved["FirstToolBar"].pop()
    elif corruption == "anchor":
        saved["SecondToolBar"].append(saved["FirstToolBar"].pop())
    state = "not JSON" if corruption == "json" else json.dumps(saved)
    restore_toolbar_actions(toolbars=[first, second], state=state)
    assert [first.actions(), second.actions()] == original
