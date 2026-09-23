# 服务间接口与消息契约

版本：baseline-0.1。字段语义遵循 [DOMAIN_MODEL.md](DOMAIN_MODEL.md)。这是待实现的规范，所有示例均非运行证据。M01 只实施表内标记为 M01 的接口。

## 1. 通用约定

- 对外 `/api/v1`，实时 `/ws/v1/realtime`；api-server 是唯一对外业务入口。
- 内部同步使用 REST，异步使用 NATS JetStream；M01 不实现 gRPC/protobuf。
- UTF-8 JSON，lowerCamelCase，时间 UTC RFC3339，ID/单位/正负方向按领域文档。
- HTTPS/TLS、服务身份、站点授权；M01 仅开发隔离网络，内部端口仅绑定本机，不以此代表生产安全完成。
- 所有请求关联 `X-Request-Id`；写请求携带 `Idempotency-Key`，同站点/主体/路径/键且 body 相同返回原结果，不同 body 返回 409。
- 请求设 deadline；M01 普通只读请求默认 2 s，Gateway 仿真轮询默认 800 ms（小于 1 s 采样周期）；未来算法为异步 job，不占用控制循环。
- 400 格式错误；401 未认证；403 未授权；404 未找到；409 版本/幂等/状态冲突；422 领域约束失败；429 限流；503 暂不可用。不得用 HTTP 200 隐藏业务失败。
- 错误格式：`{"error":{"code":"TAG_UNKNOWN","message":"Unknown tag","requestId":"req-demo","details":{}}}`。不泄露凭据或堆栈。
- 列表为 `items[]、nextCursor?`；limit 默认 100、最大 1000，稳定排序；历史时间范围 [from,to)，最大窗口按配置，超限 422。
- 配置/计划写入使用 expectedVersion 或 If-Match，冲突返回 409；不能静默覆盖新版本。

## 2. NATS Subject 与所有权

固定格式：`ems.<site>.<domain>.<entity>.<event>`，五段。禁止把任意 TagID 整段塞进 entity。

| Subject 示例/模板 | 生产者 | 消费者 | Payload | 阶段 |
|---|---|---|---|---|
| ems.site01.telemetry.ess01.updated | Gateway | core、data-service | TelemetrySample | M01 |
| ems.site01.device.ess01.connected / disconnected | Gateway | core、data-service（后续告警） | DeviceConnectionEvent | M01 |
| ems.site01.snapshot.current.updated | core | 本地诊断/后续 api-server | SystemSnapshot | M01 |
| ems.site01.command.ess01.requested | core Command Manager | Gateway | CommandRequest | M03 |
| ems.site01.command.ess01.accepted | Gateway | core | CommandAccepted | M03 |
| ems.site01.command.ess01.completed | Gateway | core | DeviceExecutionResult | M03 |
| ems.site01.command.ess01.state_changed | core | data-service、api-server | CommandEvent | M03 |
| ems.site01.control.proposal.created | core | 诊断/审计订阅者 | ControlProposal | M03 |
| ems.site01.alarm.pcs01.raised / acknowledged / recovered | data-service | api-server | Alarm | M02 |
| ems.site01.plan.dayahead.created / activated / superseded | core | API、优化、数据服务 | PlanEvent（id/version/status） | M05 |
| ems.site01.plan.intraday.created / activated / superseded | core | 同上 | PlanEvent | M06 |
| ems.site01.mode.current.changed | core | API、数据服务 | ModeTransition | M07 |
| ems.site01.audit.operation.recorded | 业务服务 | data-service | AuditEvent | M03/M09 |
| ems.site01.config.current.changed | api-server | 各运行服务 | ConfigChanged(version,hash) | M09 |

Core 内 Controller→Arbiter 使用同步函数调用，不依赖 NATS 回送本进程以完成控制；proposal 事件供观察。NATS 同一消息可被多个 durable 独立消费。
命令 subject 的发布权只授予 core；预测、优化、UI、MQTT 外部用户无发布权限。MQTT 的控制请求先经 api-server 授权再进入 core，不直通 NATS command。

### 标准消息封装

```json
{
  "schemaVersion": 1,
  "messageId": "msg-demo-001",
  "eventType": "telemetry.updated",
  "siteId": "site01",
  "producer": "device-gateway",
  "publishedAt": "2026-09-23T06:00:00.050Z",
  "correlationId": "poll-demo-001",
  "payload": {
    "sampleId": "sample-demo-001",
    "siteId": "site01",
    "deviceId": "ess01",
    "tagId": "site01.ess01.soc",
    "value": 60,
    "timestamp": "2026-09-23T06:00:00Z",
    "receivedAt": "2026-09-23T06:00:00.040Z",
    "quality": "GOOD",
    "qualityTimestamp": "2026-09-23T06:00:00Z",
    "unit": "%",
    "source": "SIMULATOR",
    "producerEpoch": "gw-epoch-demo",
    "sequence": 1,
    "configVersion": "demo-v1"
  }
}
```

