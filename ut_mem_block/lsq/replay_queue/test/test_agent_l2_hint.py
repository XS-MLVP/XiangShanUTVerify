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
from ..util.dataclass import L2Hint


class RecordingPin:
    def __init__(self):
        self.writes = []

    @property
    def value(self):
        return self.writes[-1] if self.writes else None

    @value.setter
    def value(self, new_value):
        self.writes.append(new_value)


class RecordingBundle:
    def __init__(self, scheduled):
        self.valid_pin = RecordingPin()
        self.source_id_pin = RecordingPin()
        self.is_keyword_pin = RecordingPin()
        hint_bits = SimpleNamespace(
            _sourceId=self.source_id_pin,
            _isKeyword=self.is_keyword_pin,
        )
        self.io = SimpleNamespace(
            _l2_hint=SimpleNamespace(_valid=self.valid_pin, _bits=hint_bits)
        )
        self.LoadQueueReplay = SimpleNamespace(_scheduled=scheduled)
        self.step_calls = []

    async def step(self, cycles):
        self.step_calls.append(cycles)


def test_replay_drives_l2_hint_payload_and_pulses_valid():
    scheduled = object()
    bundle = RecordingBundle(scheduled)
    source_id_pin = bundle.source_id_pin
    is_keyword_pin = bundle.is_keyword_pin
    agent = object.__new__(LoadQueueReplayAgent)
    agent.bundle = bundle
    l2_hint = L2Hint(valid=True, sourceId=7, isKeyword=False)

    replay = LoadQueueReplayAgent.replay.__original_func__
    result = asyncio.run(replay(agent, l2_hint))

    assert bundle.valid_pin.writes == [True, False]
    assert bundle.valid_pin.value is False
    assert bundle.io._l2_hint._bits._sourceId is source_id_pin
    assert bundle.io._l2_hint._bits._isKeyword is is_keyword_pin
    assert source_id_pin.writes == [7]
    assert is_keyword_pin.writes == [False]
    assert bundle.step_calls == [1, 3]
    assert result is scheduled
