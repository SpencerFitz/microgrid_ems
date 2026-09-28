# M0.1.2 契约用法

本目录中的样例是静态教学数据，不是采集结果。`python ems.py demo-contracts` 读取并验证样例，不启动设备、消息总线或数据库。

## 对象与 JSON

`ems.domain` 导出 Site、Device、TagDefinition、TelemetrySample、TelemetryEnvelope、SnapshotValue、SystemSnapshot 和对应枚举。对象为 frozen dataclass；嵌套映射复制成只读映射，集合为 tuple。Python 构造用 snake_case、枚举对象和 aware UTC datetime；JSON 用 lowerCamelCase、枚举字符串和以 Z 结尾的 UTC 时间。

```python
from pathlib import Path
from ems.domain import TagDefinition, TelemetryEnvelope

tag = TagDefinition.from_json(Path('contracts/examples/soc_tag.json').read_text(encoding='utf-8'))
event = TelemetryEnvelope.from_json(Path('contracts/examples/telemetry_good.json').read_text(encoding='utf-8'))
sample = event.payload.validate_against(tag)
print(sample.value, sample.quality)
print(event.to_json())
```

入口分两层：`from_json/from_dict` 检查字段、枚举、UTC、有限数、单位、身份内部一致性等；`validate_against(tag)` 进一步检查点表的身份、configVersion、单位、数据类型与取值范围。后续 Gateway 必须调用第二层，不能把“单个样本结构合法”当成“符合站点点表”。直接 Python 构造也执行同样的对象校验。

FLOAT64 接受 JSON 整数或小数，INT64 只接受 Python 整数且限定有符号 64 位，bool 不当数字。GOOD 必须有值；OFFLINE 等非 GOOD 可保留旧值或 null。字符串字段暂不允许空白内容。缺键与显式 null 只在允许的可选字段等价；序列化可能补出 null，时间小数位也可能规范化，因此比较语义而非文本字节。

## Schema 的保证范围

`jsonschema/*.schema.json` 使用 JSON Schema Draft 2020-12。每个对象的入口文件引用同目录 `domain.schema.json`，移动时须保留整个目录。Schema 声明字段结构、必填项、枚举、单位、基本数值界限、GOOD 不为 null、SOC 界限与版本号；它是静态结构契约。

跨字段比较（如 sampling < stale < offline、ID 前缀、快照引用存在性、单位匹配）以及与外部点表的关联由 Python 领域对象校验。标准 JSON Schema 的 integer 可包括 1.0；本项目 Python 解析器对整数域更严格，要求 JSON 整数字面值。这是明确的输入收紧，不能只通过 Schema 就跳过 Python 校验。

项目保持零第三方依赖。`tests/test_schema_examples.py` 只离线检查本仓库使用的 Schema 关键字及正反样例，遇到未支持关键字会失败；它不是通用 Schema 验证器，也没有完成官方元模式或标准符合性测试。生产入口依赖领域对象校验，不依赖该测试辅助函数。

## 快照边界

快照目前只是不可变数据类型。grid/load/pv/ess/ev 使用 `属性名 → tagId` 引用，权威值、单位、时间、质量在 tags 中。映射允许为空，缺失不能自动补零。样例只有 SOC 和显式缺失的 PCC，故为 INCOMPLETE，controlEligible 永远 false。

M0.1.6 才实现必需点清单、质量老化、ageMs 计算、截点选择、去重/乱序和聚合计算；当前不把手填快照当作这些算法已经通过验证。calculatedPcc/balanceResidual 为可选带质量数值，当前不计算。DeviceCapability、Proposal、Command、SchedulePlan 等继续只保留设计文档。
