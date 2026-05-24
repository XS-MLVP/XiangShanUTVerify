# -*- coding: utf-8 -*-
import toffee
import toffee_test
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

def _canon_sv39_to_50b(va: int, page_align: bool) -> int:
    low39 = va & ((1 << 39) - 1)
    sign  = (low39 >> 38) & 1
    upper = ((-sign) & ((1 << (50 - 39)) - 1)) << 39
    va50  = (upper | low39) & ((1 << 50) - 1)
    if page_align:
        va50 &= ~0xFFF
    return va50

async def do_sfence(dtlb_env, *, hv=False, hg=False, rs1=False, addr=0, rs2=False, id_=0, settle_cycles=10):
    sf = dtlb_env.bundle.sfence
    sf.bits_hv.value = 1 if hv else 0
    sf.bits_hg.value = 1 if hg else 0
    sf.bits_rs1.value = 1 if rs1 else 0
    sf.bits_rs2.value = 1 if rs2 else 0

    sf.bits_addr.value = _canon_sv39_to_50b(addr, page_align=rs1)
    sf.bits_id.value   = int(id_) & ((1 << 16) - 1)
    sf.bits_flushPipe.value = 0

    sf.valid.value = 1
    await dtlb_env.bundle.step()
    sf.valid.value = 0

    for _ in range(settle_cycles):
        await dtlb_env.bundle.step()


# =========================
# 1) SFENCE.VMA 全量清（非 G）
# =========================
@toffee_test.testcase
async def test_sfence_vma_global_noG(dtlb_env):
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    port = 0
    va   = 0x0000_0000_8020_1000
    pa   = 0x0000_0001_0000_9000
    asid = 0x11

    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 0
    csr.Satp.mode.value = 8
    csr.Satp.asid.value = asid
    await dtlb_env.bundle.step()

    # miss → 回填（非 G）→ hit
    assert await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=LOAD) is None
    _, s2x, _ = await _wait_ptw_req_and_capture(dtlb_env, va)
    await dtlb_env.agent.set_ptw_resp(vaddr=va, paddr=pa, level=0,
                               s1_asid=asid, s1_perm_r=True, s1_perm_a=True, s1_perm_g=False,
                               s2xlate=s2x)
    expect = (pa & ~0xFFF) | (va & 0xFFF)
    assert await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=LOAD) == expect

    # 全量清（rs1=0, rs2=0）
    await do_sfence(dtlb_env, hv=False, hg=False, rs1=False, rs2=False)

    # 应 miss
    assert await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=LOAD) is None


# =========================
# 2) SFENCE.VMA 按 ASID 清
# =========================
@toffee_test.testcase
async def test_sfence_vma_by_asid(dtlb_env):
    dtlb_env = dtlb_env
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()
    
    port = 0
    va   = 0x0000_0000_8020_1000
    pa   = 0x0000_0001_0000_9000
    asid = 0x22
    
    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 0
    csr.Satp.mode.value = 8
    csr.Satp.asid.value = asid
    await dtlb_env.bundle.step()

    

    assert await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=LOAD) is None
    _, s2x, _ = await _wait_ptw_req_and_capture(dtlb_env, va)
    await dtlb_env.agent.set_ptw_resp(vaddr=va, paddr=pa, level=0,
                               s1_asid=asid, s1_perm_r=True, s1_perm_a=True, s1_perm_g=False,
                               s2xlate=s2x)
    assert await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=LOAD) == ((pa & ~0xFFF) | (va & 0xFFF))

    # 按当前 satp.asid 清（id 用 CSR.Satp.asid）
    await do_sfence(dtlb_env, hv=False, hg=False, rs1=False, rs2=True, id_=asid)
    assert await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=LOAD) is None


# =========================
# 3) SFENCE.VMA 按 VA 清
# =========================
@toffee_test.testcase
async def test_sfence_vma_by_va(dtlb_env):
    dtlb_env = dtlb_env
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    port = 1
    va   = 0x0000_0000_8020_1000
    pa   = 0x0000_0001_0000_9000
    asid = 0x33

    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 0
    csr.Satp.mode.value = 8
    csr.Satp.asid.value = asid
    await dtlb_env.bundle.step()


    assert await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=LOAD) is None
    _, s2x, _ = await _wait_ptw_req_and_capture(dtlb_env, va)
    await dtlb_env.agent.set_ptw_resp(vaddr=va, paddr=pa, level=0,
                               s1_asid=asid, s1_perm_r=True, s1_perm_a=True, s1_perm_g=False,
                               s2xlate=s2x)
    assert await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=LOAD) == ((pa & ~0xFFF) | (va & 0xFFF))

    await do_sfence(dtlb_env, hv=False, hg=False, rs1=True, addr=va, rs2=False)
    assert await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=LOAD) is None


