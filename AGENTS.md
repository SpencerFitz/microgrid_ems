# microgrid-ems 开发规则

本项目面向单个工商业园区光储充微电网。使用中文解释设计和验收结果。
当前交付是文档基线，不代表任何软件功能已实现。

## 开始工作前

依次阅读：
1. [当前阶段](docs/roadmap/CURRENT_STAGE.md)
2. [产品边界](docs/product/EMS_V1_SCOPE.md)
3. [总体架构](ARCHITECTURE.md)
4. [领域模型](docs/architecture/DOMAIN_MODEL.md)
5. [服务接口](docs/architecture/INTERFACES.md)
6. [路线图](docs/roadmap/ROADMAP.md)及当前里程碑说明。

产品范围以 EMS_V1_SCOPE.md 为准，字段语义以 DOMAIN_MODEL.md 为准，传输约定以 INTERFACES.md 为准，实施授权以 CURRENT_STAGE.md 和用户明确指令为准。发现冲突先说明具体冲突；不得暗中改动冻结语义。

## 阶段纪律

- 只实施当前获准的子阶段；默认从 M0.1.1 开始。
- 每步遵循：阅读、解释方案、实现、测试、Demo、说明证据、人工验收。
- 首次任务若要求“只规划”，不得编写业务代码。
- 收到明确实施指令后完成该步全部必要工作，不对日常实现选择反复请求确认。
- 测试通过后标记 READY_FOR_REVIEW；用户确认后才能标记 ACCEPTED 并推进。
- 不擅自把当前步骤改成下一步，不擅自实现后续里程碑。
- 用户明确扩大授权时，先同步阶段范围和验收内容，再按新授权执行。
- 失败测试必须修复或如实记录 BLOCKED，不能伪称通过。
- 未运行的命令写“未运行”及原因；不得以文档示例冒充执行结果。
- 不默认提交、推送、打标签或连接真实设备；按用户对应授权操作。

## 范围与架构

- 不增加 VPP、多园区调度、电力市场、柴油机、风机、继电保护、逆变器内环或硬实时控制。
- Go 核心、Python 算法、Vue 3/TypeScript 前端；Monorepo，模块化核心与独立算法服务。
- 驱动负责协议、寄存器、比例和单位转换；业务不得直接读写寄存器。
- Controller 只消费同一周期的不可变 SystemSnapshot，只输出 ControlProposal。
- 控制路径固定为 Proposal → Arbiter → Interlock → Command Manager → Gateway。
- 人工控制、计划调度和北向控制也必须走上述路径，不得绕过安全约束。
- 预测和优化服务不能直接下发设备命令，也不能自行激活计划。
- Interlock、Arbiter、Command Manager 是 ems-core 内部模块，不拆成额外微服务。
- MGCC/PLC 承担快速闭环、同期、断路器动作和 V/f 建立；EMS 管理申请、约束与监视。
- 前端仅访问 api-server；不得直接访问数据库、NATS 或设备。
- 服务拥有自己的表和写权限；不得把数据库轮询当事件总线。
- 外部算法、历史数据库异常不得阻塞基础控制周期。

## 全局语义

- PCC 正值购电、负值售电；ESS 正值放电、负值充电。
- PV 正值发电；Load、EV 正值用电。Load 不包含 EV，禁止重复计量。
- P_PCC = P_Load + P_EV - P_PV - P_ESS。
- 时间持久化为 UTC，对外 RFC3339/ISO8601，显示使用 Site.timezone。
- 功率 kW、无功 kvar、电量 kWh、电压 V、电流 A、频率 Hz、SOC %、温度 °C。
- 遥测必须有时间戳和质量；0 不是缺失值，OFFLINE 不能转换成 0。
- 消息、命令、计划必须可追踪；重发不得生成重复物理动作。
- 重启不得自动重放危险命令；通信恢复不等于恢复控制授权。
- 五个冻结核心对象：TelemetrySample、SystemSnapshot、ControlProposal、Command、SchedulePlan。
- 新字段优先可选兼容扩展；更改单位、符号、字段含义或状态机必须记录架构决定和迁移方案。

## 验证和教学交付

- 领域规则用单元测试，服务边界用集成测试，异常行为用故障注入验证。
- 先 Simulator/SIL，再设备联调；未到对应阶段不得使用真实设备进行控制。
- M01 的命令、测试、演示标准见 docs/milestones/M01_KERNEL.md。
- 每次提交结果说明：改了什么、为什么、如何运行、如何证明有效。
- 给出修改文件、准确验证命令、退出状态、实际输出摘要、已知限制。
- 提供一条可追踪的数据链，并解释本步新增概念。
- 实施时维护 docs/learning/LEARNING_LOG.md；该文件由 M0.1.1 创建。
- 文档、配置示例、契约和实现同步更新；依赖版本在实施时锁定。
- 禁止把密码、证书私钥、现场凭据提交到仓库。

## 文档入口

M01：[内核里程碑](docs/milestones/M01_KERNEL.md)。
后续里程碑文件尚未创建，其边界暂以 ROADMAP.md 为准。
本仓库采用 AGENTS.md 保存简明工作规则；机制参考 [OpenAI 官方说明](https://learn.chatgpt.com/docs/agent-configuration/agents-md)。
