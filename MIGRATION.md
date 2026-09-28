# 从旧方案迁移到Python/Windows

变更依据：2026-09-24用户明确要求“所有程序均在python/windows环境下模拟运行”。本版是替代实施方案，不是并行维护第二套运行方式。

## 改了什么

Go/容器/Linux服务栈替换为Windows Python主程序；消息改为未来Python EventBus，历史改为未来SQLite；前端改为后续Python桌面界面。当前M0.1.1已完成Python启动与验证。原技术栈缺失不再是本步阻断。
领域对象语义、控制安全链、功率符号、产品业务目标与九步学习顺序保留。物理接入、商用指标/现场SAT不冒充仿真验收。

## 更新仓库

远程仓库本次没有修改。先保留已有工作，再把本包microgrid_ems目录内内容放到仓库根目录，不要嵌套目录。
若仓库只有最早8个文档：覆盖这8个文档，加入其余Python文件即可。
若已采用旧M0.1.1脚手架：本包不包含旧代码；仅覆盖不会自动删除旧文件。确认没有个人修改后，移除以下旧脚手架文件：

```text
go.mod
Makefile
docker-compose.yml
.dockerignore
.env.example
configs/site/demo.yaml
deployments/docker/Dockerfile
deployments/docker/Dockerfile.test
deployments/docker/nats.conf
internal/platform/config.go
internal/platform/app.go
internal/platform/platform_test.go
services/device-gateway/cmd/main.go
services/ems-core/cmd/main.go
services/data-service/cmd/main.go
simulator/cmd/main.go
scripts/scaffold.ps1
docs/learning/M0.1.1_STATIC_CHECKS.json
```

不要批量删除其他未列出的文件、用户数据、.git或本机环境。新旧路径不同的配置不能混用。旧zip/输出目录可以保留作历史参考，但不再用作启动说明。

## 验证入口

python ems.py doctor → validate → unittest → demo → status。所有结果真实通过后请用户验收M0.1.1，不自动推进。
