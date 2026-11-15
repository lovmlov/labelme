"""Exercise normal main()/app.exec() shutdown; never call app.quit() in the probe."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any


def install_probe(*, report: Path, scenario: str) -> Callable[[], None]:
    import numpy as np  # noqa: PLC0415
    from PySide6 import QtCore  # noqa: PLC0415
    from PySide6 import QtGui  # noqa: PLC0415
    from PySide6 import QtWidgets  # noqa: PLC0415

    import labelme.__main__ as cli  # noqa: PLC0415
    from labelme._shape import Shape  # noqa: PLC0415
    from labelme._widgets._tool_bar import ToolBar  # noqa: PLC0415

    report.parent.mkdir(parents=True, exist_ok=True)
    records: dict[str, Any] = {"pid": os.getpid(), "scenario": scenario}

    def record(stage: str, /, **extra: object) -> None:
        records[stage] = {
            "threads": [
                {"name": t.name, "daemon": t.daemon} for t in threading.enumerate()
            ],
            **extra,
        }
        temporary = report.with_suffix(".tmp")
        temporary.write_text(json.dumps(records, indent=2), encoding="utf-8")
        temporary.replace(report)

    QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
    QtCore.QSettings.setPath(
        QtCore.QSettings.Format.IniFormat,
        QtCore.QSettings.Scope.UserScope,
        str(report.parent / "qtsettings"),
    )
    original = cli.MainWindow
    original_question = QtWidgets.QMessageBox.question

    class ProbedWindow(original):
        def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
            super().__init__(**kwargs)
            self._exit_probe_auxiliary: QtWidgets.QWidget | None = None
            QtCore.QTimer.singleShot(250, self._exercise_close)

        def _exercise_close(self) -> None:
            if scenario == "floating":
                toolbar = self.findChild(ToolBar, "ToolsToolBar")
                assert toolbar is not None
                option = QtWidgets.QStyleOptionToolBar()
                toolbar.initStyleOption(option)
                handle = (
                    toolbar.style()
                    .subElementRect(
                        QtWidgets.QStyle.SubElement.SE_ToolBarHandle,
                        option,
                        toolbar,
                    )
                    .center()
                )
                destination = self.mapToGlobal(self.rect().center())
                for kind, position, button, buttons in [
                    (
                        QtCore.QEvent.Type.MouseButtonPress,
                        toolbar.mapToGlobal(handle),
                        QtCore.Qt.MouseButton.LeftButton,
                        QtCore.Qt.MouseButton.LeftButton,
                    ),
                    (
                        QtCore.QEvent.Type.MouseMove,
                        destination,
                        QtCore.Qt.MouseButton.NoButton,
                        QtCore.Qt.MouseButton.LeftButton,
                    ),
                    (
                        QtCore.QEvent.Type.MouseButtonRelease,
                        destination,
                        QtCore.Qt.MouseButton.LeftButton,
                        QtCore.Qt.MouseButton.NoButton,
                    ),
                ]:
                    event = QtGui.QMouseEvent(
                        kind,
                        QtCore.QPointF(toolbar.mapFromGlobal(position)),
                        QtCore.QPointF(position),
                        button,
                        buttons,
                        QtCore.Qt.KeyboardModifier.NoModifier,
                    )
                    QtWidgets.QApplication.sendEvent(toolbar, event)
                assert toolbar.isFloating()
                record("floating_ready", floating=True)
            elif scenario == "dialogs":
                self._open_settings()
                self._open_models()
                record("dialogs_ready")
            elif scenario == "process-tree":
                # Deliberately leave a child alive. The frozen Windows process's
                # Job Object must stop it after normal GUI termination.
                child_env = dict(os.environ, LABELME_PORTABLE_EXIT_WORKER="1")
                child = subprocess.Popen([sys.executable], env=child_env)
                self._exit_probe_child = child
                record("child_started", child_pid=child.pid)
            elif scenario == "auxiliary":
                # Reproduce a top-level auxiliary window lacking its transient
                # parent. Auto-quit alone would leave app.exec() running.
                auxiliary = QtWidgets.QWidget()
                auxiliary.setWindowTitle("Exit probe auxiliary")
                auxiliary.setAttribute(
                    QtCore.Qt.WidgetAttribute.WA_QuitOnClose, on=True
                )
                auxiliary.show()
                self._exit_probe_auxiliary = auxiliary
                record("auxiliary_ready", primary=auxiliary.isWindow())
            elif scenario in ("save", "cancel"):
                if scenario == "save":
                    self._actions.save_auto.setChecked(True)
                self._insert_shapes(
                    [
                        Shape(
                            label="exit_probe",
                            shape_type="polygon",
                            closed=True,
                            points=np.array(
                                [[20, 20], [100, 20], [100, 100]], dtype=np.float64
                            ),
                        )
                    ]
                )
                self.mark_dirty()
                if scenario == "save":
                    record("save_started")
                else:
                    choices = iter(
                        [
                            QtWidgets.QMessageBox.StandardButton.Cancel,
                            QtWidgets.QMessageBox.StandardButton.Discard,
                        ]
                    )
                    setattr(
                        QtWidgets.QMessageBox,
                        "question",
                        staticmethod(lambda *_a, **_k: next(choices)),
                    )
                    assert not self.close()
                    record("cancel_kept_window", visible=self.isVisible())
                    QtCore.QTimer.singleShot(100, self.close)
                    return
            record("ready_to_close")
            self.close()
            QtCore.QTimer.singleShot(250, lambda: record("event_loop_still_running"))

        def closeEvent(self, event: QtGui.QCloseEvent, /) -> None:
            super().closeEvent(event)
            record("close_event", accepted=event.isAccepted())

    setattr(cli, "MainWindow", ProbedWindow)
    record("probe_installed")

    def finish() -> None:
        setattr(cli, "MainWindow", original)
        setattr(QtWidgets.QMessageBox, "question", staticmethod(original_question))
        record("main_returned")

    return finish
