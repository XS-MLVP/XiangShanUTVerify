import toffee
import toffee_test
import random
from .ld_tlb_fixture import dtlb_env_plru

LOAD = 0
STORE = 1

async def _wait_ptw_req_and_capture(dtlb_env_plru, vaddr, max_cycles=32):
    vpn_expect = (int(vaddr) >> 12) & ((1 << 27) - 1)
    for _ in range(max_cycles):
        for i in range(4):
            req = dtlb_env_plru.bundle.ptw.req[i]
            if int(req.valid.value) == 1 and int(req.bits_vpn.value) == vpn_expect:
                return i, int(req.bits_s2xlate.value), int(req.bits_getGpa.value)
        await dtlb_env_plru.bundle.step()
    raise AssertionError("Timed out waiting for ptw.req on vpn=0x%x" % vpn_expect)

def _canon_sv39_vaddr(va: int) -> int:
    """把 64 位 VA 规范化为 Sv39 形式"""
    va = int(va) & ((1 << 64) - 1)
    low39 = va & ((1 << 39) - 1)
    sign  = (low39 >> 38) & 1
    upper = ((-sign) & ((1 << (64 - 39)) - 1)) << 39
    return (upper | low39) & ((1 << 64) - 1)

@toffee_test.testcase
async def test_plru_random(dtlb_env_plru):
    dtlb_env_plru.dut.reset.value = 1; await dtlb_env_plru.bundle.step()
    dtlb_env_plru.dut.reset.value = 0; await dtlb_env_plru.bundle.step()
    await dtlb_env_plru.set_sv39_defaults(); await dtlb_env_plru.bundle.step()
    va = [0]*100
    pa = [0]*100
    for i in range(100):
        va[i] = _canon_sv39_vaddr(random.randint(2 ** 12, 2 ** 39 - 1))
        pa[i] = random.randint(2 ** 12, 2 ** 36 - 1)
    for i in range(200):
        index = random.randint(0, 99)
        vaddr = va[index] 
        paddr = pa[index]
        
        r0 = await dtlb_env_plru.agent.drive_request(port=0, vaddr=vaddr, cmd=LOAD)
        
        if r0 == None:
            await dtlb_env_plru.agent.set_ptw_resp(
                vaddr=vaddr,
                paddr=paddr,
                level=0
            )
            await dtlb_env_plru.agent.drive_request(port=0, vaddr=vaddr, cmd=LOAD)    
        else:
            continue

@toffee_test.testcase
async def test_plru_sweep(dtlb_env_plru):
    dtlb_env_plru.dut.reset.value = 1; await dtlb_env_plru.bundle.step()
    dtlb_env_plru.dut.reset.value = 0; await dtlb_env_plru.bundle.step()
    await dtlb_env_plru.set_sv39_defaults(); await dtlb_env_plru.bundle.step()
    
    BASE_VA = 0x0000_0000_8020_0000
    BASE_PA = 0x0000_0001_2340_0000
    for i in range(48):
        va = BASE_VA + i * 0x8000
        pa = BASE_PA + i * 0x1000
        
        r0 = await dtlb_env_plru.agent.drive_request(port=1, vaddr=va, cmd=LOAD)
        assert r0 is None
        _, s2x, _ = await _wait_ptw_req_and_capture(dtlb_env_plru, va)
        await dtlb_env_plru.agent.set_ptw_resp(
            vaddr=va, paddr=pa, level=0,
            s1_perm_r=True, s1_perm_a=True, s1_perm_u=True,
            s2xlate=s2x
        )
        r2 = await dtlb_env_plru.agent.drive_request(port=1, vaddr=va, cmd=LOAD)
        expect = (pa & ~0xFFF) | (va & 0xFFF)
        assert r2 == expect
    new_va = BASE_VA + 0x1000 * 50
    new_pa = BASE_PA + 0x1000 * 50
    r0 = await dtlb_env_plru.agent.drive_request(port=1, vaddr=new_va, cmd=LOAD)
    assert r0 is None
    _, s2x, _ = await _wait_ptw_req_and_capture(dtlb_env_plru, new_va)
    await dtlb_env_plru.agent.set_ptw_resp(
        vaddr=new_va, paddr=new_pa, level=0,
        s1_perm_r=True, s1_perm_a=True, s1_perm_u=True,
        s2xlate=s2x
    )
    r2 = await dtlb_env_plru.agent.drive_request(port=1, vaddr=new_va, cmd=LOAD)
    expect = (new_pa & ~0xFFF) | (new_va & 0xFFF)
    assert r2 == expect
    miss_cnt = 0
    for i in range(48):
        va = BASE_VA + i * 0x8000
        ret = await dtlb_env_plru.agent.drive_request(port=1, vaddr=va, cmd=LOAD)
        if ret is None:
            miss_cnt += 1
    
    print(f"After inserting 49th entry, total miss when accessing original 48 entries: {miss_cnt}")

