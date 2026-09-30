# 核心领域模型与不变量

版本：baseline-pywin-0.2。五个冻结语义对象为 TelemetrySample、SystemSnapshot、ControlProposal、Command、SchedulePlan。冻结表示不能随意改变含义，不表示本文件已是生成的 JSON Schema；Schema 在对应阶段实现并验证。
本文件是字段语义权威，线格式与 API 见 [INTERFACES.md](INTERFACES.md)。原设计的简化结构补齐了质量、关联 ID、去重和时间语义，属于 [架构补充约定](../../ARCHITECTURE.md)。

## 1. 通用类型与规则

线格式 JSON 使用 lowerCamelCase；Python 内部使用 snake_case，通过显式序列化映射保持一致。领域对象使用 dataclass/Enum；不可变映射与tuple保证深层不可变。
`?` 表示可选或可空，具体说明优先；没有 `?` 的字段必填。数字必须有限，禁止 NaN/Infinity。

| 类型 | 规则 |
|---|---|
| ID | 非空字符串；持久化对象全局唯一 UUID 或同等唯一标识；示例短 ID 只用于文档 |
| SiteID / DeviceID | 小写字母、数字、下划线、连字符；不得含点、空白、事件 topic 通配符；DeviceID 在站内唯一 |
| TagID | `{siteId}.{deviceId}.{property}`，如 site01.ess01.active_power；property 用 snake_case，无点 |
| Time | UTC RFC3339，输出 Z，可保留毫秒；持续时间用明确 Ms/Seconds/Minutes 字段 |
| Value | number / boolean / string / null；由 TagDefinition.dataType 限定 |
| Unit | kW、kvar、kWh、V、A、Hz、%、°C；无量纲用 1；不能混用 W/kW 或 SOC 0～1/0～100 |

功率：PCC 正购电、ESS 正放电、PV 正发电、Load/EV 正消耗。`P_PCC = P_Load + P_EV - P_PV - P_ESS`，Load 不包含 EV。测量误差、损耗用 residual 表达，不修改实测量强行配平。

对象引用必须属于同一站点；配置对象有 `configVersion`。消息有 `schemaVersion`，两者含义不同。

## 2. Site、Device、TagDefinition

| 对象 | 字段 | 规则 |
|---|---|---|
| Site | id,name,timezone,pccDeviceId,ratedPowerKw,gridImportLimitKw,gridExportLimitKw,configVersion | timezone 为 IANA 时区；进/出口容量用非负数表达，PCC 下界为 -gridExportLimitKw |
| Device | id,siteId,name,type,vendor,model,driver,protocol,enabled,status,configVersion | status 为 DISABLED/DISCONNECTED/CONNECTING/ONLINE/DEGRADED；连接 ONLINE 不代表全部点有效 |
| TagDefinition | id,siteId,deviceId,name,dataType,unit,writable,minValue?,maxValue?,deadband,samplingIntervalMs,staleAfterMs,offlineAfterMs,source,configVersion | min≤max；0<采样周期<stale<offline；deadband≥0；身份/单位随配置版本管理 |

Device.type：GRID_METER、METER、PV_INVERTER、ESS_PCS、BMS、EVSE、MGCC、PLC、BREAKER、WEATHER。M01 用 PV/ESS/Load/PCC，ESS 模拟模型可输出 SOC，但不声称已实现真实 BMS 协议。
Tag.dataType：FLOAT64、INT64、BOOL、STRING；分类可附 kind=AI/DI/COUNTER/CALCULATED。
source 表明 DRIVER/CALCULATED/MANUAL；驱动模式 SIMULATOR 另在遥测 provenance 标明，不以 BAD 代替“模拟”。
比例、偏移、字节序、原始单位与地址属于设备模板映射；标准化后 Telemetry.value 必须符合 Tag.unit。
计数器回卷/复位显式处理；不得把差分负值直接累计为负电量。
M01 每个成功采样周期都发布样本，不启用 deadband 抑制。后续若启用变化抑制，必须另有新鲜度心跳与质量变更事件，不能使常量点被误判 STALE。

## 3. TelemetrySample（冻结）

