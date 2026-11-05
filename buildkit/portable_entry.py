# ruff: noqa: PLC0415 -- defer imports until startup logging is active
"""Windows portable entry point; runs the installed customized application."""

from __future__ import annotations

import faulthandler
import multiprocessing
import os
import sys
import traceback
from pathlib import Path


def run() -> None:
    multiprocessing.freeze_support()
    log_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "labelme"
    log_dir.mkdir(parents=True, exist_ok=True)
    crash_stream = (log_dir / "portable-startup.log").open(
        "a", encoding="utf-8", buffering=1
    )
    if sys.stdout is None:
        sys.stdout = crash_stream
    if sys.stderr is None:
        sys.stderr = crash_stream
    faulthandler.enable(file=crash_stream, all_threads=True)
    try:
        if report := os.environ.get("LABELME_PORTABLE_TEST_REPORT"):
            from portable_smoke import run_smoke

            raise SystemExit(run_smoke(Path(report)))
        from labelme.__main__ import main

        main()
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc(file=crash_stream)
        crash_stream.flush()
        try:
            if sys.platform == "win32":
                import ctypes

                ctypes.windll.user32.MessageBoxW(
                    None,
                    "Labelme could not start. Details were saved to:\n"
                    f"{log_dir / 'portable-startup.log'}",
                    "Labelme startup error",
                    0x10,
                )
        except Exception:
            pass
        raise


if __name__ == "__main__":
    run()