# =========================
# 4) SFENCE.VMA 按 (VA, ASID) 清
# =========================
@toffee_test.testcase
async def test_sfence_vma_by_va_asid(dtlb_env):
    dtlb_env = dtlb_env
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    port = 2
    va   = 0x0000_0000_8020_1000
    pa   = 0x0000_0001_0000_9000
    asid = 0x44
    
    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 0
    csr.Satp.mode.value = 8
    csr.Satp.asid.value = asid
    await dtlb_env.bundle.step()

    

    assert await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=LOAD) is None
    _, s2x, _ = await _wait_ptw_req_and_capture(dtlb_env, va)
    await dtlb_env.agent.set_ptw_resp(vaddr=va, paddr=pa, level=0,
                               s1_asid=asid, s1_perm_r=True, s1_perm_a=True, s1_perm_g=False,
                               s2xlate=s2x)
    assert await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=LOAD) == ((pa & ~0xFFF) | (va & 0xFFF))

    await do_sfence(dtlb_env, hv=False, hg=False, rs1=True, addr=va, rs2=True, id_=asid)
    assert await dtlb_env.agent.drive_request(port=port, vaddr=va, cmd=LOAD) is None


# =========================
# 5) HFENCE.VVMA：按 VMID（全 GVA）
# =========================
@toffee_test.testcase
async def test_hfence_vvma_by_vmid(dtlb_env):
    dtlb_env = dtlb_env
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    port = 0
    gva  = 0x0000_0000_8020_1000
    gpa  = 0x0000_0001_0000_9000
    asid = 0x12
    vmid = 0xAA

    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 1
    csr.Vsatp.mode.value = 8   # VS-S1 开启
    csr.HGatp.mode.value = 0   # S2 关闭（only VS-S1）
    csr.Vsatp.asid.value = asid
    csr.HGatp.vmid.value = vmid   # 关键：VVMA 用 CSR.HGATP.vmid 过滤
    await dtlb_env.bundle.step()

    

    assert await dtlb_env.agent.drive_request(port=port, vaddr=gva, cmd=LOAD) is None
    _, s2x, _ = await _wait_ptw_req_and_capture(dtlb_env, gva)
    await dtlb_env.agent.set_ptw_resp(vaddr=gva, paddr=gpa, level=0,
                               s1_asid=asid, s1_vmid=vmid,
                               s1_perm_r=True, s1_perm_a=True, s1_perm_u=True, s1_perm_g=False,
                               s2xlate=s2x)
    assert await dtlb_env.agent.drive_request(port=port, vaddr=gva, cmd=LOAD) == ((gpa & ~0xFFF) | (gva & 0xFFF))

    # VVMA：hv=1，通常按 VMID 过滤需 rs2=1；VMID 来源于 CSR.HGATP.vmid（id 忽略）
    await do_sfence(dtlb_env, hv=True, hg=False, rs1=False, rs2=True, id_=vmid)
    assert await dtlb_env.agent.drive_request(port=port, vaddr=gva, cmd=LOAD) is None


# =========================
# 6) HFENCE.VVMA：按 (GVA, VMID) 清
# =========================
@toffee_test.testcase
async def test_hfence_vvma_by_gva_vmid(dtlb_env):
    dtlb_env = dtlb_env
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    port = 1
    gva  = 0x0000_0000_8020_1000
    gpa  = 0x0000_0001_0000_9000
    asid = 0x21
    vmid = 0xBB

    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 1
    csr.Vsatp.mode.value = 8
    csr.HGatp.mode.value = 0
    csr.Vsatp.asid.value = asid
    csr.HGatp.vmid.value = vmid
    await dtlb_env.bundle.step()

    assert await dtlb_env.agent.drive_request(port=port, vaddr=gva, cmd=LOAD) is None
    _, s2x, _ = await _wait_ptw_req_and_capture(dtlb_env, gva)
    await dtlb_env.agent.set_ptw_resp(vaddr=gva, paddr=gpa, level=0,
                               s1_asid=asid, s1_vmid=vmid,
                               s1_perm_r=True, s1_perm_a=True, s1_perm_u=True, s1_perm_g=False,
                               s2xlate=s2x)
    assert await dtlb_env.agent.drive_request(port=port, vaddr=gva, cmd=LOAD) == ((gpa & ~0xFFF) | (gva & 0xFFF))

    await do_sfence(dtlb_env, hv=True, hg=False, rs1=True, addr=gva, rs2=True, id_=vmid)
    assert await dtlb_env.agent.drive_request(port=port, vaddr=gva, cmd=LOAD) is None


