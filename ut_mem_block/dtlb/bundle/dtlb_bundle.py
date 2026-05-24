from toffee import Bundle, Signal, Signals, SignalList, BundleList

#------------------------------------------------------------------------
class SfenceBundle(Bundle):
    valid, \
    bits_rs1, \
    bits_rs2, \
    bits_flushPipe, \
    bits_hv, \
    bits_hg = Signals(6)
    bits_addr = Signal()
    bits_id = Signal()
#------------------------------------------------------------------------
class ATPBundle(Bundle):
    mode = Signal()
    asid = Signal()
    ppn = Signal()
    changed = Signal()

class HGATPBundle(Bundle):
    mode = Signal()
    vmid = Signal()
    ppn = Signal()
    changed = Signal()

class PMMBundle(Bundle):
    mseccfg, menvcfg, henvcfg, hstatus, senvcfg = Signals(5)

class CSRBundle(Bundle):
    priv_mxr, priv_sum, priv_vmxr, priv_vsum, priv_virt, priv_spvp = Signals(6)
    priv_imode, priv_dmode = Signals(2)

    Satp = ATPBundle.from_prefix('satp_')
    Vsatp = ATPBundle.from_prefix('vsatp_')
    HGatp = HGATPBundle.from_prefix('hgatp_')
    PMM = PMMBundle.from_prefix('pmm_')
#------------------------------------------------------------------------
class RequestorReqBundle(Bundle):
    valid = Signal()
    bits_vaddr = Signal()
    bits_fullva = Signal()
    bits_checkfullva = Signal()
    bits_cmd = Signal()
    bits_hyperinst, \
    bits_hlvx, \
    bits_kill, \
    bits_isPrefetch, \
    bits_no_translate = Signals(5)
    bits_pmp_addr = Signal()
    bits_debug_robIdx_flag = Signal()
    bits_debug_robIdx_value = Signal()
    bits_debug_isFirstIssue = Signal()

class RequestorRespBundle(Bundle):
    valid = Signal()
    bits_paddr_0 = Signal()
    bits_paddr_1 = Signal()
    bits_gpaddr_0 = Signal()
    bits_fullva = Signal()
    bits_pbmt_0 = Signal()
    bits_miss = Signal()
    bits_isForVSnonLeafPTE = Signal()
    bits_excp_0_vaNeedExt, \
    bits_excp_0_isHyper, \
    bits_excp_0_gpf_ld, \
    bits_excp_0_gpf_st, \
    bits_excp_0_pf_ld, \
    bits_excp_0_pf_st, \
    bits_excp_0_af_ld, \
    bits_excp_0_af_st = Signals(8)
    bits_ptwBack = Signal()

class RequestorBundle(Bundle):
    req = RequestorReqBundle.from_prefix('req_')
    resp = RequestorRespBundle.from_prefix('resp_')
#------------------------------------------------------------------------
class RedirectBundle(Bundle):
    valid = Signal()
    bits_robIdx_flag = Signal()
    bits_robIdx_value = Signal()
    bits_level = Signal()
#------------------------------------------------------------------------
class PTWReqBundle(Bundle):
    valid = Signal()
    bits_vpn = Signal()
    bits_s2xlate = Signal()
    bits_getGpa = Signal()
class PTWRespBundle(Bundle):
    valid = Signal()
    bits_s2xlate = Signal()
    # S1 entry
    bits_s1_entry_tag = Signal()
    bits_s1_entry_asid = Signal()
    bits_s1_entry_vmid = Signal()
    bits_s1_entry_n = Signal()
    bits_s1_entry_pbmt = Signal()
    bits_s1_entry_perm_d, \
    bits_s1_entry_perm_a, \
    bits_s1_entry_perm_g, \
    bits_s1_entry_perm_u, \
    bits_s1_entry_perm_x, \
    bits_s1_entry_perm_w, \
    bits_s1_entry_perm_r = Signals(7)
    bits_s1_entry_level = Signal()
    bits_s1_entry_v = Signal()
    bits_s1_entry_ppn = Signal()
    bits_s1_addr_low = Signal()
    # 列表信号
    bits_s1_ppn_low = SignalList("bits_s1_ppn_low_#", 8)
    bits_s1_valididx = SignalList("bits_s1_valididx_#", 8)
    bits_s1_pteidx = SignalList("bits_s1_pteidx_#", 8)
    bits_s1_pf, bits_s1_af = Signals(2)
    # S2 entry
    bits_s2_entry_tag = Signal()
    bits_s2_entry_vmid = Signal()
    bits_s2_entry_n = Signal()
    bits_s2_entry_pbmt = Signal()
    bits_s2_entry_ppn = Signal()
    bits_s2_entry_perm_d, \
    bits_s2_entry_perm_a, \
    bits_s2_entry_perm_g, \
    bits_s2_entry_perm_u, \
    bits_s2_entry_perm_x, \
    bits_s2_entry_perm_w, \
    bits_s2_entry_perm_r = Signals(7)
    bits_s2_entry_level = Signal()
    bits_s2_gpf, \
    bits_s2_gaf = Signals(2)

    bits_getGpa = Signal()

class PTWBundle(Bundle):
    req = BundleList(PTWReqBundle, "req_#_", 4)
    resp = PTWRespBundle.from_prefix('resp_')
#------------------------------------------------------------------------
class PMPBundle(Bundle):
    valid = Signal()
    bits_addr = Signal()
    bits_cmd = Signal()
#------------------------------------------------------------------------
class DTLBBundle(Bundle):
    sfence = SfenceBundle.from_prefix('sfence_')
    csr = CSRBundle.from_prefix('csr_')
    hartId = Signal()
    requestor = BundleList(RequestorBundle, "requestor_#_", 4)
    redirect = RedirectBundle.from_prefix('redirect_')
    ptw = PTWBundle.from_prefix('ptw_')
    pmp = BundleList(PMPBundle, "pmp_#_", 4)
    tlbreplay = SignalList("tlbreplay_#", 4)