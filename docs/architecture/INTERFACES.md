# Python / Windows 模块接口

版本 baseline-pywin-0.2。字段语义以 [DOMAIN_MODEL.md](DOMAIN_MODEL.md) 为准；本文件替代旧部署的通信机制。M01不用HTTP服务间调用，也不启动消息或数据库服务器。

## 1. 统一契约

Python内部snake_case；JSON导入/导出及消息封装lowerCamelCase；时间UTC RFC3339，单位/符号不变。使用dataclass/Enum/Protocol表达领域与接口；禁止跨模块修改对方内部字典。不可变对象需要深层不可变映射/tuple，不能只加frozen=True后保留可变dict。
异常按ConfigError、ValidationError、Unavailable、Timeout、Conflict等显式类型表达；Application Facade再转换为用户可读结果。M0.1.1只实现配置错误和实例冲突，其他在进入步骤时增加。

## 2. EventBus（M0.1.5实现）

topic保留五段格式 `ems.<site>.<domain>.<entity>.<event>`，仅作为本地事件名称，不是外部服务器地址。

| topic | 生产者→消费者 | 阶段 |
|---|---|---|
| ems.site01.telemetry.ess01.updated | Gateway→Snapshot、Historian | M01 |
| ems.site01.device.ess01.connected/disconnected | Gateway→状态缓存、后续告警 | M01 |
| ems.site01.snapshot.current.updated | Core→CLI/后续GUI | M01 |
| ems.site01.command.ess01.requested | CommandManager→Gateway | M03 |
| ems.site01.command.ess01.accepted/completed | Gateway→CommandManager | M03 |
| ems.site01.command.ess01.state_changed | Core→Audit/GUI | M03 |
| ems.site01.plan.dayahead.created/activated | Core→GUI/Dispatch | M05 |
| ems.site01.mode.current.changed | Core→GUI/Audit | M07 |

封装：schemaVersion、messageId、eventType、siteId、producer、publishedAt、correlationId、payload。核心遥测示例：

```json
{
  "schemaVersion": 1,
  "messageId": "msg-demo-001",
  "eventType": "telemetry.updated",
  "siteId": "site01",
  "producer": "device_gateway",
  "publishedAt": "2026-09-24T00:00:00.050Z",
  "correlationId": "poll-demo-001",
  "payload": {
    "sampleId": "sample-demo-001",
    "siteId": "site01",
    "deviceId": "ess01",
    "tagId": "site01.ess01.soc",
    "value": 60,
    "timestamp": "2026-09-24T00:00:00Z",
    "receivedAt": "2026-09-24T00:00:00.040Z",
    "quality": "GOOD",
    "qualityTimestamp": "2026-09-24T00:00:00Z",
    "unit": "%",
    "source": "SIMULATOR",
    "producerEpoch": "gateway-demo-001",
    "sequence": 1,
    "configVersion": "python-windows-v1"
  }
}
```

### 投递保证与失败

- 每订阅者独立queue.Queue，默认maxsize=1000；publish对每个订阅者返回投递成功/队列满结果，不无限阻塞。
- 队列满时拒绝该订阅者本次投递、增加dropped计数并记录gap；其他订阅者继续收到。内存总线不是可靠历史仓库。
- 不提供跨重启重放或durable consumer。进程重启后从新仿真采样重建Snapshot；未取得必需新鲜数据前禁控。
- M01故意重注入重复/乱序消息，消费者按sampleId与时序规则处理。重复不依赖总线自动消除。
- Historian消费后在自己的有界待写队列保留未提交批次；事务失败有限退避1/2/5s，超过缓存能力记录缺口，不阻塞core。重试复用sampleId，SQLite唯一键幂等。
- 非法schema/topic/身份消息写隔离JSONL记录并计数；隔离写失败单独诊断，不能伪装已入库。
- 命令不能沿用“队列满丢弃遥测”规则；M03需持久化状态、失败反馈和授权重试，危险操作不自动重放。
- 所有后台线程支持停止信号/有限join，不得用daemon线程静默丢失待提交数据后声称优雅退出。

## 3. Python边界（按步骤实现）

