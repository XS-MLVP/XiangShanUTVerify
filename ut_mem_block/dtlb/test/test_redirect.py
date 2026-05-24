import toffee
import toffee_test
from .ld_tlb_fixture import dtlb_env

LOAD = 0
async def _wait_ptw_req_and_capture(dtlb_env, vaddr, max_cycles=32):
    vpn_expect = (int(vaddr) >> 12) & ((1 << 27) - 1)
    for _ in range(max_cycles):
        for i in range(4):
            req = dtlb_env.bundle.ptw.req[i]
            if int(req.valid.value) == 1 and int(req.bits_vpn.value) == vpn_expect:
                return i, int(req.bits_s2xlate.value), int(req.bits_getGpa.value)
        await dtlb_env.bundle.step()
    raise AssertionError("Timed out waiting for ptw.req on vpn=0x%x" % vpn_expect)


@toffee_test.testcase
async def test_redirect_masks_miss_via_lastCycleRedirect(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()
    
    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 1
    csr.Vsatp.mode.value = 8
    csr.HGatp.mode.value = 8
    await dtlb_env.bundle.step()

    port = 0
    rob  = 0x5C
    gva  = 0x0000_0000_8020_5000
    gpa  = 0x0000_0001_2345_0000
    hpa  = 0x0000_0003_ABCD_0000

    r0 = await dtlb_env.agent.drive_request(port=port, vaddr=gva, cmd=LOAD)
    assert r0 is None
    _, s2x, getGpa_flag = await _wait_ptw_req_and_capture(dtlb_env, gva)

    await dtlb_env.agent.set_ptw_resp(
        vaddr=gva, paddr=gpa, level=0,
        s1_perm_r=True, s1_perm_a=True, s1_perm_u=True,
        s2xlate=s2x, getGpa=getGpa_flag,
        s2_ppn=(hpa >> 12), s2_level=0,
        s2_perm_r=False, s2_perm_a=True
    )

    req = dtlb_env.bundle.requestor[port].req
    req.bits_vaddr.value = gva & ((1<<50)-1)
    req.bits_fullva.value = gva
    req.bits_cmd.value = 0      # LOAD
    req.bits_isPrefetch.value = 0
    req.bits_no_translate.value = 0
    req.bits_debug_robIdx_flag.value  = 1
    req.bits_debug_robIdx_value.value = rob
    req.valid.value = 1

    redir = dtlb_env.bundle.redirect
    redir.valid.value = 1
    redir.bits_robIdx_flag.value = 1
    redir.bits_robIdx_value.value = rob
    redir.bits_level.value = 1

    await dtlb_env.bundle.step()

 
    req.valid.value = 0
    redir.valid.value = 0

    for _ in range(32):
        for i in range(4):
            assert dtlb_env.bundle.ptw.req[i].valid.value == 0
        await dtlb_env.bundle.step()


@toffee_test.testcase
async def test_redirect_level0_kill_younger(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()
    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 1
    csr.Vsatp.mode.value = 8
    csr.HGatp.mode.value = 8
    await dtlb_env.bundle.step()

    port = 0
    rob  = 0x50         
    pivot= 0x4A          
    gva  = 0x0000_0000_8020_5000
    gpa  = 0x0000_0001_2345_0000
    hpa  = 0x0000_0003_ABCD_0000

    r0 = await dtlb_env.agent.drive_request(port=port, vaddr=gva, cmd=LOAD)
    assert r0 is None
    _, s2x, _ = await _wait_ptw_req_and_capture(dtlb_env, gva)
    await dtlb_env.agent.set_ptw_resp(
        vaddr=gva, paddr=gpa, level=0,
        s1_perm_r=True, s1_perm_a=True, s1_perm_u=True,
        s2xlate=s2x, getGpa=False,
        s2_ppn=(hpa >> 12), s2_level=0,
        s2_perm_r=False, s2_perm_a=True 
    )

    req = dtlb_env.bundle.requestor[port].req
    req.bits_vaddr.value = gva & ((1<<50)-1)
    req.bits_fullva.value = gva
    req.bits_cmd.value = LOAD
    req.bits_isPrefetch.value = 0
    req.bits_no_translate.value = 0
    req.bits_debug_robIdx_flag.value  = 1
    req.bits_debug_robIdx_value.value = rob
    req.valid.value = 1

    redir = dtlb_env.bundle.redirect
    redir.valid.value = 1
    redir.bits_robIdx_flag.value = 1
    redir.bits_robIdx_value.value = pivot 
    redir.bits_level.value = 0           

    await dtlb_env.bundle.step() 

    req.valid.value = 0
    redir.valid.value = 0

    for _ in range(32):
        for i in range(4):
            assert dtlb_env.bundle.ptw.req[i].valid.value == 0
        await dtlb_env.bundle.step()