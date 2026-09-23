# M01_KERNEL：EMS 数据内核

产品增量 V0.1；子阶段 M0.1.1～M0.1.9；版本 baseline-0.1。
前置文档：[范围](../product/EMS_V1_SCOPE.md)、[架构](../../ARCHITECTURE.md)、[模型](../architecture/DOMAIN_MODEL.md)、[接口](../architecture/INTERFACES.md)、[当前阶段](../roadmap/CURRENT_STAGE.md)。

## 1. 阶段目标与学习目标

把“设备物理量”转换成统一遥测，经消息总线形成一致快照并保存历史，让学习者可从输入追踪到存储。完成本阶段不代表控制能力、现场接入能力或商用性能已验收。

学习结束应能解释：Device/Tag 的区别；驱动为何统一单位和正负号；Telemetry 的时间/质量为什么不能省；消息总线与数据库有何不同；异步采集如何形成同一周期 Snapshot；为何使用独立历史消费者；断线、重复、乱序和数据库故障如何恢复。

## 2. 范围、非目标、前置条件

范围：版本化配置、Device/Tag/Telemetry/Snapshot、独立 Simulator、Gateway 仿真驱动、NATS JetStream、1 s Scheduler、Latest Cache、质量老化、基础 Historian、只读诊断、日志、单元/契约/集成/故障测试、Compose、Demo。
不做：真实协议、Web HMI、Alarm 规则与确认、生产 API、Controller、Arbiter、Interlock、Command Manager、真实设备写入、预测、优化、模式切换、MGCC/黑启动、碳报表、复杂工程配置平台、HA。后续对象只保留文档规范。
诊断日志和计数不是业务告警引擎；Simulator setter 是实验输入，不是 EMS 发给设备的控制通道。

环境：可运行 Docker Compose 的开发机；Go 版本与依赖锁定；容器能访问固定镜像与模块源；足够空间持久化 NATS 和 TimescaleDB。Linux 为验收基准，Windows 可用 Docker Desktop/WSL2。实施时检查实际环境并记录限制，不因未安装依赖而伪称测试通过。
Go 单 module 名称默认 `microgrid-ems`（本地开发，不冒用未确认 Git 远端）；未来如采用正式仓库模块路径需集中替换。

## 3. 数据流与组件

```text
scenarios/demo.yaml → Simulator（物理模型/故障注入）
          ↓ HTTP RawMeasurement
Gateway Driver → 单位/类型/质量标准化 → TelemetrySample
          ↓ NATS JetStream
          ├─ core consumer → Latest Cache → 1s Scheduler → Snapshot
          │                                      └→ 只读诊断/快照事件
          └─ historian consumer → DB事务/幂等写入 → 历史只读查询
```

| 组件 | 输入 | 输出/边界 | 创建步骤 |
|---|---|---|---|
| 配置/日志/启动 | YAML/env | 验证配置、JSON 日志、health/ready | .1 |
| contracts/go + jsonschema | 领域规范 | 类型、校验、测试样例 | .2 |
| Simulator | 场景/可注入 Clock | PV、ESS、Load、PCC、静态 EV 读数 | .3 |
| Gateway | RawMeasurement | 标准 Telemetry，生命周期、质量事件 | .4 |
| NATS adapter | Telemetry/连接事件 | 可确认消息、重连/有界缓冲 | .5 |
| core Scheduler/Snapshot | Telemetry | 不可变 Snapshot、质量老化 | .6 |
| Historian | 原始遥测 | TimescaleDB 记录与范围查询 | .7 |
| 集成测试工具 | 同一 Compose 与场景 | 机器可判定结果、日志与证据 | .8 |
| Demo/学习回顾 | 全链路 | 5分钟历史、故障恢复、解释与验收 | .9 |

## 4. 固定实验配置

站点 site01，timezone=Asia/Shanghai，configVersion=demo-v1；内部 UTC。设备 load01/pv01/ess01/pcc01/ev01（EV 为固定 0 的模拟聚合）。

