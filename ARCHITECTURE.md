# EMS V1.0 总体架构

文档版本：baseline-0.1；日期：2026-09-23。适用于全部 8 个初版文件。

## 1. 基线来源与补充约定

来源为“智能微电网EMS方案”对话中冻结的产品范围、后续总体设计及分阶段学习方法，原会话 ID 为 `6ab36b73-46f4-83ee-9307-396973182361`。
已读取产品范围与学习方法；总体设计工具返回内容在配置体系部分截断。本文不声称还原未读取部分；涉及具体运行、重试、数据一致性和工程目录的新增细节按下列“补充约定”处理。

冻结内容：单园区光储充、Go/Python/Vue 技术栈、六个主要后台进程、统一 Tag/Snapshot、完整控制安全链、EMS/MGCC 分工与 V1.0 产品目标。

本次补充约定（不扩大产品范围）：
- D01：保留产品版本 V0.1～V1.0 与 M01～M09 文件编号；PCC 作为 M03-B 独立学习验收点，商业发布为 G10 门禁。
- D02：M01 采用 JSON 消息、Go 单 module、独立 Simulator 进程和 HTTP 仿真适配器；protobuf/gRPC 仅预留目录。
- D03：统一对象 ID、质量时间、消息封装、幂等和存储拥有者；详见领域模型及接口文档。
- D04：遥测分别供 Snapshot 和 Historian 消费，Historian 保存原始遥测；不把 Snapshot 当唯一原始数据来源。
- D05：M01 每个子阶段单独验收；初始状态为 M0.1.1 / NOT_STARTED，未实现任何业务。
- D06：M01 仿真默认 1 s 采样、3 s STALE、5 s OFFLINE，仅用于可重复实验；现场超时、容量和动态指标必须配置。
- D07：M01 本地只读诊断使用进程内部 HTTP 端口；不是提前实现生产 api-server。

这些约定构成可实施的初版基线；若后续取得完整原文并出现冲突，应提出文档变更而非静默覆盖。

## 2. 技术栈与部署

| 层 | 选择 | 约束 |
|---|---|---|
| 核心与接入 | Go | ems-core、device-gateway、data-service、api-server |
| 算法 | Python | forecast-service、optimization-service 独立运行 |
| 界面 | Vue 3 + TypeScript | 只访问 api-server |
| 关系/时序数据 | PostgreSQL + TimescaleDB 扩展 | 可使用一个数据库实例，按服务区分 schema/角色 |
| 事件总线 | NATS JetStream | 至少一次投递；消费端负责幂等 |
| 缓存 | ems-core 内存；Redis 可选 | M01 不引入 Redis |
| 部署 | Linux + Docker Compose | 开发可用 Windows/WSL2，验收环境记录实际版本 |
| 可观测性 | JSON 日志、Prometheus、Grafana | M01 先日志、health/ready 和必要计数 |
| 北向 | REST、WebSocket、MQTT | 用户与站点授权由 api-server 执行 |
| 南向 | Modbus TCP/RTU、OPC UA | M01 仅 Simulator；IEC104 扩展，IEC61850 后续版本 |

依赖具体版本在 M0.1.1 选择受支持版本并固定，不在文档中编造“最新版本”。

```text
Web UI / 第三方
       │ HTTPS REST / WebSocket / MQTT
       ▼
api-server ──► ems-core ──REST──► forecast-service / optimization-service
                  │                         │
                  │ 计划校验、批准、激活 ◄───┘
                  │
Simulator/设备 ◄─► device-gateway ◄──命令── ems-core
                       │                       ▲
                       └──遥测──► NATS ────────┤
                                   └──► data-service ──► TimescaleDB/PostgreSQL
```

图中的命令必须经过下节全部模块；优化器没有到 Gateway 的写通路。

## 3. 服务职责、数据所有权

