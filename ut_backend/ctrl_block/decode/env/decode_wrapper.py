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

import ctypes
import datetime

import toffee
import toffee.funcov as fc
import toffee_test
from dut.DecodeStage import *
from dut.PreDecode import *
from dut.RVCExpander import *

from comm import get_out_dir, debug, UT_FCOV, get_file_logger, get_version_checker, module_name_with

# Version check
version_check = get_version_checker("openxiangshan-kmh-*")

# Create a function coverage group: INT (Int instruction)
g = fc.CovGroup(UT_FCOV("../../INT"))


def init_rvc_expander_funcov(expander, g: fc.CovGroup):
    """Add watch points to the RVCExpander module to collect function coverage information"""

    # 1. Add point RVC_EXPAND_RET to check expander return value:
    #    - bin ERROR. The instruction is not illegal
    #    - bin SUCCE. The instruction is not expanded
    g.add_watch_point(expander, {
        "ERROR": lambda x: x.stat()["ilegal"] == False,
        "SUCCE": lambda x: x.stat()["ilegal"] != False,
    }, name="RVC_EXPAND_RET")

    # 2. Add point RVC_EXPAND_16B_RANGE to check expander input range
    #   - bin RANGE[start-end]. The instruction is in the range of the compressed instruction set
    # This check point is added in case 'test_rv_decode.test_rvc_expand_16bit_full' dynamically, see the test case for details

    # 3. Add point RVC_EXPAND_32B_RANGE to check expander input range
    #   - bin RANGE[start-end]. The instruction is in the range of the 32bit instruction set
    # This check point is added in case 'test_rv_decode.test_rvc_expand_32bit_full' dynamically, see the test case for details

    # 4. Add point RVC_EXPAND_32B_BITS to check expander function coverage
    #   - bin BITS[0-31]. The instruction is expanded to the corresponding 32-bit instruction
    def _check_pos(i):
        def check(expander):
            return expander.stat()["instr"] & (1 << i) != 0

        return check

    g.add_watch_point(expander, {
        "POS_%d" % i: _check_pos(i)
        for i in range(32)
    }, name="RVC_EXPAND_32B_BITS")

    # 5. Reverse mark function coverage to the check point
    def _M(name):
        # get the module name
        return module_name_with(name, "../../test_rv_decode")

    #  - mark RVC_EXPAND_RET
    g.mark_function(
        "RVC_EXPAND_RET",
        _M(["test_rvc_expand_16bit_full",
            "test_rvc_expand_32bit_full",
            "test_rvc_expand_32bit_randomN"]),
        bin_name=["ERROR", "SUCCE"])
    #  - mark RVC_EXPAND_16B_RANGE
    g.mark_function("RVC_EXPAND_32B_BITS", _M("test_rvc_expand_32bit_randomN"), bin_name=["POS_*"], raise_error=False)

    # The End
    return None


def init_rv_decoder_funcov(g: fc.CovGroup):
    # TBD
    pass


class RVCExpander(toffee.Bundle):
    def __init__(self, cover_group, dut: DUTRVCExpander):
        super().__init__()
        self.cover_group = cover_group
        self.dut = dut
        self.io = toffee.Bundle.from_prefix("io_", self.dut)
        self.bind(self.dut)

    def expand(self, instr):
        self.io["in"].value = instr
        self.io["fsIsOff"].value = False
        self.dut.RefreshComb()
        self.cover_group.sample()
        return self.io["out_bits"].value, self.io["ill"].value

    def stat(self):
        return {
            "instr": self.io["in"].value,
            "decode": self.io["out_bits"].value,
            "ilegal": self.io["ill"].value != 0,
        }


@toffee_test.fixture
async def rvc_expander(toffee_request: toffee_test.ToffeeRequest):
    version_check()
    dut = toffee_request.create_dut(DUTRVCExpander)
    expander = RVCExpander(g, dut)
    toffee_request.cov_groups.append(g)
    expander.dut.io_in.AsImmWrite()
    init_rvc_expander_funcov(expander, g)
    return expander


