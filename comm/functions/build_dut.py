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

__all__ = ["build_dut", "UnsupportedDUTError"]

import glob
import shutil
import traceback
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from typing import Optional

from .utils import get_root_dir
from ..logger import warning, info


class UnsupportedDUTError(RuntimeError):
    """Raised by placeholder build scripts that have no DUT implementation yet."""


def _build_dut(d, cfg) -> Optional[bool]:
    try:
        module = import_module(f"scripts.{d}")
        if not module.build(cfg):
            warning(f"Build scripts/{d}.py failed")
            return False
        else:
            info(f"Build scripts/{d}.py success")
            return True
    except UnsupportedDUTError as e:
        warning(f"Skip unsupported scripts/{d}.py: {e}")
        return None
    except Exception as e:
        warning(f"Failed to build {d}, error: {e}\n{traceback.format_exc()}")
        return False


def is_dut_built(dut: str) -> bool:
    build_script = import_module(f"scripts.{dut}")
    assert hasattr(build_script, "TARGET_NAME") and isinstance(build_script.TARGET_NAME, str), \
        f"Build script: {dut} should have string variable `TARGET_NAME`"
    dut_package = find_spec(f"dut.{build_script.TARGET_NAME}")
    if not dut_package:
        return False
    elif not dut_package.loader:
        to_del = f"{get_root_dir()}/dut/{build_script.TARGET_NAME}"
        shutil.rmtree(to_del, ignore_errors=True)
        return False
    return True


def build_dut(duts: str, cfg) -> None:
    """Builds specified DUTs in parallel.

    This function discovers build scripts matching the DUT names provided,
    including support for wildcards (*, ?), and then executes them
    concurrently using a multiprocessing pool.

    Args:
        duts (str): A comma or space-separated string of DUT names to build.
        cfg: The configuration object to be passed to each build process.
    """
    target_duts = [d.strip() for d in duts.strip().split(",")]
    if not target_duts:
        warning(f"No dut to build for: {duts}")
        return
    prefix = "build_ut_"
    scripts_dir = get_root_dir("scripts")
    dut_to_build = set()
    searched_script = []
    for d in target_duts:
        if d.startswith("ut_"):
            d = d[3:]
        # Target is not a single file, is a dir
        if "/" in d:
            d = d.rstrip("/").replace("/", "_") + "*"
        searched_script.append(d)
        pattern = f"{scripts_dir}/{prefix}{d}.py"
        for match in glob.iglob(pattern):
            module_name = Path(match).stem
            dut_to_build.add(module_name)
    if not dut_to_build:
        warning(f"No dut to build for: {duts}")
        return

    import multiprocessing
    build_results = {}
    with multiprocessing.Pool() as pool:
        for dut in sorted(dut_to_build):
            if is_dut_built(dut):
                continue
            build_results[dut] = pool.apply_async(_build_dut, args=(dut, cfg))
        pool.close()
        pool.join()

    failed_duts = [dut for dut, result in build_results.items() if result.get() is False]
    if failed_duts:
        raise RuntimeError(f"Failed to build DUTs: {', '.join(failed_duts)}")
