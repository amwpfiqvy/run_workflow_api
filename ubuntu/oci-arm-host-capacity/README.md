# Ubuntu：systemd timer

适用 Ubuntu 22.04/24.04，使用系统 `/usr/bin/python3`，无需 pip、浏览器或 GitHub CLI。

## 行为

- 每个偶数分钟检查一次；最近一次工作流创建时间距现在达到 420 秒才提交 `workflow_dispatch`。
- 默认目标与 Windows 版相同：`amwpfiqvy/oci-arm-host-capacity` 的 `oci-arm-capacity.yml`，分支 `main`。
- 默认不指定代理；可配置 `HTTPS_PROXY`。API 请求超时为 30 秒，提交后轮询新记录约 20 秒，systemd 总时限 110 秒。
- service 为 `Type=oneshot`，同一 service 尚在运行时 timer 不会再启动一份。不要在多台机器或 Windows/Ubuntu 同时启用同一目标的 watchdog。
- `Persistent=true`：恢复 timer 后补一次遗漏的检查，不逐次回放停机期间的检查。
- 失败退出码为 1，正常跳过/发现新记录为 0。超时或确认失败不盲目重发 dispatch。
- 日志：`/var/log/run-workflow-api/YYYY-MM-DD.log`（最近 7 个日期）和 systemd journal。journal 的保留由系统配置管理。

## 安装（在 Ubuntu 上）

在 root 用户目录克隆仓库，服务直接运行克隆下来的脚本。安装器按自身目录生成绝对路径，不复制程序；安装后不要移动该目录。服务以 root 运行，保留 `ProtectSystem=strict`、`ProtectHome=read-only` 和 `NoNewPrivileges=yes`；无需放宽 `/root` 权限。不要放临时目录。

```bash
git clone https://github.com/amwpfiqvy/run_workflow_api.git /root/run_workflow_api
cd /root/run_workflow_api/ubuntu/oci-arm-host-capacity
sudo bash install-timer.sh
sudoedit /etc/run-workflow-api/watchdog.env
sudo chown root:root /etc/run-workflow-api/watchdog.env
sudo chmod 600 /etc/run-workflow-api/watchdog.env
```

填写 `GITHUB_TOKEN`。建议 fine-grained PAT 仅授权目标仓库，赋予 Actions 读写权限。不要将真实 token 写入仓库。安装器不会覆盖已有环境文件，覆盖 unit 前会生成带时间戳的备份；检测到 service/timer 正在运行时拒绝覆盖。

环境文件可设置：

| 变量 | 默认值 | 用途 |
|---|---|---|
| `GITHUB_TOKEN` | 空，需填写 | GitHub PAT |
| `WATCHDOG_THRESHOLD` | `420` | 补触发阈值（秒） |
| `WATCHDOG_REF` | `main` | dispatch 分支/标签 |
| `HTTPS_PROXY` | 不设置 | 可选 HTTP 代理 |

systemd 不会自动读取交互 shell 的 `.bashrc` 或 Windows 用户环境变量。服务从上述环境文件读取 token，不依赖交互登录。

## 启用（在 Ubuntu 上）

安装器只写 unit 和初始环境文件，不 reload、不启用 timer、不触发工作流。填写 token 后手动启用：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now run-workflow-api.timer
systemctl list-timers run-workflow-api.timer
sudo journalctl -u run-workflow-api.service -n 30 --no-pager
```

启用 timer 后可能立即执行补偿检查；达到阈值会实际触发工作流。当前脚本确认的是“出现新记录”，不等待 GitHub 工作流完成，也不能保证 GitHub runner 立即开始运行。

## 只读检查（在 Ubuntu 上）

当前用户需通过环境变量提供 token；此命令不读取 systemd 的环境文件：

```bash
read -rsp 'GitHub token: ' GITHUB_TOKEN; printf '\n'
export GITHUB_TOKEN
WATCHDOG_LOG_DIR="$HOME/.local/state/run-workflow-api/logs" python3 oci_workflow_watchdog.py --dry-run
unset GITHUB_TOKEN
```

`--dry-run` 只读 GitHub，仍会记日志。手动检查应在 timer 停用时进行；无历史 run 会报错，不会自动首次触发。

## 停止（在 Ubuntu 上）

```bash
sudo systemctl disable --now run-workflow-api.timer
sudo systemctl stop run-workflow-api.service
```

第一条阻止后续检查；第二条用于结束可能正在执行的检查，不能撤销已经提交给 GitHub 的工作流。

参考：[systemd.timer 官方文档](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)。