| 字段 | 类型 | 语义 |
|---|---|---|
| sampleId | ID | Gateway 创建，重传保持不变；不是消息序号 |
| siteId/deviceId/tagId | string | 三者与配置和 subject 一致 |
| value | Value | null 表示没有可用数值；不得用 0 代替 |
| timestamp | Time | 本数值最近一次实际采样时间；无首次样本时为质量事件时刻且 value=null |
| receivedAt | Time | Gateway 收到采样/检测事件的时刻 |
| quality | QualityCode | 本次数据/质量事件的质量 |
| qualityTimestamp | Time | 本质量被判定的时刻；断线不能把旧 value 的 timestamp 更新成现在 |
| unit | string | 与 TagDefinition 相同 |
| source | string | 生产驱动或 SIMULATOR/MANUAL 等来源 |
| producerEpoch | string | Gateway 每次进程启动的唯一标识 |
| sequence | integer | 同一 epoch、同一 Tag 的事件递增序号，包括质量事件 |
| reason? | string | 质量异常或人工置数原因 |
| configVersion | string | 解析所用配置版本 |

### 质量状态

| 码 | 含义 | 自动控制资格 |
|---|---|---|
| GOOD | 类型/范围/时钟/采样均有效且新鲜 | 可用，仍受联锁与设备能力约束 |
| BAD | 解析失败、越界、设备无效标记等 | 不可用 |
| STALE | 未超过离线门限，但值已过新鲜期限 | 不可用 |
| OFFLINE | 明确断开或采样 age≥offlineAfterMs | 不可用 |
| MANUAL | 人工置数，保留操作者来源 | 默认不可用；显式工程策略决定，必须审计 |
| UNCERTAIN | 时钟、来源或可信度未满足约束 | 不可用 |

有效质量计算：明确断线/离线门限优先判 OFFLINE；其次 age≥stale 判 STALE；其余保留采样质量。未来时间超过允许偏差（M01 默认 1 s）判 UNCERTAIN，负 age 不用于证明新鲜。
Gateway 发连接状态及质量变更；即使 Gateway 整体停止，Snapshot 也按采样 age 独立判过期。OFFLINE 恢复只能由重新成功读取且校验有效的样本转 GOOD，连接成功本身不能转 GOOD。
若保留 last value，则保留它的 timestamp 并附新 qualityTimestamp。缺失 value=null 必须配非 GOOD。

实时缓存只接受更新的质量事件排序键 `(qualityTimestamp, receivedAt, producerEpoch, sequence)`；同 epoch/Tag 的重复或退序 sequence 丢弃。跨 epoch 不按 sequence 直接比较；先比 UTC 事件时间，异常时钟判 UNCERTAIN。过旧数值可入历史，但不能回退已接受的采样 timestamp；新质量事件可保留同一旧数值并降低质量。实施需覆盖跨重启及乱序测试。
这不是依靠 arrival time 恢复控制新鲜性；即使新事件到达，旧采样 age 仍可能 STALE/OFFLINE。

## 4. DeviceCapability

字段：id、siteId、deviceId、timestamp、validTo、quality、ratedPowerKw、maxChargePowerKw、maxDischargePowerKw、minSoc、maxSoc、chargeAllowed、dischargeAllowed、qMinKvar?、qMaxKvar?、apparentPowerKva?、constraints[]。
功率上限非负；0≤minSoc≤maxSoc≤100。禁止充电时允许充电功率为 0；禁止放电同理。能力是随 BMS/PCS 更新的运行态，不是仅铭牌数据；过期/未知能力不视为无限能力。P/Q 联合容量约束需满足设备能力曲线，不能只分别夹紧 P 和 Q。

## 5. SystemSnapshot（冻结）

| 字段 | 类型/语义 |
|---|---|
| id,siteId,cycle,coreEpoch | 快照唯一 ID、站点、进程内递增周期、core 重启标识 |
| timestamp,cutoffTime | 快照生成时间与输入截断时刻；cutoffTime≤timestamp |
| configVersion | 本周期统一配置版本 |
| operatingMode | OperatingMode；M01 只反映模拟 GRID_CONNECTED，不实现模式机 |
| tags | map<TagID,SnapshotValue>；M01 权威原始点映像 |
| grid,load,pv,ess,ev | 类型化资源视图，字段来源需可追溯到 tags |
| completeness | COMPLETE/INCOMPLETE；只表示必需 Tag 是否出现，不表示质量有效 |
| controlEligible | 所有必需控制输入 GOOD/新鲜且配置完备才 true；M01 恒 false（控制未启用） |
| missingTagIds,invalidTagIds | 数组；空数组合法 |
| calculatedPcc?,balanceResidual? | 带质量的计算值；缺失依赖不输出 GOOD；residual=实测PCC-计算PCC |

