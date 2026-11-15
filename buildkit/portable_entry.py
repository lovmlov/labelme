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
    if (
        os.environ.get("LABELME_PORTABLE_EXIT_REPORT")
        and os.environ.get("LABELME_PORTABLE_EXIT_WORKER") == "1"
    ):
        import time

        time.sleep(120)  # Controlled descendant for the Windows process-tree test.
        return
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
        from portable_processes import install_process_guard

        try:
            install_process_guard()
        except OSError:
            # Nested-job restrictions must not prevent the GUI from starting.
            traceback.print_exc(file=crash_stream)
        if report := os.environ.get("LABELME_PORTABLE_TEST_REPORT"):
            from portable_smoke import run_smoke

            raise SystemExit(run_smoke(Path(report)))
        from labelme.__main__ import main

        finish_probe = None
        if exit_report := os.environ.get("LABELME_PORTABLE_EXIT_REPORT"):
            from portable_exit_probe import install_probe

            finish_probe = install_probe(
                report=Path(exit_report),
                scenario=os.environ.get("LABELME_PORTABLE_EXIT_SCENARIO", "plain"),
            )
        try:
            main()
        finally:
            if finish_probe is not None:
                finish_probe()
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
