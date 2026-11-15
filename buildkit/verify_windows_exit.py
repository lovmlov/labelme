"""Close the real Windows GUI and verify the entire PyInstaller process family exits."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path
from typing import Final

import psutil


def _windows(*, pids: set[int]) -> list[dict]:
    if sys.platform != "win32":
        raise RuntimeError("Native window enumeration requires Windows.")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    result: list[dict] = []
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]

    def visit(hwnd: int, _parameter: int, /) -> bool:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd) + 1)
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, len(title))
            user32.GetClassNameW(hwnd, class_name, len(class_name))
            result.append(
                {
                    "hwnd": hwnd,
                    "pid": pid.value,
                    "title": title.value,
                    "class": class_name.value,
                }
            )
        return True

    user32.EnumWindows(callback_type(visit), 0)
    return result


def _alive(process: psutil.Process, /) -> bool:
    try:
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def _profile(*, floating: bool) -> None:
    # Only used on the ephemeral Windows CI runner. Native Qt stores this
    # under HKCU, just as the standalone program does.
    from PySide6 import QtCore  # noqa: PLC0415
    from PySide6 import QtGui  # noqa: PLC0415
    from PySide6 import QtWidgets  # noqa: PLC0415

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    settings = QtCore.QSettings("labelme", "labelme")
    settings.clear()
    if floating:
        window = QtWidgets.QMainWindow()
        window.resize(1000, 700)
        toolbar = QtWidgets.QToolBar("Tools")
        toolbar.setObjectName("ToolsToolBar")
        toolbar.setWindowFlags(
            toolbar.windowFlags() | QtCore.Qt.WindowType.FramelessWindowHint
        )
        toolbar.addAction("Probe")
        window.addToolBar(toolbar)
        shapes = QtWidgets.QToolBar("Shape Tools")
        shapes.setObjectName("CreateShapeToolsToolBar")
        shapes.addAction("Polygon")
        window.addToolBar(QtCore.Qt.ToolBarArea.LeftToolBarArea, shapes)
        window.show()
        app.processEvents()
        option = QtWidgets.QStyleOptionToolBar()
        toolbar.initStyleOption(option)
        handle = (
            toolbar.style()
            .subElementRect(
                QtWidgets.QStyle.SubElement.SE_ToolBarHandle, option, toolbar
            )
            .center()
        )
        destination = window.mapToGlobal(window.rect().center())
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
            app.processEvents()
        assert toolbar.isFloating()
        settings.setValue("window/state", window.saveState())
        settings.setValue("window/size", window.size())
        settings.setValue("settingsVersion", 1)
        window.close()
        app.processEvents()
    settings.sync()


def verify(
    *,
    executable: Path,
    report: Path,
    image: Path | None,
    floating: bool,
    timeout: float,
) -> bool:
    if sys.platform != "win32":
        raise RuntimeError("This native WM_CLOSE test must run on Windows.")
    _profile(floating=floating)
    outcome: dict = {"ok": False, "profile": "floating" if floating else "default"}
    tracked: dict[int, psutil.Process] = {}
    process = None
    STARTUP_TIMEOUT: Final = 60
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="labelme-exit-") as temporary:
        env = dict(os.environ, LOCALAPPDATA=temporary)
        command = [str(executable), "--config", json.dumps({"auto_save": False})]
        if image is not None:
            command.append(str(image))
        try:
            process = subprocess.Popen(command, env=env)
            tracked[process.pid] = psutil.Process(process.pid)
            hwnd = None
            while time.monotonic() - start < STARTUP_TIMEOUT:
                for current in list(tracked.values()):
                    try:
                        for child in current.children(recursive=True):
                            tracked.setdefault(child.pid, child)
                    except psutil.NoSuchProcess:
                        pass
                windows = _windows(pids=set(tracked))
                matches = [
                    w
                    for w in windows
                    if "labelme" in w["title"].lower() and w["class"].startswith("Qt")
                ]
                if matches:
                    hwnd = matches[0]["hwnd"]
                    outcome["window"] = matches[0]
                    break
                if process.poll() is not None:
                    raise RuntimeError(
                        "Application exited before its main window: "
                        f"{process.returncode}"
                    )
                time.sleep(0.1)
            if hwnd is None:
                raise RuntimeError("The main window did not appear within 60 seconds.")
            # Allow the image/prefetch startup to settle before sending the same
            # native message produced by the main window's Close button.
            time.sleep(0.5)
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.PostMessageW.argtypes = [
                wintypes.HWND,
                wintypes.UINT,
                wintypes.WPARAM,
                wintypes.LPARAM,
            ]
            if not user32.PostMessageW(hwnd, 0x0010, 0, 0):
                raise ctypes.WinError(ctypes.get_last_error())
            closed = time.monotonic()
            while time.monotonic() - closed < timeout:
                for current in list(tracked.values()):
                    try:
                        for child in current.children(recursive=True):
                            tracked.setdefault(child.pid, child)
                    except psutil.NoSuchProcess:
                        pass
                if process.poll() is not None and not any(
                    _alive(p) for p in tracked.values()
                ):
                    break
                time.sleep(0.1)
            remaining = [p for p in tracked.values() if _alive(p)]
            outcome.update(
                seconds_after_close=round(time.monotonic() - closed, 3),
                parent_exit_code=process.poll(),
                observed_pids=sorted(tracked),
                remaining_pids=[p.pid for p in remaining],
                visible_windows_after_close=_windows(pids=set(tracked)),
                rss_after_close=sum(p.memory_info().rss for p in remaining),
            )
            outcome["ok"] = process.poll() == 0 and not remaining
        except Exception as error:
            outcome["error"] = f"{type(error).__name__}: {error}"
        finally:
            # Failure cleanup belongs to the test harness. A killed process is
            # always a failed test, never counted as a successful application exit.
            for current in reversed(list(tracked.values())):
                if _alive(current):
                    current.kill()
            if process is not None:
                process.wait(timeout=5)
            psutil.wait_procs(list(tracked.values()), timeout=5)
            logs = Path(temporary) / "labelme"
            outcome["logs"] = {
                p.name: p.read_text(encoding="utf-8", errors="replace")[-12000:]
                for p in logs.glob("*.log")
            }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(outcome, ensure_ascii=False))
    return outcome["ok"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--floating", action="store_true")
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    ok = verify(
        executable=args.exe.resolve(),
        report=args.report,
        image=args.image,
        floating=args.floating,
        timeout=args.timeout,
    )
    raise SystemExit(0 if ok or args.observe_only else 1)
