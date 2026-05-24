from toffee.agent import Agent, driver_method, monitor_method
from toffee import Value
from ld_tlb_bundle import DTLBBundle, RequestorBundle, CSRBundle, PTWBundle, PMPBundle

class DTLBAgent(Agent):
    def __init__(self, dtlb_bundle: DTLBBundle):
        super().__init__(dtlb_bundle)
        self.requestor = dtlb_bundle.requestor

    @driver_method()
    async def drive_request(self, port: int, vaddr: int, cmd: int, hyperinst: bool = False):
        """发送请求到指定端口。
        Args:
            port: 端口号 (0-3)
            vaddr: 虚拟地址
            cmd: 请求命令
            hyperinst: 是否为 hypervisor 指令
        Returns:
            int or None: 物理地址 (paddr_0) 如果有效；否则 None（miss 或异常）
        """
        if not 0 <= port < 4:
            raise ValueError("Port must be 0-3")
        
        req_bundle = self.requestor[port].req
        req_bundle.valid.value = 1
        req_bundle.bits_vaddr.value = vaddr
        req_bundle.bits_cmd.value = cmd
        req_bundle.bits_hyperinst.value = 1 if hyperinst else 0
        await self.bundle.step()  # 启动请求
        req_bundle.valid.value = 0
        resp = self.requestor[port].resp

        await Value(resp.valid, 1)  # 等待 resp.valid = 1，无论miss还是hit

        # 检查异常信号（扩展所有相关异常）
        has_fault = (resp.bits_excp_0_gpf_ld.value == 1 or
                     resp.bits_excp_0_pf_ld.value == 1 or
                     resp.bits_excp_0_af_ld.value == 1)

        if resp.valid.value == 1 and resp.bits_miss.value == 0 and not has_fault:
            return resp.bits_paddr_0.value
        return None  # miss 或异常，检查 monitor_resp
    
    @monitor_method()
    async def monitor_resp(self):
        """
        监测响应。
        """
        for port in range(4):
            resp = self.requestor[port].resp
            if resp.valid.value == 1:
                return {
                    "port": port,
                    "miss": resp.bits_miss.value,
                    "paddr": resp.bits_paddr_0.value,
                    "fullva": resp.bits_fullva.value,
                    "pbmt": resp.bits_pbmt_0.value,
                    "excp_pf_ld": resp.bits_excp_0_pf_ld.value,
                    "excp_af_ld": resp.bits_excp_0_af_ld.value,
                }
        return None

    @monitor_method()
    async def monitor_multi_port(self):
        """
        监测多端口请求内容。
        """
        for port in range(4):
            req = self.requestor[port].req
            if req.valid.value == 1:
                return {
                    "port": port,
                    "vaddr": req.bits_vaddr.value,
                    "fullva": req.bits_fullva.value,
                    "checkfullva": req.bits_checkfullva.value,
                    "cmd": req.bits_cmd.value,
                    "hyperinst": req.bits_hyperinst.value,
                    "hlvx": req.bits_hlvx.value,
                    "kill": req.bits_kill.value,
                    "isPrefetch": req.bits_isPrefetch.value,
                    "no_translate": req.bits_no_translate.value,
                    "pmp_addr": req.bits_pmp_addr.value,
                    "debug_robIdx_flag": req.bits_debug_robIdx_flag.value,
                    "debug_robIdx_value": req.bits_debug_robIdx_value.value,
                    "debug_isFirstIssue": req.bits_debug_isFirstIssue.value
                }
        return None

class CSRAgent(Agent):
    def __init__(self, csr_bundle: CSRBundle):
        super().__init__(csr_bundle)

    @driver_method()
    async def drive_virt_config(self, virt: bool, satp_mode: int, vsatp_mode: int, hgatp_mode: int):
        """配置虚拟化模式。
        Args:
            virt: 是否启用虚拟化
            satp_mode: SATP 模式
            vsatp_mode: VSATP 模式
            hgatp_mode: HGATP 模式
        """
        self.bundle.priv_virt.value = 1 if virt else 0
        self.bundle.Satp.mode.value = satp_mode
        self.bundle.Vsatp.mode.value = vsatp_mode
        self.bundle.HGatp.mode.value = hgatp_mode
        await self.bundle.step()


