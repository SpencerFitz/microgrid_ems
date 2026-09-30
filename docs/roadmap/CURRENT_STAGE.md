# 当前开发阶段

更新：2026-09-28；全Python / Windows本机仿真，Python3.12+标准库。

| 项目 | 当前值 |
|---|---|
| 里程碑 | M01_KERNEL |
| 当前子阶段 | M0.1.3 Simulator |
| 状态 | READY_FOR_REVIEW |
| 实施情况 | 场景/Clock→理想物理模型→原始测量；适配器与通信故障；CLI Demo/测试 |
| 人工验收 | M0.1.3待用户本机验证与确认 |
| 下一动作 | 运行测试、demo-simulator和自选放电场景，理解功率/能量/断线语义 |
| GitHub | 本轮只读核对，未修改、提交或推送 |

用户确认M0.1.2：“本机验证通过了，github也更新了，现在继续开发”。据此将M0.1.2记ACCEPTED并实施M0.1.3，未推定用户具体运行的命令。

| 子阶段 | 状态 | 证据 |
|---|---|---|
| M0.1.1 脚手架 | ACCEPTED | 用户此前确认；保留原验证记录 |
| M0.1.2 领域契约 | ACCEPTED | 用户本次确认；保留原验证记录 |
| M0.1.3 Simulator | READY_FOR_REVIEW | [实际验证](../learning/M0.1.3_VALIDATION.md) |
| M0.1.4 Gateway | NOT_STARTED | 本步验收后进入 |
| M0.1.5 Python EventBus | NOT_STARTED | 无 |
| M0.1.6 Snapshot 构建器 | NOT_STARTED | 当前仅数据类型 |
| M0.1.7 SQLite Historian | NOT_STARTED | 无 |
| M0.1.8 Integration/Fault | NOT_STARTED | 无 |
| M0.1.9 Demo/Review | NOT_STARTED | 无 |

当前允许模拟器及其配置、原始读取适配器、测试和学习文档。禁止提前实现Gateway轮询/质量老化/重连、总线、快照构建器、历史采集、GUI、控制/预测/优化。满空饱和属于理想物理模型，set_scenario仅是实验注入，不是控制命令。

## 本机验收

```powershell
python ems.py doctor
python -m unittest discover -s tests -v
python ems.py demo-simulator
python ems.py simulate --scenario configs/scenarios/discharge.json --seconds 3600
```

预期测试全部OK、Demo PASS、自选放电场景SOC=50%、PCC=50kW。详细说明见 [学习指南](../learning/M0.1.3_LEARNING.md)。测试通过不代替用户验收；确认后再进入M0.1.4。