class Decode(toffee.Bundle):
    def __init__(self, dut: DUTDecodeStage):
        super().__init__()
        self.dut = dut
        self._input_pin_names = tuple(
            name
            for name in dir(dut)
            if getattr(getattr(dut, name), "mIOType", None) == 0
            and name not in {"clock", "reset"}
        )
        for name in self._input_pin_names:
            getattr(dut, name).AsImmWrite()
        payload_prefix = "io_out_0_bits_"
        self._output_payload_fields = tuple(sorted(
            name[len(payload_prefix):]
            for name in dir(dut)
            if name.startswith(payload_prefix)
            and hasattr(getattr(dut, name), "value")
        ))
        required_payload_fields = {
            "instr", "firstUop", "lastUop", "uopIdx", "numUops"
        }
        missing_payload_fields = required_payload_fields.difference(
            self._output_payload_fields
        )
        if missing_payload_fields:
            raise RuntimeError(
                "DecodeStage output payload discovery missed: "
                + ", ".join(sorted(missing_payload_fields))
            )
        self._last_cycle_state = {}
        self._run_stats = {}

    def SetDefaultValue(self):
        """Drive every non-clock input to a deterministic default value."""
        for name in self._input_pin_names:
            getattr(self.dut, name).value = 0
        self.Set_output_ready(True)

    def Set_output_ready(self, ready):
        """Drive the six output ready signals with the same value.

        DecodeStage only uses lane 0 ready to calculate its global output
        capacity.  The integration contract therefore requires all six lanes
        to be driven together.
        """
        if type(ready) not in (bool, int) or ready not in (0, 1):
            raise ValueError("output ready must be boolean")
        ready_value = int(bool(ready))
        for lane in range(6):
            getattr(self.dut, f"io_out_{lane}_ready").value = ready_value

    def Get_output_ready_state(self):
        """Return the output ready state and reject partial-ready driving."""
        ready_state = tuple(
            int(getattr(self.dut, f"io_out_{lane}_ready").value)
            for lane in range(6)
        )
        assert len(set(ready_state)) == 1, \
            "DecodeStage output ready must be identical on all lanes"
        return ready_state

    def Reset(self):
        """Directly operate the dut pins to reset"""
        self.dut.reset.value = 0
        self.dut.Step(1)
        self.dut.reset.value = 1
        self.dut.Step(2)
        self.dut.reset.value = 0
        self.dut.Step(1)

    def Input_instruction(self, i, valid, instr, isRVC, brType, isCall, isRet, pred_taken, instr_ex):
        getattr(self.dut, f"io_in_{i}_valid").value = valid
        getattr(self.dut, f"io_in_{i}_bits_instr").value = instr
        foldpc = getattr(self.dut, f"io_in_{i}_bits_foldpc", None)
        if foldpc is not None:
            foldpc.value = 0
        for j in range(24):
            p = getattr(self.dut, f'io_in_{i}_bits_exceptionVec_{j}', None)
            if p is not None:
                p.value = 0
        getattr(self.dut, f"io_in_{i}_bits_exceptionVec_2").value = instr_ex
        getattr(self.dut, f"io_in_{i}_bits_trigger").value = 0
        getattr(
            self.dut, f"io_in_{i}_bits_preDecodeInfo_isRVC"
        ).value = isRVC
        getattr(
            self.dut, f"io_in_{i}_bits_preDecodeInfo_brType"
        ).value = brType
        getattr(
            self.dut, f"io_in_{i}_bits_preDecodeInfo_isCall"
        ).value = isCall
        getattr(
            self.dut, f"io_in_{i}_bits_preDecodeInfo_isRet"
        ).value = isRet
        getattr(self.dut, f"io_in_{i}_bits_pred_taken").value = pred_taken
        getattr(
            self.dut, f"io_in_{i}_bits_crossPageIPFFix"
        ).value = 0
        getattr(self.dut, f"io_in_{i}_bits_ftqPtr_flag").value = 0
        getattr(self.dut, f"io_in_{i}_bits_ftqPtr_value").value = 0
        getattr(self.dut, f"io_in_{i}_bits_ftqOffset").value = 0

    def FromCSR_illegalInst(self, sfenceVMA, sfencePart, hfenceGVMA, hfenceVVMA, hlsv, fsIsOff, vsIsOff, wfi, frm):
        self.dut.io_fromCSR_illegalInst_sfenceVMA.value = sfenceVMA
        self.dut.io_fromCSR_illegalInst_sfencePart.value = sfencePart
        self.dut.io_fromCSR_illegalInst_hfenceGVMA.value = hfenceGVMA
        self.dut.io_fromCSR_illegalInst_hfenceVVMA.value = hfenceVVMA
        self.dut.io_fromCSR_illegalInst_hlsv.value = hlsv
        self.dut.io_fromCSR_illegalInst_fsIsOff.value = fsIsOff
        self.dut.io_fromCSR_illegalInst_vsIsOff.value = vsIsOff
        self.dut.io_fromCSR_illegalInst_wfi.value = wfi
        self.dut.io_fromCSR_illegalInst_frm.value = frm

    def FromCSR_virtualInst(self, sfenceVMA, sfencePart, hfence, hlsv, wfi):
        self.dut.io_fromCSR_virtualInst_sfenceVMA.value = sfenceVMA
        self.dut.io_fromCSR_virtualInst_sfencePart.value = sfencePart
        self.dut.io_fromCSR_virtualInst_hfence.value = hfence
        self.dut.io_fromCSR_virtualInst_hlsv.value = hlsv
        self.dut.io_fromCSR_virtualInst_wfi.value = wfi

    def Get_input_ready(self, i):
        return getattr(self.dut, f"io_in_{i}_ready").value

    def Get_allow_input_number(self):
        """Return the contiguous prefix of inputs accepted this cycle."""
        fire_mask = self.Get_input_fire_mask()
        return next(
            (lane for lane, fired in enumerate(fire_mask) if not fired),
            len(fire_mask),
        )

    def Get_input_fire_mask(self):
        """Return input handshakes for the current combinational cycle."""
        return tuple(
            int(
                bool(getattr(self.dut, f"io_in_{lane}_valid").value)
                and bool(getattr(self.dut, f"io_in_{lane}_ready").value)
            )
            for lane in range(6)
        )

    def Get_input_valid_mask(self):
        """Return the current input valid state."""
        return tuple(
            int(bool(getattr(self.dut, f"io_in_{lane}_valid").value))
            for lane in range(6)
        )

    def Get_input_ready_state(self):
        """Return the current input ready state."""
        return tuple(
            int(bool(getattr(self.dut, f"io_in_{lane}_ready").value))
            for lane in range(6)
        )

    def Get_output_fire_mask(self):
        """Return output handshakes for the current combinational cycle."""
        return tuple(
            int(
                bool(getattr(self.dut, f"io_out_{lane}_valid").value)
                and bool(getattr(self.dut, f"io_out_{lane}_ready").value)
            )
            for lane in range(6)
        )

    def Get_output_valid_mask(self):
        """Return the current output valid state."""
        return tuple(
            int(bool(getattr(self.dut, f"io_out_{lane}_valid").value))
            for lane in range(6)
        )

    def Get_output_payloads(self):
        """Copy every output payload field into ordinary Python values."""
        output_payloads = []
        for lane in range(6):
            if getattr(self.dut, f"io_out_{lane}_valid").value != 1:
                continue
            fields = tuple(
                (field, int(getattr(
                    self.dut,
                    f"io_out_{lane}_bits_{field}"
                ).value))
                for field in self._output_payload_fields
            )
            output_payloads.append((lane, fields))
        return tuple(output_payloads)

    def Get_fired_uops(self):
        """Return the uops transferred on the current output handshake."""
        fired_uops = []
        for lane in range(6):
            if getattr(self.dut, f"io_out_{lane}_valid").value != 1 or \
                    getattr(self.dut, f"io_out_{lane}_ready").value != 1:
                continue
            fired_uops.append({
                "lane": lane,
                "instr": int(getattr(
                    self.dut, f"io_out_{lane}_bits_instr"
                ).value),
                "first_uop": int(getattr(
                    self.dut, f"io_out_{lane}_bits_firstUop"
                ).value),
                "last_uop": int(getattr(
                    self.dut, f"io_out_{lane}_bits_lastUop"
                ).value),
                "uop_idx": int(getattr(
                    self.dut, f"io_out_{lane}_bits_uopIdx"
                ).value),
                "num_uops": int(getattr(
                    self.dut, f"io_out_{lane}_bits_numUops"
                ).value),
            })
        return tuple(fired_uops)

    def Get_last_cycle_state(self):
        """Return the most recent Run_cycle handshake snapshot."""
        return self._last_cycle_state

    def Set_run_stats(self, stats):
        """Store the most recent decode_run statistics for functional coverage."""
        self._run_stats = dict(stats)

    def Get_run_stats(self):
        """Return statistics from the most recent decode_run call."""
        return self._run_stats

    def Input_instruction_list(self, insts, valid):
        if len(insts) > 6:
            raise ValueError("DecodeStage accepts at most six instructions")
        for i in range(6):
            self.Input_instruction(i, 0, 0, 0, 0, 0, 0, 0, 0)
        for i, inst in enumerate(insts):
            self.Input_instruction(i, valid, inst[0], 0, 0, 0, 0, 0, inst[3])

    def Get_decode_result(self, fired_only=False):
        """Return completed architectural instructions.

        The default preserves the historical valid-only behavior.  Protocol
        scoreboards should pass ``fired_only=True`` so a stalled output is not
        consumed more than once.
        """
        insts_result = []
        num = 0
        for i in range(6):
            output_valid = getattr(self.dut, f"io_out_{i}_valid").value == 1
            output_ready = getattr(self.dut, f"io_out_{i}_ready").value == 1
            output_fired = output_valid and output_ready
            output_last_uop = getattr(
                self.dut, f"io_out_{i}_bits_lastUop"
            ).value
            if output_valid and output_last_uop == 1 and (
                    not fired_only or output_fired):
                output_instr = getattr(
                    self.dut, f"io_out_{i}_bits_instr"
                ).value
                output_exception = (
                    getattr(
                        self.dut, f"io_out_{i}_bits_exceptionVec_2"
                    ).value
                    or getattr(
                        self.dut, f"io_out_{i}_bits_exceptionVec_22"
                    ).value
                )
                output_first_uop = getattr(
                    self.dut, f"io_out_{i}_bits_firstUop"
                ).value
                insts_result.append((
                    output_instr,
                    output_exception,
                    output_first_uop,
                ))
                num = num + 1
        return num, insts_result

    def Run_cycle(self, insts=(), output_ready=True, cover_group=None):
        """Drive and sample one ready/valid cycle before its rising edge."""
        insts = list(insts)
        if len(insts) > 6:
            raise ValueError("Run_cycle accepts at most six instructions")
        self.Set_output_ready(output_ready)
        self.Input_instruction_list(insts, int(bool(insts)))
        self.dut.RefreshComb()

        input_fire_mask = self.Get_input_fire_mask()
        seen_gap = False
        for fired in input_fire_mask:
            if not fired:
                seen_gap = True
            elif seen_gap:
                raise AssertionError("DecodeStage input fire must be a prefix")

        _, completed = self.Get_decode_result(fired_only=True)
        fired_uops = self.Get_fired_uops()
        self._last_cycle_state = {
            "accepted": sum(input_fire_mask),
            "input_valid_mask": self.Get_input_valid_mask(),
            "input_ready_state": self.Get_input_ready_state(),
            "input_instructions": tuple(
                int(getattr(
                    self.dut, f"io_in_{lane}_bits_instr"
                ).value)
                for lane in range(6)
            ),
            "input_fire_mask": input_fire_mask,
            "output_ready_state": self.Get_output_ready_state(),
            "output_valid_mask": self.Get_output_valid_mask(),
            "output_fire_mask": self.Get_output_fire_mask(),
            "output_payloads": self.Get_output_payloads(),
            "fired_uops": fired_uops,
            "completed": tuple(completed),
            "complex_last_uop_fired": any(
                uop["last_uop"] and not uop["first_uop"]
                for uop in fired_uops
            ),
        }
        if cover_group is not None:
            cover_group.sample()
        self.dut.Step(1)
        return self._last_cycle_state

    def Get_decode_checkpoint_illeagl_inst(self):
        illegal = 0
        for i in range(6):
            if getattr(self.dut, f"io_out_{i}_valid").value == 1 and \
                    getattr(self.dut, f"io_out_{i}_bits_lastUop").value == 1:
                if getattr(
                        self.dut,
                        f"io_out_{i}_bits_exceptionVec_2"
                ).value or getattr(
                        self.dut,
                        f"io_out_{i}_bits_exceptionVec_22"
                ).value:
                    illegal = 1
        if self._run_stats.get("saw_illegal_completion", False):
            illegal = 1
        return illegal

    def Get_decode_checkpoint_complex_inst(self):
        complex = 0
        for i in range(6):
            if getattr(self.dut, f"io_out_{i}_valid").value == 1 and \
                    getattr(self.dut, f"io_out_{i}_bits_lastUop").value == 1 and \
                    getattr(self.dut, f"io_out_{i}_bits_firstUop").value != 1:
                complex = 1
        if self._run_stats.get("saw_complex_last_uop", False):
            complex = 1
        return complex