| Tag | 单位 | 初始值/语义 |
|---|---|---|
| site01.load01.active_power | kW | 500，不含 EV |
| site01.pv01.active_power | kW | 0，场景可改为 300/350 |
| site01.ess01.active_power | kW | 0，放电正、充电负 |
| site01.ess01.soc | % | 60 |
| site01.pcc01.active_power | kW | 500，由模拟物理平衡独立输出 |
| site01.ev01.active_power | kW | 0，明确存在的模拟量 |

Simulator 使用固定输入、seed 和可控时间，默认无随机噪声。单元测试中功率误差≤1e-6 kW；集成稳定场景允许≤0.1 kW 的显示/序列化误差。步骤切换瞬间的不同步样本不用于稳态断言。
轮询 1000 ms；HTTP 超时 800 ms；STALE 3000 ms；OFFLINE 5000 ms；时钟未来容差 1000 ms。明确连接失败可立即 OFFLINE，整进程停止时由 core 在 age≥5 s 判 OFFLINE。
ESS 最小模型支持功率与 SOC 积分，测试用能量容量 1000 kWh、充放电效率 1（仅教学理想值）；P>0 时 SOC 下降，P<0 上升。Demo P=0 时 SOC 保持 60。越过模拟 SOC 边界时标记无效输入/拒绝场景设置，不实现 EMS SOC 控制器。
单独切断 ESS 通信不会停止模拟电气系统，也不把 ESS 物理功率置零；用此区分“未知测量”与“真实功率变化”。

## 5. 验证命令约定

以下均是**后续步骤必须实现的命令入口**，本次 8 个文档不含这些脚本，不能立即运行。每步首次提供入口时写入 README；命令失败退出非零，不用仅打印 PASS 冒充验证。
标准入口在仓库根目录，Makefile 负责封装；Windows 无 make 时 README 提供等价 `docker compose` / `go` 命令，场景验证优先用 Go 小工具而非依赖 shell 文本处理。

| 步骤 | 需要提供并实际执行的入口 | 检查内容 |
|---|---|---|
| .1 | `make test-scaffold`；`docker compose config -q`；`make up`；`make health` | 配置/日志/启动，基础服务健康 |
| .2 | `make test-contracts` | 领域校验、JSON Schema、示例 round-trip |
| .3 | `make test-simulator`；`make demo-simulator` | 功率平衡、SOC 积分、可重复读数 |
| .4 | `make test-gateway`；`make demo-gateway` | 标准化、轮询、断线重连，recording publisher |
| .5 | `make test-bus`；`make demo-telemetry` | JetStream 发布/确认/重发/独立订阅者 |
| .6 | `make test-snapshot`；`make demo-snapshot` | 新鲜度、不可变、乱序、重启重建 |
| .7 | `make test-historian`；`make demo-history` | DB 幂等、查询、恢复 |
| .8 | `make test-unit`；`make test-integration`；`make test-faults` | 全链路与故障用例；Go 单元含 race 检查 |
| .9 | `make demo-m01`；`make verify-m01` | 自动场景和最终验收汇总 |

`make up` 封装 `docker compose up -d --build`；`make down` 封装 `docker compose down`（保留数据卷）。禁止把 `down -v` 隐藏在日常停止命令中。
建议集成测试使用独立 Compose project `ems-m01-test` 与专用卷，Demo 用 `ems-m01-demo`；清理仅操作该测试项目明确创建的资源，不能清理用户其他容器或数据。
M01 的 make up/down/health/demo-* 默认统一使用 `ems-m01-demo`，测试入口显式覆盖为 `ems-m01-test`；README 的原生 Compose 等价命令必须带相同 `-p` 参数，避免启动两套同名但不同项目的数据栈。
必需数据卷 nats_data/postgres_data；健康检查和应用层重试共同处理启动先后，不只依赖容器创建顺序。

## 6. M0.1.1 — 仓库脚手架

**学习目标：** 分清仓库、服务进程、配置、依赖与健康状态，能独立启动/停止开发栈。

