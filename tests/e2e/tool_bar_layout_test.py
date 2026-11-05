from __future__ import annotations

import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import TOOLBAR_ACTIONS_KEY
from labelme._widgets._tool_bar import ToolBar

from .conftest import MainWinFactory


@pytest.mark.gui
@pytest.mark.parametrize(
    "area",
    [
        Qt.ToolBarArea.TopToolBarArea,
        Qt.ToolBarArea.BottomToolBarArea,
        Qt.ToolBarArea.LeftToolBarArea,
        Qt.ToolBarArea.RightToolBarArea,
    ],
)
def test_toolbars_redock_while_menu_stays_fixed(
    *, qtbot: QtBot, main_win: MainWinFactory, area: Qt.ToolBarArea
) -> None:
    win = main_win(size=None)
    win.show()
    menu = win.menuBar()
    menu_actions = menu.actions()
    toolbar = win.findChild(ToolBar, "CreateShapeToolsToolBar")
    assert toolbar is not None
    assert toolbar.isMovable() and toolbar.isFloatable()
    win.addToolBar(area, toolbar)
    qtbot.wait(10)
    assert win.toolBarArea(toolbar) == area
    assert win.menuWidget() is menu
    assert menu.parentWidget() is win
    assert menu.actions() == menu_actions
    assert menu.pos().y() == 0
    assert menu.isVisible()
    assert not isinstance(menu, QtWidgets.QToolBar)


@pytest.mark.gui
def test_toolbar_positions_and_button_order_survive_restart_and_reset(
    *, qtbot: QtBot, main_win: MainWinFactory
) -> None:
    win = main_win(size=None)
    win.show()
    tools = win.findChild(ToolBar, "ToolsToolBar")
    shapes = win.findChild(ToolBar, "CreateShapeToolsToolBar")
    assert tools is not None and shapes is not None
    original_tools = [a.property(ToolBar.ACTION_KEY) for a in tools.actions()]
    original_shapes = [a.property(ToolBar.ACTION_KEY) for a in shapes.actions()]
    menu_actions = list(win._menus.file.actions())
    action = win._actions.open_dir
    win.addToolBar(Qt.ToolBarArea.BottomToolBarArea, tools)
    win.addToolBar(Qt.ToolBarArea.RightToolBarArea, shapes)
    qtbot.wait(20)
    mime = ToolBar.mime_for_action(action)
    position = shapes.actionGeometry(shapes.actions()[0]).topLeft()
    enter = QtGui.QDragEnterEvent(
        position,
        Qt.DropAction.MoveAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QtWidgets.QApplication.sendEvent(shapes, enter)
    drop = QtGui.QDropEvent(
        QtCore.QPointF(position),
        Qt.DropAction.MoveAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QtWidgets.QApplication.sendEvent(shapes, drop)
    assert drop.isAccepted()
    assert shapes.actions()[0] is action
    assert action not in tools.actions()
    assert win._menus.file.actions() == menu_actions
    win.close()
    assert win._window_state.contains(TOOLBAR_ACTIONS_KEY)

    # Stable action keys must work independently of translated button text.
    reopened = main_win(config_overrides={"language": "zh_CN"}, size=None)
    reopened.show()
    qtbot.wait(20)
    tools2 = reopened.findChild(ToolBar, "ToolsToolBar")
    shapes2 = reopened.findChild(ToolBar, "CreateShapeToolsToolBar")
    assert tools2 is not None and shapes2 is not None
    assert reopened.toolBarArea(tools2) == Qt.ToolBarArea.BottomToolBarArea
    assert reopened.toolBarArea(shapes2) == Qt.ToolBarArea.RightToolBarArea
    assert shapes2.actions()[0] is reopened._actions.open_dir
    assert reopened._actions.open_dir not in tools2.actions()
    assert reopened._ai_annotation.parentWidget() is not None
    reopened._actions.reset_layout.trigger()
    assert reopened.toolBarArea(tools2) == Qt.ToolBarArea.TopToolBarArea
    assert reopened.toolBarArea(shapes2) == Qt.ToolBarArea.LeftToolBarArea
    assert [a.property(ToolBar.ACTION_KEY) for a in tools2.actions()] == original_tools
    assert [
        a.property(ToolBar.ACTION_KEY) for a in shapes2.actions()
    ] == original_shapes
    assert not reopened._window_state.contains(TOOLBAR_ACTIONS_KEY)


@pytest.mark.gui
def test_floating_toolbar_survives_restart(
    *, qtbot: QtBot, main_win: MainWinFactory
) -> None:
    win = main_win()
    win.show()
    qtbot.wait(10)
    toolbar = win.findChild(ToolBar, "CreateShapeToolsToolBar")
    assert toolbar is not None
    option = QtWidgets.QStyleOptionToolBar()
    toolbar.initStyleOption(option)
    handle = (
        toolbar.style()
        .subElementRect(QtWidgets.QStyle.SubElement.SE_ToolBarHandle, option, toolbar)
        .center()
    )
    qtbot.mousePress(toolbar, Qt.MouseButton.LeftButton, pos=handle)
    destination = win.mapToGlobal(win.rect().center())
    move = QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseMove,
        QtCore.QPointF(toolbar.mapFromGlobal(destination)),
        QtCore.QPointF(destination),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QtWidgets.QApplication.sendEvent(toolbar, move)
    qtbot.mouseRelease(
        toolbar, Qt.MouseButton.LeftButton, pos=toolbar.mapFromGlobal(destination)
    )
    assert toolbar.isFloating()
    win.close()
    reopened = main_win()
    reopened.show()
    qtbot.wait(10)
    restored = reopened.findChild(ToolBar, "CreateShapeToolsToolBar")
    assert restored is not None and restored.isFloating()
    assert reopened.menuBar().parentWidget() is reopened
    reopened._actions.reset_layout.trigger()
    assert not restored.isFloating()
