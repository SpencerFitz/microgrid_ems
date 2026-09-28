# M01_KERNEL：Python / Windows 仿真内核

版本 baseline-pywin-0.2，2026-09-24。M0.1.1～M0.1.9每步单独实施、测试、Demo及人工验收。当前授权仅.1；后续命令均为规划，尚未实现。

## 总目标、学习目标、范围与非目标

用一个Windows Python工程理解设备数据如何进入EMS，最终形成统一遥测→消息→快照/历史闭环。学习Device/Tag区别、质量/时间、适配器、广播队列、不可变Snapshot、幂等与SQLite事务、故障恢复。
M01范围为配置、日志、领域对象、Simulator、Gateway、Python EventBus、Scheduler/Snapshot、基础SQLite Historian、测试与CLI演示。
非目标：真实设备/协议、GUI、业务Alarm、控制器/仲裁/联锁/命令、预测优化、MGCC/黑启动流程、商业规模验收。当前四组件健康名不等于后续模块已实现。

## 环境和数据流

Windows + Python3.12+；M01尽量标准库，不需联网下载依赖。M0.1.1已实际使用Python3.12.14测试。桌面界面和算法库留到对应阶段。

```text
JSON场景→Python Simulator→Driver→TelemetrySample→EventBus
                                         ├→Cache→1s Scheduler→Snapshot→CLI
                                         └→Historian→SQLite→历史查询
```

EventBus是进程内广播，每订阅者独立有界队列；进程退出时未写内存事件可能丢失，不能声称可靠重放。Historian直接保存遥测，不只保存Snapshot。SQLite连接由所属线程管理，core不等待数据库锁。
使用UTC记录采样，time.monotonic计算超时；测试可注入Clock。Windows多进程必须__main__保护，未来算法进程不能直接控制设备。

## 固定实验参数

site01；configVersion=python-windows-v1；显示时区Asia/Shanghai，存储UTC。
Load500kW（不含EV），PV初始0，ESS0kW/SOC60%，EV明确模拟为0，PCC由Simulator输出500。
Tag为site01.load01.active_power、pv01.active_power、ess01.active_power、ess01.soc、pcc01.active_power、ev01.active_power，实际完整Tag前缀均为site01。
采样1000ms、超时800ms、STALE3000ms、OFFLINE5000ms。断线保留旧采样时间/值或null，不写GOOD0。每周期发样本，M01不启用deadband抑制。
ESS正放电负充电；教学容量1000kWh、效率1，仅作为理想模拟。Load500/PV300/ESS0/EV0→PCC200；PV350→150；ESS+100时→50；ESS-100时→250。
单元模型误差≤1e-6kW，集成稳定场景≤0.1kW；过渡期不以不同步采样冒充稳态误差。

## 命令和门禁

当前可运行：`python ems.py doctor`、`validate`、`run --ticks 3`、`run`、`status`、`demo`；测试：`python -m unittest discover -s tests -v`。CLI全局--config/--data-dir位于子命令前。
以下.2～.9的test/demo命令或测试文件由对应步骤创建，不能提前运行或当作已通过。每步记录准确命令、退出码和实际结果；READY_FOR_REVIEW不等于ACCEPTED。
测试使用tempfile隔离目录，不读取/删除用户其他数据。持久数据放runtime/，停止不删除；新实例不能同时写同一数据目录。错误返回非零。

## M0.1.1 — 仓库脚手架

**学习目标：** 理解Python入口、配置、生命周期、健康和本地数据目录。

**范围：** ems.py、ems/config.py/cli.py/runtime.py、pyproject.toml、JSON配置、日志、Windows实例锁、状态文件、SQLite bootstrap_meta、测试和说明。

**非目标：** 不实现领域对象、模拟物理量、EventBus、Historian业务表或GUI。

**数据流：** JSON→校验→四逻辑组件注册→bootstrap心跳/日志→停止→重新打开同一SQLite启动标记。

