import pytest

from ..env import ittage_wrapper as wrapper_module


class FakeSignal:
    def __init__(self, value):
        self.value = value


class FakeClock:
    def __init__(self, dut, ready_after_wait_cycles):
        self.dut = dut
        self.ready_after_wait_cycles = ready_after_wait_cycles
        self.step_calls = []
        self.waited_cycles = 0

    def Step(self, cycles):
        self.step_calls.append(cycles)
        if self.dut.reset.value == 0 and self.dut.io_s1_ready.value == 0:
            self.waited_cycles += cycles
            if (
                self.ready_after_wait_cycles is not None
                and self.waited_cycles >= self.ready_after_wait_cycles
            ):
                self.dut.io_s1_ready.value = 1


class FakeDut:
    def __init__(self, ready_after_wait_cycles):
        initially_ready = ready_after_wait_cycles == 0
        self.reset = FakeSignal(0)
        self.io_s1_ready = FakeSignal(int(initially_ready))
        self.xclock = FakeClock(self, ready_after_wait_cycles)
        self.clock_names = []

    def InitClock(self, name):
        self.clock_names.append(name)


class FakeBundle:
    @classmethod
    def from_prefix(cls, _prefix):
        return cls()

    def set_name(self, _name):
        return self

    def bind(self, _dut):
        return self


def make_wrapper(ready_after_wait_cycles):
    dut = FakeDut(ready_after_wait_cycles)
    wrapper = wrapper_module.ITTageWrapper.__new__(wrapper_module.ITTageWrapper)
    wrapper.dut = dut
    wrapper.xclock = dut.xclock
    return wrapper, dut


def test_reset_returns_immediately_when_ready():
    wrapper, dut = make_wrapper(ready_after_wait_cycles=0)

    wrapper.reset(ready_timeout_cycles=3)

    assert dut.xclock.step_calls == [1, 10]


@pytest.mark.parametrize("ready_timeout_cycles", [0, -1])
def test_reset_rejects_non_positive_timeout_without_clocking(ready_timeout_cycles):
    wrapper, dut = make_wrapper(ready_after_wait_cycles=None)

    with pytest.raises(ValueError, match="must be greater than zero"):
        wrapper.reset(ready_timeout_cycles=ready_timeout_cycles)

    assert dut.reset.value == 0
    assert dut.xclock.step_calls == []


def test_reset_accepts_ready_on_last_allowed_cycle():
    wrapper, dut = make_wrapper(ready_after_wait_cycles=3)

    wrapper.reset(ready_timeout_cycles=3)

    assert dut.xclock.waited_cycles == 3
    assert dut.xclock.step_calls == [1, 1, 1, 1, 10]


def test_reset_times_out_after_bounded_wait():
    wrapper, dut = make_wrapper(ready_after_wait_cycles=None)

    with pytest.raises(TimeoutError, match=r"3 cycles waiting for io_s1_ready=1"):
        wrapper.reset(ready_timeout_cycles=3)

    assert dut.reset.value == 0
    assert dut.xclock.waited_cycles == 3
    assert dut.xclock.step_calls == [1, 1, 1, 1]


def test_constructor_forwards_configurable_timeout(monkeypatch):
    for bundle_name in ("UpdateBundle", "InBundle", "OutBundle", "PipelineCtrl"):
        monkeypatch.setattr(wrapper_module, bundle_name, FakeBundle)
    dut = FakeDut(ready_after_wait_cycles=None)

    with pytest.raises(TimeoutError, match=r"2 cycles waiting for io_s1_ready=1"):
        wrapper_module.ITTageWrapper(dut, ready_timeout_cycles=2)

    assert dut.clock_names == ["clock"]
    assert dut.xclock.step_calls == [1, 1, 1]
