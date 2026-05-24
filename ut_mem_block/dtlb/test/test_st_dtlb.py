import toffee
import toffee_test
import random
from .ld_tlb_fixture import dtlb_env

LOAD = 0
STORE = 1

async def _wait_ptw_req_and_capture(dtlb_env, vaddr, max_cycles=32):
    vpn_expect = (int(vaddr) >> 12) & ((1 << 27) - 1)
    for _ in range(max_cycles):
        for i in range(4):
            req = dtlb_env.bundle.ptw.req[i]
            if int(req.valid.value) == 1 and int(req.bits_vpn.value) == vpn_expect:
                return i, int(req.bits_s2xlate.value), int(req.bits_getGpa.value)
        await dtlb_env.bundle.step()
    raise AssertionError("Timed out waiting for ptw.req on vpn=0x%x" % vpn_expect)
def _canon_sv39_vaddr(va: int) -> int:
    va = int(va) & ((1 << 64) - 1)
    low39 = va & ((1 << 39) - 1)
    sign  = (low39 >> 38) & 1
    upper = ((-sign) & ((1 << (64 - 39)) - 1)) << 39
    return (upper | low39) & ((1 << 64) - 1)

@toffee_test.testcase
async def test_ptwresp_s1_pf_propagates_to_requestor(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 0
    csr.Satp.mode.value = 8
    await dtlb_env.bundle.step()

    port = 0
    va = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))
    pa = random.randint(2 ** 12, 2 ** 36 - 1)
    r0 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
    assert r0 is None

    _, s2x, _ = await _wait_ptw_req_and_capture(dtlb_env, va)
    await dtlb_env.agent.set_ptw_resp(vaddr=va, paddr=pa, level=0,
                               s1_perm_u=True, s1_perm_w=True, s1_perm_a=True,
                               s1_perm_d=True, s1_perm_r=False,
                               s1_pf=True,           
                               s2xlate=s2x)

    r1 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
    assert r1 == -1

    resp = dtlb_env.bundle.requestor[port].resp
    assert int(resp.bits_excp_0_pf_st.value) == 1
    
@toffee_test.testcase
async def test_ptwresp_s1_af_propagates_to_requestor(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 0
    csr.Satp.mode.value = 8
    await dtlb_env.bundle.step()

    port = 0
    va = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))
    pa = random.randint(2 ** 12, 2 ** 36 - 1)
    r0 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
    assert r0 is None

    _, s2x, _ = await _wait_ptw_req_and_capture(dtlb_env, va)
    await dtlb_env.agent.set_ptw_resp(vaddr=va, paddr=pa, level=0,
                               s1_perm_u=True, s1_perm_w=True, s1_perm_a=True,
                               s1_perm_d=True, s1_perm_r=False,
                               s1_af=True,           
                               s2xlate=s2x)

    r1 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
    assert r1 == -1

    resp = dtlb_env.bundle.requestor[port].resp
    assert int(resp.bits_excp_0_af_st.value) == 1

@toffee_test.testcase
async def test_ptwresp_s2_gpf_propagates_to_requestor(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 1
    csr.Vsatp.mode.value = 0
    csr.HGatp.mode.value = 8
    await dtlb_env.bundle.step()

    port = 0
    gpa = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))

    r0 = await dtlb_env.agent.drive_request(port=port, vaddr=gpa, cmd=STORE)
    assert r0 is None

    _, s2x, _ = await _wait_ptw_req_and_capture(dtlb_env, gpa)
    await dtlb_env.agent.set_ptw_resp(vaddr=gpa, paddr=0, level=0,
                               s1_v=False,         
                               s2_tag=(gpa >> 12) & ((1<<27)-1),
                               s2_perm_u=True, s2_perm_w=True, s2_perm_a=True,
                               s2_perm_d=True, s2_perm_r=False,
                               s2_gpf=True,        
                               s2xlate=s2x)

    r1 = await dtlb_env.agent.drive_request(port=port, vaddr=gpa, cmd=STORE)
    assert r1 == -1

    resp = dtlb_env.bundle.requestor[port].resp
    assert int(resp.bits_excp_0_gpf_st.value) == 1