重传保持 messageId、sampleId、payload 不变，设置 `Nats-Msg-Id=messageId`。质量变更是新样本事件，新的 ID/sequence，数值可保留旧值和原 timestamp。Schema 和 subject/site/device 不一致的消息隔离，不能进入实时缓存。
DeviceConnectionEvent：deviceId、status、timestamp、reason、producerEpoch、sequence。连接恢复通知先到时，数据质量仍等有效采样才恢复 GOOD。

## 3. JetStream 投递、重试和恢复（M01 实现部分）

本表为本次可复现实验默认值，非现场留存承诺。配置必须显式，不能依赖不可见默认设置。

| 流 | Subjects | M01 默认策略 |
|---|---|---|
| EMS_TELEMETRY | ems.*.telemetry.*.updated、ems.*.device.*.* | 文件存储、Limits retention、MaxAge=24h、MaxBytes=1GiB、超限 DiscardOld、重复窗口 2min |
| EMS_SNAPSHOT | ems.*.snapshot.*.updated | 文件存储、MaxAge=10min、MaxBytes=128MiB、DiscardOld |
| EMS_COMMANDS（M03） | ems.*.command.*.* | 独立持久化、按命令保留/审计策略配置，不沿用遥测过期策略 |

- durable `core-site01-telemetry` 与 `historian-site01-telemetry` 分离，AckExplicit；AckWait=30s，MaxAckPending=1000。core 缓存处理后 ACK，Historian 在数据库事务提交后 ACK。
- 正常应用关闭 drain；应用崩溃允许重投。JetStream 去重窗口不等于永久 exactly-once；业务必须基于 sampleId 去重。
- DB 暂时错误采用有界退避 1/2/5/10/30s，延迟 NAK，无限消息投递次数由配置显式允许，应用无无限内存队列；重试仅在流保留时间/容量内可恢复。
- 永久格式/未知 schema 错误：写持久化隔离记录（原消息、错误、时间、subject），成功后 TERM/ACK；隔离失败不确认并报警诊断。不得静默丢弃。
- Gateway 断总线本地内存队列上限 10,000 事件，满时丢最旧遥测并增加 droppedSamples；恢复逐条重发原 ID。M01 不保证 Gateway 崩溃时未发布队列不丢失，明确记录限制。
- 达到保留时间/容量造成的数据缺口必须报告；24h 只是上限条件之一，不承诺 1GiB 一定容纳 24h。
- core 重启从已有 durable 的未确认位置继续；已确认最新值通过初始化历史重放重建：使用临时独立重放 consumer 读取流中保留遥测到启动水位，再与 live 消费按排序合并。禁止启动控制直至必需点新鲜。
- 重放和 live 在缓存层幂等；历史已确认数据不能因 core 重放被重复插入数据库。M01 接口诊断暴露 recovering/degraded 状态。
- M0.1.5 先验证发布/独立测试订阅者；正式 core 和 Historian durable 分别在 M0.1.6/7 接入。

## 4. M01 进程内与仿真接口

以下端口是 Compose 内服务端口；本机映射仅用于开发。不存在生产控制权。

| 接口 | 输入/输出 | 拥有者/约束 |
|---|---|---|
| GET :8081/healthz、/readyz | liveness 200；依赖/配置就绪 200，否则 503 | Gateway；NATS 断开为 degraded/503，但继续有界采样 |
| GET :8082/healthz、/readyz | 同上，ready 表示 Snapshot 管线初始化完成 | core；DB 不属于其就绪依赖 |
| GET :8083/healthz、/readyz | 同上；DB/NATS 异常 ready 503 | data-service |
| GET :8090/healthz | 仿真进程健康 | Simulator |
| GET :8090/sim/v1/devices/{deviceId}/measurements | `{deviceId,timestamp,values:[{property,value,unit,quality}]}` | 仿真物理量；Gateway 负责补 Tag/ID/标准化 |
| PUT :8090/sim/v1/scenario | `{loadPowerKw,pvPowerKw,essPowerKw,essSoc,evPowerKw}`→场景状态 | 本地测试专用；不是 EMS 控制接口 |
| PUT :8090/sim/v1/devices/{id}/connection | `{online:false}`→状态 | 故障注入；轮询离线设备返回 503 |
| GET :8082/internal/v1/snapshots/current?siteId=site01 | SystemSnapshot；尚未生成返回 503 | CLI/Demo 读取，无写接口 |
| GET :8083/internal/v1/telemetry?siteId=...&tagId=...&from=...&to=...&limit=... | `{items:[TelemetrySample],nextCursor?}` | 只读 Historian；按 timestamp/sampleId 稳定排序 |

