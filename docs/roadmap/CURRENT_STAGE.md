# 当前开发阶段

更新：2026-09-28；全 Python / Windows 本机仿真，Python 3.12+ 标准库。

| 项目 | 当前值 |
|---|---|
| 当前里程碑 | M01_KERNEL |
| 当前子阶段 | M0.1.2 核心领域对象与契约 |
| 状态 | READY_FOR_REVIEW |
| 实施情况 | 不可变领域对象、严格解析/校验、JSON Schema、静态样例、测试和 CLI Demo |
| 人工验收 | M0.1.2 尚待用户确认 |
| 下一动作 | 用户本机运行测试和 demo-contracts，理解质量与时间语义后验收 |
| GitHub | 本轮只读取核对，未修改、提交或推送 |

用户于2026-09-28反馈“在本机上验证成功了，也更新到github上了，现在我们继续开发”，据此接受 M0.1.1，并授权下一步 M0.1.2。未推定用户运行的具体命令。

| 子阶段 | 状态 | 证据 |
|---|---|---|
| M0.1.1 脚手架 | ACCEPTED | 用户上述确认；M0.1.1_VALIDATION.md 保留原测试记录 |
| M0.1.2 核心领域对象 | READY_FOR_REVIEW | [验证记录](../learning/M0.1.2_VALIDATION.md) |
| M0.1.3 Simulator | NOT_STARTED | 等待本步验收 |
| M0.1.4 Gateway | NOT_STARTED | 无 |
| M0.1.5 Python EventBus | NOT_STARTED | 无 |
| M0.1.6 Snapshot 构建器 | NOT_STARTED | 当前仅数据类型 |
| M0.1.7 SQLite Historian | NOT_STARTED | 无 |
| M0.1.8 Integration/Fault | NOT_STARTED | 无 |
| M0.1.9 Demo/Review | NOT_STARTED | 无 |

当前允许 M0.1.2 契约及其测试/Demo/文档，禁止提前实现物理仿真、轮询、总线、快照构建器、历史采集、GUI、控制/预测/优化。静态样例不是实时测量。

## 验收操作

```text
python ems.py doctor
python -m unittest discover -s tests -v
python ems.py demo-contracts
```

步骤与预期见 [学习指南](../learning/M0.1.2_LEARNING.md)。自动验证通过不代替用户验收；本步确认后才能进入 M0.1.3。
