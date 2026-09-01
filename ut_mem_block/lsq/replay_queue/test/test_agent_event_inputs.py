# coding=utf8
# ***************************************************************************************
# This project is licensed under Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#          http://license.coscl.org.cn/MulanPSL2
#
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
#
# See the Mulan PSL v2 for more details.
# **************************************************************************************/


import asyncio
from types import SimpleNamespace

from ..agent.LoadQueueReplayAgent import LoadQueueReplayAgent
from ..util.dataclass import (
    IOldWbPtr,
    ReadySqPtr,
    StoreAddrIn,
    StoreDataIn,
    TLChannel,
    TlbHint,
)


class RecordingPin:
    def __init__(self):
        self.writes = []

    @property
    def value(self):
        return self.writes[-1] if self.writes else None

    @value.setter
    def value(self, new_value):
        self.writes.append(new_value)


def pin_vector(size):
    return SimpleNamespace(**{f"_{index}": RecordingPin() for index in range(size)})


def pointer():
    return SimpleNamespace(_flag=RecordingPin(), _value=RecordingPin())


def store_addr_port():
    return SimpleNamespace(
        _valid=RecordingPin(),
        _bits=SimpleNamespace(_uop_sqIdx=pointer(), _miss=RecordingPin()),
    )


def store_data_port():
    return SimpleNamespace(_valid=RecordingPin(), _bits_uop_sqIdx=pointer())


class RecordingBundle:
    def __init__(self):
        self.store_addr_ports = [store_addr_port() for _ in range(2)]
        self.store_data_ports = [store_data_port() for _ in range(2)]
        self.io = SimpleNamespace(
            _stDataReadySqPtr=pointer(),
            _sqEmpty=RecordingPin(),
            _stAddrReadyVec=pin_vector(56),
            _stDataReadyVec=pin_vector(56),
            _storeAddrIn=SimpleNamespace(
                **{f"_{index}": port for index, port in enumerate(self.store_addr_ports)}
            ),
            _storeDataIn=SimpleNamespace(
                **{f"_{index}": port for index, port in enumerate(self.store_data_ports)}
            ),
            _stAddrReadySqPtr=pointer(),
            _tlb_hint_resp=SimpleNamespace(
                _valid=RecordingPin(),
                _bits=SimpleNamespace(_id=RecordingPin(), _replay_all=RecordingPin()),
            ),
            _tl_d_channel=SimpleNamespace(_valid=RecordingPin(), _mshrid=RecordingPin()),
            _rarFull=RecordingPin(),
            _rawFull=RecordingPin(),
            _ldWbPtr=pointer(),
        )
        self.LoadQueueReplay = object()
        self.step_calls = []

    async def step(self, cycles):
        self.step_calls.append(cycles)


def test_update_blocking_pulses_event_valids_and_preserves_level_inputs():
    bundle = RecordingBundle()
    agent = object.__new__(LoadQueueReplayAgent)
    agent.bundle = bundle

    update_blocking = LoadQueueReplayAgent.Update_blocking.__original_func__
    result = asyncio.run(
        update_blocking(
            agent,
            stDataReadySqPtr=ReadySqPtr(flag=True, value=9),
            stAddrReadySqPtr=ReadySqPtr(flag=False, value=7),
            sqEmpty=True,
            storeAddrIn=[
                StoreAddrIn(valid=True, sqIdx_flag=True, sqIdx_value=3, miss=False),
                StoreAddrIn(valid=True, sqIdx_flag=False, sqIdx_value=4, miss=True),
            ],
            storeDataIn=[
                StoreDataIn(valid=True, sqIdx_flag=True, sqIdx_value=5),
                StoreDataIn(valid=True, sqIdx_flag=False, sqIdx_value=6),
            ],
            stAddrReadyVec=[True] * 56,
            stDataReadyVec=[False] * 56,
            tlb_hint=TlbHint(valid=True, id=11, replay_all=False),
            tl_channel=TLChannel(valid=True, mshrid=13),
            rarFull=True,
            ldWbPtr=IOldWbPtr(flag=True, value=15),
            rawFull=True,
        )
    )

    event_valids = [
        *(port._valid for port in bundle.store_addr_ports),
        *(port._valid for port in bundle.store_data_ports),
        bundle.io._tlb_hint_resp._valid,
        bundle.io._tl_d_channel._valid,
    ]
    assert all(pin.writes == [True, False] for pin in event_valids)
    assert all(pin.value is False for pin in event_valids)
    assert bundle.io._sqEmpty.value is True
    assert bundle.io._rarFull.value is True
    assert bundle.io._rawFull.value is True
    assert bundle.io._stDataReadySqPtr._flag.value is True
    assert bundle.io._stDataReadySqPtr._value.value == 9
    assert bundle.io._stAddrReadySqPtr._flag.value is False
    assert bundle.io._stAddrReadySqPtr._value.value == 7
    assert bundle.io._ldWbPtr._flag.value is True
    assert bundle.io._ldWbPtr._value.value == 15
    assert all(
        getattr(bundle.io._stAddrReadyVec, f"_{index}").value is True
        for index in range(56)
    )
    assert all(
        getattr(bundle.io._stDataReadyVec, f"_{index}").value is False
        for index in range(56)
    )
    assert bundle.step_calls == [1, 1]
    assert result is bundle.LoadQueueReplay