**组件：** 当前根入口及ems/四文件、tests/test_scaffold.py、configs/site/demo.json、docs/learning/。

**测试：** 缺/未知/重复配置键、非法类型/超时、并发实例拒绝、崩溃锁释放、陈旧状态、日志UTC、Ctrl+C语义、目录不可写和重启标记保留。

**Demo：** `python ems.py demo`运行两轮各3次心跳，自动比较installationId；`python ems.py status`显示STOPPED。

**验收：** doctor/validate/unit tests/demo均实际通过；无联网服务依赖；不把健康名解释为遥测就绪。

**完成条件：** 当前11项测试和Demo已通过，等待用户理解/验收；只标READY_FOR_REVIEW。

## M0.1.2 — 核心领域对象与契约

**学习目标：** 区别点定义与样本、理解单位/正负号/UTC/质量。

**范围：** dataclass/Enum定义Site/Device/Tag/Telemetry及Snapshot所需类型、JSON序列化和字段校验；保留后续对象规范但不实现业务。

**非目标：** 不采集、不联网、不执行控制，不引入ORM。

**数据流：** JSON fixture→校验→Python对象→JSON，同语义往返。

**组件：** ems/domain/、contracts/jsonschema/、contracts/examples/、tests/test_contracts.py。

**测试：** 身份/单位/数据类型、GOOD+null拒绝、SOC范围、非有限数字、未知schema、深层不可变；旧值质量变化不更新时间。

**Demo：** 展示SOC60 GOOD与相同采样时间的OFFLINE事件，说明两者差异。

**验收：** JSON/对象/规范一致，错误定位明确，测试不依赖外部服务。

**完成条件：** 领域与契约测试通过、样例Demo完成、用户确认后进入.3。

## M0.1.3 — Simulator

**学习目标：** 用确定性场景理解功率平衡与SOC积分。

**范围：** Python PV/Load/ESS/Grid/静态EV模型、场景设置/故障注入、可注入Clock与seed。

**非目标：** 不做真实协议、控制策略、保护或GUI。

**数据流：** JSON scene+time→物理模型→RawMeasurement，尚不经过EventBus。

**组件：** ems/simulator/、configs/scenarios/、tests/test_simulator.py。

**测试：** PCC200→150及ESS正负功率例；100kW放电1h使1000kWh的SOC60→50；充电回60；相同时间输入可重复，越界场景拒绝。

**Demo：** 新增 `python ems.py demo-simulator`，改变PV查询PCC，用虚拟时间展示SOC。

**验收：** 时间/质量/单位完整，断开读接口不改变真实模拟功率，恢复可重复。

**完成条件：** 模型测试/Demo通过、学习日志解释功率与能量、用户验收。

## M0.1.4 — Device Gateway

**学习目标：** 理解适配器、标准化、轮询、连接与质量分离。

**范围：** Python Driver Protocol、设备管理、1s轮询、超时/重连、单位转换、RecordingPublisher。

**非目标：** 不实现真实协议、EventBus、告警或命令。

**数据流：** Simulator.read→Driver→标准化Telemetry→RecordingPublisher。

**组件：** ems/gateway/、tests/test_gateway.py。

**测试：** W→kW、epoch/sequence、超时非GOOD0、连接后需读到新有效样本才GOOD；停止线程可join且无忙循环。

**Demo：** demo-gateway断ESS读接口→OFFLINE→恢复GOOD，无需重启主程序。

**验收：** 轮询/超时阈值可配置，未知值不补零，发布器可替换。

**完成条件：** 测试/Demo/数据追踪说明通过后人工验收进入.5。

## M0.1.5 — Python EventBus

**学习目标：** 理解广播与竞争队列不同、有界队列和背压、内存消息的可靠性边界。

**范围：** Topic/Envelope、本地订阅注册、每订阅者独立Queue、有限投递、计数/缺口、隔离坏消息、停止机制。

