from __future__ import annotations

import weakref
from typing import cast

import pytest
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._automation import OsamSession


class _LoadedModel:
    pass


def _install_loaded_sessions(
    *, win: MainWindow
) -> tuple[weakref.ReferenceType, weakref.ReferenceType]:
    point_model = _LoadedModel()
    text_model = _LoadedModel()
    canvas = win._canvas_widgets.canvas
    canvas._ai_assist_session.set_model_name("sam2:latest")
    canvas._ai_assist_session._session = cast(OsamSession, point_model)
    win._text_osam_session = cast(OsamSession, text_model)
    return weakref.ref(point_model), weakref.ref(text_model)


def test_accepted_close_releases_models_and_pending_preview(
    *, raw_win: MainWindow, qtbot: QtBot
) -> None:
    point, text = _install_loaded_sessions(win=raw_win)
    canvas = raw_win._canvas_widgets.canvas
    canvas._ai_preview_timer.start(10_000)
    raw_win._fit_selection_timer.start(10_000)
    with qtbot.waitSignal(raw_win.close_accepted):
        assert raw_win.close()
    assert point() is None and text() is None
    assert not canvas._ai_preview_timer.isActive()
    assert not raw_win._fit_selection_timer.isActive()


def test_cancelled_close_keeps_models_and_emits_no_exit(
    *, raw_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    point, text = _install_loaded_sessions(win=raw_win)
    raw_win._actions.save_auto.setChecked(False)
    raw_win.mark_dirty()
    with monkeypatch.context() as patch:
        patch.setattr(
            QtWidgets.QMessageBox,
            "question",
            lambda *_a, **_k: QtWidgets.QMessageBox.StandardButton.Cancel,
        )
        with qtbot.assertNotEmitted(raw_win.close_accepted):
            assert not raw_win.close()
        assert raw_win.isVisible()
        assert point() is not None and text() is not None
    raw_win.mark_clean()
    assert raw_win.close()


def test_failed_worker_shutdown_does_not_exit_or_release_active_models(
    *, raw_win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    point, text = _install_loaded_sessions(win=raw_win)
    with monkeypatch.context() as patch:
        patch.setattr(raw_win._model_manager, "shutdown", lambda: False)
        with qtbot.assertNotEmitted(raw_win.close_accepted):
            assert not raw_win.close()
        assert raw_win.isVisible()
        assert point() is not None and text() is not None
    assert raw_win.close()