| 进程 | 内部模块与输入输出 | 拥有的数据/权限 | 首次进入 |
|---|---|---|---|
| device-gateway | 连接管理、轮询、协议、厂家驱动、质量、命令执行；设备→Telemetry，Command→回执 | 设备连接运行态；M03 起本地持久化命令去重记录；不拥有策略 | M01 |
| ems-core | Scheduler、Snapshot、State、Control、Arbiter、Interlock、Command、Dispatch、Mode、Fallback | commands/command_events、plans/plan_points、operating_mode_events、策略与联锁运行态 | M01，仅 Scheduler/Snapshot |
| data-service | Historian、Alarm、SOE、Audit、Report、基础 Carbon | telemetry_raw/聚合、alarms、audit_events、报告；仅此服务写历史遥测 | M01，仅 Historian |
| forecast-service | 特征、模型注册、预测、评估 | forecasts/forecast_points、预测 jobs | M04 |
| optimization-service | 建模、求解、校验、导出候选计划 | optimization_jobs、求解诊断；候选计划提交 core 后由 core 持久化 | M05 |
| api-server | REST/WS、JWT/RBAC、工程配置、用户管理、MQTT 北向适配 | sites/devices/tags/templates、users/roles、tariffs/config revisions | M02 起；M09 完整工程化 |

M01 工程配置来自版本化 YAML，按配置版本加载；后续 api-server 管理配置入库并发布变更事件，其他服务接收版本化配置。其他服务不得直接改写配置表。
跨服务读取走 API/消息；不用共享 ORM 模型替代契约。数据库不可用时，Snapshot 继续更新；Historian 保留未确认消息，恢复后补写。

## 4. 核心数据和控制流

### 数据流

```text
设备物理量 → 协议读取 → 驱动标准化 → TelemetrySample → NATS
                                                    ├→ Latest Cache → Snapshot(k)
                                                    └→ Historian → 历史查询
Snapshot(k) → 各 Controller（同一不可变对象）
```

Snapshot 是某一截止时刻的过程映像，并不宣称各设备同时采样。保留每个点的原始采样时间与有效质量，过期与缺失数据不伪装成有效数值。
PCC 实测值与功率平衡计算值分别保留；现场不能用公式值覆盖电表值。仿真 PCC 由 Simulator 独立输出，测试再用公式检查。

### 完整控制流（M03 起）

```text
预测 → 优化候选计划 → core 校验/批准/激活 → Dispatch ─┐
Snapshot → Rule-Based Controller ────────────────────┤
用户意图 → 身份/权限/原因检查 ─────────────────────────┤
                                                     ▼
ControlProposal[] → Arbiter → SetpointDecision → Interlock
             → Command Manager → NATS → Gateway → MGCC/设备
                    ▲                        │
                    └──接受/执行回执/遥测校验──┘
```

Safety 1000、Device Limit 900、Manual Emergency 800、MGCC Constraint 700、PCC Constraint 600、Demand 500、Intraday 400、Day-Ahead 300、Economic 200、Default 100。
硬约束取交集，不能被高优先级人工目标覆盖；优先级用于选择可行目标。交集为空则拒绝并进入配置的安全降级，不输出随意夹紧值。
命令接受不等于设备执行成功；Command Manager 根据回执及有效遥测核验结果。

## 5. EMS 与 MGCC

| EMS | MGCC/PLC/保护设备 |
|---|---|
| 1 s 监控、1～10 s 协调、分钟级滚动、15 min～小时级计划 | 毫秒/亚秒级闭环与保护 |
| 模式申请、SOC/资源检查、P/Q/V/f 参考值、状态监视 | 断路器执行、同期、V/f 建立、并离网瞬态 |
| 负荷等级与 LoadSheddingRequest | 快速减载执行及独立保护 |
| 黑启动前置条件、流程管理、失败记录 | PCS 启动、母线建压、负荷恢复、PV 投入 |

失联策略必须在工程配置中明确，由设备侧独立保持安全。EMS 不承担 <100 ms 关键闭环，也不以网络可用性替代设备保护。

## 6. 故障、恢复与安全

