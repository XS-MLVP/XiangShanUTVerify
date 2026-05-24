import toffee
import toffee_test
import toffee.funcov as fc
from ..env.dtlb_env import DTLBEnv, DTLBEnv_PLRU
from dut.TLBNonBlock import DUTTLBNonBlock
from .funcov_dtlb import init_dtlb_funcov

@toffee_test.fixture
async def dtlb_env_plru(toffee_request: toffee_test.ToffeeRequest):
    
    toffee.setup_logging(toffee.ERROR)
    dut = toffee_request.create_dut(DUTTLBNonBlock)

    dut.InitClock("clock")
    toffee.start_clock(dut)
    env = DTLBEnv_PLRU(dut)
    # env.req.start_monitor("monitor_req", 50)
    # env.req.start_monitor("monitor_resp", 50)
    # env.req.start_monitor("monitor_ptw_resp", 50)
    # env.req.start_monitor("monitor_ptw_req", 50)

    yield env

    import asyncio
    loop = asyncio.get_event_loop()
    for task in asyncio.all_tasks(loop):
        if task.get_name() == "__clock_loop":
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

g = fc.CovGroup("DTLB_FCOV_CASE")
@toffee_test.fixture
async def dtlb_env(toffee_request: toffee_test.ToffeeRequest):
    
    toffee.setup_logging(toffee.ERROR)
    dut = toffee_request.create_dut(DUTTLBNonBlock)
    
    dut.InitClock("clock")
    toffee.start_clock(dut)
    env = DTLBEnv(dut)
    toffee_request.add_cov_groups(init_dtlb_funcov(dut, g))
    # env.req.start_monitor("monitor_req", 50)
    # env.req.start_monitor("monitor_resp", 50)
    # env.req.start_monitor("monitor_ptw_resp", 50)
    # env.req.start_monitor("monitor_ptw_req", 50)
    yield env


    import asyncio
    loop = asyncio.get_event_loop()
    for task in asyncio.all_tasks(loop):
        if task.get_name() == "__clock_loop":
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
