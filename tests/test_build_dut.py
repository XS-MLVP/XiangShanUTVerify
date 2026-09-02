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
import multiprocessing
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest


BUILD_DUT_PATH = Path(__file__).parents[1] / "comm" / "functions" / "build_dut.py"
UNSUPPORTED_BUILD_SCRIPTS = [
    "build_ut_backend_ctrl_block_rob.py",
    "build_ut_frontend_bpu_ftb.py",
    "build_ut_frontend_bpu_top.py",
    "build_ut_frontend_bpu_uftb.py",
    "build_ut_frontend_bpu_ras.py",
    "build_ut_mem_block_lsq.py",
]


def load_build_dut_module():
    comm = types.ModuleType("comm")
    comm.__path__ = []
    functions = types.ModuleType("comm.functions")
    functions.__path__ = []
    utils = types.ModuleType("comm.functions.utils")
    utils.get_root_dir = lambda *parts: str(BUILD_DUT_PATH.parents[2].joinpath(*parts))
    logger = types.ModuleType("comm.logger")
    logger.warning = lambda *args: None
    logger.info = lambda *args: None

    module_name = "comm.functions._build_dut_under_test"
    spec = importlib.util.spec_from_file_location(module_name, BUILD_DUT_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "comm": comm,
            "comm.functions": functions,
            "comm.functions.utils": utils,
            "comm.logger": logger,
            module_name: module,
        },
    ):
        spec.loader.exec_module(module)
    return module


build_dut_module = load_build_dut_module()


class ImmediateResult:
    def __init__(self, value):
        self.value = value
        self.consumed = False

    def get(self):
        self.consumed = True
        return self.value


class RaisingResult:
    def __init__(self, error):
        self.error = error
        self.consumed = False

    def get(self):
        self.consumed = True
        raise self.error


class ImmediatePool:
    def __init__(self):
        self.submitted = []
        self.results = []
        self.closed = False
        self.joined = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def apply_async(self, function, args):
        self.submitted.append(args[0])
        result = ImmediateResult(function(*args))
        self.results.append(result)
        return result

    def close(self):
        self.closed = True

    def join(self):
        self.joined = True


class AsyncFailurePool(ImmediatePool):
    def apply_async(self, _function, args):
        self.submitted.append(args[0])
        result = RaisingResult(RuntimeError("synthetic worker transport failure"))
        self.results.append(result)
        return result


@pytest.mark.parametrize("build_result", [False, None])
def test_worker_reports_falsey_build_result(monkeypatch, build_result):
    script = types.SimpleNamespace(build=lambda _cfg: build_result)
    monkeypatch.setattr(build_dut_module, "import_module", lambda _name: script)

    assert build_dut_module._build_dut("build_ut_example", object()) is False


def test_worker_reports_exception(monkeypatch):
    def raise_during_build(_cfg):
        raise RuntimeError("synthetic build failure")

    script = types.SimpleNamespace(build=raise_during_build)
    monkeypatch.setattr(build_dut_module, "import_module", lambda _name: script)

    assert build_dut_module._build_dut("build_ut_example", object()) is False


def test_worker_reports_success(monkeypatch):
    script = types.SimpleNamespace(build=lambda _cfg: True)
    monkeypatch.setattr(build_dut_module, "import_module", lambda _name: script)

    assert build_dut_module._build_dut("build_ut_example", object()) is True


def test_worker_skips_explicitly_unsupported_build(monkeypatch):
    def unsupported_build(_cfg):
        raise build_dut_module.UnsupportedDUTError("not implemented")

    script = types.SimpleNamespace(build=unsupported_build)
    monkeypatch.setattr(build_dut_module, "import_module", lambda _name: script)

    assert build_dut_module._build_dut("build_ut_example", object()) is None