@toffee_test.testcase
async def test_priv_sum_supervisor_can_read_user_page(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()
    
    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 0
    csr.Satp.mode.value = 8           
    csr.Satp.asid.value = 0x2
    csr.priv_dmode.value = 1
    await dtlb_env.bundle.step()
    
    port = 0
    va = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))
    pa = random.randint(2 ** 12, 2 ** 36 - 1)

    r0 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
    assert r0 is None
    _, s2x, _ = await _wait_ptw_req_and_capture(dtlb_env, va)
    await dtlb_env.agent.set_ptw_resp(
        vaddr=va, paddr=pa, level=0,
        s1_asid=0x2,
        s1_perm_u=True, s1_perm_w=True, s1_perm_a=True,
        s1_perm_d=True, s1_perm_r=False,
        s2xlate=s2x
    )

    r1 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
    assert r1 == -1

    csr.priv_sum.value = 1
    await dtlb_env.bundle.step()

    r2 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
    expect = (pa & ~0xFFF) | (va & 0xFFF)
    assert r2 == expect

@toffee_test.testcase
async def test_priv_vsum_vs_supervisor_can_read_user_page(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()
    
    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 1
    csr.Vsatp.mode.value = 8           
    csr.HGatp.mode.value = 0           
    csr.Vsatp.asid.value = 0x34
    csr.HGatp.vmid.value = 0xB        
    csr.priv_dmode.value = 1
    await dtlb_env.bundle.step()
    
    port = 0
    va = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))
    gpa = random.randint(2 ** 12, 2 ** 41 - 1)

    r0 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
    assert r0 is None
    _, s2x, _ = await _wait_ptw_req_and_capture(dtlb_env, va)
    await dtlb_env.agent.set_ptw_resp(
        vaddr=va, paddr=gpa, level=0,
        s1_asid=0x34, s1_vmid=0xB,
        s1_perm_u=True, s1_perm_w=True, s1_perm_a=True,
        s1_perm_d=True, s1_perm_r=False,
        s2xlate=s2x
    )

    r1 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
    assert r1 == -1

    csr.priv_vsum.value = 1
    await dtlb_env.bundle.step()
    
    r2 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
    expect = (gpa & ~0xFFF) | (va & 0xFFF)
    assert r2 == expect

@toffee_test.testcase
async def test_asid_isolation_bare(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 0
    csr.Satp.mode.value = 8           
    csr.Satp.asid.value = 0x10
    await dtlb_env.bundle.step()
    
    port = 0
    va = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))
    pa = random.randint(2 ** 12, 2 ** 36 - 1)

    r0 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
    assert r0 is None
    _, s2x, _ = await _wait_ptw_req_and_capture(dtlb_env, va)   
    await dtlb_env.agent.set_ptw_resp(
        vaddr=va, paddr=pa, level=0,
        s1_asid=0x10, s1_perm_u=True, s1_perm_w=True, s1_perm_a=True,
        s1_perm_d=True, s1_perm_r=False,
        s2xlate=s2x
    )
    r1 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
    expect = (pa & ~0xFFF) | (va & 0xFFF)
    assert r1 == expect

    csr.Satp.asid.value = 0x21
    await dtlb_env.bundle.step()

    r2 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
    assert r2 is None

@toffee_test.testcase
async def test_asid_isolation_onlyStage1(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 1
    csr.Vsatp.mode.value = 8           
    csr.HGatp.mode.value = 0           
    csr.Vsatp.asid.value = 0x33
    csr.HGatp.vmid.value = 0xA        
    await dtlb_env.bundle.step()

    port = 0
    va = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))
    gpa = random.randint(2 ** 12, 2 ** 41 - 1)

    r0 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
    assert r0 is None
    _, s2x, _ = await _wait_ptw_req_and_capture(dtlb_env, va)   
    await dtlb_env.agent.set_ptw_resp(
        vaddr=va, paddr=gpa, level=0,
        s1_asid=0x33, s1_vmid=0xA, s1_perm_u=True, s1_perm_w=True, s1_perm_a=True,
        s1_perm_d=True, s1_perm_r=False,
        s2xlate=s2x
    )
    r1 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
    expect = (gpa & ~0xFFF) | (va & 0xFFF)
    assert r1 == expect

    csr.Vsatp.asid.value = 0x44
    csr.Vsatp.changed.value = True
    await dtlb_env.bundle.step()
    csr.Vsatp.changed.value = False
    r2 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
    assert r2 is None

    csr.Vsatp.asid.value = 0x33
    csr.HGatp.vmid.value = 0xB
    csr.Vsatp.changed.value = True
    csr.HGatp.changed.value = True
    await dtlb_env.bundle.step()
    csr.Vsatp.changed.value = False
    csr.HGatp.changed.value = False
    
    r3 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
    assert r3 is None