@toffee_test.fixture
async def decoder(toffee_request: toffee_test.ToffeeRequest):
    import os
    # before test
    init_rv_decoder_funcov(g)
    # If the output directory does not exist, create it
    output_dir_path = get_out_dir("decoder/log")
    os.makedirs(output_dir_path, exist_ok=True)
    dut = toffee_request.create_dut(DUTDecodeStage, "clock")
    toffee_request.cov_groups.append(g)
    decoder = Decode(dut)
    return decoder


def comapre_result(ref_value_list, dut_value_list, num):
    eq = True
    if num == 0:
        return None
    else:
        for i in range(num):
            expected_exception = (
                ref_value_list[i][1] or ref_value_list[i][3]
            )
            if ref_value_list[i][0] != dut_value_list[i][0] or \
                    expected_exception != dut_value_list[i][1]:
                debug("================================")
                debug(ref_value_list[i])
                debug(dut_value_list[i])
                eq = False
    return eq


log_all_info_file = None
log_err_info_file = None


def open_log_file(name):
    global log_all_info_file
    global log_err_info_file
    # Obtain the current time and format it
    current_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = get_out_dir("decoder/log/log")
    # Create a file name
    if name is not None:
        filename_all = output_dir + f"_all_{name}.txt"
        filename_err = output_dir + f"_err_{name}.txt"
    else:
        filename_all = output_dir + f"_all_{current_time}.txt"
        filename_err = output_dir + f"_err_{current_time}.txt"
    log_all_info_file = get_file_logger(filename_all, format=None)
    log_err_info_file = get_file_logger(filename_err, format=None)