SnapshotValue：value、unit、sampleTimestamp、receivedAt、effectiveQuality、qualityTimestamp、ageMs、sampleId、source。不把资源视图裸数字当有效值。
GridState：activePowerKw/reactivePowerKvar/voltageV/frequencyHz/gridPresent/breakerState；Load/PV/EV：activePowerKw（以及需要时 Q/限额）；ESS：activePowerKw/soc/maxChargePowerKw/maxDischargePowerKw/online。每个量为 SnapshotValue 或明确引用对应 Tag；字段未知时 null + 非 GOOD。
M01 EV 可配置静态 0，必须有明确 SIMULATOR 数据源；不得因为没有 EV 设备而静默补 0。
Snapshot 发布后不可变；复制字典并转换为不可变映射/tuple；后续 Cache 更新不能改变已有 Snapshot。同周期 Controller 必须拿到同一个 id。

## 6. ControlProposal（冻结，M03 实现）

字段：id、siteId、snapshotId、source、targetDeviceId、targetProperty、kind、desiredValue?、minValue?、maxValue?、priority、validFrom、validTo、reason、correlationId、configVersion。
targetProperty 规范如 active_power_kw/reactive_power_kvar/start_stop/mode_request；离散操作的 desiredValue 可用 bool/string，数值约束仅适用于数值目标。
kind=TARGET 时 desiredValue 必需；kind=CONSTRAINT 时至少一个边界必需。约束和目标不混为“最后写入者获胜”。有效期为 [validFrom,validTo)，validTo 必须更晚。snapshotId 不匹配本周期或已过期的 proposal 不能执行。
优先级矩阵见 ARCHITECTURE.md。相同 priority 采用配置的 source 排序，再用 id 保证确定性；不得使用消息到达顺序决定控制权。
安全/设备约束取交集；对选中目标夹紧到可行区间，记录约束。空交集拒绝，生成明确失败理由。

SetpointDecision：id、siteId、snapshotId、targetDeviceId、targetProperty、finalValue、winningProposalId、appliedConstraints[]、timestamp、validTo、reason。没有可行值时不创建可执行 Decision。
InterlockRule：id、action、expression、severity、message、configVersion；选安全表达式求值机制，禁止任意 Python/JS eval。
InterlockResult：id、decisionId、snapshotId、result(ALLOW/DENY/REQUIRE_CONFIRMATION)、checkedAt、validTo、ruleResults[]、reasons[]。
确认必须绑定原请求/操作者/有效期；发命令前再次核验实时条件，旧 ALLOW 不可无限复用。

## 7. Command（冻结，M03 实现）

字段：id、siteId、deviceId、action、parameters、source、userId?、decisionId、interlockResultId、snapshotId、createdAt、expiresAt、timeoutMs、status、idempotencyKey、correlationId、reason、statusVersion。
action：START、STOP、SET_ACTIVE_POWER、SET_REACTIVE_POWER、SET_PV_LIMIT、SET_EV_LIMIT、REQUEST_MODE、REQUEST_LOAD_SHEDDING。参数有各自动作 schema，禁止任意寄存器写入接口。
SET_ACTIVE_POWER 使用 powerKw；SET_REACTIVE_POWER 使用 reactivePowerKvar；限额 limitKw≥0；REQUEST_MODE 使用 targetMode；LoadSheddingRequest 见后文。

正常生命周期：CREATED → VALIDATING → APPROVED → SENT → ACKNOWLEDGED → VERIFIED → SUCCEEDED。
- VALIDATING 可 REJECTED；APPROVED/SENT 之前可 CANCELLED；等待可 TIMEOUT；发送/执行/校验失败可 FAILED。
- ACKNOWLEDGED 仅说明 Gateway 接受。VERIFIED 需要有效遥测/设备反馈满足数值容差及持续时间，再 SUCCEEDED。
- 下发后取消只是请求，不能声明物理动作撤销；不支持撤销的操作返回冲突。
- 状态更新单调且有 statusVersion；迟到回执保存为 CommandEvent，不回退终态。
- 超时可能已实际执行，禁止自动重发非幂等动作；核验后由新授权生成新命令。
- 幂等范围 `(siteId,deviceId,idempotencyKey)`，相同参数返回原 commandId，参数冲突返回 409；Gateway 重复接收同 commandId 不重复执行。
- 去重记录需持久化并覆盖命令最大有效期/重试窗口；现场默认不支持安全自动重试时，只允许一次物理提交。
- 审计写入失败或持久化去重不可用时，危险命令不进入发送阶段。