**范围：** README、go.mod/go.sum（实际有依赖时）、.gitignore、.env.example、Makefile、docker-compose.yml、最小 YAML 配置/验证、JSON 日志，Gateway/core/data-service 三个仅健康入口的空壳及 Simulator 健康入口，NATS/TimescaleDB 容器与卷。
**非目标：** 无 Telemetry 业务类型/轮询/模型/数据库表，不提前写下一步。

**数据流：** 文件/env → 配置验证 → 进程启动 → health/ready/日志。此步不是完整遥测流。
**组件/路径：** 各 services/*/cmd、必要 internal/config/logging，simulator/cmd、configs/site/demo.yaml、deployments/docker/、scripts/、docs/learning/LEARNING_LOG.md。仅创建当前真正使用目录。

**测试：** 缺 siteId、非法采样/超时关系、端口冲突、配置解析失败时进程退出非零；JSON 日志含 time/level/service/siteId/message，无密码。健康端点确认存活与依赖就绪含义不同。
**Demo：** 从仓库根目录构建启动；展示各容器与 HTTP health 状态；停止再启动，数据卷保留。
**验收：** 新环境按 README 可执行；镜像/Go 依赖固定版本；配置样例无秘密；命令失败透明；无业务控制逻辑。
**完成条件：** 本步测试和 Demo 实际通过，学习日志解释进程关系，CURRENT_STAGE 标 READY_FOR_REVIEW；用户确认后才 ACCEPTED 并进入 .2。

## 7. M0.1.2 — 核心领域对象与契约

**学习目标：** 明白 Device、TagDefinition、TelemetrySample、SnapshotValue/SystemSnapshot 的层次，理解单位、质量与时间。

**范围：** Site/Device/Tag、QualityCode、TelemetrySample、Snapshot 所需类型、校验函数、JSON Schema、正常/异常样例。开发当前所用类型，不一次实现后续所有领域对象。
**非目标：** 网络采集、控制模型实现、生产 ORM、代码生成大框架。

**数据流：** JSON fixture → 校验 → Go 类型 → JSON → 相同语义 fixture。
**组件/路径：** contracts/go/、contracts/jsonschema/、contracts/examples/、对应 *_test.go。

**测试：** 正确符号与单位；SOC 0～100；Tag 身份一致；GOOD+null 拒绝；OFFLINE+旧值保留时间；bool/string/numeric 类型匹配；未知主 schema、NaN、未来时钟策略；深拷贝不可变规则。
**Demo：** 读一条 SOC=60 GOOD 和一条同采样时间 OFFLINE 消息，解释为什么不能将后者视为新的 60% 或 0%。
**验收：** 示例与 Schema/Go 往返一致；字段/枚举与领域文档一致；错误可定位到字段；测试不依赖数据库/网络。
**完成条件：** test-contracts 通过，学习者能区分“点定义”和“点当前值”，记录证据待验收后进入 .3。

## 8. M0.1.3 — Simulator

**学习目标：** 建立最小物理模型，用确定性输入验证电网功率与储能能量方向。

**范围：** 独立 Simulator、Load/PV/ESS/Grid 模型、静态 EV 聚合；只读 measurements 和测试用 scenario/connection 接口；场景 YAML、可注入 Clock。
**非目标：** 虚拟 Modbus、真实硬件、UI、EMS 策略或保护算法。

**数据流：** scene+time → 模型 → RawMeasurement JSON，尚不经过 NATS。
**组件/路径：** simulator/internal/{pv,ess,load,grid}/、simulator/scenarios/demo.yaml、simulator/cmd/。

**测试：** Load500/PV300/ESS0/EV0→PCC200；PV350→150；ESS+100→PCC50（在 PV350 时）；ESS-100→PCC250。固定 1000kWh、η=1 时放电100kW持续1h，SOC60→50；充电同量回60。单位/边界/非法场景拒绝，相同 seed/time 得相同输出。
**Demo：** demo-simulator 改 PV 并查询 PCC；用虚拟时间展示 SOC 积分，无需等待一小时。
**验收：** PV/Load/ESS/PCC/SOC/EV 带时间/质量；无随机不稳定用例；连接故障可注入并恢复。
**完成条件：** test-simulator 和 demo-simulator 通过、说明符号和能量公式、待用户验收后进入 .4。

## 9. M0.1.4 — Device Gateway

**学习目标：** 理解驱动隔离协议、标准化、连接生命周期、轮询和质量判定。

**范围：** Driver 接口、仿真 HTTP 适配器、Device Manager、1s Poll Scheduler、单位/比例转换、超时/重连、Telemetry 生成、可注入 Publisher。此步用 recording Publisher 收集输出。
**非目标：** 实际 NATS 集成留到 .5；无 Modbus/OPC UA、命令/告警/控制器。

**数据流：** Simulator HTTP → Driver.RawMeasurement → 标准化 → TelemetrySample → recording Publisher。
**组件/路径：** services/device-gateway/internal/{device,driver,polling,quality,simulator}/；必要公共契约补充须同步 Schema。

**测试：** W→kW 转换只在驱动；正常采样 sampleId/sequence/epoch；超时不产生 GOOD 0；断线保留原时间或 null；退避重连不忙循环；恢复读取后才 GOOD；取消 context 停止轮询，goroutine 不泄漏。
**Demo：** 采集 ESS60%，切断仿真 ESS，观察 OFFLINE/reason；恢复连接后 GOOD，进程无需重启。
**验收：** 采集周期1s，轮询超时800ms；记录每条标准遥测且身份/单位正确；连接与点质量分开；无命令写接口。
**完成条件：** test-gateway/demo-gateway 通过，解释上层为何不读寄存器，验收后进入 .5。

## 10. M0.1.5 — NATS Telemetry

**学习目标：** 理解发布、订阅、流、durable、ACK、重投和业务幂等的区别。

**范围：** 把 Publisher 替换为 JetStream；配置流与上限、标准 envelope、publisher ACK、重连、有界缓冲、测试订阅器、隔离错误消息机制。
**非目标：** core Snapshot/Historian 正式消费者在后两步接入；不做命令总线和遥测 exactly-once 承诺。

**数据流：** Gateway → EMS_TELEMETRY → 两个独立测试 durable → 终端/测试断言。
**组件/路径：** Gateway 内 NATS adapter、deployments/docker/nats 配置、contracts envelope、tests/integration/bus/、scripts/demo-telemetry。

**测试：** 两订阅者都收到消息；ACK 丢失触发重投；保留 messageId/sampleId；重复窗口内总线去重及窗口外应用去重测试预备；坏 JSON/错误 subject/未知 schema 隔离；NATS 中断30s 后重连；队列满可观测且内存不无界增长。
**Demo：** 订阅 `ems.site01.telemetry.ess01.updated`，显示合法消息；暂停/恢复 NATS，观察原 ID 补发与 droppedSamples 指标。
**验收：** 流配置与 INTERFACES.md 一致；JSON schema 校验通过；NATS 断开不退出 Gateway；发布确认和消息消费确认不混淆。
**完成条件：** test-bus/demo-telemetry 通过，证据注明缓冲仅内存、超保留会丢失的边界，用户验收后进入 .6。

## 11. M0.1.6 — Snapshot 与 Scheduler

**学习目标：** 理解异步遥测和同周期一致视图，掌握数据老化而非只看“最后一次值”。

**范围：** core 独立 durable、Latest Cache、1s Scheduler、不可变 Snapshot、类型化资源视图、STALE/OFFLINE、新鲜度与缺点检查、只读查询、snapshot event、重启重建。
**非目标：** Controller、Arbiter、真实模式机；controlEligible 在 M01 恒 false。

**数据流：** NATS → Cache.Apply → Build(cutoff) → Snapshot ID → 诊断 REST/事件。Historian 不依赖 Snapshot 才能入库。
**组件/路径：** services/ems-core/internal/{snapshot,scheduler,state}/、相应测试、诊断 handler。

**测试：** 快照后修改 cache 不改变旧对象；同周期统一 id；不完整点列出 missing；重复/乱序不回退最新值；未知/坏时间降低质量；停止 Gateway 后 fake clock 精确验证3s STALE/5s OFFLINE；重启/重放跨 epoch 不提升旧值新鲜度；`go test -race` 无并发竞态。
**Demo：** PV300 时显示 PCC 实测200及计算200；PV350 稳定后150；暂停全部 Gateway，快照仍每秒生成，质量变 STALE/OFFLINE；恢复后基于新采样转 GOOD。
**验收：** cutoff 与 sampleTimestamp 可追溯；M01 无隐式 0 补缺；正常稳定场景不超过2个快照周期更新；重启恢复期间显示 recovering 且禁控。
**完成条件：** test-snapshot/demo-snapshot 通过，能说明一致快照不等于同步采样，验收后进入 .7。

## 12. M0.1.7 — 基础 Historian

**学习目标：** 理解时序持久化、事务后 ACK、幂等写入与查询时间边界。

**范围：** TimescaleDB migrations、telemetry_raw、一条消息/批量事务持久化、唯一键、独立 durable、只读历史范围/分页查询、恢复补写与保留配置入口。
**非目标：** SCADA 曲线、完整1min/15min/日报聚合、业务 Alarm/Report、生产1年留存验收。M01 仅保留基础原始遥测及质量事件。

**数据流：** EMS_TELEMETRY → Historian → DB事务提交 → ACK；查询 API → 原始记录。
**组件/路径：** services/data-service/internal/historian/、database/migrations/、database/retention/、tests/integration/historian/。

**测试：** 新库迁移、重复启动无破坏；混合类型/null/质量；重复消息只一条；事务提交后 ACK 丢失仍无重复；相同 ID 不同内容隔离；from包含/to不包含，分页无重复遗漏；DB离线30s后补写，core Snapshot 独立运行。
**Demo：** 至少连续采样60s，查询 PV/Load/PCC/SOC；断数据库后 Snapshot 正常更新，恢复后查询补齐收到总线的数据。
**验收：** 唯一键与 Timescale 分区兼容；只在 commit 后 ACK；没有每 Tag 一表；历史保留原时间与质量，不用补写时间替代采样时间。
**完成条件：** test-historian/demo-history 通过，记录容量/保留限制，用户验收后进入 .8。

## 13. M0.1.8 — 集成与故障测试

**学习目标：** 用可复现证据证明数据链正确，理解单服务测试通过不等于系统正确。

**范围：** 同一 Compose 全链路自动测试、确定性场景、故障注入、跨重启恢复、日志/测试结果收集、CI 入口。
**非目标：** 5000 Tag 商业性能、7天稳定性、真实硬件 FAT/SAT、后续业务。

**数据流：** 测试脚本设场景 → 等待有界条件 → 查 Snapshot/历史 → 自动断言 → 收集证据。采用有截止时间的等待，不用固定 sleep 后直接判 PASS。
**组件/路径：** tests/integration/、tests/fault_injection/、scripts/verify-*、CI 配置（按实际仓库平台决定）。

**测试：** 下一节 T01～T12；单元/契约/race 一并跑一次。容器进程重启、DB/NATS 停止仅针对测试项目，不操作生产环境。
**Demo：** 一条命令跑正常数据链、ESS离线、DB恢复三组场景，终端每个断言打印 expected/actual，失败返回非零。
**验收：** 固定 seed/config、记录 commit 和镜像版本、测试独立可重复；重复跑两次没有残留数据影响结果；没有未解释失败/跳过；明确未执行的环境项。
**完成条件：** test-unit/integration/faults 实际通过，证据可复查；阻断缺陷修复，用户验收后进入 .9。

## 14. M0.1.9 — Demo、学习回顾与验收

**学习目标：** 能自己启动、观察、故障注入、查历史，并沿代码说明一条遥测的全过程。

**范围：** 一键 Demo、5分钟场景、README/运行排障、M01_REVIEW.md、最终验收记录与限制汇总。
**非目标：** 为演示好看新增 UI、控制策略或预测；不自动开始 M02。

**数据流：** 完整 Simulator→Gateway→NATS→Snapshot/历史，演示和测试共享配置，避免两个不同系统。
**组件/路径：** scripts/demo-m01、scripts/verify-m01、docs/learning/M01_REVIEW.md、README、CURRENT_STAGE。

**测试：** 正常 Demo 自动断言、5分钟历史查询、OFFLINE→GOOD、数据卷保留；verify-m01 汇总现有必要测试，不因出报告重复无关耗时测试。
**Demo：** 按第16节原样执行，保留终端输出/结构化结果；手工复现一次关键路径。
**验收：** 所有 T 用例和最终清单满足；学习者可回答第18节问题；没有伪称现场/控制能力已完成。
**完成条件：** READY_FOR_REVIEW；用户确认 M01 后才 ACCEPTED。标签 v0.1.0-kernel 仅在授权后创建，M02 需新的阶段授权和详细规格。

## 15. 必须通过的测试矩阵

| ID | 输入/故障 | 应观察的结果 | 主要层 |
|---|---|---|---|
| T01 | 固定场景 Load500、PV300、ESS0、EV0 | PCC200，GOOD，单位/时间/身份正确 | 单元+端到端 |
| T02 | PV改350 | 稳定后 PCC150，历史保留变化前后 | 端到端 |
| T03 | ESS ±100、虚拟时间积分 | 正放电/负充电，PCC与SOC方向正确 | Simulator 单元 |
| T04 | ESS返回503后恢复 | OFFLINE/非零伪造，恢复有效采样后GOOD，无重启 | Gateway+集成 |
| T05 | Gateway全停至少8s | core继续生成快照，3s老化/5s离线；恢复后新采样GOOD | core单元+集成 |
| T06 | 重复sampleId；DB提交后丢ACK | raw无重复、统计不增、实时值不抖动 | 总线+DB |
| T07 | 乱序/旧采样/重启epoch/未来时间 | 历史可保留迟到值，Snapshot不倒退，异常时钟不GOOD | 契约+core |
| T08 | 停DB30s | core继续；Historian not-ready；恢复30s内补齐测试窗口已入总线记录 | 集成故障 |
| T09 | 停NATS30s | Gateway有界缓冲，core质量老化；恢复30s内送达队列内记录 | 集成故障 |
| T10 | 重启core/Gateway/data-service | 配置/流恢复，cache重建，质量仍按原采样年龄，无命令 | 集成故障 |
| T11 | 非法JSON/Tag/unit/null/schema | 拒绝/隔离并可诊断，合法数据继续流动 | 契约+集成 |
| T12 | 全栈持续5min、历史查询与分页 | PV/Load/PCC/SOC有记录、去重、时间顺序正确，停止重启历史保留 | Demo+集成 |

T08/09 在本机固定六 Tag、流容量足够时要求恢复窗口≤30s，是 M01 实验门槛，不是商业 SLA。外部环境造成失败必须记录实测并修复/说明，不自动放宽门槛。
物理有线设备有效采集率、页面延迟、命令延迟、PCC控制误差均不在 M01 宣称范围。

## 16. 最终 Demo 的可复现步骤

前提：.1～.8 已验收，测试环境没有真实设备连接，Compose 使用独立 demo project。启动日志记录 UTC 起始 t0。

1. `make up`，等待 health/ready 成功；`make demo-m01` 开始自动场景（脚本自行使用同一 demo project）。
2. t=0～30s：Load500/PV0/ESS0/SOC60/EV0；稳定 PCC500。
3. t=30～90s：PV改300；稳定 Snapshot 的 PV300、Load500、ESS0、PCC200、SOC60，全 GOOD。
4. t=90～150s：PV改350；稳定 PCC150；同时显示实测PCC与计算PCC。
5. t=150～165s：仅断开 ESS 仿真读接口；有效质量 OFFLINE，保留旧 sampleTimestamp 或 null；计算PCC不可再标GOOD，PCC实测仍可GOOD。系统不生成任何设备命令。
6. t=165s：恢复 ESS；在成功读取后回 GOOD，不重启任何服务。
7. 持续到至少 t=310s；查询 [t0,t0+300s) 的 PV、Load、PCC、ESS SOC，展示记录数、时间范围、质量分布和变化片段。轮询数量允许启动/转换时序差异，不用“必须恰好300条”制造脆弱测试。
8. 对该场景要求 PV/Load/PCC 每项至少290条GOOD；SOC 至少270条GOOD并至少一条OFFLINE质量事件；计数按唯一 sampleId 去重。详细缺口需解释，不能被平均值掩盖。
9. `make down`（保留卷）再启动，确认上述时间段历史仍可查询；`make verify-m01` 检查最终标准并输出结果。

预期节选（仅示意，不是已执行输出）：

```text
PV=300 kW  Load=500 kW  EV=0 kW  ESS=0 kW  PCC=200 kW
PV=350 kW  Load=500 kW  EV=0 kW  ESS=0 kW  PCC=150 kW
ESS quality=OFFLINE  sampleTimestamp=<断线前采样时间>
ESS quality=GOOD     sampleTimestamp=<恢复后的新时间>
history: PV / Load / PCC / SOC returned, quality events preserved
```

如果用 PowerShell/curl 手工操作，README 必须给出对应 JSON 请求与查询示例，避免让学习者自行猜端口或 Tag 名称。

## 17. 最终验收与 Definition of Done

- [ ] 初版配置/Schema/代码与 8 个基线文件一致，任何偏差有记录。
- [ ] .1～.9 各步有实际测试和 Demo 证据，不提前跳步。
- [ ] 六个实验 Tag 带单位、时间、质量和来源；SOC/PCC符号通过测试。
- [ ] Gateway、core、Historian 的总线消费相互独立，故障不会形成无界积压。
- [ ] Snapshot 每秒构建、不可变、质量老化正确，缺失/乱序/重放规则通过。
- [ ] 历史事务后ACK与幂等、查询/分页、DB故障恢复通过。
- [ ] NATS故障、服务重启、非法消息的证据完整，已知数据丢失边界公开。
- [ ] Demo稳定数值200→150、ESS离线→恢复、5分钟历史均通过。
- [ ] 未增加控制器/命令、真实驱动、UI、算法或模式管理。
- [ ] README可从干净环境复现，版本固定，停止不删除数据卷。
- [ ] LEARNING_LOG和M01_REVIEW完整；未执行项与限制不被标记通过。
- [ ] 用户完成验收，CURRENT_STAGE记录 ACCEPTED；未擅自进入M02。

关联产品 F01/F03 基础能力，为 A02/A10/A11/A12/A14/A18 建立测试基础；不表示这些 V1.0 指标已全面验收。
发布后遗留：真实协议、生产安全与权限、完整历史聚合、告警、控制与全部后续业务；M01 Gateway内存队列掉电可能丢失未发布数据，流保留范围外无法补齐；仿真无现场噪声/设备特性，不证明现场控制性能。

## 18. 学习回顾必须回答的问题

1. 一条 site01.ess01.soc 从哪里产生，经过哪些函数和服务，在哪里入库？
2. TagDefinition 与 TelemetrySample 有什么区别？改变单位为何不能只改 UI？
3. 为什么 Controller 不应该直接读 Modbus 或不断变化的 cache？
4. NATS 的ACK、数据库事务和命令回执分别保证什么？
5. Snapshot 为什么能一致却不代表设备同步采样？
6. BAD、STALE、OFFLINE 与0有何区别？断线旧值的timestamp为什么不更新？
7. 为什么 Historian 直接消费遥测，而非只保存 Snapshot？
8. 重复、乱序、DB/NATS故障和服务重启分别如何恢复，哪里仍可能丢数据？
9. M01做到什么、还没做到什么，为什么不能称为商用EMS？

完成教学回顾后，由用户决定是否推进，不把“生成一份回顾文档”当作用户已理解和验收。
