# 当前开发阶段（唯一推进入口）

版本：baseline-0.1；更新日期：2026-09-23。

## 1. 当前状态

| 项目 | 当前值 |
|---|---|
| 产品目标 | EMS V1.0，当前增量 V0.1 Kernel |
| 当前里程碑 | M01_KERNEL |
| 当前子阶段 | M0.1.1 仓库脚手架 |
| 状态 | NOT_STARTED |
| 实施情况 | 只有 8 个文档文件；无业务代码、无运行结果、无 Git 标签 |
| 下一动作 | 阅读基线并提出 M0.1.1 实施方案；收到实施指令后只做该步 |
| 人工验收 | 未进行 |
| 已获后续授权 | 无 |

## 2. 本步允许范围

M0.1.1：README、Go 单 module、必要服务健康入口、配置与 JSON 日志、Compose 基础、NATS/TimescaleDB 开发依赖、环境示例、测试入口和学习日志。
具体文件与验证见 [M01_KERNEL.md](../milestones/M01_KERNEL.md)。依赖版本在此步锁定并记录。

本里程碑最终允许：领域对象、Simulator、Gateway、NATS 遥测、Scheduler/Snapshot、基础 Historian、集成故障测试、Demo。**这是 M01 的最终范围，不是一次性授权实现九步。**

当前禁止提前实现：M0.1.2～9 的业务行为、真实 Modbus/OPC UA、SCADA UI、Alarm 引擎、控制器、Arbiter、Interlock、设备命令、预测、优化、MGCC、黑启动、生产用户系统。字段规范可以阅读，不代表可以提前实现。
M01 需要的只读诊断和仿真场景设置不属于生产控制接口。

## 3. 子阶段账本

| 子阶段 | 内容 | 状态 | 证据/用户验收 |
|---|---|---|---|
| M0.1.1 | 脚手架 | NOT_STARTED | 无 |
| M0.1.2 | 核心领域对象与契约 | NOT_STARTED | 无 |
| M0.1.3 | Simulator | NOT_STARTED | 无 |
| M0.1.4 | Gateway | NOT_STARTED | 无 |
| M0.1.5 | NATS Telemetry | NOT_STARTED | 无 |
| M0.1.6 | Snapshot | NOT_STARTED | 无 |
| M0.1.7 | Historian | NOT_STARTED | 无 |
| M0.1.8 | Integration / Fault Tests | NOT_STARTED | 无 |
| M0.1.9 | Demo / Review | NOT_STARTED | 无 |

## 4. 每步结束如何更新

实施者填写当前步状态、变更摘要、验证命令/退出状态/证据路径、未运行项与原因、已知限制，测试和 Demo 全部满足后标 READY_FOR_REVIEW。用户确认后记 ACCEPTED，并填写验收人/日期/反馈；只有用户明确要求推进时切换下一步。
不因工具运行时间长、需要日常调试或一次失败就请求人工验收；先完成已授权的修复和验证。

验收记录模板（当前为空）：

```text
步骤：
代码版本/配置版本：
变化和设计原因：
测试命令、退出状态、结果路径：
Demo 输入和实测输出：
未验证项、风险与阻断：
用户确认内容/日期：
下一步授权范围：
```

## 5. 可直接复制的启动任务

```text
阅读 AGENTS.md、ARCHITECTURE.md、docs/product/EMS_V1_SCOPE.md、
docs/architecture/DOMAIN_MODEL.md、docs/architecture/INTERFACES.md、
docs/roadmap/CURRENT_STAGE.md、docs/milestones/M01_KERNEL.md。
检查仓库现状。现在只规划 M0.1.1，不编写业务代码。
用中文说明：将创建哪些文件、各组件职责、配置与启动顺序、
依赖版本选择、测试命令、Demo、验收方法及尚需澄清的实际阻断。
不要实现后续步骤。说明计划后等待我的实施指令。
```

方案理解后，可发：

```text
实施 M0.1.1，仅限其规定范围。完成必要测试和健康检查 Demo，
记录实际结果并更新 CURRENT_STAGE.md 为 READY_FOR_REVIEW。
解释改了什么、为什么、如何运行、如何证明有效。
不要自动进入 M0.1.2，不要自动提交或打标签。
```

这些提示是未来用户任务模板，不表示本次生成文档时应执行开发。
