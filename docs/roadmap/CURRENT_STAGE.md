# 当前开发阶段

版本 baseline-pywin-0.2；2026-09-24。

| 项目 | 当前值 |
|---|---|
| 技术路线 | 全Python / Windows本机仿真，标准库启动 |
| 当前里程碑 | M01_KERNEL |
| 当前子阶段 | M0.1.1 仓库脚手架 |
| 状态 | READY_FOR_REVIEW |
| 实施情况 | Python脚手架、测试、CLI Demo已实际运行通过；无遥测业务 |
| 人工验收 | 未进行 |
| 下一动作 | 用户运行/理解本步并验收；未经确认不得进入M0.1.2 |
| GitHub | 未修改、未提交、未推送 |

用户已授权实施M0.1.1，并明确要求将所有程序改为Python/Windows仿真；本版据此修改技术约束。原工具链阻断已通过新技术路线解除；未来GUI的Tcl缺失属于M02准备项，不是M01依赖。

## 允许与禁止

允许配置、日志、启动/停止、Windows实例锁、健康记录、SQLite启动元数据和测试/Demo。禁止提前做领域Tag/Telemetry、仿真物理模型、EventBus、Historian、GUI、控制/预测/优化。四组件名称只代表bootstrap注册，不表示模块业务实现。

| 子阶段 | 状态 | 证据 |
|---|---|---|
| M0.1.1 脚手架 | READY_FOR_REVIEW | [验证记录](../learning/M0.1.1_VALIDATION.md) |
| M0.1.2 核心领域对象 | NOT_STARTED | 无 |
| M0.1.3 Simulator | NOT_STARTED | 无 |
| M0.1.4 Gateway | NOT_STARTED | 无 |
| M0.1.5 Python EventBus | NOT_STARTED | 无 |
| M0.1.6 Snapshot | NOT_STARTED | 无 |
| M0.1.7 SQLite Historian | NOT_STARTED | 无 |
| M0.1.8 Integration/Fault | NOT_STARTED | 无 |
| M0.1.9 Demo/Review | NOT_STARTED | 无 |

## 验收操作

从README准备Python，然后在仓库根目录运行：

```text
python ems.py doctor
python ems.py validate
python -m unittest discover -s tests -v
python ems.py demo
python ems.py status
```

理解配置→校验→启动→心跳/日志→停止→重启保留元数据的链路，再确认本步。此时还不应看到PV/SOC业务数据。
验收记录目前为空：验收人/日期/反馈/后续授权均待用户填写；测试通过不替代用户验收。