def close_log_file():
    global log_all_info_file
    global log_err_info_file
    if log_all_info_file is not None:
        log_all_info_file = None
    if log_err_info_file is not None:
        log_err_info_file = None


def write_all_info_to_file(info):
    if log_all_info_file is not None:
        log_all_info_file.info(info)
    else:
        debug("remember open_log_file , close_log_file")


def write_err_info_to_file(info):
    if log_err_info_file is not None:
        log_err_info_file.info(info)
    else:
        debug("remember open_log_file , close_log_file")


# Write the comparison results to a file
# ref_value_list[i][0] = Decimal display of instructions, ref_value_list[i][1] = The reference results are used to determine whether the instruction is illegal,
# ref_value_list[i][2] = Disassembly result of the instruction, ref_value_list[i][3] = Preliminary screening for illegal instructions is conducted through the RVCExpander module
# dut_value_list[i][0] = Decimal representation of the instructions output by the Decoder module, 
# dut_value_list[i][1] = The output results from the Decoder are used to determine whether anomalies exist, 
# dut_value_list[i][2] = The output results from the Decoder are used to determine whether the instruction is a complex instruction
def comapre_result_in_text(ref_value_list, dut_value_list, num):
    eq = True
    if num == 0:
        return None
    else:
        for i in range(num):
            disasm_text = ref_value_list[i][2]
            instruction_matches = (
                disasm_text == 0
                or ref_value_list[i][0] == dut_value_list[i][0]
            )
            # Random syntax-only disassembly has no architectural extension,
            # CSR or VType context, and may not know DUT-specific encodings.
            # This path therefore checks transfer/order only; deterministic
            # exception tests use comapre_result for an exact comparison.
            if instruction_matches:
                # print("Meets expectations:（￣︶￣）↗")
                good_info = f"good  ----- ref: {ref_value_list[i][0]}, {ref_value_list[i][1]}, {ref_value_list[i][2]}, {ref_value_list[i][3]}"
                write_all_info_to_file(good_info)
            else:
                # print("Not meeting expectations: <(_ _)>")
                bad_info = f"bad   ----- ref: {ref_value_list[i][0]}, {ref_value_list[i][1]}, {ref_value_list[i][2]}, {ref_value_list[i][3]}, old inst: {ref_value_list[i][4]},   dut: {dut_value_list[i][0]}, {dut_value_list[i][1]}, complex: {dut_value_list[i][2] == 0}"
                write_all_info_to_file(bad_info)
                write_err_info_to_file(bad_info)
                eq = False
    return eq


