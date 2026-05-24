from dut.TLBNonBlock import DUTTLBNonBlock
import toffee.funcov as fc
from toffee.funcov import CovGroup

def init_dtlb_funcov(dut, g: fc.CovGroup):
    # ---------------- 功能点1：接收请求（valid/resp/miss-hit） ----------------
    for i in range(4):
        g.add_watch_point(dut, {
            f"F1.{i}.req_valid":    lambda d, i=i: getattr(d, f"io_requestor_{i}_req_valid").value == 1,
            f"F1.{i}.resp_valid":   lambda d, i=i: getattr(d, f"io_requestor_{i}_resp_valid").value == 1,
            f"F1.{i}.hit":          lambda d, i=i: getattr(d, f"io_requestor_{i}_resp_valid").value == 1
                                               and getattr(d, f"io_requestor_{i}_resp_bits_miss").value == 0,
            f"F1.{i}.miss":         lambda d, i=i: getattr(d, f"io_requestor_{i}_resp_valid").value == 1
                                               and getattr(d, f"io_requestor_{i}_resp_bits_miss").value == 1,
        }, name=f"F1_REQ_RESP_P{i}")

    # ---------------- 功能点2：miss 处理 & PTW 交互 -------------------------
    # 各端口 PTW 请求 valid（valid-ready 这层多数后端抽象不到，这里只看 valid）
    for i in range(4):
        g.add_watch_point(dut, {
            f"F2.{i}.ptw_req_valid": lambda d, i=i: getattr(d, f"io_ptw_req_{i}_valid").value == 1,
        }, name=f"F2_PTW_REQ_P{i}")

    # s2xlate 模式覆盖：0(bare?) / 1(onlyS1) / 2(onlyS2)（以你的 RTL 约定为准）
    g.add_watch_point(dut, {
        "F2.s2xlate==0": lambda d: any(getattr(d, f"io_ptw_req_{i}_valid").value == 1
                                       and getattr(d, f"io_ptw_req_{i}_bits_s2xlate").value == 0 for i in range(4)),
        "F2.s2xlate==1": lambda d: any(getattr(d, f"io_ptw_req_{i}_valid").value == 1
                                       and getattr(d, f"io_ptw_req_{i}_bits_s2xlate").value == 1 for i in range(4)),
        "F2.s2xlate==2": lambda d: any(getattr(d, f"io_ptw_req_{i}_valid").value == 1
                                       and getattr(d, f"io_ptw_req_{i}_bits_s2xlate").value == 2 for i in range(4)),
        "F2.s2xlate==3": lambda d: any(getattr(d, f"io_ptw_req_{i}_valid").value == 1
                                       and getattr(d, f"io_ptw_req_{i}_bits_s2xlate").value == 3 for i in range(4)),
    }, name="F2_S2XLATE_MODES")

    

    # ---------------- 功能点3：hit 返回（paddr/gpaddr/页内偏移一致） ----------
    for i in range(4):
        g.add_watch_point(dut, {
            f"F3.{i}.paddr_seen": lambda d, i=i: getattr(d, f"io_requestor_{i}_resp_valid").value == 1 \
                                           and getattr(d, f"io_requestor_{i}_resp_bits_miss").value == 0 \
                                           and getattr(d, f"io_requestor_{i}_resp_bits_paddr_0").value != 0,
        }, name=f"F3_RET_P{i}")
    for i in range(3):
        g.add_watch_point(dut, {
            f"F3.{i}.gpaddr_seen": lambda d, i=i: getattr(d, f"io_requestor_{i}_resp_valid").value == 1 \
                                            and getattr(d, f"io_requestor_{i}_resp_bits_gpaddr_0").value != 0,
        }, name=f"F3_RET_gpaddr_P{i}")

    # ---------------- 功能点4：getGpa 功能测试 ----------
    g.add_watch_point(dut, {
        "F4.getGpa==1_seen": lambda d: any(getattr(d, f"io_ptw_req_{i}_bits_getGpa").value == 1 for i in range(4)),
    }, name="F4_GETGPA")
    
    # ---------------- 功能点5：H扩展功能测试 ----------
    g.add_watch_point(dut, {
        "F5.Bare": lambda d: any(getattr(d, f"io_ptw_req_{i}_bits_s2xlate").value == 0 for i in range(4)),
        "F5.onlyStage1": lambda d: any(getattr(d, f"io_ptw_req_{i}_bits_s2xlate").value == 1 for i in range(4)),
        "F5.onlyStage2": lambda d: any(getattr(d, f"io_ptw_req_{i}_bits_s2xlate").value == 2 for i in range(4)),
        "F5.allStage": lambda d: any(getattr(d, f"io_ptw_req_{i}_bits_s2xlate").value == 3 for i in range(4)),
    }, name="F5_S2XLATE_MODES")

    # ---------------- 功能点6：TLB 压缩（valididx 统计） --------------------
    # io_ptw_resp_bits_s1_valididx_0..7 为 8 位 one-hot/稀疏集合
    def _sum_valididx(d):
        return sum(getattr(d, f"io_ptw_resp_bits_s1_valididx_{k}").value for k in range(8))
    g.add_watch_point(dut, {
        "F6.valididx_onehot": lambda d: getattr(d, "io_ptw_resp_valid").value == 1 and _sum_valididx(d) == 1,
        "F6.valididx_full8":  lambda d: getattr(d, "io_ptw_resp_valid").value == 1 and _sum_valididx(d) == 8,
        "F6.valididx_mid":    lambda d: getattr(d, "io_ptw_resp_valid").value == 1 and 1 < _sum_valididx(d) < 8,
    }, name="F6_COMPRESSION_IDX")

    # ---------------- 功能点7：刷新（sfence & 管道） -----------------------
    g.add_watch_point(dut, {
        "F7.sfence_all(0,0)":   lambda d: getattr(d, "io_sfence_valid").value == 1
                                       and getattr(d, "io_sfence_bits_rs1").value == 0
                                       and getattr(d, "io_sfence_bits_rs2").value == 0,
        "F7.sfence_by_va(1,0)": lambda d: getattr(d, "io_sfence_valid").value == 1
                                       and getattr(d, "io_sfence_bits_rs1").value == 1
                                       and getattr(d, "io_sfence_bits_rs2").value == 0,
        "F7.sfence_by_id(0,1)": lambda d: getattr(d, "io_sfence_valid").value == 1
                                       and getattr(d, "io_sfence_bits_rs1").value == 0
                                       and getattr(d, "io_sfence_bits_rs2").value == 1,
        "F7.sfence_va_id(1,1)": lambda d: getattr(d, "io_sfence_valid").value == 1
                                       and getattr(d, "io_sfence_bits_rs1").value == 1
                                       and getattr(d, "io_sfence_bits_rs2").value == 1,
        "F7.hv==1":             lambda d: getattr(d, "io_sfence_valid").value == 1
                                       and getattr(d, "io_sfence_bits_hv").value == 1,
        "F7.hg==1":             lambda d: getattr(d, "io_sfence_valid").value == 1
                                       and getattr(d, "io_sfence_bits_hg").value == 1,
    }, name="F7_SFENCE")

    # ---------------- 功能点8：Reset --------------------------------------
    g.add_watch_point(dut, {
        "F8.reset_high": lambda d: getattr(d, "reset").value == 1,
        "F8.reset_low":  lambda d: getattr(d, "reset").value == 0,
    }, name="F8_RESET")

    # ---------------- 功能点9：权限检查（CSR + resp 异常位） ----------------
    g.add_watch_point(dut, {
        "F9.mxr==1":  lambda d: getattr(d, "io_csr_priv_mxr").value  == 1,
        "F9.sum==1":  lambda d: getattr(d, "io_csr_priv_sum").value  == 1,
        "F9.vmxr==1": lambda d: getattr(d, "io_csr_priv_vmxr").value == 1,
        "F9.vsum==1": lambda d: getattr(d, "io_csr_priv_vsum").value == 1,
    }, name="F9_PRIV_SWITCHES")
    for i in range(4):
        g.add_watch_point(dut, {
            f"F9.{i}.pf.ld": lambda d, i=i: getattr(d, f"io_requestor_{i}_resp_bits_excp_0_pf_ld").value == 1,
            f"F9.{i}.af.ld": lambda d, i=i: getattr(d, f"io_requestor_{i}_resp_bits_excp_0_af_ld").value == 1,
        }, name=f"F9_EXCP_ld_P{i}")
    g.add_watch_point(dut, {
                f"F9.0.pf.st": lambda d: getattr(d, f"io_requestor_0_resp_bits_excp_0_pf_st").value == 1,
                f"F9.0.af.st": lambda d: getattr(d, f"io_requestor_0_resp_bits_excp_0_af_st").value == 1,
            }, name=f"F9_EXCP_st_P0")
    # ---------------- 功能点10：异常（GPF/GAF） ----------------------------
    g.add_watch_point(dut, {
        "F10.s1_pf":         lambda d: getattr(d, "io_ptw_resp_valid").value == 1
                                    and getattr(d, "io_ptw_resp_bits_s1_pf").value == 1,
        "F10.s1_af":         lambda d: getattr(d, "io_ptw_resp_valid").value == 1
                                    and getattr(d, "io_ptw_resp_bits_s1_af").value == 1,
        "F10.s2_gpf":        lambda d: getattr(d, "io_ptw_resp_valid").value == 1
                                    and getattr(d, "io_ptw_resp_bits_s2_gpf").value == 1, 
    }, name="F10_PTW_RESP_FAULTS")
    for i in range(4):
        g.add_watch_point(dut, {
            f"F10.{i}.gpf.ld": lambda d, i=i: getattr(d, f"io_requestor_{i}_resp_bits_excp_0_gpf_ld").value == 1,
        }, name=f"F10_GPF_ld_P{i}")
    g.add_watch_point(dut, {
            f"F10.0.gpf.st": lambda d: getattr(d, f"io_requestor_0_resp_bits_excp_0_gpf_st").value == 1,
        }, name=f"F10_GPF_st_P0")
    
    # ---------------- 功能点11：隔离（ASID/VMID/changed） -------------------
    g.add_watch_point(dut, {
        "F11.asid!=0":        lambda d: getattr(d, "io_csr_satp_asid").value != 0,
        "F11.vmid!=0":        lambda d: getattr(d, "io_csr_hgatp_vmid").value != 0,
        "F11.satp.changed":   lambda d: getattr(d, "io_csr_satp_changed").value  == 1,
        "F11.vsatp.changed":  lambda d: getattr(d, "io_csr_vsatp_changed").value == 1,
        "F11.hgatp.changed":  lambda d: getattr(d, "io_csr_hgatp_changed").value == 1,
    }, name="F11_ISOLATION")

    # ---------------- 功能点12：并行访问（同拍多端口） ---------------------
    g.add_watch_point(dut, {
        "F12.simul_req>=2": lambda d: sum(getattr(d, f"io_requestor_{i}_req_valid").value for i in range(4)) >= 2,
        "F12.simul_miss>=2": lambda d: sum(
            getattr(d, f"io_requestor_{i}_resp_valid").value == 1
            and getattr(d, f"io_requestor_{i}_resp_bits_miss").value == 1
            for i in range(4)
        ) >= 2,
        "F12.simul_hit>=2": lambda d: sum(
            getattr(d, f"io_requestor_{i}_resp_valid").value == 1
            and getattr(d, f"io_requestor_{i}_resp_bits_miss").value == 0
            for i in range(4)
        ) >= 2,
    }, name="F12_PARALLEL")

    # ---------------- 功能点13：大小页（level 分布） ------------------------
    g.add_watch_point(dut, {
        "F13.s1_level==0": lambda d: getattr(d, "io_ptw_resp_valid").value == 1
                                  and getattr(d, "io_ptw_resp_bits_s1_entry_level").value == 0,
        "F13.s1_level==1": lambda d: getattr(d, "io_ptw_resp_valid").value == 1
                                  and getattr(d, "io_ptw_resp_bits_s1_entry_level").value == 1,
        "F13.s1_level==2": lambda d: getattr(d, "io_ptw_resp_valid").value == 1
                                  and getattr(d, "io_ptw_resp_bits_s1_entry_level").value == 2,
        "F13.s2_level==0": lambda d: getattr(d, "io_ptw_resp_valid").value == 1
                                  and getattr(d, "io_ptw_resp_bits_s2_entry_level").value == 0,
        "F13.s2_level==1": lambda d: getattr(d, "io_ptw_resp_valid").value == 1
                                  and getattr(d, "io_ptw_resp_bits_s2_entry_level").value == 1,
        "F13.s2_level==2": lambda d: getattr(d, "io_ptw_resp_valid").value == 1
                                  and getattr(d, "io_ptw_resp_bits_s2_entry_level").value == 2,              
    }, name="F13_LEVELS")

    # ---------------- 功能点14: redirect ------------------------
    g.add_watch_point(dut, {
        "F14.redirect_seen": lambda d: getattr(d, "io_redirect_valid").value == 1,
        "F14.redirect_bits_level==0": lambda d: getattr(d, "io_redirect_valid").value == 1
                                            and getattr(d, "io_redirect_bits_level").value == 0,
        "F14.redirect_bits_level==1": lambda d: getattr(d, "io_redirect_valid").value == 1
                                            and getattr(d, "io_redirect_bits_level").value == 1,
                      
    }, name="F14_REDIRECT")
    
    return g