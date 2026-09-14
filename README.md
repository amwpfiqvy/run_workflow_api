# OciByGhapi
通过 GitHub API 检查目标工作流最近运行时间，超过阈值则触发 `workflow_dispatch`。

每个目标工作流一个目录，目标直接写在 `oci_workflow_watchdog.py` 顶部常量，不做运行时配置：

- `windows/<目标>/`：Windows 计划任务版（`install-task.ps1` 注册 `OCI-ARM-Watchdog-API`）。
- `ubuntu/<目标>/`：Ubuntu systemd timer 版（`install-timer.sh` 安装，见目录内 README）。

当前目标：`oci-arm-host-capacity`（`amwpfiqvy/oci-arm-host-capacity` 的 `oci-arm-capacity.yml`，分支 `main`，阈值 420 秒）。

新增目标：在对应平台下再开一个目录，复制现有目标目录，修改 `oci_workflow_watchdog.py` 顶部常量（`OWNER`、`REPO`、`WORKFLOW_FILE`、`DEFAULT_REF`、`THRESHOLD_SECONDS`）。同一主机部署多个目标时需改名避免冲突：Windows 改 `install-task.ps1` 的 `$TaskName`，Ubuntu 改 `install-timer.sh` 内 unit 文件名及 `run-workflow-api.service.in` / `.timer` 文件名。
