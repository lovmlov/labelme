"""Observe real application and descendant exit without forcing success."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Final

import psutil


def _alive(process: psutil.Process, /) -> bool:
    try:
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def verify_exit(
    *, command: list[str], scenario: str, directory: Path, image: Path | None = None
) -> dict:
    STARTUP_TIMEOUT: Final = 60
    EXIT_TIMEOUT: Final = 15
    directory.mkdir(parents=True, exist_ok=True)
    probe = directory / "lifecycle.json"
    output = directory / "labels"
    output.mkdir(exist_ok=True)
    home = directory / "home"
    home.mkdir(exist_ok=True)
    env = dict(
        os.environ,
        HOME=str(home),
        USERPROFILE=str(home),
        LOCALAPPDATA=str(home),
        LABELME_PORTABLE_EXIT_REPORT=str(probe),
        LABELME_PORTABLE_EXIT_SCENARIO=scenario,
    )
    env.pop("LABELME_PORTABLE_TEST_REPORT", None)
    env.pop("LABELME_PORTABLE_EXIT_WORKER", None)
    arguments = [
        *command,
        "--config",
        json.dumps({"auto_save": False}),
        "--output",
        str(output),
    ]
    if image is not None:
        arguments.append(str(image))
    tracked: dict[int, psutil.Process] = {}
    result: dict = {"ok": False, "scenario": scenario}
    records: dict = {}
    start = time.monotonic()
    closing_started = None
    process = None
    with (directory / "console.log").open("w", encoding="utf-8") as console:
        try:
            process = subprocess.Popen(
                arguments, env=env, stdout=console, stderr=console
            )
            tracked[process.pid] = psutil.Process(process.pid)
            while True:
                for current in list(tracked.values()):
                    try:
                        for child in current.children(recursive=True):
                            tracked.setdefault(child.pid, child)
                    except psutil.NoSuchProcess:
                        pass
                if probe.exists():
                    try:
                        records = json.loads(probe.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        pass
                    child_pid = records.get("child_started", {}).get("child_pid")
                    if child_pid is not None and child_pid not in tracked:
                        try:
                            tracked[child_pid] = psutil.Process(child_pid)
                        except psutil.NoSuchProcess:
                            pass
                    if "close_event" in records and closing_started is None:
                        closing_started = time.monotonic()
                if process.poll() is not None and not any(
                    _alive(p) for p in tracked.values()
                ):
                    break
                deadline = (
                    start + STARTUP_TIMEOUT
                    if closing_started is None
                    else closing_started + EXIT_TIMEOUT
                )
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "Application or descendants remained after the close request."
                    )
                time.sleep(0.05)
            # The last lifecycle write can land between the polling read and
            # process.poll(). Read once more after exit before judging cleanup.
            if probe.exists():
                records = json.loads(probe.read_text(encoding="utf-8"))
            remaining = [p.pid for p in tracked.values() if _alive(p)]
            result.update(
                parent_exit_code=process.poll(),
                observed_pids=sorted(tracked),
                remaining_pids=remaining,
                seconds_after_close=round(
                    time.monotonic() - (closing_started or start), 3
                ),
                lifecycle=records,
            )
            assert process.poll() == 0, result
            assert "main_returned" in records, records
            assert records.get("close_event", {}).get("accepted") is True, records
            assert "event_loop_still_running" not in records, records
            assert not remaining, remaining
            threads = records["main_returned"]["threads"]
            assert not any(
                t["name"].startswith(("loguru-writer-", "image-prefetch"))
                for t in threads
            ), threads
            if scenario == "cancel":
                assert records.get("cancel_kept_window", {}).get("visible") is True, (
                    records
                )
            if scenario == "save":
                assert image is not None
                saved = json.loads(
                    (output / image.with_suffix(".json").name).read_text(
                        encoding="utf-8"
                    )
                )
                assert saved["shapes"][0]["label"] == "exit_probe", saved
            if scenario == "process-tree":
                assert records.get("child_started", {}).get("child_pid") is not None, (
                    records
                )
            result["ok"] = True
        except Exception as error:
            result["error"] = f"{type(error).__name__}: {error}"
            result["lifecycle"] = records
            result["remaining_pids"] = [p.pid for p in tracked.values() if _alive(p)]
        finally:
            # Kill only this failed test's own process family, after recording
            # failure. Production shutdown must never depend on the harness.
            for current in reversed(list(tracked.values())):
                if _alive(current):
                    current.kill()
            if process is not None:
                process.wait(timeout=5)
            psutil.wait_procs(list(tracked.values()), timeout=5)
    (directory / "result.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    args = parser.parse_args()
    scenarios = [
        "plain",
        "floating",
        "dialogs",
        "auxiliary",
        "save",
        "cancel",
        "process-tree",
    ]
    results = [
        verify_exit(
            command=[str(args.exe.resolve())],
            scenario=scenario,
            directory=args.reports / scenario,
            image=args.image.resolve(),
        )
        for scenario in scenarios
    ]
    summary = {"ok": all(r["ok"] for r in results), "scenarios": results}
    (args.reports / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if summary["ok"] else 1)
