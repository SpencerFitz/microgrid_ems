# microgrid_ems — Python / Windows 仿真版

所有项目程序使用Python，Windows本机模拟运行。当前为 **M0.1.1 / READY_FOR_REVIEW**，已实际通过测试和CLI Demo，等待用户验收；尚不产生PV/SOC遥测。
技术路线取代之前版本，详见 [架构](ARCHITECTURE.md)、[迁移说明](MIGRATION.md)、[当前阶段](docs/roadmap/CURRENT_STAGE.md)。

## 直接运行

需要Windows的Python3.12+，M01只用标准库，无pip依赖，无外部服务。
将压缩包内microgrid_ems目录解压，在该目录打开终端，运行：

```text
python ems.py doctor
python ems.py validate
python -m unittest discover -s tests -v
python ems.py demo
python ems.py status
```

若系统提供Python启动器，可把python换成 `py -3.12`。若未配置PATH，用实际python.exe绝对路径运行；PowerShell写法为 `& '你的python.exe路径' ems.py demo`。本次测试使用本机已存在的Python3.12.14，不需要下载安装。
doctor预期READY_M01；validate为VALID；测试预期全部OK；Demo结果PASS；Demo结束后的status为STOPPED。这里的READY只表示启动环境，不代表后续业务已完成。

持续运行及查看状态：

```text
python ems.py run
```

另一个终端执行status查看活跃状态；原终端按Ctrl+C停止。也可 `python ems.py run --ticks 3` 运行三次心跳自动结束。相同数据目录只能有一个实例，第二个返回非零错误。
全局参数必须在子命令前：`python ems.py --data-dir runtime-demo demo`；使用独立目录进行不同实验，停止不会删除数据。

## 本步到底实现了什么

配置文件→严格校验→注册simulator/device_gateway/ems_core/data_service四个逻辑组件→心跳/结构化日志→停止→重启验证启动元数据保留。
这四个名称目前只是bootstrap中的组件清单，未实现物理Simulator、数据采集、消息总线或历史遥测。对应业务将在M0.1.2～9逐步加入。

| 文件 | 用途 |
|---|---|
| ems.py | 唯一启动入口 |
| ems/config.py | JSON配置与类型/范围/时区/重复键校验 |
| ems/runtime.py | Windows实例锁、日志、心跳、SQLite启动元数据、Demo |
| ems/cli.py | 命令与退出码 |
| configs/site/demo.json | 当前实验配置 |
| tests/test_scaffold.py | 正常/异常/并发/崩溃恢复测试 |
| runtime/ | 自动生成的数据文件，不入库 |

SQLite当前只有bootstrap_meta表；state.sqlite3不是已实现的Historian。元数据标记在Demo的两次运行间应保持一致。
status.json是最后心跳记录，程序同时检查Windows锁和5s新鲜度；进程被终止而状态文件残留RUNNING时，status会显示UNAVAILABLE并退出1，不能把旧记录当活跃。
普通成功退出0；运行/配置错误退出1；CLI参数错误退出2。日志为UTF-8 JSON/UTC，大小轮转；不打印整个配置或环境。

## 环境限制与后续设计

M01无需界面；本机捆绑Python缺完整Tcl初始化资源，尚未验证GUI。M02准备完整Windows Python/Tkinter环境后再开发界面，不阻塞当前CLI。
当前timezone只支持Asia/Shanghai或UTC，日志始终UTC；更广泛IANA支持待GUI阶段准备tzdata后验证。
未来EventBus为本地内存广播，不承诺跨重启重放；SQLite单写者、有限缓存，故障缺口明确。Windows模拟通过不代表硬实时/实物/商业可用性验收。

## 验证与阶段推进

实际记录见 [M0.1.1验证](docs/learning/M0.1.1_VALIDATION.md)。本次11项测试及两轮启动Demo通过，但未自动标ACCEPTED，也未进入M0.1.2。GitHub未写入；本包可用于更新本地仓库。
