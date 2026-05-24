# -*- coding: utf-8 -*-
from __future__ import annotations
from toffee.model import Model, driver_hook

def _canon_sv39_vaddr(va: int) -> int:
    va = int(va) & ((1 << 64) - 1)
    low39 = va & ((1 << 39) - 1)
    sign  = (low39 >> 38) & 1
    upper = ((-sign) & ((1 << (64 - 39)) - 1)) << 39
    return (upper | low39) & ((1 << 64) - 1)

def _page_key_from_va(va: int) -> int:
    canon = _canon_sv39_vaddr(va)
    va39  = canon & ((1 << 39) - 1)
    return va39 & ~0xFFF  

# ---------------------- 不平衡 48-way Tree-PLRU（根 32/16） ----------------------
class TreePLRU48:
    class Node:
        __slots__ = ("L", "R", "bit", "lch", "rch")
        def __init__(self, L, R):
            self.L, self.R = L, R 
            self.bit = 0     
            self.lch = None
            self.rch = None

    def __init__(self):
        self.root = self.Node(32, 16)
        def build(n):
            if n.L > 1:
                n.lch = self.Node(n.L // 2, n.L - n.L // 2)
                build(n.lch)
            if n.R > 1:
                n.rch = self.Node(n.R // 2, n.R - n.R // 2)
                build(n.rch)
        build(self.root)

    def pick_victim(self) -> int:
        n = self.root
        idx = 0
        while True:
            if n.L + n.R == 1:
                break
            if n.bit == 1:
                idx += n.L
                if n.R == 1:
                    break           # 右侧是叶，不再往下
                n = n.rch
            else:
                if n.L == 1:
                    break           # 左侧是叶，不再往下
                n = n.lch
        return idx

    def touch(self, i: int) -> None:
        n = self.root
        idx = i
        while n and (n.L + n.R > 1):
            if idx < n.L:
                # 走左：把右标冷（bit=1）
                n.bit = 1
                if n.L == 1:
                    break           # 左侧是叶，不再向下
                n = n.lch
            else:
                # 走右：把左标冷（bit=0）
                idx -= n.L
                n.bit = 0
                if n.R == 1:
                    break           # 右侧是叶，不再向下
                n = n.rch

    def reset(self):
        def walk(n):
            if not n: return
            n.bit = 0
            walk(n.lch); walk(n.rch)
        walk(self.root)


# ---------------------- 参考模型：48 项全相联 ----------------------
class DTLBPLRURefModel(Model):
    CAP = 48

    def __init__(self):
        super().__init__()
        self.entries = [{"valid": False, "va": 0, "pa": 0} for _ in range(self.CAP)]
        self.plru = TreePLRU48()

    @driver_hook(agent_name="agent", driver_name="drive_request")
    def drive_request(
        self,
        port: int,
        vaddr: int,
        cmd: int,
        *,
        hyperinst: bool = False,
        pmp_addr: int | None = None,
        hlvx: bool = False,
        kill: bool = False,
        is_prefetch: bool = False,
        no_translate: bool = False,
        check_fullva: bool = False,
        debug_robIdx_flag: int = 0,
        debug_robIdx_value: int = 0,
        debug_isFirstIssue: int = 0,
        return_on_miss: bool = False,
    ):
        key = _page_key_from_va(vaddr)
        for idx, e in enumerate(self.entries):
            if e["valid"] and e["va"] == key:
                self.plru.touch(idx)  # 命中也要更新 PLRU
                return int(e["pa"] | (int(vaddr) & 0xFFF))
        return None

    @driver_hook(agent_name="agent", driver_name="set_ptw_resp")
    def set_ptw_resp(self, vaddr, paddr, level, *,
                        # S1/S2 选择
                        valid: bool = True,
                        s2xlate: int = 0,
                        getGpa: bool = False,
                        # ---------- S1 entry ----------
                        s1_asid: int = 0,
                        s1_vmid: int = 0,
                        s1_n: bool = False,
                        s1_pbmt: int = 0,
                        s1_perm_d: bool = False, s1_perm_a: bool = True, s1_perm_g: bool = False,
                        s1_perm_u: bool = True, s1_perm_x: bool = False, s1_perm_w: bool = False, s1_perm_r: bool = True,
                        s1_v: bool = True,              
                        s1_ppn_low: list[int] | None = None, 
                        s1_valididx: list[int] | None = None, 
                        s1_pteidx: list[int] | None = None,   
                        s1_pf: bool = False, s1_af: bool = False,
                        s2_tag: int = 0,
                        s2_vmid: int = 0,
                        s2_n: bool = False,
                        s2_pbmt: int = 0,
                        s2_ppn: int = 0,
                        s2_perm_d: bool = False, s2_perm_a: bool = True, s2_perm_g: bool = False,
                        s2_perm_u: bool = False, s2_perm_x: bool = False, s2_perm_w: bool = False, s2_perm_r: bool = True,
                        s2_level: int = 0,
                        s2_gpf: bool = False, s2_gaf: bool = False,
                    ):
        if not valid:
            return None

        key = _page_key_from_va(vaddr)
        pa_base = int(paddr) & ~0xFFF

        # 若已有同 VA：覆写 + touch（避免同一 VA 出现多份）
        for idx, e in enumerate(self.entries):
            if e["valid"] and e["va"] == key:
                e["pa"] = pa_base
                self.plru.touch(idx)
                return None

        # 由 PLRU 直接给 wayIdx（即便有 invalid 也不优先用）
        victim = self.plru.pick_victim()
        self.entries[victim]["valid"] = True
        self.entries[victim]["va"] = key
        self.entries[victim]["pa"] = pa_base
        self.plru.touch(victim)
        return None
