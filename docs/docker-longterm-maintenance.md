# Docker Desktop 长期维护清单（Windows）

> 适用范围：负责人 Windows 主机。目标是把“每次重启电脑后 Docker 不可用”变成可预测、
> 可一键自愈的常规维护，而不是反复重装。
>
> 对应工具：`scripts/ensure_docker.ps1`。本项目所有红线以 `AGENTS.md` 为准。

## 一、核心原则（必须长期遵守）

1. **数据盘永远不动**：`D:\DockerDesktopData` 保存 WSL VM 盘与 Docker 运行数据
   （`disk\docker_data.vhdx`、`main\ext4.vhdx`）。任何情况下不清理、不移动、不“重置”。
2. **安装路径固定**：安装目录保持 `D:\Docker\Docker`，WSL 数据根保持
   `D:\DockerDesktopData`。C 盘只允许 Docker Desktop 必需的小型配置、日志和缓存。
3. **不执行 “Reset to factory defaults”**：重置会丢弃 VM 状态，导致评测环境重搭。
4. **重装必须带固定参数**，例如：

   ```powershell
   & "D:\Docker\Docker\Docker Desktop Installer.exe" install --accept-license `
     --installation-dir="D:\Docker\Docker" --wsl-default-data-root="D:\DockerDesktopData"
   ```

5. **恢复 ≠ 伪造结果**：Docker 或外部服务未恢复时，不把降级输出当正式评测证据。

## 二、重启电脑后的 3 分钟检查法

每次开机后按顺序执行，任何一步异常都先处理再往下走。

### 第 1 步：一键自检（推荐）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\ensure_docker.ps1
```

脚本会自动：
- 检查 docker CLI 与 daemon 是否可连接；
- 不可用时自动启动 Docker Desktop 并等待（最多 120 秒）；
- 仍不可用且加了 `-Force` 时做受控重启（只重启运行时，不删数据）；
- 结束时输出容器列表与 `docker version`。

### 第 2 步：手动三连（不想用脚本时）

```powershell
wsl -l -v        # docker-desktop 应为 Running
docker version   # Client 和 Server 都必须有输出
docker ps        # 能看到项目容器
```

### 第 3 步：确认项目依赖健康

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8010/api/health -TimeoutSec 20
```

返回 `"status":"ok"` 且 `unavailable_count: 0` 表示 ECHO 与各外部依赖均正常。

## 三、常见故障分级处理

| 现象 | 判断 | 处理 |
| --- | --- | --- |
| `docker ps` 报 pipe 找不到、daemon 未运行 | Docker 引擎未启动 | `scripts\ensure_docker.ps1 -Force`；仍失败则人工 `wsl --shutdown` 后重启 Docker Desktop |
| `wsl -l -v` 中 docker-desktop 为 Stopped | WSL VM 未启动 | 启动 Docker Desktop 等待；必要时 `wsl --shutdown` 后再启动 |
| 服务端口 8000/8001/8030/8010 不通 | 外部服务或容器未起 | 先确认第 1、2 步通过，再 `docker compose up -d` 并复查 `/health` |
| 直接访问 `127.0.0.1:8020` 失败 | 正常现象 | SimpleMem 默认不向宿主机发布 8020，只在容器内部网络可达；以 ECHO `/health` 中 simplemem 状态为准 |

## 四、每日/每阶段收尾建议

- 关闭电脑前保持 Docker Desktop 正常退出，不要强制杀进程后再关机。
- 每阶段结束把 `data/` 与 Docker 数据盘状态记入 `AGENTS.md` 的“运行环境维护记录”。
- 升级或重装 Docker Desktop 前先备份关键状态，重装命令必须带
  `--installation-dir` 与 `--wsl-default-data-root`。

## 五、红线清单（出现即停）

- [ ] 不清理、不移动 `D:\DockerDesktopData`。
- [ ] 不执行 Reset to factory defaults。
- [ ] 不在 C 盘重建 Docker 虚拟磁盘（`.vhdx` 不应出现在 `C:\Users\<user>\AppData\Local\Docker`）。
- [ ] 外部服务未恢复时不把降级结果当成正式评测证据。
