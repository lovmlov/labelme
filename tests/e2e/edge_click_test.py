from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PySide6 import QtWidgets
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._shape import Shape
from labelme._shape import ShapeType
from labelme._yaml import safe_load

from .conftest import MainWinFactory
from .conftest import drag_canvas
from .conftest import hover_widget_pos
from .conftest import image_to_widget_pos


@pytest.fixture(autouse=True)
def _discard_test_edits(
    *, raw_win: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Failed assertions must not leave a save-confirmation dialog in Qt teardown.
    monkeypatch.setattr(raw_win, "_can_continue", lambda: True)


def _insert_shape(*, win: MainWindow, shape_type: ShapeType = "polygon") -> Shape:
    canvas = win._canvas_widgets.canvas
    win._apply_setting_change(("auto_save",), False)  # noqa: FBT003
    win._switch_canvas_mode(edit=True, create_mode=None)
    width, height = canvas.pixmap.width(), canvas.pixmap.height()
    shape = Shape(
        label="edge_click_test",
        shape_type=shape_type,
        points=np.array(
            [
                (width * 0.2, height * 0.2),
                (width * 0.8, height * 0.2),
                (width * 0.8, height * 0.8),
                (width * 0.2, height * 0.8),
            ],
            dtype=np.float64,
        ),
        closed=shape_type == "polygon",
    )
    win._insert_shapes([shape])
    return shape


def _edge_position(*, shape: Shape) -> QPointF:
    return QPointF(*((shape.points[0] + shape.points[1]) / 2))


def _click_edge(
    *,
    qtbot: QtBot,
    win: MainWindow,
    shape: Shape,
    modifier: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    canvas = win._canvas_widgets.canvas
    pos = image_to_widget_pos(canvas=canvas, image_pos=_edge_position(shape=shape))
    hover_widget_pos(qtbot=qtbot, canvas=canvas, pos=pos)
    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, modifier, pos=pos)


@pytest.mark.gui
@pytest.mark.parametrize("shape_type", ["polygon", "linestrip"])
@pytest.mark.parametrize(
    "modifier", [Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.AltModifier]
)
def test_edge_click_inserts_saves_and_undoes(
    *,
    qtbot: QtBot,
    raw_win: MainWindow,
    tmp_path: Path,
    shape_type: ShapeType,
    modifier: Qt.KeyboardModifier,
) -> None:
    shape = _insert_shape(win=raw_win, shape_type=shape_type)
    original = shape.points.copy()
    _click_edge(qtbot=qtbot, win=raw_win, shape=shape, modifier=modifier)
    assert len(shape.points) == 5
    np.testing.assert_array_equal(shape.points[[0, 2, 3, 4]], original)
    output = tmp_path / "edge-click.json"
    assert raw_win.save_labels(label_path=str(output))
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert len(saved["shapes"][0]["points"]) == 5
    raw_win._actions.undo.trigger()
    np.testing.assert_array_equal(
        raw_win._canvas_widgets.canvas.shapes[0].points, original
    )


@pytest.mark.gui
@pytest.mark.parametrize(
    "modifier",
    [
        Qt.KeyboardModifier.ControlModifier,
        Qt.KeyboardModifier.ShiftModifier,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    ],
)
def test_selection_modifiers_do_not_insert_points(
    *, qtbot: QtBot, raw_win: MainWindow, modifier: Qt.KeyboardModifier
) -> None:
    shape = _insert_shape(win=raw_win)
    original = shape.points.copy()
    _click_edge(qtbot=qtbot, win=raw_win, shape=shape, modifier=modifier)
    np.testing.assert_array_equal(shape.points, original)


@pytest.mark.gui
@pytest.mark.parametrize(
    "modifier", [Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.AltModifier]
)
def test_locked_polygon_cannot_gain_points(
    *, qtbot: QtBot, raw_win: MainWindow, modifier: Qt.KeyboardModifier
) -> None:
    shape = _insert_shape(win=raw_win)
    shape.locked = True
    original = shape.points.copy()
    _click_edge(qtbot=qtbot, win=raw_win, shape=shape, modifier=modifier)
    np.testing.assert_array_equal(shape.points, original)


@pytest.mark.gui
def test_new_vertex_can_be_dragged_and_undone(
    *, qtbot: QtBot, raw_win: MainWindow
) -> None:
    canvas = raw_win._canvas_widgets.canvas
    shape = _insert_shape(win=raw_win)
    original = shape.points.copy()
    edge = _edge_position(shape=shape)
    start = image_to_widget_pos(canvas=canvas, image_pos=edge)
    end = image_to_widget_pos(canvas=canvas, image_pos=edge + QPointF(0, 25))
    hover_widget_pos(qtbot=qtbot, canvas=canvas, pos=start)
    drag_canvas(
        qtbot=qtbot,
        canvas=canvas,
        button=Qt.MouseButton.LeftButton,
        start=start,
        end=end,
    )
    assert len(shape.points) == 5
    assert shape.points[1, 1] > original[0, 1]
    np.testing.assert_array_equal(shape.points[[0, 2, 3, 4]], original)
    raw_win._actions.undo.trigger()
    np.testing.assert_array_equal(canvas.shapes[0].points, original)


@pytest.mark.gui
def test_existing_vertex_drag_does_not_insert(
    *, qtbot: QtBot, raw_win: MainWindow
) -> None:
    canvas = raw_win._canvas_widgets.canvas
    shape = _insert_shape(win=raw_win)
    start = image_to_widget_pos(canvas=canvas, image_pos=QPointF(*shape.points[0]))
    end = image_to_widget_pos(
        canvas=canvas, image_pos=QPointF(*shape.points[0]) + QPointF(20, 20)
    )
    original = shape.points.copy()
    hover_widget_pos(qtbot=qtbot, canvas=canvas, pos=start)
    drag_canvas(
        qtbot=qtbot,
        canvas=canvas,
        button=Qt.MouseButton.LeftButton,
        start=start,
        end=end,
    )
    assert len(shape.points) == 4
    assert not np.array_equal(shape.points[0], original[0])
    np.testing.assert_array_equal(shape.points[1:], original[1:])


@pytest.mark.gui
def test_setting_updates_canvas_and_persists(
    *, qtbot: QtBot, raw_win: MainWindow, main_win: MainWinFactory
) -> None:
    shape = _insert_shape(win=raw_win)
    raw_win._open_settings()
    dialog = raw_win._settings_dialog
    assert dialog is not None
    editor = dialog._editors[("canvas", "add_point_on_edge_without_alt")]
    assert isinstance(editor, QtWidgets.QCheckBox)
    assert editor.isChecked()
    editor.setChecked(False)
    dialog.close()
    assert raw_win._config_file is not None
    saved = safe_load(raw_win._config_file.read_text(encoding="utf-8"))
    assert saved["canvas"]["add_point_on_edge_without_alt"] is False
    _click_edge(qtbot=qtbot, win=raw_win, shape=shape)
    assert len(shape.points) == 4
    _click_edge(
        qtbot=qtbot, win=raw_win, shape=shape, modifier=Qt.KeyboardModifier.AltModifier
    )
    assert len(shape.points) == 5
    reopened = main_win(config_file=raw_win._config_file)
    assert reopened._canvas_widgets.canvas._add_point_on_edge_without_alt is False
    raw_win._apply_setting_change(("canvas", "add_point_on_edge_without_alt"), True)  # noqa: FBT003
    assert raw_win._canvas_widgets.canvas._add_point_on_edge_without_alt is True
