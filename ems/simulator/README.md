# Simulator 模块接口（M0.1.3）

仅使用标准库，单线程同步计算，无后台线程、轮询、网络、历史写入或控制命令。Gateway 在 M0.1.4 调用设备绑定的 SimulatedDriver。

```python
from dataclasses import replace
from pathlib import Path
from ems.simulator import load_scenario, ManualClock, Simulator, SimulatedDriver

config = load_scenario(Path('configs/scenarios/discharge.json'))
clock = ManualClock(config.start_time)
plant = Simulator(config, clock)
driver = SimulatedDriver(plant, 'ess01')
driver.connect()
clock.advance(3600)
print(driver.read())  # actual power 100kW, SOC 50%
plant.set_scenario(replace(plant.scenario, ess_kw=-100))
driver.close()
```

## 文件与类型

| 文件 | 责任 |
|---|---|
| clock.py | Clock Protocol、ClockReading、ManualClock/SystemClock |
| config.py | Scenario、SimulatorConfig、严格 JSON 场景读取 |
| model.py | Simulator、只读 PlantState、RawMeasurement、SimulatedDriver、通信故障 |
| demo.py | 自动验证固定教学步骤；单次自定义场景演算 |

Clock.read() 同时返回 UTC timestamp 和单调秒数。能量积分只用单调时间；UTC只标注原始读数。ManualClock从场景 startTime 起步，advance以微秒分辨率向前推进，每次上限一年。SystemClock可注入真实时钟，config.startTime不会重设系统时间；同样不启动调度器。自定义Clock单调时间倒退时拒绝读取，UTC校时不影响能量积分。

config 固定容量、初始SOC、额定功率、seed、站点/配置版本。set_scenario只改变不可变Scenario（loadKw/pvKw/essKw/evKw/pvVariationKw），不重置时间或能量。先将旧工况积分到变更时刻，再切换工况；非法新工况被拒绝且不修改原状态。

能量计算以最近一次场景变更为锚点，查询不反复累加，因而不依赖查询次数。E限制到[0,capacity]；触及满/空边界后对应方向实际功率为0，反方向可以恢复。PlantState明确区分requestedEssKw与essKw。PCC使用实际瞬时ESS功率和当秒PV值。效率固定1，不模拟保护动作。

## 数据输出

`read(device_id)` 返回 tuple[RawMeasurement, ...]，ESS两个点，其他设备一个点。字段：siteId、deviceId、property、value、unit、timestamp、quality、source、configVersion。property仅active_power/soc，单位kW/%；source=SIMULATOR，GOOD值不为null。RawMeasurement为冻结对象且可JSON往返。

RawMeasurement是适配器原始读数，不包含sampleId、receivedAt、qualityTimestamp、producerEpoch、sequence；这些由后续Gateway生成。当前不发布TelemetryEnvelope，不自行执行去重/老化/缓存。inspect_state是测试观测口，可绕过通信故障检查物理状态，Gateway和未来UI不能把它当正常遥测来源。

## 故障语义

| 实验接口 | 结果 |
|---|---|
| set_connection(device_id, False) | connect/read抛DeviceUnavailable，物理模型持续 |
| set_connection(device_id, True) | 仅恢复可读性；下一次成功read才产生新测量 |
| set_fault(device_id, ReadFault.TIMEOUT) | read立即抛SimulatedTimeout，不制造真实等待 |
| set_fault(device_id, ReadFault.BAD_DATA) | read返回BAD/null，时间为本次原始读取时间 |
| set_fault(device_id, ReadFault.NONE) | 清除该设备读故障，不影响连接开关 |

设备间故障隔离；连接失败优先于TIMEOUT/BAD_DATA。close只关闭适配器读取权限，既不停止物理模型，也不解除通信故障。配置变化、种子、连接与故障设置仅用于教学/测试；不向控制器暴露绕过控制链的命令接口。

## 配置限制

UTF-8/BOM JSON，最大64KiB，未知/缺失/重复键拒绝。严格整数版本1、seed为uint32；有限数且bool不能冒充数字。SOC为[0,100]；容量(0,1e9]kWh，功率额定/Load/EV/PV等为[0,1e6]kW，ESS位于配置充放电额定界限内。PV整个扰动范围必须在[0,pvRatedKw]。这些是数值输入界限，不是工程性能承诺。

场景结构由Python解析器校验；本步没有为新场景增加JSON Schema。M0.1.2已有契约Schema保留不变。
