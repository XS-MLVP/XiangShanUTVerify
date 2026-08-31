# Decode 单元验证

## 测试目标

解码单元的功能是对输入的指令进行解码，最终转换为后端可识别的微指令。输出的指令有两种类型：16位的压缩指令（RVC） 和 32位的普通指令（RVI）。本单元测试检查 Decode 模块能否识别非法指令，并验证输出反压期间的 ready/valid 协议及复杂指令的多 uop 排空行为。

测试基本流程为：

1. 用固定编码验证合法/非法结果、反压和复杂指令排空
1. 随机生成指令并输入 DUT，检查每条指令的握手、传输顺序和完成次数
1. 用 disasm 提供随机指令的辅助诊断信息，但不把缺少架构状态的语法解析当作异常位 Golden
1. 对固定用例的异常位和多 uop 属性做严格比较


## 测试环境 Env

本测试基于disasm对 DUT 进行了封装。输入的DUT模块为 `ut.predecode`,`ut.decodestage` 和 `ut.rvcexpander` 三个模块。

- **ut.rvcexpander**
对输入的指令进行展开，输入支持16位压缩指令和普通32指令。

- **ut.predecode**
预解码阶段，[TBD]

- **ut.decodestage**
提供 6 路输入和 6 路输出。当前 RTL 以 `io_out_0_ready` 计算全局输出容量，因此 Env 将 6 路 output ready 作为一个整体驱动，不支持部分 lane ready。


依赖：
- disasm 反汇编工具 （该工具位置为 tools.disasm）

## 功能检查

本测试需要进行的功能点和检查点（checkpoint/coverpoint）如下：

|序号|所属模块|功能描述|检查点描述|检查标识|检查项|
|-|-|-|-|-|-|
|1|rvcexpander|压缩指令展开|检查是否能判断非法指令|RVC_EXPAND_RET|ERROR：stat接口`ilegal==False`<br>SUCCE：stat接口`ilegal==True`|
|2|||检查是否能展开所有正常指令，<br>发现所有非法指令|RVC_EXPAND_ALL_16B|RANGE[`start~end`]: 16位压缩指令共有 2^16种可能，<br>通过不同的start-end指定输入指令的<br>遍历范围，遍历该范围内的输入是否<br>是合法或非法指令（start，end由用例指定）|
|3||常规指令展开|遍历所有32bit指令，<br>检查是否合法|RVC_EXPAND_ALL_32B|检查项同上|
|4|||随机生成N条32位指令，<br>检查是否合法|RVC_EXPAND_RANDOM_32B|POS_{i}：为了保证随机指令足够多，判断随机<br>生成的指令中第i位是否为1(0 <= i < 32)|
|5|decodestage|输出反压|检查全阻塞期间无握手且 payload 保持，恢复后仅传输一次|DECODE_OUTPUT_READY|ALL_STALLED、ALL_READY|
|6|decodestage|复杂指令多 uop 解码|检查输入结束后继续运行直至最后一个 uop 握手|DECODE_COMPLEX_DRAIN|COMPLEX_LAST_UOP_FIRED|
|7|decodestage|确定性非法指令|检查固定非法编码仅完成一次且置异常位|DECODE_KNOWN_ILLEGAL|KNOWN_ILLEGAL_COMPLETED|


## Env提供的验证接口(API)

为了让测试用例更通用，具有继承性，本Env提供的接口**对外屏蔽了电路引脚和时序，且接口保持稳定**：

#### 1. rvcexpander

```python

# 封装主类
class RVCExpander
    # 对指令指令 instr 进行展开
    # 参数：
    #    instr 输入指令
    # 返回：
    #    value 扩展结果
    #    ilegel 是否非法指令
    def expand(self, instr) -> (value, ilegal):
    # 获取 expander的状态
    # 返回：
    #    {
    #     instr：当前的输入指令
    #     decode: 展开结果
    #     ilegal：输入是否为非法指令
    #     }
    def stat(self) -> dict(instr => int, decode=>int, ilegal => bool):

# 用于自动创建RVCExpander的fixture
@pytest.fixture()
def rvc_expander(request) -> RVCExpander:
```

#### 2. decodestage

```python
# 同步驱动 6 路 output ready；不允许部分 lane ready
decoder.Set_output_ready(ready)

# 驱动并采样一个周期，在上升沿前返回 ready/valid 握手快照
cycle = decoder.Run_cycle(insts=(), output_ready=True)

# 按输入握手推进，并在所有指令的 lastUop 握手后结束
success = decode_run(decoder, inst_list, need_log_file=False)

# 调试或协议检查可请求统计信息
success, stats = decode_run(
    decoder, inst_list, need_log_file=False, return_stats=True
)
```