# Filter out certain cases where exception can be identified through instruction itself, 
# Supplement with the exception detection situation of the reference model.
def instr_filter(insn_disasm_text):
    instr_opcode = insn_disasm_text.split(' ')[0]
    is_except = 0
    if (instr_opcode == "c.lwsp" or instr_opcode == "c.ldsp" or instr_opcode == "c.addiw"):
        dst = insn_disasm_text.split()[1].split(',')[0]
        if dst == "zero":
            is_except = 1
    elif (instr_opcode == "c.addi4spn"):
        imm = insn_disasm_text.split()[3]
        if imm == "0":
            is_except = 1
    elif (instr_opcode == "c.addi16sp"):
        imm = insn_disasm_text.split()[2]
        if imm == "0":
            is_except = 1
    elif (instr_opcode == "c.lui"):
        imm = insn_disasm_text.split()[2]
        if imm == "0x0":
            is_except = 1
    elif (instr_opcode == "c.jr"):
        rs1 = insn_disasm_text.split()[1]
        if rs1 == "zero":
            is_except = 1
    elif (instr_opcode == "c.unimp"):
        is_except = 1
    return is_except


# Disassemble the instruction and send it to the rvc_expand module for decoding of compressed instructions
def convert_reference_format(rvc_expander, ref_insts, need_expand, disasm_func, disasm_free_func, disasm_arg=0):
    inst_list = []
    for insn in ref_insts:
        c_void_ptr = disasm_func(ctypes.c_uint64(insn), disasm_arg)
        insn_disasm = ctypes.cast(c_void_ptr, ctypes.c_char_p).value.decode('utf-8')
        disasm_free_func(c_void_ptr)

        if need_expand == True:
            instr_bits, instr_ex = rvc_expander.expand(insn)
        else:
            instr_ex = 0
            instr_bits = insn

        if insn_disasm == "unknown":
            inst_list.append((instr_bits, 1, insn_disasm, instr_ex, insn))
        else:
            is_excpet = instr_filter(insn_disasm)
            inst_list.append((instr_bits, is_excpet, insn_disasm, instr_ex, insn))
    return inst_list


