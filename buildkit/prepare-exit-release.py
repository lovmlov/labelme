"""Validate this run's Windows output before publishing a new release."""

import hashlib
import json
import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Final
from zipfile import ZIP_DEFLATED
from zipfile import ZipFile

dist = Path("dist")
release = Path("release")
release.mkdir(exist_ok=True)
exe_name = "Labelme-7.9.1-exit.1-Windows-x64.exe"
bundle_name = "Labelme-7.9.1-exit.1-Windows-x64.zip"
source_sha = os.environ["GITHUB_SHA"]
repository = os.environ["GITHUB_REPOSITORY"]
run_id = os.environ["GITHUB_RUN_ID"]
assert (dist / "source-commit.txt").read_text().strip() == source_sha

report = json.loads((dist / "smoke-test.json").read_text(encoding="utf-8-sig"))
assert report["ok"] and report["version"] == "7.9.1+exit.1", report
assert "plain left click inserts polygon vertex in frozen EXE" in report["checks"]
assert "undo restores polygon after edge insertion" in report["checks"]
assert "Alt-only setting and Alt-click compatibility" in report["checks"]
assert (
    "toolbar button rearrangement, saved layout and fixed menu bar" in report["checks"]
)
assert "native toolbar handle drag, float and reset" in report["checks"]

exit_report = json.loads((dist / "exit-test.json").read_text(encoding="utf-8"))
assert exit_report["ok"], exit_report
assert {r["scenario"] for r in exit_report["scenarios"]} == {
    "plain",
    "floating",
    "dialogs",
    "auxiliary",
    "save",
    "cancel",
    "process-tree",
}
for scenario in exit_report["scenarios"]:
    assert scenario["ok"] and scenario["parent_exit_code"] == 0, scenario
    assert scenario["remaining_pids"] == [], scenario
    assert scenario["lifecycle"]["close_event"]["accepted"] is True, scenario
    assert "main_returned" in scenario["lifecycle"], scenario
    assert "event_loop_still_running" not in scenario["lifecycle"], scenario
for profile in ("default", "floating"):
    native_report = json.loads(
        (dist / f"native-exit-{profile}.json").read_text(encoding="utf-8")
    )
    assert native_report["ok"] and native_report["parent_exit_code"] == 0, native_report
    assert native_report["remaining_pids"] == [], native_report

tests = ET.parse(dist / "windows-tests.xml").getroot()
suites = [tests] if tests.tag == "testsuite" else list(tests.iter("testsuite"))
assert suites
assert all(int(suite.get("failures", "0")) == 0 for suite in suites)
assert all(int(suite.get("errors", "0")) == 0 for suite in suites)
test_count = sum(int(suite.get("tests", "0")) for suite in suites)
skipped = sum(int(suite.get("skipped", "0")) for suite in suites)
assert test_count > skipped
SOURCE_EXIT_SCENARIOS: Final = 6
assert (
    sum(
        case.get("name", "").startswith(
            "test_real_entrypoint_releases_process_after_close"
        )
        for case in tests.iter("testcase")
    )
    == SOURCE_EXIT_SCENARIOS
)
assert any(
    case.get("name") == "test_accepted_close_releases_models_and_pending_preview"
    for case in tests.iter("testcase")
)
assert any(
    case.get("name", "").startswith("test_edge_click_inserts_saves_and_undoes")
    for case in tests.iter("testcase")
)

assert any(
    case.get("name", "").startswith("test_native_handle_drag_floats_toolbar")
    for case in tests.iter("testcase")
)

with (dist / exe_name).open("rb") as stream:
    exe_hash = hashlib.file_digest(stream, "sha256").hexdigest()
assert (dist / "SHA256SUMS.txt").read_text().strip() == f"{exe_hash}  {exe_name}"
shutil.copy2(dist / exe_name, release / exe_name)
with ZipFile(release / bundle_name, "w", compression=ZIP_DEFLATED) as archive:
    for path in sorted(dist.iterdir()):
        assert path.is_file(), path
        archive.write(path, arcname=path.name)
with (release / bundle_name).open("rb") as stream:
    bundle_hash = hashlib.file_digest(stream, "sha256").hexdigest()
(release / "SHA256SUMS.txt").write_text(
    f"{exe_hash}  {exe_name}\n{bundle_hash}  {bundle_name}\n", encoding="ascii"
)

notes = Path("buildkit/exit-release-notes.md").read_text(encoding="utf-8")
notes += (
    f"\n验证结果：Windows 回归测试 {test_count - skipped} 项通过，"
    f"{skipped} 项跳过；生成的 EXE 自检、7 种完整进程退出场景"
    "和 2 种 Windows 原生关闭场景通过。\n\n"
    f"[构建与测试记录](https://github.com/{repository}/actions/runs/{run_id}) · "
    f"[本包精确源码](https://github.com/{repository}/tree/{source_sha})\n"
)
Path("release-notes.md").write_text(notes, encoding="utf-8")
print(f"Validated {test_count - skipped} Windows tests and frozen EXE: {exe_hash}")