@toffee_test.testcase
async def test_vmid_isolation_onlyStage2(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 1
    csr.Vsatp.mode.value = 0           
    csr.HGatp.mode.value = 8           
    csr.HGatp.vmid.value = 0x55        
    await dtlb_env.bundle.step()

    port   = 0
    gpa_in = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))
    hpa = random.randint(2 ** 12, 2 ** 36 - 1)

    r0 = await dtlb_env.agent.drive_request(port=port, vaddr=gpa_in, cmd=STORE)
    assert r0 is None
    _, s2x, getGpa_req = await _wait_ptw_req_and_capture(dtlb_env, gpa_in)   
    await dtlb_env.agent.set_ptw_resp(
        vaddr=gpa_in, paddr=0, level=0,            
        s1_v=False,
        s2xlate=s2x, getGpa=getGpa_req,
        s2_tag=(gpa_in >> 12) & ((1<<27)-1),
        s2_ppn=(hpa >> 12), s2_level=0,         
        s1_vmid=0x55, s2_perm_u=True, s2_perm_w=True, s2_perm_a=True,
        s2_perm_d=True, s2_perm_r=False,
    )
    r1 = await dtlb_env.agent.drive_request(port=port, vaddr=gpa_in, cmd=STORE)
    expect = (hpa & ~0xFFF) | (gpa_in & 0xFFF)
    assert r1 == expect

    csr.HGatp.vmid.value = 0x66
    csr.HGatp.changed.value = True
    await dtlb_env.bundle.step()
    csr.HGatp.changed.value = False

    r2 = await dtlb_env.agent.drive_request(port=port, vaddr=gpa_in, cmd=STORE)
    assert r2 is None

@toffee_test.testcase
async def test_hit_onlyStage1(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 1
    csr.Vsatp.mode.value = 8
    csr.HGatp.mode.value = 0
    await dtlb_env.bundle.step()

    port = 0
    va = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))
    gpa = random.randint(2 ** 12, 2 ** 41 - 1)
    
    r0 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
    assert r0 is None

    ptw_port, s2x, getGpa_req = await _wait_ptw_req_and_capture(dtlb_env, va)
    await dtlb_env.agent.set_ptw_resp(
        vaddr=va, paddr=gpa, level=0,           
        s1_perm_u=True, s1_perm_w=True, s1_perm_a=True,
        s1_perm_d=True, s1_perm_r=False,
        s2xlate=s2x, getGpa=getGpa_req                
    )

    r1 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
    expect = (gpa & ~0xFFF) | (va & 0xFFF)
    assert r1 == expect
    

@toffee_test.testcase
async def test_hit_onlyStage2_4k(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 1
    csr.Vsatp.mode.value = 0
    csr.HGatp.mode.value = 8
    await dtlb_env.bundle.step()

    port = 0
    gpa = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))
    hpa = random.randint(2 ** 12, 2 ** 36 - 1)

    r0 = await dtlb_env.agent.drive_request(port=port, vaddr=gpa, cmd=STORE)
    assert r0 is None

    _, s2x, getGpa_req = await _wait_ptw_req_and_capture(dtlb_env, gpa)
    await dtlb_env.agent.set_ptw_resp(
        vaddr=gpa, paddr=0, level=0,   
        s1_v=False,
        s2xlate=s2x, getGpa=False,
        s2_tag=(gpa >> 12) & ((1<<27)-1),
        s2_ppn=(hpa >> 12), s2_level=0,         
        s2_perm_u=True, s2_perm_w=True, s2_perm_a=True,
        s2_perm_d=True, s2_perm_r=False,
    )

    r1 = await dtlb_env.agent.drive_request(port=port, vaddr=gpa, cmd=STORE)
    expect = (hpa & ~0xFFF) | (gpa & 0xFFF)
    assert r1 == expect

