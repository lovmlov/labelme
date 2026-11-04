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
        import labelme  # Imports ONNXRuntime before Qt on Windows.
        import onnxruntime
        import osam
        from PIL import Image
        from PySide6 import QtCore, QtWidgets

        from labelme._app import MainWindow
        from labelme._locale import available_translation_locales
        from labelme._shape import Shape

        assert labelme.__version__ == "7.9.1", labelme.__version__
        results["version"] = labelme.__version__
        results["onnxruntime"] = onnxruntime.__version__
        results["qt"] = QtCore.qVersion()
        results["checks"].append("version and native dependency imports")
        assert "zh_CN" in available_translation_locales()
        results["checks"].append("bundled Simplified Chinese translations")
        assert osam.apis
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        with tempfile.TemporaryDirectory(prefix="labelme-portable-test-") as tmp:
            tmp_path = Path(tmp)
            image_path = tmp_path / "sample.png"
            annotation_path = tmp_path / "sample.json"
            Image.new("RGB", (320, 240), (180, 190, 200)).save(image_path)
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
            win._insert_shapes([shape])
            assert win.save_labels(label_path=str(annotation_path))
            data = json.loads(annotation_path.read_text(encoding="utf-8"))
            assert data["shapes"][0]["label"] == "portable_test", data
            assert data["imageWidth"] == 320 and data["imageHeight"] == 240
            assert win._load_file(image_or_label_path=str(annotation_path))
            assert win._canvas_widgets.canvas.shapes[0].label == "portable_test"
            results["checks"].append("polygon annotation save and reopen")
            app.processEvents()
            win.close()
            app.processEvents()
        results["ok"] = True
    except BaseException:
        results["error"] = traceback.format_exc()
    finally:
        report.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        if app:
            app.quit()
    return 0 if results["ok"] else 1