**非目标：** 不实现外部broker、跨机器通信、持久消息重放或命令总线。

**数据流：** Gateway→EventBus→两个独立测试订阅者；任一慢消费者不无限阻塞其他模块。

**组件：** ems/messaging/、tests/test_event_bus.py；Gateway替换RecordingPublisher。

**测试：** 同事件两订阅者均收到；队列满返回部分失败并计gap；坏消息隔离；重复/乱序显式注入；close/join有限时间。

**Demo：** demo-events展示订阅收到样本，暂停一个消费者触发队列上限，另一个继续。

**验收：** 有界内存、错误显式；明确崩溃后未持久化事件丢失，不承诺补齐。

**完成条件：** 正常/慢消费者/退出测试通过及人工验收。

## M0.1.6 — Snapshot与Scheduler

**学习目标：** 理解异步采样如何形成同周期不可变视图。

**范围：** Latest Cache、排序去重、1s周期、质量老化、必需点完整性、快照CLI/事件。

**非目标：** 无Controller/Arbiter/模式机；M01 controlEligible恒false。

**数据流：** EventBus→Cache→Build(cutoff)→Snapshot；原始遥测并行去Historian。

**组件：** ems/core/snapshot.py、scheduler.py、tests/test_snapshot.py。

**测试：** 发布后修改Cache不改变旧Snapshot；同周期ID一致；迟到不回退；3s/5s质量；缺点/未来时间；重启用新采样恢复。

**Demo：** demo-snapshot显示PCC200→150，停Gateway后快照继续且质量老化，恢复新值才GOOD。

**验收：** 采样与cutoff可追溯，缺失非0，不依赖历史DB；新输入2周期内体现在快照。

**完成条件：** 正常/乱序/故障/停止测试通过，用户能解释一致视图不等于同步采样。

## M0.1.7 — SQLite Historian

**学习目标：** 理解原始遥测、事务、唯一键、待写缓存和查询边界。

**范围：** 单写者、SQLite WAL/busy_timeout、版本迁移、telemetry_raw、幂等批写、只读分页查询、有界重试。

**非目标：** 不做GUI曲线、完整聚合报表或长期商业留存，不实现外部数据库服务。

**数据流：** 独立订阅者→待写批次→SQLite事务；Core独立更新。

**组件：** ems/data/、database/migrations/、tests/test_historian.py。

**测试：** schema迁移、null/类型/质量、重复无重复行、相同ID内容冲突、[from,to)分页；注入SQLite锁竞争/写失败后恢复补写未溢出缓存。

**Demo：** demo-history查询60s数据；测试连接持有写锁造成Historian busy，Core继续；释放锁后重试成功。

**验收：** 不跨线程共享未受控连接；事务后清理待写；失败/溢出缺口明确；无每Tag一张表。

**完成条件：** 测试/Demo通过，不将缓存之外丢失数据声称补齐，用户验收。

## M0.1.8 — 集成与故障测试

**学习目标：** 证明全链路行为，区别单元通过与系统通过。

**范围：** 同一配置、固定seed、单进程多模块集成、独立临时目录、故障注入与证据。

**非目标：** 无真实硬件、商用容量、GUI或后续业务。

**数据流：** 场景输入→有截止时间地等条件→查Snapshot/历史→断言→收集结果。

**组件：** tests/integration/、tests/fault_injection/、测试发现入口与场景fixtures。

**测试：** T01～T10矩阵，重复运行无跨测试污染；写入失败、队列满、模块停启、重启、坏数据均有预期。

**Demo：** demo-integration自动跑正常链路、ESS断线、SQLite锁恢复三组场景，失败非零退出。

**验收：** 测试无未知跳过；配置/版本/耗时/缺口记录完整；当前代码的必要测试全部通过。

**完成条件：** 阻断缺陷修复，证据可复查，用户验收后进入.9。