`decode_run` 会在输入全部接收后清空 input valid，继续运行直至所有架构指令的 `lastUop` 完成；如果超过按输入数量计算的超时上限则失败。默认返回值仍为布尔值，以兼容已有用例。

随机指令用例中的 syntax-only disasm 没有当前扩展、CSR、VType 状态，也可能不了解 DUT 的自定义编码，因此只用于辅助诊断；随机结果严格检查指令传输与顺序，不把 disasm 当作异常位 Golden。异常位由固定合法序列和固定非法编码用例做严格比较。固定的复杂指令排空用例会先执行 `vsetvli`，并逐条检查多 uop 的 `firstUop`、`lastUop` 和 `numUops`。

## 用例说明

本测试创建的用例如下（以下内容建议以funciton doc的形式写入case的具体实现中，然后以link的形式做链接）:

#### 1. test_rv_decode.test_rvc_expand_16bit_smoke 压缩指令展开冒烟测试 

|步骤|操作内容|预期结果|覆盖功能点|
|-|-|-|-|
|1|选择一条特定压缩指令||[RVC_EXPAND_RET]()|
|2|通过RVCExpander.expand接口获取解码结果||||
||通过disasm获取反汇编结果|||
|3|检查两边的结果是否一致|所有指令是否非法指令判断结果一致|[.SUCCE]()，[.ERROR]()|


#### 2. test_rv_decode.test_rvc_expand_32bit_smoke 普通指令展开冒烟测试 
|步骤|操作内容|预期结果|覆盖功能点|
|-|-|-|-|
|1|选择一条特定32位指令||[RVC_EXPAND_RET]()|
|2|通过RVCExpander.expand接口获取解码结果||||
||通过disasm获取反汇编结果|||
|3|检查两边的结果是否一致|所有指令是否非法指令判断结果一致|[.SUCCE]()，[.ERROR]()|


#### 3.test_rv_decode.test_rvc_expand_16bit_full 对所有压缩指令进行展开检查
|步骤|操作内容|预期结果|覆盖功能点|
|-|-|-|-|
|1|将16位指令的取值范围拆分为N个分段|-|[1->RVC_EXPAND_RET]()<br> [2->RVC_EXPAND_16B_RANGE]()|
|2|遍历每个分段中的所有值，作为压缩指令|-|[2.RANGE]()|
|3|通过RVCExpander.expand接口获取解码结果|-|-|
||通过disasm获取反汇编结果|||
|4|检查两边的结果是否一致|所有指令是否非法指令判断结果一致|[1.SUCCE]()，[1.ERROR]()|

#### 4.test_rv_decode.test_rvc_expand_32bit_full 对所有压缩指令进行展开检查
同上，只是指令格式不一样

#### 5.test_rv_decode.test_rvc_expand_32bit_randomN 随机对32位指令进行展开检查
|步骤|操作内容|预期结果|覆盖功能点|
|-|-|-|-|
|1|随机运行K次，每次随机生成N个32位指令|-|[1->RVC_EXPAND_RET]()<br>[2->RVC_EXPAND_RANDOM_32B]()|
|2|遍历N个指令|-|[2.POS_i(0-32)]()|
|3|通过RVCExpander.expand接口获取解码结果|-|-|
||通过disasm获取反汇编结果|||
|4|检查两边的结果是否一致|所有指令是否非法指令判断结果一致|[1.SUCCE]()，[1.ERROR](), |


## 目录结构

```bash
decode
├── README.md                 # 说明文件
├── __init__.py               # python模块文件
├── env                       # 环境模块
│   └── __init__.py
│   └── decode_wrapper.py
└── test_rv_decode.py         # 测试用例
```

## 检查列表

- [ ] 本文档符合指定[模板]()要求
- [ ] Env提供的API不包含任何DUT引脚和时序信息
- [ ] Env的API保持稳定（共有[ X ]个）
- [ ] Env中对所支持的RTL版本（支持版本[ X ]）进行了检查
- [ ] 功能点（共有[ X ]个）与[设计文档]()一致
- [ ] 检查点（共有[ X ]个）覆盖所有功能点
- [ ] 检查点的输入不依赖任何DUT引脚，仅依赖Env的标准API
- [ ] 所有测试用例（共有[ X ]个）都对功能检查点进行了反标
- [ ] 所有测试用例都是通过 assert 进行的结果判断
- [ ] 所有DUT或对应wrapper都是通过fixture创建
- [ ] 在上述fixture中对RTL版本进行了检查
- [ ] 创建DUT或对应wrapper的fixture进行了功能和代码行覆盖率统计
- [ ] 设置代码行覆盖率时对过滤需求进行了检查
