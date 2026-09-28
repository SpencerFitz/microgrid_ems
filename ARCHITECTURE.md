# EMS Python / Windows 仿真架构

版本 baseline-pywin-0.2；2026-09-24。本版根据用户“所有程序均在python/windows环境下模拟运行”替代旧部署方案，仍保留EMS V1.0业务功能目标和M01～M09/G10的学习顺序。

## 1. 本次明确变更

| 项目 | 当前采用 |
|---|---|
| 操作系统与语言 | Windows 10/11 + Python 3.12+；本次实际测试Windows11/Python3.12.14 |
| 程序组织 | Python模块化主程序；算法阶段按需增加Python子进程 |
| 内部通信 | Python接口调用 + 有界进程内EventBus（M0.1.5） |
| 历史与配置 | JSON配置；SQLite本地文件（M0.1.7业务历史） |
| 界面 | Python桌面界面，M02默认Tkinter；界面阶段再验证Tcl/Tk |
| 设备与快速控制 | 全部Python Simulator，包括设备、故障和MGCC过程 |
| 启动/测试 | python ems.py；unittest；不要求管理员安装服务器 |

M0.1.1不需要第三方依赖，使用当前已有Python即可执行。SQLite是Python调用的嵌入式存储引擎，不是另起服务。后续预测/优化库按实际需要锁定Windows兼容版本，不在M01预装。

与旧版的对应：Go→Python；Vue/TypeScript→Python GUI；NATS JetStream→本地EventBus；PostgreSQL/TimescaleDB→SQLite；六个后台进程→六个逻辑模块；Docker Compose/Linux→Windows直接启动。它们的行为并非完全等价，尤其本地总线不具有默认持久化/跨机器投递保证。

## 2. 模块与数据流

```text
Python GUI / CLI
       ↓ Application Facade（鉴权、参数与用例边界）
Simulator → Gateway → EventBus ─┬→ Latest Cache → Scheduler → Snapshot
                               └→ Historian → SQLite
Snapshot → Controllers / Dispatch → Proposal → Arbiter → Interlock
          → Command Manager → Gateway → Simulator / MGCC模拟器
历史/快照 → Forecast → Optimization候选计划 → Core批准/激活
```

此图是目标数据流；M0.1.1只实现程序启动、配置、日志、实例锁、状态文件和启动元数据保留，不产生遥测、不实现EventBus。

| 模块 | 责任 | 所有权/首次实现 |
|---|---|---|
| simulator | PV/ESS/Load/PCC/EV与故障；后续MGCC状态过程 | M0.1.3；本步仅注册健康名 |
| device_gateway | 轮询仿真适配器、标准化、质量、后续模拟命令 | M0.1.4 |
| ems_core | Scheduler、Snapshot、后续控制安全链/计划/模式 | M0.1.6起；控制M03 |
| data_service | Historian、后续Alarm/Audit/Report/Carbon | M0.1.7起 |
| forecast | Load/PV预测与评估 | M04，独立Python计算任务 |
| optimization | 日前/日内求解与候选计划 | M05/M06，独立Python子进程，不得操作设备 |
| application/gui | 用例入口、权限、桌面视图 | M02起；不绕过core |

六个服务名保留为逻辑边界，不要求六个操作系统进程。M01四个组件共享bootstrap，不以它们显示READY证明业务实现。

## 3. 并发、消息与持久化边界

M01.5使用每订阅者独立有界队列，避免单队列被多个消费者竞争取走；回调不得在发布者线程同步执行昂贵工作。I/O工作线程有停止信号及join超时。快照由固定周期构建并复制为不可变数据；墙钟UTC用于采样时刻，单调时钟用于调度/超时。
SQLite由Historian单写者拥有连接；查询使用独立连接，WAL和有限busy_timeout。Core不能在控制线程等待SQLite。存储暂不可用时保留有界待写批次；超过容量明确报告缺口。进程崩溃后内存队列不可恢复，不声称持久总线语义。
命令记录和幂等在M03引入持久化，未安全记录则不执行模拟危险动作；同样不宣称“恰好一次”。
算法任务在Windows spawn子进程启动，入口有 __main__ 保护；仅传递可序列化数据，设置截止时间，子进程失败由core决定降级。主GUI线程只处理界面，任务返回通过队列交付。

## 4. 不变的控制职责

Controller只能输出Proposal；优先级Safety1000、DeviceLimit900、ManualEmergency800、MGCC700、PCC600、Demand500、Intraday400、DayAhead300、Economic200、Default100。硬约束取交集；空交集拒绝，不能由高优先级人工目标越权。
EMS负责能量/模式/流程管理；MGCC模拟器负责快速过程的行为模型。模拟时间可以加速，但不是实现真实毫秒保护。PCC实测模拟值与平衡计算值分开，Load不含EV。
掉线/过期、命令超时、无解、数据库故障、重启安全规则继续执行。仿真关闭不等于现场安全验收通过。

## 5. 当前与目标目录

```text
microgrid_ems/
├── AGENTS.md / ARCHITECTURE.md / README.md / MIGRATION.md
├── pyproject.toml
├── ems.py                    # 唯一当前启动入口
├── ems/
│   ├── __init__.py / cli.py / config.py / runtime.py  # M0.1.1已实现
│   ├── domain/               # M0.1.2起，暂未创建
│   ├── simulator/            # M0.1.3
│   ├── gateway/              # M0.1.4
│   ├── messaging/            # M0.1.5
│   ├── core/                 # M0.1.6起，后续control/arbiter等
│   ├── data/                 # M0.1.7起，后续alarm/audit/report/carbon
│   ├── application/ / gui/   # M02
│   └── forecast/ / optimization/  # M04/M05
├── configs/site/demo.json
├── tests/test_scaffold.py
├── contracts/{jsonschema,examples}/  # M0.1.2起
├── docs/{product,architecture,roadmap,milestones,learning}/
└── runtime/                  # 运行自动创建，不入库
    ├── instance.lock / status.json / logs/ems.log
    ├── state.sqlite3         # M0.1.1仅bootstrap_meta，无业务表
    └── demo_result.json
```

后续目录仅表示规划，不生成空模块或提前实现。原8个文档路径保留。

## 6. 环境和验收

本次M01使用标准库，不依赖GUI资源。当前捆绑Python能运行CLI/SQLite，但Tcl初始化缺init.tcl；M02需准备完整的Windows Python/Tcl-Tk，不能因import tkinter成功就称GUI可用。
Windows是开发和仿真验收环境；真实Modbus设备、物理规模、现场SAT、保护/硬实时和商业可靠性验证不在本轮执行。产品文档中的原商用指标保留为未来工程化参考，不能用仿真结果代替。
当前状态见 [CURRENT_STAGE.md](docs/roadmap/CURRENT_STAGE.md)，迁移操作见 [MIGRATION.md](MIGRATION.md)。