# The main part of the test environment
def decode_run(decoder, inst_list, need_log_file, log_file_name=None,
               timeout_cycles=None, return_stats=False, cover_group=None):
    if need_log_file:
        open_log_file(log_file_name)
    decoder.SetDefaultValue()
    decoder.Reset()
    decoder.Set_run_stats({})
    pos = 0
    detect_pos = 0
    insts_length = len(inst_list)
    success = True
    if timeout_cycles is None:
        timeout_cycles = max(64, 16 * insts_length + 16)
    stats = {
        "accepted": 0,
        "completed": 0,
        "cycles": 0,
        "uops_fired": 0,
        "uop_trace": [],
        "last_input_fire_cycle": None,
        "last_completion_cycle": None,
        "timed_out": False,
        "drained": False,
        "saw_illegal_completion": False,
        "saw_complex_last_uop": False,
        "completed_instructions": [],
    }

    try:
        while pos < insts_length or detect_pos < insts_length:
            if stats["cycles"] >= timeout_cycles:
                stats["timed_out"] = True
                success = False
                debug(f"Decode timeout after {timeout_cycles} cycles")
                break

            cycle = stats["cycles"]
            cycle_state = decoder.Run_cycle(
                inst_list[pos:pos + 6],
                output_ready=True,
                cover_group=cover_group,
            )
            accepted = cycle_state["accepted"]
            old_pos = pos
            pos = pos + accepted
            stats["accepted"] = pos
            if old_pos < insts_length and pos >= insts_length:
                stats["last_input_fire_cycle"] = cycle

            step_result_list = list(cycle_state["completed"])
            num = len(step_result_list)
            stats["uops_fired"] += len(cycle_state["fired_uops"])
            stats["uop_trace"].extend(
                dict(uop, cycle=cycle)
                for uop in cycle_state["fired_uops"]
            )
            stats["saw_complex_last_uop"] = (
                stats["saw_complex_last_uop"]
                or cycle_state["complex_last_uop_fired"]
            )
            stats["saw_illegal_completion"] = (
                stats["saw_illegal_completion"]
                or any(bool(result[1]) for result in step_result_list)
            )
            if detect_pos + num > pos:
                success = False
                debug("Decode produced a completion before input handshake")
            if detect_pos + num > insts_length:
                success = False
                num = insts_length - detect_pos
                step_result_list = step_result_list[:num]
            if num > 0:
                ref_results = inst_list[detect_pos:detect_pos + num]
                if need_log_file:
                    if comapre_result_in_text(
                            ref_results, step_result_list, num) is False:
                        success = False
                elif comapre_result(
                        ref_results, step_result_list, num) is False:
                    success = False
                detect_pos = detect_pos + num
                stats["completed"] = detect_pos
                stats["last_completion_cycle"] = cycle
                stats["completed_instructions"].extend(
                    int(result[0]) for result in step_result_list
                )
            stats["cycles"] += 1

        stats["drained"] = (
            pos == insts_length and detect_pos == insts_length
        )
        if success and stats["drained"]:
            quiet_state = decoder.Run_cycle(
                (),
                output_ready=True,
                cover_group=cover_group,
            )
            stats["cycles"] += 1
            stats["uops_fired"] += len(quiet_state["fired_uops"])
            stats["uop_trace"].extend(
                dict(uop, cycle=stats["cycles"] - 1)
                for uop in quiet_state["fired_uops"]
            )
            if quiet_state["fired_uops"] or quiet_state["completed"]:
                success = False
    finally:
        close_log_file()

    stats["completed_instructions"] = tuple(
        stats["completed_instructions"]
    )
    stats["uop_trace"] = tuple(stats["uop_trace"])
    decoder.Set_run_stats(stats)
    if return_stats:
        return success, stats
    return success