Simulator 的 setter 只用于设定实验条件，默认与 Gateway/核心网络隔离的外部生产部署不得启用。离线注入以 503/超时模拟，不能直接向 core 写 quality。

进程内 Go 接口（实现时可增加 context，禁止跨服务导入实现）：

```text
Driver.Connect(ctx) error
Driver.Read(ctx) ([]RawMeasurement, error)
Driver.Close(ctx) error
TelemetryPublisher.Publish(ctx, sample) error
SnapshotBuilder.Apply(sample) error
SnapshotBuilder.Build(cutoffTime) (SystemSnapshot, error)
Historian.Append(ctx, samples) error
Historian.Query(ctx, filter) (Page, error)
```

M0.1.4 使用可注入 recording Publisher 验证 Gateway，M0.1.5 替换为 NATS 实现；前一步不提前要求真实总线。Scheduler/Clock 可注入，质量阈值测试不依赖长时间 sleep。

## 5. Command 接口（M03）

外部 `POST /api/v1/commands` 表达用户意图：siteId、deviceId、action、parameters、reason、confirmationToken?。身份由认证上下文获得，禁止信任 body 自报 userId/priority。
api-server→core `/internal/v1/command-intents`，执行授权、Proposal、仲裁、联锁与 Command Manager。202 返回 commandId、status、statusUrl；`GET /api/v1/commands/{id}` 查询生命周期。

Core 发到 `ems.site01.command.ess01.requested` 的 envelope.payload：

```json
{
  "commandId": "cmd-demo-001",
  "siteId": "site01",
  "deviceId": "ess01",
  "action": "SET_ACTIVE_POWER",
  "parameters": {"powerKw": -100},
  "decisionId": "decision-demo-001",
  "interlockResultId": "interlock-demo-001",
  "snapshotId": "snap-demo-001",
  "createdAt": "2026-09-23T06:00:00Z",
  "expiresAt": "2026-09-23T06:00:03Z",
  "timeoutMs": 3000,
  "idempotencyKey": "operator-operation-demo-001"
}
```

这里 CommandRequest.commandId 映射领域 Command.id，刻意只传执行所需字段；必须验证 core 服务身份、有效期和设备适配能力。Gateway 不仅凭请求含有 interlockResultId 就信任任意客户端。
accepted payload：`{commandId,accepted,receivedAt,reason?}`。accepted=false 由 core 转 REJECTED/FAILED。
completed payload：`{commandId,status,executedAt,actualValue?,quality?,reason?}`，status=EXECUTED/REJECTED/FAILED，刻意不使用 SUCCEEDED 避免把驱动回执误认为端到端成功。
core 用新鲜 telemetry/设备反馈验证后，发布最终 CommandEvent SUCCEEDED；数值容差/持续时间按项目配置。
传输重试复用 commandId；超过 expiresAt 不再物理执行，重启危险命令不自动重放。危急停机由独立保护实现，不能依赖此异步链路时延。

## 6. Forecast API（M04）

外部 `POST /api/v1/forecasts/jobs` → api-server 转 forecast-service `POST /internal/v1/forecasts/jobs`。
请求：siteId、target、startTime、horizonMinutes、intervalMinutes、model?；历史数据由 Data API 获取，禁止跨库轮询。

```json
{
  "siteId": "site01",
  "target": "LOAD_POWER",
  "startTime": "2026-09-24T00:00:00Z",
  "horizonMinutes": 1440,
  "intervalMinutes": 15,
  "model": "persistence"
}
```

202：`{jobId,status:"PENDING",statusUrl}`。
`GET /api/v1/forecasts/jobs/{jobId}` 返回 JobStatus、forecastId?/error?。
`GET /api/v1/forecasts/{forecastId}` 返回 ForecastSeries。
必须拒绝不能整除的窗口/间隔；预测失败不得返回成功的全零数组。job 超时返回 FAILED 并有 error.code=DEADLINE_EXCEEDED。

## 7. Optimization、Plan 与 Dispatch（M05/M06）

`POST /api/v1/optimization/day-ahead` 转内部同义任务端点，请求：

```json
{
  "siteId": "site01",
  "startTime": "2026-09-24T00:00:00Z",
  "loadForecastId": "forecast-load-demo",
  "pvForecastId": "forecast-pv-demo",
  "tariffId": "tariff-demo-v1",
  "constraintVersion": "constraints-demo-v1",
  "initialState": {"soc": 60},
  "horizonMinutes": 1440,
  "intervalMinutes": 15
}
```