@pytest.mark.parametrize("script_name", UNSUPPORTED_BUILD_SCRIPTS)
def test_placeholder_build_script_declares_unsupported(script_name):
    script_path = BUILD_DUT_PATH.parents[2] / "scripts" / script_name
    comm = types.ModuleType("comm")
    comm.UnsupportedDUTError = build_dut_module.UnsupportedDUTError
    module_name = f"_unsupported_{script_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    module = importlib.util.module_from_spec(spec)

    with patch.dict(sys.modules, {"comm": comm, module_name: module}):
        spec.loader.exec_module(module)

    with pytest.raises(build_dut_module.UnsupportedDUTError, match="build implementation"):
        module.build(object())


def test_build_dut_raises_after_all_workers_finish(monkeypatch):
    pool = ImmediatePool()
    outcomes = {
        "build_ut_alpha": False,
        "build_ut_beta": True,
        "build_ut_gamma": False,
    }

    def fake_iglob(pattern):
        target = Path(pattern).stem
        return iter([f"/repo/scripts/{target}.py"])

    monkeypatch.setattr(build_dut_module.glob, "iglob", fake_iglob)
    monkeypatch.setattr(build_dut_module, "is_dut_built", lambda _dut: False)
    monkeypatch.setattr(build_dut_module, "_build_dut", lambda dut, _cfg: outcomes[dut])
    monkeypatch.setattr(multiprocessing, "Pool", lambda: pool)

    with pytest.raises(
        RuntimeError,
        match=r"Failed to build DUTs: build_ut_alpha, build_ut_gamma",
    ):
        build_dut_module.build_dut("gamma,alpha,beta", object())

    assert pool.submitted == ["build_ut_alpha", "build_ut_beta", "build_ut_gamma"]
    assert all(result.consumed for result in pool.results)
    assert pool.closed
    assert pool.joined


def test_build_dut_propagates_async_result_failure(monkeypatch):
    pool = AsyncFailurePool()

    monkeypatch.setattr(
        build_dut_module.glob,
        "iglob",
        lambda _pattern: iter(["/repo/scripts/build_ut_example.py"]),
    )
    monkeypatch.setattr(build_dut_module, "is_dut_built", lambda _dut: False)
    monkeypatch.setattr(multiprocessing, "Pool", lambda: pool)

    with pytest.raises(RuntimeError, match="synthetic worker transport failure"):
        build_dut_module.build_dut("example", object())

    assert pool.submitted == ["build_ut_example"]
    assert pool.results[0].consumed
    assert pool.closed
    assert pool.joined


@pytest.mark.parametrize("target", ["*", "ut_frontend/bpu"])
def test_build_dut_skips_unsupported_results_for_broad_targets(monkeypatch, target):
    pool = ImmediatePool()
    outcomes = {
        "build_ut_frontend_bpu_ftb": None,
        "build_ut_frontend_bpu_ittage": True,
        "build_ut_frontend_bpu_top": None,
    }

    def fake_iglob(_pattern):
        return iter(f"/repo/scripts/{dut}.py" for dut in outcomes)

    monkeypatch.setattr(build_dut_module.glob, "iglob", fake_iglob)
    monkeypatch.setattr(build_dut_module, "is_dut_built", lambda _dut: False)
    monkeypatch.setattr(build_dut_module, "_build_dut", lambda dut, _cfg: outcomes[dut])
    monkeypatch.setattr(multiprocessing, "Pool", lambda: pool)

    assert build_dut_module.build_dut(target, object()) is None
    assert pool.submitted == sorted(outcomes)
    assert all(result.consumed for result in pool.results)


def test_build_dut_accepts_success_and_skips_prebuilt(monkeypatch):
    pool = ImmediatePool()

    def fake_iglob(pattern):
        target = Path(pattern).stem
        return iter([f"/repo/scripts/{target}.py"])

    monkeypatch.setattr(build_dut_module.glob, "iglob", fake_iglob)
    monkeypatch.setattr(build_dut_module, "is_dut_built", lambda dut: dut == "build_ut_cached")
    monkeypatch.setattr(build_dut_module, "_build_dut", lambda _dut, _cfg: True)
    monkeypatch.setattr(multiprocessing, "Pool", lambda: pool)

    assert build_dut_module.build_dut("cached,new", object()) is None
    assert pool.submitted == ["build_ut_new"]
    assert pool.closed
    assert pool.joined