```python
# 下列 Protocol 及非领域辅助返回类型在对应组件步骤实现；此处仅是设计签名。
class DeviceDriver(Protocol):
    def connect(self) -> None: ...
    def read(self) -> tuple[RawMeasurement, ...]: ...
    def close(self) -> None: ...

class TelemetryPublisher(Protocol):
    def publish(self, sample: TelemetrySample) -> PublishResult: ...

class SnapshotBuilder(Protocol):
    def apply(self, sample: TelemetrySample) -> None: ...
    def build(self, cutoff_time: datetime) -> SystemSnapshot: ...

class Historian(Protocol):
    def append(self, samples: tuple[TelemetrySample, ...]) -> None: ...
    def query(self, query: HistoryQuery) -> HistoryPage: ...
```

Gateway在M0.1.4先使用RecordingPublisher；M0.1.5替换为EventBus适配器。Simulator通过Python适配器read/set_scenario/set_connection提供输入和故障；测试setter不经过控制链，也不伪装成EMS控制器。
轮询1000ms、超时800ms、STALE3000ms、OFFLINE5000ms。调用时限必须可取消/隔离，不能仅在阻塞调用返回后测时。M01仿真适配器使用可注入Clock/故障行为，真实协议不实现。
原始配置JSON；历史查询时间区间[from,to)，按timestamp/sampleId排序，分页默认100最大1000。

## 4. 命令与计划（M03以后）

ApplicationFacade.submit_command意图字段：siteId、deviceId、action、parameters、reason、confirmationToken、idempotencyKey；身份从会话获得，不能信任界面自报priority/userId。
Facade→Core产生Proposal→Arbiter→Interlock→CommandManager→Gateway模拟动作。
接受回执accepted只表示入执行流程；设备回执EXECUTED/REJECTED/FAILED；最终SUCCEEDED由Core使用有效遥测核验。commandId重复不执行，过期不执行，未知结果不盲重试。

ForecastService.submit_job：siteId、target、startTime、horizonMinutes、intervalMinutes、model→jobId。get_job返回状态/forecastId/error；get_series返回ForecastSeries。缺数不能填零冒充成功。
OptimizationService.submit_dayahead：站点、预测ID、电价ID、约束版本、SOC0、窗口/分辨率→jobId；完成返回候选SchedulePlan，不能自激活。
submit_intraday增加snapshotId、activePlanId、最新预测；默认4h/15min窗口。Core.validate_plan/approve_plan/activate_plan负责状态、权限、时效与原子版本替换；Dispatch只转换当前点为Proposal。
GUI通过Facade请求/查询和订阅视图事件，主线程不等待求解。Python算法子进程用multiprocessing.Queue/Pipe传可序列化对象，结果附jobId和截止时间；超时交给Core降级。

## 5. 对外接口范围

REST/WebSocket/MQTT是原产品北向能力目标，仿真版先以Facade与Python测试客户端表达相同用例。M09若要演示网络接口，使用Python本机loopback实现并单独验收，不成为M01启动依赖，不要求浏览器前端或外部broker。
站点/用户授权、查询分页、错误、命令幂等与计划版本语义沿用领域基线；所有对外控制仍走完整控制链。不能将Facade单元测试冒充网络协议验收。

## 6. 当前 CLI（M0.1.1～M0.1.2）

| 命令 | 含义 |
|---|---|
| python ems.py doctor | 检查Windows/Python/SQLite，GUI未检查 |
| python ems.py validate | 严格校验configs/site/demo.json |
| python ems.py run --ticks 3 | 三次bootstrap心跳后停止；不是三次遥测采样 |
| python ems.py run | 前台持续运行，Ctrl+C退出 |
| python ems.py status | 状态记录+Windows实例锁+5s新鲜度判断，陈旧记录不当活跃 |
| python ems.py demo | 两次启动/停止，验证SQLite启动标记保留 |
| python ems.py demo-contracts | M0.1.2：静态 JSON 校验、往返与 GOOD/OFFLINE 对比，无采集 |

全局参数 --config/--data-dir 放在子命令前。错误输出stderr JSON并返回1；参数错误返回2。数据目录独占锁由Windows在进程退出时释放，不能通过删除锁文件绕过正在运行的实例。
