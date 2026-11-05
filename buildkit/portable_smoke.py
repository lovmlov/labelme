# ruff: noqa: PLC0415 -- defer imports until startup logging is active
"""Exercise the packaged GUI and annotation I/O without downloading AI models."""

from __future__ import annotations

import json
import tempfile
import traceback
from pathlib import Path


def run_smoke(report: Path) -> int:
    results: dict = {"ok": False, "checks": []}
    report.parent.mkdir(parents=True, exist_ok=True)
    app = None
    win = None
    try:
        import onnxruntime
        import osam
        from PIL import Image
        from PySide6 import QtCore
        from PySide6 import QtGui
        from PySide6 import QtWidgets

        import labelme  # Imports ONNXRuntime before Qt on Windows.
        from labelme._app import MainWindow
        from labelme._locale import available_translation_locales
        from labelme._shape import Shape

        assert labelme.__version__ == "7.9.1+edgeclick.1", labelme.__version__
        results["version"] = labelme.__version__
        results["onnxruntime"] = onnxruntime.__version__
        results["qt"] = QtCore.qVersion()
        results["checks"].append("version and native dependency imports")
        assert "zh_CN" in available_translation_locales()
        translator = QtCore.QTranslator()
        assert translator.load(
            str(Path(labelme.__file__).parent / "translate" / "zh_CN.qm")
        )
        assert (
            translator.translate("Canvas", "Click to add a point on the edge")
            == "单击以在边缘新增点"
        )
        results["checks"].append("bundled Simplified Chinese translations")
        assert osam.apis
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        with tempfile.TemporaryDirectory(prefix="labelme-portable-test-") as tmp:
            tmp_path = Path(tmp)
            image_path = tmp_path / "sample.png"
            annotation_path = tmp_path / "sample.json"
            sample_size = (320, 240)
            Image.new("RGB", sample_size, (180, 190, 200)).save(image_path)
            win = MainWindow(
                config_file=None,
                config_overrides={"auto_save": False, "language": "zh_CN"},
                file_or_dir=None,
            )
            win.show()
            app.processEvents()
            assert win._load_file(image_or_label_path=str(image_path))
            app.processEvents()
            results["checks"].append("Qt window and image decoding")
            shape = Shape(
                label="portable_test",
                shape_type="polygon",
                points=[[20, 20], [100, 20], [100, 100]],
                closed=True,
            )
            original_point_count = len(shape.points)
            win._insert_shapes([shape])
            win._switch_canvas_mode(edit=True, create_mode=None)
            canvas = win._canvas_widgets.canvas
            assert canvas._add_point_on_edge_without_alt is True

            def click_edge(modifiers: QtCore.Qt.KeyboardModifier) -> None:
                position = canvas.transform_image_point_to_widget(
                    QtCore.QPointF(60, 20)
                )
                # Explicit events also refresh hover on repeated clicks at one pixel.
                for event_type, button, buttons in [
                    (
                        QtCore.QEvent.Type.MouseMove,
                        QtCore.Qt.MouseButton.NoButton,
                        QtCore.Qt.MouseButton.NoButton,
                    ),
                    (
                        QtCore.QEvent.Type.MouseButtonPress,
                        QtCore.Qt.MouseButton.LeftButton,
                        QtCore.Qt.MouseButton.LeftButton,
                    ),
                    (
                        QtCore.QEvent.Type.MouseButtonRelease,
                        QtCore.Qt.MouseButton.LeftButton,
                        QtCore.Qt.MouseButton.NoButton,
                    ),
                ]:
                    event = QtGui.QMouseEvent(
                        event_type,
                        position,
                        QtCore.QPointF(canvas.mapToGlobal(position.toPoint())),
                        button,
                        buttons,
                        modifiers,
                    )
                    QtWidgets.QApplication.sendEvent(canvas, event)
                    app.processEvents()

            click_edge(QtCore.Qt.KeyboardModifier.NoModifier)
            assert len(canvas.shapes[0].points) == original_point_count + 1
            results["checks"].append(
                "plain left click inserts polygon vertex in frozen EXE"
            )
            win._actions.undo.trigger()
            assert len(canvas.shapes[0].points) == original_point_count
            results["checks"].append("undo restores polygon after edge insertion")
            canvas.set_add_point_on_edge_without_alt(value=False)
            click_edge(QtCore.Qt.KeyboardModifier.NoModifier)
            assert len(canvas.shapes[0].points) == original_point_count
            click_edge(QtCore.Qt.KeyboardModifier.AltModifier)
            assert len(canvas.shapes[0].points) == original_point_count + 1
            results["checks"].append("Alt-only setting and Alt-click compatibility")
            assert win.save_labels(label_path=str(annotation_path))
            data = json.loads(annotation_path.read_text(encoding="utf-8"))
            assert data["shapes"][0]["label"] == "portable_test", data
            assert len(data["shapes"][0]["points"]) == original_point_count + 1
            assert (data["imageWidth"], data["imageHeight"]) == sample_size
            assert win._load_file(image_or_label_path=str(annotation_path))
            assert win._canvas_widgets.canvas.shapes[0].label == "portable_test"
            assert (
                len(win._canvas_widgets.canvas.shapes[0].points)
                == original_point_count + 1
            )
            results["checks"].append("polygon annotation save and reopen")
            app.processEvents()
            win.close()
            app.processEvents()
        results["ok"] = True
    except BaseException:
        results["error"] = traceback.format_exc()
    finally:
        report.write_text(
            json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if app:
            app.quit()
    return 0 if results["ok"] else 1