class PTWAgent(Agent):
    def __init__(self, dtlb_bundle: DTLBBundle):
        super().__init__(dtlb_bundle.ptw)
        self.dtlb_bundle = dtlb_bundle

    @driver_method()
    async def drive_ptw_req(self, port: int, vpn: int, s2xlate: int):
        """发送 PTW 请求并等待完整流程。
        Args:
            port: 端口号 (0-3)
            vpn: 虚拟页号
            s2xlate: 二阶段翻译模式
        Returns:
            int or None: 最终物理地址 (paddr_0) 如果无 fault；否则 None
        """
        if not 0 <= port < 4:
            raise ValueError("Port must be 0-3")
        
        req = self.bundle.req[port]
        req.valid.value = 1
        req.bits_vpn.value = vpn
        req.bits_s2xlate.value = s2xlate
        await self.bundle.step()
        req.valid.value = 0

        await Value(self.bundle.resp.valid, 1)
        has_fault = (self.bundle.resp.bits_s1_pf.value == 1 or
                     self.bundle.resp.bits_s1_af.value == 1 or
                     self.bundle.resp.bits_s2_gpf.value == 1 or
                     self.bundle.resp.bits_s2_gaf.value == 1)
        if has_fault:
            return None  # Fault 发生
        
        await Value(self.dtlb_bundle.requestor[port].resp.valid, 1)
        resp = self.dtlb_bundle.requestor[port].resp
        resp_has_fault = (resp.bits_excp_0_gpf_ld.value == 1 or
                          resp.bits_excp_0_pf_ld.value == 1 or
                          resp.bits_excp_0_af_ld.value == 1)
        if resp.bits_miss.value == 0 and not resp_has_fault:
            return resp.bits_paddr_0.value
        return None  # Miss 或异常，检查 monitor_resp

    @monitor_method()
    async def monitor_ptw_resp(self):
        """监测 PTW 响应内容。
        """
        if self.bundle.resp.valid.value == 1:
            # 查找最近触发的 PTW 请求端口
            for port in range(4):
                if self.bundle.req[port].valid.value == 1 or self.dtlb_bundle.tlbreplay[port].value == 1:
                    return {
                        "port": port,
                        "s1_pf": self.bundle.resp.bits_s1_pf.value,
                        "s1_af": self.bundle.resp.bits_s1_af.value,
                        "s2_gpf": self.bundle.resp.bits_s2_gpf.value,
                        "s2_gaf": self.bundle.resp.bits_s2_gaf.value,
                        "s2xlate": self.bundle.resp.bits_s2xlate.value
                    }
                    
    @monitor_method()
    async def monitor_requestor_resp(self):
        """监测 DTLB 请求响应内容。
        """
        for port in range(4):
            resp = self.dtlb_bundle.requestor[port].resp
            if resp.valid.value == 1:
                return {
                    "port": port,
                    "miss": resp.bits_miss.value,
                    "paddr": resp.bits_paddr_0.value,
                    "pbmt": resp.bits_pbmt_0.value,
                    "excp_pf_ld": resp.bits_excp_0_pf_ld.value,
                    "excp_af_ld": resp.bits_excp_0_af_ld.value,
                    "excp_gpf_ld": resp.bits_excp_0_gpf_ld.value,
                    "excp_pf_st": resp.bits_excp_0_pf_st.value,
                    "excp_af_st": resp.bits_excp_0_af_st.value,
                    "excp_gpf_st": resp.bits_excp_0_gpf_st.value,
                    "excp_vaNeedExt": resp.bits_excp_0_vaNeedExt.value,
                    "excp_isHyper": resp.bits_excp_0_isHyper.value
                }
        return None

class ControlAgent(Agent):
    def __init__(self, dtlb_bundle: DTLBBundle):
        super().__init__(dtlb_bundle)
        self.sfence = dtlb_bundle.sfence
        self.redirect = dtlb_bundle.redirect

    @driver_method()
    async def drive_sfence(self, rs1: bool, rs2: bool, addr: int = 0, id: int = 0, flushPipe: bool = False, hv: bool = False, hg: bool = False):
        """配置SFENCE，配置刷新范围。
        Args:
            rs1: 是否基于 RS1（地址刷新）
            rs2: 是否基于 RS2（ASID/VMID 刷新）
            addr: 目标虚拟地址（50 位）
            id: ASID 或 VMID（16 位）
            flushPipe: 是否刷新流水线
            hv: 是否针对 Hypervisor 模式
            hg: 是否针对 Guest 模式
        """
        self.sfence.bits_rs1.value = 1 if rs1 else 0
        self.sfence.bits_rs2.value = 1 if rs2 else 0
        self.sfence.bits_addr.value = addr & ((1 << 50) - 1)  
        self.sfence.bits_id.value = id & ((1 << 16) - 1)      
        self.sfence.bits_flushPipe.value = 1 if flushPipe else 0
        self.sfence.bits_hv.value = 1 if hv else 0
        self.sfence.bits_hg.value = 1 if hg else 0
        await self.bundle.step()

    @driver_method()
    async def drive_redirect(self, flag: bool, value: int, level: bool):
        """配置redirect。
        Args:
            robIdx_flag: robIdx 标志
            robIdx_value: robIdx 值
            level: 重定向级别
        """
        self.redirect.bits_robIdx_value.value = value & ((1 << 8) - 1)
        self.redirect.bits_robIdx_flag.value = 1 if flag else 0
        self.redirect.bits_level.value = 1 if level else 0
        await self.bundle.step()

class PMPAgent(Agent):
    def __init__(self, dtlb_bundle: DTLBBundle):
        super().__init__(dtlb_bundle.pmp)

    @monitor_method()
    async def monitor_pmp_excp(self):
        """监测 PMP 。
        """
        for i in range(4):
            if self.bundle[i].valid.value == 1:
                return {
                    "port": i,
                    "pmp_triggered": True,
                    "af_ld": self.dtlb_bundle.requestor[i].resp.bits_excp_0_af_ld.value
                }
        return None