# =========================
# 7) HFENCE.GVMA：按 VMID 清 S2（GPA 全范围）
# =========================
@toffee_test.testcase
async def test_hfence_gvma_by_vmid(dtlb_env):
    dtlb_env = dtlb_env
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    port = 2
    gpa_in = 0x0000_0000_8020_1000
    hpa    = 0x0000_0002_2000_0000
    vmid   = 0x66

    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 1
    csr.Vsatp.mode.value = 0
    csr.HGatp.mode.value = 8
    csr.HGatp.vmid.value = vmid
    await dtlb_env.bundle.step()

    assert await dtlb_env.agent.drive_request(port=port, vaddr=gpa_in, cmd=LOAD) is None
    _, s2x, getGpa_req = await _wait_ptw_req_and_capture(dtlb_env, gpa_in)
    await dtlb_env.agent.set_ptw_resp(vaddr=gpa_in, paddr=0, level=0, s1_v=False,
                               s2xlate=s2x, getGpa=getGpa_req,
                               s2_tag=(gpa_in >> 12) & ((1<<27)-1),
                               s2_ppn=(hpa >> 12), s2_level=0,
                               s1_vmid=vmid, s2_perm_r=True, s2_perm_a=True)
    assert await dtlb_env.agent.drive_request(port=port, vaddr=gpa_in, cmd=LOAD) == ((hpa & ~0xFFF) | (gpa_in & 0xFFF))

    # GVMA：hg=1，按 VMID（来自 bits_id）清 S2
    await do_sfence(dtlb_env, hv=False, hg=True, rs1=False, rs2=True, id_=vmid)
    assert await dtlb_env.agent.drive_request(port=port, vaddr=gpa_in, cmd=LOAD) is None


# =========================
# 8) HFENCE.GVMA：按 (GPA, VMID) 清 S2
# =========================
@toffee_test.testcase
async def test_hfence_gvma_by_gpa_vmid(dtlb_env):
    dtlb_env = dtlb_env
    dtlb_env.dut.reset.value = 1; await dtlb_env.bundle.step()
    dtlb_env.dut.reset.value = 0; await dtlb_env.bundle.step()
    await dtlb_env.set_sv39_defaults(); await dtlb_env.bundle.step()

    port = 3
    gpa_in = 0x0000_0000_8020_1000
    hpa    = 0x0000_0002_2000_1000
    vmid   = 0x77

    csr = dtlb_env.bundle.csr
    csr.priv_virt.value = 1
    csr.Vsatp.mode.value = 0
    csr.HGatp.mode.value = 8
    csr.HGatp.vmid.value = vmid
    await dtlb_env.bundle.step()

    assert await dtlb_env.agent.drive_request(port=port, vaddr=gpa_in, cmd=LOAD) is None
    _, s2x, getGpa_req = await _wait_ptw_req_and_capture(dtlb_env, gpa_in)
    await dtlb_env.agent.set_ptw_resp(vaddr=gpa_in, paddr=0, level=0, s1_v=False,
                               s2xlate=s2x, getGpa=getGpa_req,
                               s2_tag=(gpa_in >> 12) & ((1<<27)-1),
                               s2_ppn=(hpa >> 12), s2_level=0,
                               s1_vmid=vmid, s2_perm_r=True, s2_perm_a=True)
    assert await dtlb_env.agent.drive_request(port=port, vaddr=gpa_in, cmd=LOAD) == ((hpa & ~0xFFF) | (gpa_in & 0xFFF))

    await do_sfence(dtlb_env, hv=False, hg=True, rs1=True, addr=gpa_in, rs2=True, id_=vmid)
    assert await dtlb_env.agent.drive_request(port=port, vaddr=gpa_in, cmd=LOAD) is None
