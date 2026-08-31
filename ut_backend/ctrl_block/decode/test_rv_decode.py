#coding=utf8
#***************************************************************************************
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
#**************************************************************************************/


from .env import *
from tools.insn_gen import *
from tools.disasm import disasmbly, libdisasm


def _decode_references(instructions, expected_exception=0):
    """Build deterministic references without invoking the random generator."""
    return [
        (instruction, expected_exception, "", 0, instruction)
        for instruction in instructions
    ]


@toffee_test.testcase
async def test_decode_backpressure_holds_and_releases(decoder):
    """Stalled outputs stay stable and transfer exactly once after release."""
    instructions = (
        0x00100093,  # addi x1, x0, 1
        0x00200113,  # addi x2, x0, 2
        0x00300193,  # addi x3, x0, 3
        0x00400213,  # addi x4, x0, 4
        0x00500293,  # addi x5, x0, 5
        0x00600313,  # addi x6, x0, 6
    )
    references = _decode_references(instructions)
    g.add_cover_point(decoder, {
        "ALL_STALLED": lambda env: env.Get_output_ready_state() == (0,) * 6,
        "ALL_READY": lambda env: env.Get_output_ready_state() == (1,) * 6,
    }, name="DECODE_OUTPUT_READY")

    decoder.SetDefaultValue()
    decoder.Reset()
    stalled_first = decoder.Run_cycle(
        references, output_ready=False, cover_group=g
    )
    stalled_second = decoder.Run_cycle(
        references, output_ready=False, cover_group=g
    )
    released = decoder.Run_cycle(
        references, output_ready=True, cover_group=g
    )
    quiet = decoder.Run_cycle((), output_ready=True, cover_group=g)

    assert stalled_first["input_fire_mask"] == (0,) * 6
    assert stalled_first["output_fire_mask"] == (0,) * 6
    assert stalled_first["output_valid_mask"] == \
        stalled_second["output_valid_mask"]
    assert stalled_first["output_valid_mask"] == (1,) * 6
    assert stalled_second["input_fire_mask"] == (0,) * 6
    assert stalled_second["output_fire_mask"] == (0,) * 6
    assert stalled_first["output_payloads"] == stalled_second["output_payloads"]
    assert released["input_fire_mask"] == (1,) * 6
    assert released["output_fire_mask"] == (1,) * 6
    assert tuple(
        int(result[0]) for result in released["completed"]
    ) == instructions
    assert quiet["fired_uops"] == ()
    assert quiet["completed"] == ()

    g.mark_function(
        "DECODE_OUTPUT_READY",
        test_decode_backpressure_holds_and_releases,
        bin_name=["ALL_STALLED", "ALL_READY"],
    )


@toffee_test.testcase
async def test_decode_drains_complex_tail(decoder):
    """The runner waits for a complex instruction's last uop after input ends."""
    instructions = (
        0x00100093,  # addi x1, x0, 1
        0x0C007057,  # vsetvli zero, zero, e8, m1, ta, ma
        0xC221A257,  # vwaddu.vv v4, v2, v3
    )
    references = _decode_references(instructions)
    g.add_cover_point(decoder, {
        "COMPLEX_LAST_UOP_FIRED": lambda env: env.Get_last_cycle_state().get(
            "complex_last_uop_fired", False
        ),
    }, name="DECODE_COMPLEX_DRAIN")

    success, stats = decode_run(
        decoder,
        references,
        need_log_file=False,
        return_stats=True,
        cover_group=g,
    )

    assert success is True, (
        stats["completed_instructions"],
        stats["uop_trace"],
    )
    assert stats["timed_out"] is False
    assert stats["drained"] is True
    assert stats["accepted"] == len(instructions)
    assert stats["completed"] == len(instructions)
    assert stats["completed_instructions"] == instructions
    assert stats["uops_fired"] == 5
    assert stats["saw_complex_last_uop"] is True
    assert stats["last_completion_cycle"] > stats["last_input_fire_cycle"]
    for instruction in instructions[1:]:
        instruction_uops = tuple(
            uop for uop in stats["uop_trace"]
            if uop["instr"] == instruction
        )
        assert instruction_uops
        assert instruction_uops[0]["first_uop"] == 1
        assert all(
            uop["first_uop"] == 0 for uop in instruction_uops[1:]
        )
        assert instruction_uops[-1]["last_uop"] == 1
        assert all(
            uop["last_uop"] == 0 for uop in instruction_uops[:-1]
        )
        assert all(
            uop["num_uops"] == len(instruction_uops)
            for uop in instruction_uops
        )
        assert all(
            0 <= uop["uop_idx"] < len(instruction_uops)
            for uop in instruction_uops
        )

    g.mark_function(
        "DECODE_COMPLEX_DRAIN",
        test_decode_drains_complex_tail,
        bin_name="COMPLEX_LAST_UOP_FIRED",
    )