@toffee_test.testcase
async def test_hit_onlyStage2_2m(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 1
    csr.Vsatp.mode.value = 0
    csr.HGatp.mode.value = 8
    await dtlb_env.bundle.step()

    port = 0
    gpa = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1)) & ~((1<<21)-1)
    hpa = random.randint(2 ** 12, 2 ** 36 - 1) & ~((1<<21)-1)


    r0 = await dtlb_env.agent.drive_request(port=port, vaddr=gpa, cmd=STORE)
    assert r0 is None

    _, s2x, getGpa_req = await _wait_ptw_req_and_capture(dtlb_env, gpa)
    await dtlb_env.agent.set_ptw_resp(
        vaddr=gpa, paddr=0, level=0,   
        s1_v=False,
        s2xlate=s2x, getGpa=False,
        s2_tag=(gpa >> 12) & ((1<<27)-1),
        s2_ppn=(hpa >> 12), s2_level=1,         
        s2_perm_u=True, s2_perm_w=True, s2_perm_a=True,
        s2_perm_d=True, s2_perm_r=False,
    )
    for off in (0x000, 0x1000, 0x1FF000):
        va = gpa + off
        r1 = await dtlb_env.agent.drive_request(port=0, vaddr=va, cmd=STORE)
        mask = (1 << 21) - 1
        expect = (hpa & ~mask) | (va & mask)
        assert r1 == expect

@toffee_test.testcase
async def test_hit_onlyStage2_1g(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 1
    csr.Vsatp.mode.value = 0
    csr.HGatp.mode.value = 8
    await dtlb_env.bundle.step()

    port = 0
    gpa = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1)) & ~((1<<30)-1)
    hpa = random.randint(2 ** 12, 2 ** 36 - 1) & ~((1<<30)-1)


    r0 = await dtlb_env.agent.drive_request(port=port, vaddr=gpa, cmd=STORE)
    assert r0 is None

    _, s2x, getGpa_req = await _wait_ptw_req_and_capture(dtlb_env, gpa)
    await dtlb_env.agent.set_ptw_resp(
        vaddr=gpa, paddr=0, level=0,   
        s1_v=False,
        s2xlate=s2x, getGpa=False,
        s2_tag=(gpa >> 12) & ((1<<27)-1),
        s2_ppn=(hpa >> 12), s2_level=2,         
        s2_perm_u=True, s2_perm_w=True, s2_perm_a=True,
        s2_perm_d=True, s2_perm_r=False,
    )
    for off in (0x0, 0x21_000, 0x3FF_F000):
        va = gpa + off
        r1 = await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=STORE)
        mask = (1 << 30) - 1
        expect = (hpa & ~mask) | (va & mask)
        assert r1 == expect

@toffee_test.testcase
async def test_hit_allStage(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 1
    csr.Vsatp.mode.value = 8
    csr.HGatp.mode.value = 8
    await dtlb_env.bundle.step()

    port = 0
    gva = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))
    gpa = random.randint(2 ** 12, 2 ** 41 -1)
    hpa = random.randint(2 ** 12, 2 ** 36 - 1)

    r0 = await dtlb_env.agent.drive_request(port=port, vaddr=gva, cmd=STORE)
    assert r0 is None

    _, s2x, getGpa_ptw = await _wait_ptw_req_and_capture(dtlb_env, gva)
    await dtlb_env.agent.set_ptw_resp(
        vaddr=gva, paddr=gpa, level=0,          
        s1_perm_u=True, s1_perm_w=True, s1_perm_a=True,
        s1_perm_d=True, s1_perm_r=False,
        s2xlate=s2x, getGpa=getGpa_ptw,
        s2_tag=(gpa>>12) & ((1<<27)-1),
        s2_ppn=(hpa >> 12), s2_level=0,         
        s2_perm_u=True, s2_perm_w=True, s2_perm_a=True,
        s2_perm_d=True, s2_perm_r=False,
    )

    r1 = await dtlb_env.agent.drive_request(port=port, vaddr=gva, cmd=STORE)
    expect = (hpa & ~0xFFF) | (gva & 0xFFF)
    assert r1 == expect

