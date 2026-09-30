# microgrid_ems — Python / Windows 仿真版

当前 **M0.1.3 / READY_FOR_REVIEW**，软件版本0.1.3.dev1。M0.1.1和M0.1.2已获用户确认；本步加入可重复运行的设备模拟器，等待本机验收。

## 本机运行

Windows 10/11、Python 3.12+，仅标准库，无需安装外部服务或第三方包。解压后在microgrid_ems目录运行：

```powershell
python ems.py doctor
python -m unittest discover -s tests -v
python ems.py demo-simulator
```

预期READY_M01、43项测试OK、Demo结果PASS。虚拟时间会直接推进，不需要等实际一小时。使用Python启动器时，可将python替换成 `py -3.12`。

自选放电场景：

```powershell
python ems.py simulate --scenario configs/scenarios/discharge.json --seconds 3600
```

应得到SOC从60%到50%、PCC为50kW。详细实验、预期数值、更新仓库及验收见 [M0.1.3学习指南](docs/learning/M0.1.3_LEARNING.md)，实际验证见 [验证记录](docs/learning/M0.1.3_VALIDATION.md)。请先本机验证，再同步GitHub。

## 当前做到了哪里

| 阶段 | 已实现 |
|---|---|
| M0.1.1（已验收） | 配置/日志/Windows实例锁/启动停止/状态/SQLite启动元数据 |
| M0.1.2（已验收） | 不可变领域对象、JSON契约/样例、字段/点表关联校验 |
| M0.1.3（待验收） | 理想PV/Load/ESS/PCC/EV、能量与SOC、虚拟时钟/seed、原始读取/通信故障 |

本步数据流：场景JSON + 时间 → 物理模型 → RawMeasurement → CLI。当前每类资源一个聚合设备，效率1；尚无自动轮询、消息总线、快照构建器、历史遥测、GUI或控制策略。

PCC=Load+EV−PV−ESS。ESS正值放电、负值充电；PCC正值购电、负值送电；Load不含EV。满/空电时模型实际功率饱和到0；通信断开只阻断读接口，不停止物理演化。

## 命令说明

| 命令 | 用途 |
|---|---|
| python ems.py doctor | 检查Windows/Python/SQLite；不验证GUI |
| python ems.py validate | 校验configs/site/demo.json启动配置 |
| python ems.py demo | 两轮bootstrap启动/停止，验证启动元数据保留 |
| python ems.py run --ticks 3 | 三次bootstrap心跳后停止，不是遥测采样 |
| python ems.py run | 持续bootstrap心跳，Ctrl+C停止 |
| python ems.py status | 最后状态结合实例锁与5s新鲜度判断 |
| python ems.py demo-contracts | M0.1.2静态GOOD/OFFLINE样例校验 |
| python ems.py demo-simulator | M0.1.3功率/SOC/断线恢复自动验证 |
| python ems.py simulate --scenario 路径 --seconds 秒数 | 从场景初始状态推进虚拟时间，返回瞬时状态/读数 |

全局--config/--data-dir放在子命令前；simulate的--scenario/--seconds放在simulate后。bootstrap配置与模拟场景不同。新模拟命令不写runtime；旧run/demo仍只演示生命周期，尚未接入模拟器轮询。

成功退出0，参数/运行错误非零。SQLite当前仅bootstrap_meta，不是Historian。状态文件不可单独当健康依据。运行数据、日志、Python缓存不入Git；已跟踪产物需单独取消跟踪，.gitignore不会自动清除。

## 目录导航

```text
microgrid_ems/
├── AGENTS.md / ARCHITECTURE.md / README.md / MIGRATION.md
├── ems.py / pyproject.toml
├── ems/
│   ├── cli.py / config.py / runtime.py
│   ├── domain/            # M0.1.2 契约
│   └── simulator/         # M0.1.3 模型、时钟、配置、适配器、Demo
├── configs/
│   ├── site/demo.json     # bootstrap配置
│   └── scenarios/         # 初始/放电场景
├── contracts/             # 领域JSON Schema与静态样例
├── tests/                 # 基础、契约、Schema样例、模拟器测试
└── docs/
    ├── product/ / architecture/
    ├── roadmap/ / milestones/
    └── learning/          # 各步学习指南与验证证据
```

规则见 [AGENTS.md](AGENTS.md)，模型接口见 [Simulator说明](ems/simulator/README.md)，当前门禁见 [CURRENT_STAGE.md](docs/roadmap/CURRENT_STAGE.md)。本轮不自动更新GitHub，也不提前进入M0.1.4 Gateway。