- 遥测超时：STALE/OFFLINE；控制禁用无效关键量，产生诊断与后续告警。
- NATS 重复：消息/样本标识去重；乱序保留历史但不回退实时值；重放不得触发历史控制。
- NATS 中断：Gateway 有界缓冲，容量满报告丢失；禁止无限内存积压。
- 数据库中断：不阻塞 core，Historian 不提前 ACK；恢复补写并校验唯一性。
- 算法失败：仅在有效窗口且满足新约束时复用上一计划，否则 Rule-Based；不无限沿用过期计划。
- core 重启：重建 Snapshot，未取得有效必需量前不允许自动控制；不重放危险命令。
- 命令超时：状态是未知执行结果，先核验设备，不盲目重发启停/模式切换。
- V1.0 要求 TLS、RBAC、操作原因/确认、审计、备份恢复、升级回滚。基本命令权限随 M03 同步引入，不能拖到 M09 后补。
- M01 仿真端口仅本机开发使用，不含可供生产使用的控制接口。

## 7. Git 仓库目标布局

以下是后续逐步创建的目标布局；本 ZIP 实际仅含文末所列 8 个 Markdown 文件，不含脚手架或代码。

```text
microgrid-ems/
├── AGENTS.md
├── ARCHITECTURE.md
├── README.md                   # M0.1.1 创建
├── go.mod                      # M01 单 Go module
├── Makefile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── docs/
│   ├── product/EMS_V1_SCOPE.md
│   ├── architecture/{DOMAIN_MODEL,INTERFACES}.md
│   ├── roadmap/{ROADMAP,CURRENT_STAGE}.md
│   ├── milestones/M01_KERNEL.md
│   ├── learning/               # 实施时创建学习日志和 M01_REVIEW.md
│   ├── api/
│   ├── protocols/
│   ├── database/
│   ├── control/
│   ├── deployment/
│   ├── fat/
│   └── sat/
├── contracts/
│   ├── go/                    # 无基础设施依赖的公共领域类型
│   ├── jsonschema/            # M01 权威线格式
│   ├── openapi/
│   ├── examples/
│   └── protobuf/              # 预留，M01 不创建空占位实现
├── services/
│   ├── ems-core/{cmd,internal,config,tests}/
│   │   # internal: scheduler/snapshot/state/control/arbiter/interlock/command/dispatch/mode/strategy/fallback
│   ├── device-gateway/{cmd,internal,templates,tests}/
│   │   # internal: protocol/driver/device/polling/quality/simulator
│   ├── data-service/{cmd,internal,tests}/
│   │   # internal: historian/alarm/audit/report/carbon
│   ├── api-server/{cmd,internal,tests}/
│   │   # internal: auth/rest/websocket/config/mqtt
│   ├── forecast-service/{src,tests}/
│   │   # src: load/pv/features/models/evaluation/registry
│   └── optimization-service/{src,tests}/
│       # src: dayahead/intraday/objectives/constraints/solver/validation
├── web/ems-ui/src/{views,components,stores,api,router}/
├── database/{migrations,seeds,retention}/
├── configs/{site,devices,tariffs,strategies,alarms,interlocks}/
├── simulator/{cmd,internal,scenarios}/
│   # internal: pv/ess/load/grid，EV 聚合可选
├── deployments/{docker,linux,monitoring}/
├── scripts/
└── tests/{integration,system,fault_injection,sil,fat}/
```

每个 Go 服务的入口在 cmd/，实现收拢到自身 internal/；跨服务只能依赖 contracts/go/，不得导入另一服务 internal/。公共基础设施抽象在出现实际复用后再提取。

## 8. 文件导航与首次使用

实际初版文件：本文件、AGENTS.md、[范围](docs/product/EMS_V1_SCOPE.md)、[模型](docs/architecture/DOMAIN_MODEL.md)、[接口](docs/architecture/INTERFACES.md)、[路线图](docs/roadmap/ROADMAP.md)、[当前阶段](docs/roadmap/CURRENT_STAGE.md)、[M01](docs/milestones/M01_KERNEL.md)。

将 ZIP 中 microgrid-ems/ 下的内容复制到目标空仓库根目录，避免多嵌套一层。先阅读 CURRENT_STAGE.md，按其中启动提示规划 M0.1.1。这里没有创建 .git、提交或标签。