@toffee_test.testcase
async def test_hit_allStage_with_getGpa(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 1
    csr.Vsatp.mode.value = 8   
    csr.HGatp.mode.value = 8
    await dtlb_env.bundle.step()

    gva = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))
    gpa = random.randint(2 ** 12, 2 ** 41 -1)
    hpa = random.randint(2 ** 12, 2 ** 36 - 1)

    _ = await dtlb_env.agent.drive_request(port=0, vaddr=gva, cmd=STORE)
    _, s2x, getGpa_ptw = await _wait_ptw_req_and_capture(dtlb_env, gva)

    await dtlb_env.agent.set_ptw_resp(
        vaddr=gva, paddr=gpa, level=0,          
        s1_perm_u=True, s1_perm_w=True, s1_perm_a=True,
        s1_perm_d=True, s1_perm_r=False,
        s2xlate=s2x, getGpa=getGpa_ptw,
        s2_ppn=(hpa >> 12), s2_level=0,         
        s2_perm_u=True, s2_perm_w=False, s2_perm_a=True,
        s2_perm_d=True, s2_perm_r=False,
    )

    r0 = await dtlb_env.agent.drive_request(port=0, vaddr=gva, cmd=STORE)

    _, s2x_req, getGpa_req = await _wait_ptw_req_and_capture(dtlb_env, gva)
    assert getGpa_req == 1   


@toffee_test.testcase
async def test_parallel_simul_req_miss(dtlb_env):
    requestor = dtlb_env.bundle.requestor

    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    VA0 = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))
    VA1 = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))
    VA2 = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))

    requestor[0].req.valid.value = 1
    requestor[0].req.bits_vaddr.value = VA0
    requestor[0].req.bits_fullva.value = VA0
    requestor[0].req.bits_cmd.value = STORE
    requestor[0].req.bits_no_translate.value = 0
    requestor[1].req.valid.value = 1
    requestor[1].req.bits_vaddr.value = VA1
    requestor[1].req.bits_fullva.value = VA1
    requestor[1].req.bits_cmd.value = STORE
    requestor[1].req.bits_no_translate.value = 0
    requestor[2].req.valid.value = 1
    requestor[2].req.bits_vaddr.value = VA2
    requestor[2].req.bits_fullva.value = VA2
    requestor[2].req.bits_cmd.value = STORE
    requestor[2].req.bits_no_translate.value = 0

    await dtlb_env.bundle.step()

    requestor[0].req.valid.value = 0
    requestor[1].req.valid.value = 0
    requestor[2].req.valid.value = 0
    await dtlb_env.bundle.step()


@toffee_test.testcase
async def test_parallel_simul_req_hit(dtlb_env):
    requestor = dtlb_env.bundle.requestor

    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    VA0 = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))
    VA1 = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))
    VA2 = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))
    PA0 = random.randint(2 ** 12, 2** 36 - 1)
    PA1 = random.randint(2 ** 12, 2** 36 - 1)
    PA2 = random.randint(2 ** 12, 2** 36 - 1)

    
    assert await dtlb_env.agent.drive_request(port=0, vaddr=VA0, cmd=STORE) == None
    await dtlb_env.agent.set_ptw_resp(vaddr=VA0,paddr=PA0,level=0,s1_perm_u=True, s1_perm_w=True, s1_perm_a=True,
        s1_perm_d=True, s1_perm_r=False)
    assert await dtlb_env.agent.drive_request(port=0, vaddr=VA0, cmd=STORE) == ((VA0 & (0xFFF)) | (PA0 & ~(0xFFF)))
        
    assert await dtlb_env.agent.drive_request(port=0, vaddr=VA1, cmd=LOAD) == None
    await dtlb_env.agent.set_ptw_resp(vaddr=VA1,paddr=PA1,level=0,s1_perm_u=True, s1_perm_r=True, s1_perm_a=True)
    assert await dtlb_env.agent.drive_request(port=0, vaddr=VA1, cmd=LOAD) == ((VA1 & (0xFFF)) | (PA1 & ~(0xFFF)))
    
    assert await dtlb_env.agent.drive_request(port=0, vaddr=VA2, cmd=LOAD) == None
    await dtlb_env.agent.set_ptw_resp(vaddr=VA2,paddr=PA2,level=0,s1_perm_u=True, s1_perm_r=True, s1_perm_a=True)
    assert await dtlb_env.agent.drive_request(port=0, vaddr=VA2, cmd=LOAD) == ((VA2 & (0xFFF)) | (PA2 & ~(0xFFF)))
    await dtlb_env.bundle.step()
    requestor[0].req.valid.value = 1
    requestor[0].req.bits_vaddr.value = VA0
    requestor[0].req.bits_fullva.value = VA0
    requestor[0].req.bits_cmd.value = STORE
    requestor[0].req.bits_no_translate.value = 0
    requestor[1].req.valid.value = 1
    requestor[1].req.bits_vaddr.value = VA1
    requestor[1].req.bits_fullva.value = VA1
    requestor[1].req.bits_cmd.value = LOAD
    requestor[1].req.bits_no_translate.value = 0
    requestor[2].req.valid.value = 1
    requestor[2].req.bits_vaddr.value = VA2
    requestor[2].req.bits_fullva.value = VA2
    requestor[2].req.bits_cmd.value = LOAD
    requestor[2].req.bits_no_translate.value = 0

    await dtlb_env.bundle.step()

    requestor[0].req.valid.value = 0
    requestor[1].req.valid.value = 0
    requestor[2].req.valid.value = 0
    await dtlb_env.bundle.step()

