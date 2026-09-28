# microgrid-ems 开发规则（Python / Windows 仿真版）

版本：baseline-pywin-0.2，2026-09-24。用户已明确将方案改为所有程序在 Python/Windows 下模拟运行；本规则取代旧技术栈约束。业务控制安全链和分阶段学习方法继续有效。

## 必读顺序

1. [当前阶段](docs/roadmap/CURRENT_STAGE.md)
2. [产品边界](docs/product/EMS_V1_SCOPE.md)
3. [架构](ARCHITECTURE.md)
4. [领域模型](docs/architecture/DOMAIN_MODEL.md)
5. [接口](docs/architecture/INTERFACES.md)
6. [路线图](docs/roadmap/ROADMAP.md)、[M01](docs/milestones/M01_KERNEL.md)

产品范围、模型、接口分别是对应事实来源；实施授权由用户指令及当前阶段共同限定。不得恢复旧技术栈或悄悄扩大业务范围。

## 技术路线

- 全部项目程序使用 Python，Windows 本机运行，M01 基于 Python 3.12+ 标准库。
- 一个主运行程序，内部按职责模块化；后续预测/优化可用 Python 子进程隔离，兼容 Windows spawn。
- M01.5 开始实现 Python 进程内事件总线；M01.7 用 SQLite 本地文件保存历史。
- 后续界面由 Python 实现，默认规划 Tkinter；进入 M02 再验证完整 Tcl/Tk 环境。
- 不要求外部数据库服务器、消息服务器、容器或Linux子系统。
- 仅仿真设备和MGCC/PLC；不连接真实设备，不宣称现场/商用验收通过。
- 只读状态不能假称有效遥测；后续 GUI 只能经 Application Facade 调用业务，不直接读写存储或设备。

## 开发门禁

- 当前仅 M0.1.1。用户授权修改方案和本步实现，不等于授权 M0.1.2。
- 流程：阅读→解释→实现→测试→Demo→证据→人工验收。
- 日常实现和调试按已授权范围自主完成；测试失败先修复，未运行如实记录。
- 测试和Demo通过后 READY_FOR_REVIEW，用户确认后才能 ACCEPTED/推进。
- 不自动提交、推送、打标签或改 GitHub 仓库。
- 历史文件和旧ZIP仅用于溯源；使用当前 Python/Windows 文档开发。

## 领域与控制规则

- 驱动隔离设备差异；业务不得直接访问协议地址。
- Controller 消费同周期不可变 SystemSnapshot，仅输出 ControlProposal。
- 所有控制意图必须经过 Proposal→Arbiter→Interlock→Command Manager→Gateway，即使目标为模拟设备。
- 预测/优化不能直接控制设备或自行激活计划；硬约束不能被人工或经济目标覆盖。
- 并离网/黑启动快速过程由 Python MGCC 模拟器表示；EMS仍只管理申请、约束、监视和记录。
- PCC正购电，ESS正放电，PV正发电，Load/EV正消耗；Load不含EV。
- P_PCC = P_Load + P_EV - P_PV - P_ESS。
- UTC存储与传输，站点时区显示；kW/kvar/kWh/V/A/Hz/%/°C保持统一。
- 0不是缺失值，旧值保留采样时间；质量和时间不可省略。
- 五个冻结语义对象：TelemetrySample、SystemSnapshot、ControlProposal、Command、SchedulePlan。
- 业务消息/命令须去重；重启禁止盲目重放危险模拟动作。
- 数据库慢/算法失败不允许无限阻塞控制周期；队列有界，降级明确。

## 验证与教学

- 默认 `python -m unittest discover -s tests -v`；Demo入口见里程碑，退出非零表示失败。
- 新规则覆盖正常、异常、恢复；测试只用临时目录和自建子进程。
- 报告改了什么、为什么、怎么运行、如何证明有效，并维护学习日志。
- 状态文件是最后一次记录；必须结合实例锁与新鲜度判断活跃，不能把陈旧RUNNING标记当健康。
- runtime/、虚拟环境、缓存不入库；配置、样例、文档同步更新。
