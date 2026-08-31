# coding=utf8
# ***************************************************************************************
# This project is licensed under Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#          http://license.coscl.org.cn/MulanPSL2
#
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
#
# See the Mulan PSL v2 for more details.
# **************************************************************************************/


import importlib.util
import runpy
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


RUN_PATH = Path(__file__).parents[1] / "run.py"


def load_run_module():
    # Keep this infrastructure test independent of the DUT/config dependency
    # stack.  The CI image can then verify run.py before installing project
    # dependencies or downloading RTL.
    comm = types.ModuleType("comm")
    for name in (
        "base64_encode",
        "build_dut",
        "download_rtl",
        "error",
        "get_rtl_dir",
        "get_rtl_lnk_version",
        "init_cfg",
        "init_log",
        "new_report_name",
        "process_doc_result",
        "remove_version_tag",
    ):
        setattr(comm, name, object())

    module_name = "_unitychip_run_under_test"
    spec = importlib.util.spec_from_file_location(module_name, RUN_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    with patch.dict(sys.modules, {"comm": comm}):
        spec.loader.exec_module(module)
    return module


run = load_run_module()


@pytest.mark.parametrize(
    "pytest_exit_code",
    [
        pytest.ExitCode.OK,
        pytest.ExitCode.TESTS_FAILED,
        pytest.ExitCode.INTERRUPTED,
        pytest.ExitCode.INTERNAL_ERROR,
        pytest.ExitCode.USAGE_ERROR,
        pytest.ExitCode.NO_TESTS_COLLECTED,
    ],
)
def test_run_tests_preserves_pytest_exit_code_and_processes_report(monkeypatch, pytest_exit_code):
    calls = []
    pytest_args = ["-q", "tests"]
    cfg = object()

    def fake_pytest_main(args, plugins):
        calls.append(("pytest", args, plugins))
        return pytest_exit_code

    def fake_process_doc_result(report_dir, report_name, report_cfg):
        calls.append(("report", report_dir, report_name, report_cfg))

    monkeypatch.setattr(run.pytest, "main", fake_pytest_main)
    monkeypatch.setattr(run, "process_doc_result", fake_process_doc_result)

    exit_code = run.run_tests(pytest_args, "out/report", "index.html", cfg)

    assert exit_code == int(pytest_exit_code)
    assert calls == [
        ("pytest", pytest_args, [run]),
        ("report", "out/report", "index.html", cfg),
    ]


def test_cli_exits_with_pytest_failure_code_after_processing_report(monkeypatch):
    calls = []
    cfg = SimpleNamespace(
        rtl=SimpleNamespace(
            base_url=SimpleNamespace(encoded_string=lambda: "https://example.invalid/rtl"),
            cache_dir="rtl",
            version="latest",
        ),
        report=SimpleNamespace(
            report_name="",
            information=SimpleNamespace(model_dump=lambda **kwargs: {}),
        ),
        test=SimpleNamespace(
            skip_tags=[],
            run_tags=[],
            skip_cases=[],
            run_cases=[],
            skip_exceptions=[],
        ),
        model_dump=lambda **kwargs: {},
    )
    comm = types.ModuleType("comm")
    comm.base64_encode = lambda value: value
    comm.build_dut = lambda *args: None
    comm.download_rtl = lambda *args: None
    comm.error = lambda *args: None
    comm.get_rtl_dir = lambda *args: "rtl"
    comm.get_rtl_lnk_version = lambda *args: "openxiangshan-kmh-test-00000000"
    comm.init_cfg = lambda *args: cfg
    comm.init_log = lambda *args: None
    comm.new_report_name = lambda *args: ("out/report", "index.html")
    comm.process_doc_result = lambda *args: calls.append("report")
    comm.remove_version_tag = lambda version: version

    def fake_pytest_main(args, plugins):
        calls.append("pytest")
        return pytest.ExitCode.TESTS_FAILED

    monkeypatch.setattr(pytest, "main", fake_pytest_main)
    monkeypatch.setattr(
        sys,
        "argv",
        [str(RUN_PATH), "--no-waveform", "--no-code-cov", "--no-func-cov", "--", "-q", "tests"],
    )

    with patch.dict(sys.modules, {"comm": comm}):
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(str(RUN_PATH), run_name="__main__")

    assert exc_info.value.code == int(pytest.ExitCode.TESTS_FAILED)
    assert calls == ["pytest", "report"]