@toffee_test.testcase
async def test_store_2mb_page(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    va_base = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1)) & ~((1<<21)-1)
    pa_base = random.randint(2 ** 12, 2 ** 36 - 1) & ~((1<<21)-1)


    r0 = await dtlb_env.agent.drive_request(port=0, vaddr=va_base, cmd=STORE)
    assert r0 is None

    await dtlb_env.agent.set_ptw_resp(
        vaddr=va_base, paddr=pa_base, level=1, s1_asid=0,
        s1_ppn_low=[0]*8, s1_valididx=[1]*8, s1_pteidx=[0]*8,
        s1_perm_u=True, s1_perm_w=True, s1_perm_a=True,
        s1_perm_d=True, s1_perm_r=False,
    )

    for off in (0x000, 0x1000, 0x1FF000):
        va = va_base + off
        r1 = await dtlb_env.agent.drive_request(port=0, vaddr=va, cmd=STORE)
        mask = (1 << 21) - 1
        expect = (pa_base & ~mask) | (va & mask)
        assert r1 == expect


@toffee_test.testcase
async def test_store_1gb_page(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    va_base = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1)) & ~((1<<30)-1)
    pa_base = random.randint(2 ** 12, 2 ** 36 - 1) & ~((1<<30)-1)

    r0 = await dtlb_env.agent.drive_request(port=0, vaddr=va_base, cmd=STORE)
    assert r0 is None

    await dtlb_env.agent.set_ptw_resp(
        vaddr=va_base, paddr=pa_base, level=2, s1_asid=0,
        s1_ppn_low=[0]*8, s1_valididx=[1]*8, s1_pteidx=[0]*8,
        s1_perm_u=True, s1_perm_w=True, s1_perm_a=True,
        s1_perm_d=True, s1_perm_r=False,
    )

    for off in (0x0, 0x21_000, 0x3FF_F000):
        va = va_base + off
        r1 = await dtlb_env.agent.drive_request(port=0, vaddr=va, cmd=STORE)
        mask = (1 << 30) - 1
        expect = (pa_base & ~mask) | (va & mask)
        assert r1 == expect

@toffee_test.testcase
async def test_express_random(dtlb_env):
    dtlb_env.dut.reset.value = 1
    await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0
    await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults()
    await dtlb_env.bundle.step()
    va = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))
    pa = random.randint(2 ** 12, 2 ** 36 - 1)
    r0 = await dtlb_env.agent.drive_request(port=0, vaddr=va, cmd=STORE)
    assert r0 is None
    vpn_low = (va >> 12) & 0x7
    ppn_low = (pa >> 12) & 0x7
    rand_valididx = [0]*8
    rand_ppn_low = [0]*8
    pteidx = [0]*8
    for i in range(8):
        rand_valididx[i] = random.randint(0,1)
        rand_ppn_low[i] = i
    rand_valididx[vpn_low] = 1
    pteidx[vpn_low] = 1
    await dtlb_env.agent.set_ptw_resp(
        vaddr=va,
        paddr=pa,
        level=0,  
        s1_perm_u=True, s1_perm_w=True, s1_perm_a=True,
        s1_perm_d=True, s1_perm_r=False,
        s1_asid=0,
        s1_ppn_low=rand_ppn_low, 
        s1_valididx=rand_valididx, 
        s1_pteidx=pteidx  
    )
    va_base = va & ~((1<<15)-1)
    pa_base = pa & ~((1<<15)-1)
    for i in range(8):
        va = va_base | (i << 12)
        pa = pa_base | (rand_ppn_low[i] << 12)
        r1 = await dtlb_env.agent.drive_request(port=0, vaddr=va, cmd=STORE)
        if rand_valididx[i] != 0:    
            expect = (pa & ~0xFFF) | (va & 0xFFF)
        else:
            expect = None
        assert r1 == expect

