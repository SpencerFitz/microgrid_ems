# Python / Windows 分阶段路线

版本 baseline-pywin-0.2。产品版本编号保留；M03-A/B区分基础控制和PCC。全部设备与MGCC使用Python模型，所有阶段在Windows本机仿真验证。真实工程部署需另立计划。

| 阶段/版本 | 学习与范围 | 演示/验收 |
|---|---|---|
| M01/V0.1 | 配置、领域对象、Simulator、Gateway、EventBus、Snapshot、SQLite Historian | 数据进入EMS、断线质量、历史与恢复；细分.1～.9 |
| M02/V0.2 | Python GUI、Application Facade、历史/告警、协议行为模拟 | 桌面看功率/曲线、故障确认恢复；检查Tk环境；不连接实物 |
| M03-A/V0.3 | Rule-Based、SOC/能力、仲裁/联锁/命令、权限审计 | 多策略竞争、BMS模拟限制、幂等、超时、重启不重放 |
| M03-B/V0.3 | PCC、防逆流、需量、PV/EV/ESS分配 | 仿真扰动跟踪、限幅、能力不足和失联降级 |
| M04/V0.4 | Python Load/PV预测与评估 | 日前96点、日内预测、数据缺失、基线比较 |
| M05/V0.5 | Python日前优化、计划与Dispatch | SOC/成本/约束校验、批准激活、无解降级 |
| M06/V0.6 | Python MPC，Windows子进程隔离 | 15min周期、4h窗口、只执行第一步、超时不阻塞core |
| M07/V0.7 | 模式、Python MGCC模拟器、孤岛与Q/V协调 | 并离网请求/回执、减载、拒动/超时；不做物理保护 |
| M08/V0.8 | 黑启动与分级负荷恢复仿真 | 条件检查、逐步确认、失败/中止、重启不盲续 |
| M09/V0.9 | JSON模板/配置、RBAC/Audit、报表、基础碳核算、备份 | 不改core添加模拟设备，Python界面工程配置、数据备份恢复 |
| G10/V1.0-SIM | 仿真全功能回归、性能/稳定性、Windows交付说明 | 仿真FAT/SIL证据；明确未覆盖实物/现场SAT，不称商用发布 |

原商业版本的物理设备规模、现场SAT、可用率和长期留存是工程化目标，不能由Python模拟测试自动满足。仿真通过后若要商用，另做硬件接入、平台选型和现场验收，不在本轮自动恢复旧技术栈。

每步：阅读→设计→实现→单元/契约测试→集成/故障测试→Demo→用户验收。每步都应有可观察结果，但M0.1.1只展示进程生命周期，完整遥测闭环在M01结束。
NOT_STARTED→IN_PROGRESS→READY_FOR_REVIEW→ACCEPTED；真实阻断记BLOCKED并说明条件。用户确认前不标ACCEPTED，不自动进入下一步。
当前唯一入口为 [CURRENT_STAGE.md](CURRENT_STAGE.md)。后续详细里程碑在进入前补齐范围/非目标/数据流/测试/Demo/完成条件，不能凭路线表提前实现。
建议里程碑标签统一加-sim（如v0.1.0-kernel-sim、v1.0.0-sim），只按用户授权提交/打标签。
