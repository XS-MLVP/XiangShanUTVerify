# env/dtlb_env.py
from toffee import Env
from ..bundle.dtlb_bundle import DTLBBundle
from ..agent.dtlb_agent import DTLBAgent
from .dtlb_mdl import DTLBPLRURefModel

class DTLBEnv_PLRU(Env):
    def __init__(self, dut):
        super().__init__()
        self.dut = dut
        self.bundle = DTLBBundle.from_prefix("io_").bind(dut)
        self.agent = DTLBAgent(self.bundle)
        self.mdl = DTLBPLRURefModel()
        self.attach(self.mdl)
        
    async def set_sv39_defaults(self):
        csr = self.bundle.csr
        csr.priv_mxr.value  = 0; csr.priv_sum.value  = 0
        csr.priv_vmxr.value = 0; csr.priv_vsum.value = 0
        csr.priv_virt.value = 0; csr.priv_spvp.value = 0
        csr.priv_imode.value = 0; csr.priv_dmode.value = 0

        csr.Satp.mode.value    = 8  # Sv39 常见编码
        csr.Satp.asid.value    = 0
        csr.Satp.ppn.value     = 0
        csr.Satp.changed.value = 0

        csr.Vsatp.mode.value    = 0
        csr.Vsatp.asid.value    = 0
        csr.Vsatp.ppn.value     = 0
        csr.Vsatp.changed.value = 0

        csr.HGatp.mode.value    = 0
        csr.HGatp.vmid.value    = 0
        csr.HGatp.ppn.value     = 0
        csr.HGatp.changed.value = 0

        sf = self.bundle.sfence
        sf.valid.value = 0; sf.bits_rs1.value = 0; sf.bits_rs2.value = 0
        sf.bits_flushPipe.value = 0; sf.bits_hv.value = 0; sf.bits_hg.value = 0
        sf.bits_addr.value = 0; sf.bits_id.value = 0

class DTLBEnv(Env):
    def __init__(self, dut):
        super().__init__()
        self.dut = dut
        self.bundle = DTLBBundle.from_prefix("io_").bind(dut)
        self.agent = DTLBAgent(self.bundle)

    async def set_sv39_defaults(self):
        csr = self.bundle.csr
        csr.priv_mxr.value  = 0; csr.priv_sum.value  = 0
        csr.priv_vmxr.value = 0; csr.priv_vsum.value = 0
        csr.priv_virt.value = 0; csr.priv_spvp.value = 0
        csr.priv_imode.value = 0; csr.priv_dmode.value = 0

        csr.Satp.mode.value    = 8  # Sv39 常见编码
        csr.Satp.asid.value    = 0
        csr.Satp.ppn.value     = 0
        csr.Satp.changed.value = 0

        csr.Vsatp.mode.value    = 0
        csr.Vsatp.asid.value    = 0
        csr.Vsatp.ppn.value     = 0
        csr.Vsatp.changed.value = 0

        csr.HGatp.mode.value    = 0
        csr.HGatp.vmid.value    = 0
        csr.HGatp.ppn.value     = 0
        csr.HGatp.changed.value = 0

        sf = self.bundle.sfence
        sf.valid.value = 0; sf.bits_rs1.value = 0; sf.bits_rs2.value = 0
        sf.bits_flushPipe.value = 0; sf.bits_hv.value = 0; sf.bits_hg.value = 0
        sf.bits_addr.value = 0; sf.bits_id.value = 0