@toffee_test.testcase
async def test_express_full(dtlb_env):
    dtlb_env.dut.reset.value = 1
    await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0
    await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults()
    await dtlb_env.bundle.step()
    
    va = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))
    pa = random.randint(2 ** 12, 2 ** 36 - 1)
    r0 = await dtlb_env.agent.drive_request(port=0, vaddr=va, cmd=STORE)
    assert r0 is None
    vpn_low = (va >> 12) & 0x7
    pteidx = [0]*8
    pteidx[vpn_low] = 1
    await dtlb_env.agent.set_ptw_resp(
        vaddr=va,
        paddr=pa,
        level=0,  
        s1_asid=0,
        s1_perm_u=True, s1_perm_w=True, s1_perm_a=True,
        s1_perm_d=True, s1_perm_r=False,
        s1_ppn_low=[0,1,2,3,4,5,6,7], 
        s1_valididx=[1,1,1,1,1,1,1,1], 
        s1_pteidx=pteidx 
    )
    va_base = va & ~((1<<15)-1)
    pa_base = pa & ~((1<<15)-1)
    for i in range(8):
        va = va_base | (i << 12)
        pa = pa_base | (i << 12)
        r1 = await dtlb_env.agent.drive_request(port=0, vaddr=va, cmd=STORE)    
        expect = (pa & ~0xFFF) | (va & 0xFFF)
        assert r1 == expect
    
@toffee_test.testcase
async def test_req_kill(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    port = 0
    rob = 0x3A
    va  = 0x0000_0000_8020_9000

    req = dtlb_env.bundle.requestor[port].req
    req.bits_vaddr.value = va & ((1<<50)-1)
    req.bits_fullva.value = va
    req.bits_cmd.value = 0  
    req.bits_kill.value = 1
    req.valid.value = 1
   
    req.valid.value = 0

    N = 32
    for _ in range(N):
        assert dtlb_env.bundle.requestor[port].resp.valid.value == 0
        for i in range(4):
            assert dtlb_env.bundle.ptw.req[i].valid.value == 0
        await dtlb_env.bundle.step()

@toffee_test.testcase
async def test_req_notranslate(dtlb_env):
    dtlb_env.dut.reset.value = 1
    await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0
    await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults()
    await dtlb_env.bundle.step()
    
    va = 0x0000_0000_8020_1000
    r0 = await dtlb_env.agent.drive_request(port=0, vaddr=va, cmd=STORE, no_translate = 1)
    assert r0 == va
    

@toffee_test.testcase
async def test_hit_smoke(dtlb_env):
    dtlb_env.dut.reset.value = 1
    await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0
    await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults()
    await dtlb_env.bundle.step()
    
    r0 = await dtlb_env.agent.drive_request(port=0, vaddr=0x0000_0000_8020_1000, cmd=STORE)
    assert r0 is None
    
    await dtlb_env.agent.set_ptw_resp(
        vaddr=0x0000_0000_8020_1000,
        paddr=0x0000_0001_2345_6000,
        level=0,  
        s1_asid=0,
        s1_perm_u=True, s1_perm_w=True, s1_perm_a=True,
        s1_perm_d=True, s1_perm_r=False,
    )

    r1 = await dtlb_env.agent.drive_request(port=0, vaddr=0x0000_0000_8020_1000, cmd=STORE)    
    expect = (0x0000_0001_2345_6000 & ~0xFFF) | (0x0000_0000_8020_1000 & 0xFFF)
    assert r1 == expect


@toffee_test.testcase
async def test_miss_smoke(dtlb_env):
    dtlb_env.dut.reset.value = 1
    await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0
    await dtlb_env.bundle.step()
    
    await dtlb_env.set_sv39_defaults()
    await dtlb_env.bundle.step()
    
    r0 = await dtlb_env.agent.drive_request(port=0, vaddr=0x0000_0000_8020_1000, cmd=STORE, kill=False ,no_translate=False)
    
    assert r0 is None