CommandEvent：id、commandId、fromStatus、toStatus、timestamp、actor、detail、actualValue?、quality?。

## 8. ForecastSeries

字段：forecastId、siteId、target、issueTime、startTime、intervalMinutes、values[]、unit、model、version、quality、inputWindow、metrics?。
target=LOAD_POWER/PV_POWER/EV_POWER/ELECTRICITY_PRICE；前两项必做，EV 按聚合方案，电价预测仅扩展。value[i] 是 [start+iΔ,start+(i+1)Δ) 区间均值，长度×间隔决定窗口。功率预测非负；货币价格允许按项目电价规则出现负数。
24 h 窗口固定 96 个 15 min 点，与站点“自然日”在夏令时日不等价；本基线优化采用连续时长，界面按时区显示。
质量差/缺失预测不能偷偷填 0；Persistence 降级需标注 model、quality 和原因。
ForecastJob：jobId、siteId、request、status、createdAt、finishedAt?、forecastId?、error?。
JobStatus=PENDING/RUNNING/SUCCEEDED/FAILED/CANCELLED，取消是否可用由 API 返回能力决定。

## 9. SchedulePlan（冻结）与 DispatchInstruction

SchedulePlan：id、siteId、type、source、createdAt、startTime、endTime、resolutionMinutes、version、status、points[]、initialSoc、forecastIds[]、tariffId、constraintVersion、snapshotId?、validationReport、approvedBy?、activatedAt?、supersedesPlanId?。
type=DAY_AHEAD/INTRADAY/MANUAL/FALLBACK。有效区间 [startTime,endTime)；严格递增、等间隔、无缺点；N×分辨率=end-start。
PlanPoint：timestamp、essPowerKw、pvLimitKw?、evLimitKw?、pccPowerKw、soc。功率为该区间均值/执行目标，soc 为该区间结束时的 SOC，initialSoc 为首区间开始 SOC。
null PV/EV limit 表示该计划不提出限制，不表示 0；最终设备限制仍必须生效。
SOC 验证：下一 SOC = 当前 SOC + 100×(η_charge×max(-P_ESS,0) - max(P_ESS,0)/η_discharge)×Δt_h/E_kWh；容量/效率使用相同约束版本。PCC 计划检查计量边界与预测一致。

状态：CREATED → VALIDATED → APPROVED → ACTIVE → COMPLETED；被替换为 SUPERSEDED；验证/运行不成立为 FAILED。FAILED 不自动回到 ACTIVE，需要新版本。
同站同一调度通道同时只能有一个 ACTIVE 计划；日内替代当前生效窗口，旧日前计划可留作参考但不能并行争夺同一资源。激活原子化、版本检查和审计；同计划版本重复激活幂等。
DispatchInstruction：id、siteId、planId、planVersion、pointIndex、effectiveFrom、effectiveTo、targets[]、snapshotId、createdAt。只选当前区间；过期点不补执行；转为 Proposal 后再经过安全链。

## 10. Alarm、AuditEvent 与 OperatingMode

Alarm：id、siteId、sourceId、alarmCode、severity、message、raisedAt、acknowledgedAt?、acknowledgedBy?、clearedAt?、status、occurrenceCount。
状态 ACTIVE → ACKNOWLEDGED → RECOVERED；也允许 ACTIVE → RECOVERED（未确认已恢复）。恢复后确认只补 acknowledged 字段，不把状态改回活动；再次触发创建新的发生实例。等级 INFO/WARNING/MAJOR/CRITICAL。
AuditEvent：id、siteId、userId（系统动作用 service identity）、action、resourceType、resourceId、before?、after?、timestamp、result、reason、correlationId。追加写，敏感信息脱敏，不记录密码。