## M0.1.9 — Demo与学习回顾

**学习目标：** 能自己启动、改变场景、注入故障、查历史并追踪代码。

**范围：** 5分钟完整CLI Demo、README与M01_REVIEW、最终检查单。

**非目标：** 不为演示添加GUI/控制/预测，不自动开始M02。

**数据流：** Simulator→Gateway→EventBus→Snapshot/SQLite历史共享同一实验配置。

**组件：** CLI demo-m01、verify-m01、docs/learning/M01_REVIEW.md、当前阶段记录。

**测试：** 正常200→150、OFFLINE→GOOD、5分钟历史、重启历史保留及前述必要测试。

**Demo：** 按下一节时间表执行 `python ems.py demo-m01`，输出actual/expected与历史质量分布。

**验收：** 所有T用例、最终清单、学习问题满足，未验现场内容明确。

**完成条件：** 先READY_FOR_REVIEW，用户确认M01后才ACCEPTED；下阶段需新授权。

## 测试矩阵（.8/.9必须覆盖）

| ID | 输入/故障 | 预期 |
|---|---|---|
| T01 | Load500/PV300/ESS0/EV0 | PCC200且GOOD，单位/时间正确 |
| T02 | PV350、ESS正负功率 | PCC150，ESS方向正确，历史保留变化 |
| T03 | ESS断读15s再恢复 | OFFLINE→新有效采样GOOD，无伪造零 |
| T04 | Gateway停8s | 快照继续，3s STALE/5s OFFLINE |
| T05 | 重复/乱序/未来时间 | 历史幂等、最新值不回退、坏时钟非GOOD |
| T06 | 一个订阅者队列满 | 缺口可见，另一个不阻塞，无无界内存 |
| T07 | SQLite写锁/写入故障30s | Core继续，释放后30s内补写缓存内记录；溢出明确缺口 |
| T08 | 重启程序 | 新采样重建，历史保留，不假称内存事件重放 |
| T09 | 非法JSON/Tag/unit/schema | 拒绝/隔离，合法数据继续 |
| T10 | 运行至少5min、查询/分页/重启 | 数据完整可追踪、分页无重复遗漏 |

## 最终5分钟Demo

仅在.1～.8验收后执行。使用独立数据目录，不清理用户已有运行数据。
0～30s：Load500/PV0/ESS0/SOC60/EV0，PCC500。
30～90s：PV300，PCC200。90～150s：PV350，PCC150。
150～165s：断ESS读接口；ESS质量OFFLINE，依赖ESS的计算PCC非GOOD，但模拟PCC表可继续GOOD；不生成控制命令。
165s恢复，成功采样后GOOD。持续至少310s；查[t0,t0+300s)的PV/Load/PCC/SOC。
去重后PV/Load/PCC每项≥290条GOOD，SOC≥270条GOOD且至少1条OFFLINE质量事件；差异/缺口明确说明。关闭并重新运行，查询旧时间段历史仍在。
数量是固定六Tag无随机噪声的教学场景标准，不是商业采集率保证。

## 最终验收与完成条件

- [ ] .1～.9每步真实测试/Demo及用户验收记录存在。
- [ ] 功率符号/单位/UTC/质量/缺失语义一致。
- [ ] EventBus广播、容量上限、缺口和进程退出边界清楚。
- [ ] Snapshot深层不可变、时序/老化正确，数据存储不阻塞core。
- [ ] SQLite事务/唯一键/查询/故障恢复验证通过。
- [ ] 200→150、离线恢复、5分钟历史、重启保留全部演示通过。
- [ ] README用Windows Python可复现，runtime/不入库，无真实设备操作。
- [ ] 回答Tag与样本、驱动边界、总线广播、快照一致性、质量时间、历史事务、异常恢复的学习问题。
- [ ] 用户确认M01；不将仿真称作商用或现场验收，不自动进入M02。