202 返回 jobId；`GET /api/v1/optimization/jobs/{jobId}` 返回 status、objective?、currency?、planId?、solverStatus、error?。成功只表示求解/候选提交完成，不表示计划已激活。
优化结果经 `POST core:/internal/v1/plans` 提交候选 SchedulePlan，core 验证来源、时间网格、SOC/功率/约束后持久化，产生 CREATED/VALIDATED 事件。
`POST /api/v1/optimization/intraday` 输入 siteId、snapshotId（由服务读取不可变快照）、最新 forecastIds、activePlanId、constraintVersion、startTime、horizonMinutes=240、intervalMinutes=15；过期/不完整 snapshot 返回 422。

计划接口：

| 路径 | 行为 |
|---|---|
| GET /api/v1/plans/{planId} | 返回指定版本计划和校验结果 |
| POST /api/v1/plans/{planId}/validate | core 重新验证输入、约束与版本 |
| POST /api/v1/plans/{planId}/approve | Engineer/被授权角色批准，带 reason/expectedVersion |
| POST /api/v1/plans/{planId}/activate | 只有 core 在批准、RBAC、模式、时效、约束复查通过后原子激活 |

激活同一版本幂等；并发版本冲突 409；配置变更使约束不再成立时拒绝或使计划失效。Dispatch 仅将当前区间转换为 Proposal。API 不提供“直接执行整份优化结果到设备”的端点。

## 8. 北向 REST/WS/MQTT

| 资源 | 主要方法 | 所有者/阶段 |
|---|---|---|
| /api/v1/sites、/devices、/tags | GET；配置 POST/PATCH | api-server，M02 读/M09 完整写 |
| /api/v1/telemetry、/snapshots/current | GET，站点/Tag/时间过滤 | Data/core，M02 |
| /api/v1/alarms、/alarms/{id}/acknowledge | GET / POST | Data，M02 |
| /api/v1/commands | POST / GET | core，M03 |
| /api/v1/forecasts、/optimization、/plans | 见前文 | M04～M06 |
| /api/v1/modes/requests | POST，targetMode/reason | core，M07 |
| /api/v1/black-start/requests | POST，站点/原因/确认 | core，M08 |
| /api/v1/reports、/carbon | GET、异步生成 | Data，M09 |
| /api/v1/users、/roles、/config | 授权管理与版本化配置 | api-server，M09 完整 |

WebSocket `/ws/v1/realtime` 建连时认证，站点与 topic 授权，不能直接指定任意 NATS subject：

```json
{"action":"subscribe","siteId":"site01","topics":["telemetry","alarm","command","mode"]}
```

确认消息 `{type:"subscribed",subscriptionId,topics}`；推送 `{type,eventId,siteId,sequence,timestamp,payload}`。按连接序号检测缺口，重连先 REST 取当前快照/告警/命令，再重新订阅；客户端不假设 WS 可靠补齐历史。
慢客户端有界队列：遥测可合并为最新值，事件缺口须通知 resyncRequired；不能静默丢弃命令终态。M02 实现并测试限流/断线恢复。
MQTT M09 北向状态 topic `ems/{siteId}/telemetry/{deviceId}`，QoS1，payload 与统一 envelope 一致，消费去重。北向命令 topic 不向 Gateway 桥接；若项目启用指令接收，必须转换为 api-server CommandIntent 并执行同一授权/确认流程。

## 9. 数据一致性与接口验证

- M01 JSON Schema 包含 envelope、telemetry、device event、snapshot；examples 同时供 Go/后续 Python 契约测试。
- Telemetry 验证类型、单位、Tag/site/device、枚举、时间、非有限数值、null 质量与配置版本。
- 未识别兼容可选字段可忽略；不支持的主 schemaVersion 必须拒绝并隔离。
- 历史 DB 事务成功后 ACK；故意制造“提交成功但 ACK 丢失”，验证重投只有一条记录。
- 接收重复、乱序、重启 epoch、未来时间、断开/恢复、DB/NATS 中断；结果与领域规则一致。
- REST 契约验证状态码/分页/时间范围；命令验证权限、幂等键冲突、过期、迟到回执；WS 验证重连和事件缺口。
- 计划、命令状态和必须发送的事件在后续采用事务 outbox/等效机制避免“数据库已提交但事件丢失”；不宣称跨数据库与 NATS 原子事务。
- 后续服务进入开发前，必须补齐该接口 OpenAPI/JSON Schema、错误集合与负向测试；本次不提前实现后续服务。