OperatingMode 为 STOPPED/GRID_CONNECTED/ISLAND_TRANSITION/ISLAND/BLACK_START/FAULT/MAINTENANCE。
模式请求不是模式事实；事实由 MGCC/设备有效反馈及状态机确定。ModeTransition 保存 requestId、from/to、requestedBy、条件结果、deadline、MGCC 回执、实际状态与失败原因。
基本转换：STOPPED 可请求 GRID_CONNECTED/BLACK_START/MAINTENANCE；GRID_CONNECTED 经 ISLAND_TRANSITION 到 ISLAND；ISLAND 并网同样经转换状态；BLACK_START 成功进入 ISLAND；失败进入 FAULT；维护进入前必须满足停控条件。具体工程联锁在 M07/M08 完善并验收。
BlackStartState 独立于 OperatingMode：READY/ESS_STARTING/BUS_ESTABLISHED/CRITICAL_LOAD_RESTORE/PV_CONNECT/LOAD_RESTORE/ISLAND_NORMAL/FAILED/ABORTED。恢复执行前重新检查，禁止服务器重启后从上次步骤盲目续跑。
LoadSheddingRequest：requestId、siteId、priorityGroups[]、requestedReductionKw、reason、expiresAt；重要/一般/可切负荷配置映射到 MGCC，EMS 不实现低频保护。

## 11. 配置、存储与迁移边界

- Site/Device/Tag 使用配置版本，M01 JSON 为真源；运行态与配置态分离。
- telemetry_raw 必须保存 sampleId、timestamp、qualityTimestamp、receivedAt、质量、来源、epoch/sequence 和类型化值；数字/文本/布尔列互斥，null 可表示无值。
- 历史唯一键至少为 `(timestamp,site_id,tag_id,sample_id)`，在SQLite中由复合唯一索引约束，不按时间分区；同 sampleId 必须具有相同内容，冲突隔离报告，不能静默覆盖。
- 状态变化与命令/计划审计追加保存；计划版本不原地重写历史。
- 迁移脚本由所属服务管理，集成启动统一运行；迁移失败拒绝 ready，不启动伪健康业务。
- wire schemaVersion=1 为初始版。兼容新增字段可沿用 v1；变更时间、单位、符号或必填结构必须提升版本并提供兼容方案。
- M01 只实现当前使用类型和契约测试；其余模型保留规范，禁止为“完整”提前实现控制、预测或模式服务。

## Python/Windows执行补充

本版保留全部字段、控制/命令/计划状态机与不变量；原先面向跨服务的对象也用于本地Python模块边界。SQLite保存UTC文本时间和类型化值，JSON导出语义不变。
M01只实现当前步骤所用类型；M0.1.1仅配置与启动元数据，领域类型在.2开始。当前站点时区支持Asia/Shanghai或UTC，其他IANA时区在GUI阶段引入并验证tzdata，不使用Windows本地时区悄悄替代。
历史重放是测试场景中的显式重新注入，不意味着本地EventBus具备持久消息功能；缓存满/进程崩溃的缺口必须显式记录。

## M0.1.2 实施映射（2026-09-28）

已实现 Site、Device、TagDefinition、TelemetrySample、TelemetryEnvelope、SnapshotValue、SystemSnapshot；见 [契约用法](../../contracts/README.md)。其他领域对象保留设计，未实现业务。

资源视图选用明确的 TagID 引用映射，限定属性及单位，tags 为权威带质量数据。无数据时映射可为空，不自动填零。快照当前只检查形状、引用、截点和禁控等不变量；必需点清单/质量老化/时间选择/聚合计算在 M0.1.6 实现。ageMs 暂只接受非负整数，未来时钟偏差由构建器显式处理。

Python 对象构造、from_dict、from_json 均校验；遥测还需 validate_against(tag) 检查点表关联。JSON Schema 表达结构规则，跨字段与点表规则由 Python 补充。可选字段省略后序列化可补 null；以语义一致为往返标准。详细限制及标准符合性验证范围见契约说明。

## M0.1.3 原始读数与模型状态

`ems.simulator.RawMeasurement` 是边界输入类型，字段与接口文档第7节一致；它不是 TelemetrySample，尚无Gateway接收/质量判断时间、事件ID或序列。原始读数有源时间、单位、质量，BAD可为null；通信失败直接抛异常。

`PlantState` 仅用于模拟器测试观测，含UTC时间、elapsedSeconds、各资源瞬时功率、requestedEssKw/essKw、energyKwh、soc。它不替代SystemSnapshot。Scenario/SimulatorConfig和RawMeasurement均不可变且执行字段校验，模型状态演化由Simulator持有。
