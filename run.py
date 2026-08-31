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


import argparse
import json
import os

import pytest

from comm import build_dut, remove_version_tag
from comm import download_rtl, get_rtl_dir, init_log, new_report_name, process_doc_result, base64_encode
from comm import init_cfg, get_rtl_lnk_version, error


def run_tests(pytest_args, report_dir, report_name, cfg):
    pytest_exit_code = pytest.main(pytest_args, plugins=[__import__(__name__)])
    process_doc_result(report_dir, report_name, cfg)
    return int(pytest_exit_code)


def main():
    parser = argparse.ArgumentParser(description="Run pytest")
    parser.add_argument("--config", type=str, help="config file", default=None)
    parser.add_argument("-b", "--build", type=str, help="duts to buld, eg: -b dut1,dut2; -b dut*", default="")
    parser.add_argument("--download-rtl", action="store_true", help="only download rtl")
    parser.add_argument("--allure-json", action="store_true", help="generate allure-report json data")
    parser.add_argument("--no-waveform", action="store_true", default=False, help="don't generate waveform")
    parser.add_argument("--no-code-cov", action="store_true", default=False, help="don't generate code coverage")
    parser.add_argument("--no-func-cov", action="store_true", default=False, help="do not generate coverage report")
    args, append_args = parser.parse_known_args()
    cfg_value = []
    for a in append_args.copy():
        key = append_args.pop(0)
        if "=" in key:
            cfg_value.append(key)
        if a.startswith("--"):
            break
    if args.config:
        if not os.path.exists(args.config):
            error("config file not found: %s", args.config)
            return
    # Initial config and logger
    cfg = init_cfg(args.config, cfg_value)
    init_log(cfg)
    # Download rtl
    base_url = cfg.rtl.base_url.encoded_string()
    download_rtl(base_url, cfg.rtl.cache_dir, cfg.rtl.version)
    if args.download_rtl:
        return
    # Check & Set rtl version
    link_version = get_rtl_lnk_version(cfg)
    if cfg.rtl.version != "latest":
        assert link_version == cfg.rtl.version, f"RTL link version ({link_version}) not equal to config version ({cfg.rtl.version})"
    else:
        cfg.rtl.version = link_version  # set current rtl version
    cfg.rtl.version = remove_version_tag(cfg.rtl.version)
    # Set report dir & name
    report_dir, report_name = new_report_name(cfg)
    cfg.report.report_name = report_name
    # Set waveform and coverage
    cfg.no_waveform = args.no_waveform
    cfg.no_func_cov = args.no_func_cov
    cfg.no_code_cov = args.no_code_cov
    # Build dut
    if args.build:
        build_dut(args.build, cfg)
        return
    else:
        build_duts = ",".join([x for x in append_args if not x.startswith("-")])
        build_dut(build_duts, cfg)
    # Set report args
    toffee_key_value = {
        "toffee_tags_current_version": cfg.rtl.version,
        "toffee_tags_skip_tags": cfg.test.skip_tags,
        "toffee_tags_run_tags": cfg.test.run_tags,
        "toffee_tags_skip_cases": cfg.test.skip_cases,
        "toffee_tags_run_cases": cfg.test.run_cases,
        "toffee_ignore_exceptions": cfg.test.skip_exceptions,
        "toffee_report_information": cfg.report.information.model_dump(mode="json", by_alias=True),
        "global_unitychip_cfg": cfg.model_dump(mode="json", by_alias=True),
    }
    append_args.extend([
        "--report-dir", report_dir,
        "--report-name", report_name,
        "--report-dump-json",
        "--custom-key-value", base64_encode(json.dumps(toffee_key_value))
    ])
    if args.allure_json:
        def _allure_dir(pdir, pname):
            return os.path.join(os.path.dirname(os.path.join(pdir, pname)), "allure")
        append_args.extend(["--alluredir", _allure_dir(report_dir, report_name)])
    return run_tests(append_args, report_dir, report_name, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