@toffee_test.testcase
async def test_decode_known_illegal_instructions(decoder):
    """Known invalid encodings complete once with the illegal exception set."""
    instructions = (0x00000000, 0xFFFFFFFF)
    references = _decode_references(
        instructions, expected_exception=1
    )
    g.add_cover_point(decoder, {
        "KNOWN_ILLEGAL_COMPLETED": lambda env: any(
            bool(result[1])
            for result in env.Get_last_cycle_state().get("completed", ())
        ),
    }, name="DECODE_KNOWN_ILLEGAL")

    success, stats = decode_run(
        decoder,
        references,
        need_log_file=False,
        return_stats=True,
        cover_group=g,
    )

    assert success is True, stats["completed_instructions"]
    assert stats["drained"] is True
    assert stats["completed_instructions"] == instructions
    assert stats["saw_illegal_completion"] is True
    g.mark_function(
        "DECODE_KNOWN_ILLEGAL",
        test_decode_known_illegal_instructions,
        bin_name="KNOWN_ILLEGAL_COMPLETED",
    )


@toffee_test.testcase
async def test_rvc_inst(decoder, rvc_expander):
    """
    Test the RVC instruction set, an example of the tag version in range.

    Args:
        decoder (fixure): the fixture of the decoder
    """
    need_log_file   = True
    # insn_list_temp  = generate_rvc_instructions()
    insn_list_temp  = generate_random_32bits(1)
    ref_lists       = convert_reference_format(rvc_expander, insn_list_temp, True, libdisasm.disasm, libdisasm.disasm_free_mem)
    assert decode_run(decoder, ref_lists, need_log_file,"test_rvc_inst") == True, "RVC decode error"
    g.add_cover_point(decoder, {"fast_check_RVC_ramdom": lambda _: True}, name="RVC").sample()
    g.mark_function("RVC", test_rvc_inst, bin_name="fast_check_RVC_ramdom")


@toffee_test.testcase
async def test_rvi_inst(decoder, rvc_expander):
    """
    Test the RVI instruction set. randomly generate instructions for testing

    Args:
        decoder (fixure): the fixture of the decoder
    """
    need_log_file   = True
    insn_list_temp  = generate_random_32bits(100)
    ref_lists       = convert_reference_format(rvc_expander, insn_list_temp, True, libdisasm.disasm, libdisasm.disasm_free_mem)
    assert decode_run(decoder, ref_lists, need_log_file,"test_rvi_inst") == True, "RVI decode error"
    g.add_cover_point(decoder, {"illegal_inst_triggers_an_exception": lambda _: decoder.Get_decode_checkpoint_illeagl_inst() != 0}, name="RVI_illegal_inst").sample()
    g.add_cover_point(decoder, {"fast_check_random_32bit_int": lambda _: True}, name="RVI").sample()


@toffee_test.testcase
async def test_rv_custom_inst(decoder, rvc_expander):
    """
    Test the custom instruction set. Testing of V extension instructions, which are not actually used

    Args:
        decoder (fixure): the fixture of the decoder
    """
    need_log_file   = True
    custom_v_opcode   = 0b1010111
    insn_list_temp  = generate_OP_V_insn(100)
    ref_lists       = convert_reference_format(rvc_expander, insn_list_temp, True, libdisasm.disasm_custom_insn, libdisasm.disasm_free_mem, custom_v_opcode)
    assert decode_run(decoder, ref_lists, need_log_file,"test_rv_custom_inst") == True, "RVI decode error"
    g.add_cover_point(decoder, {"input_data_contains_complex_insts": lambda _: decoder.Get_decode_checkpoint_complex_inst() != 0}, name="RVI_complex_inst").sample()
    g.add_cover_point(decoder, {"fast_check_OP_V_insn": lambda _: True}, name="RVI_Costom").sample()
