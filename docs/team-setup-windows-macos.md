# ECHO + PunditRAG 团队本地部署指南（Windows / macOS）

本文面向第一次接触 Docker、Git 和本项目的成员。目标不是“容器看起来启动了”，而是让每位成员在自己的电脑上完成以下闭环：

1. 可以打开 ECHO：`http://127.0.0.1:8010`；
2. PunditRAG 导入服务 `8000` 和查询服务 `8001` 均健康；
3. 可以导入 Microsoft 官方课程材料；
4. 可以在 ECHO 中提问，并看到来自本地知识库的引用；
5. 重启电脑后仍能继续使用已有模型缓存、知识库和业务数据。

> `127.0.0.1` 和 `localhost` 都表示“当前这台电脑”。成员访问自己电脑的
> `127.0.0.1:8001`，不会连接到负责人电脑上的 PunditRAG。

## 一、开始前必须确认

### 1. 仓库权限

每名需要运行完整检索链路的成员必须同时能访问以下两个仓库：

- `Pitkil/echo-adaptive-skill-training`
- `Pitkil/PunditRAG`

两个仓库都是私有仓库。负责人需要在 GitHub 仓库的
`Settings -> Collaborators -> Add people` 中邀请成员。成员接受邀请后再克隆。

检查权限最简单的方法：登录 GitHub 后直接打开两个仓库页面。如果显示 `404`，就是还没有权限。

### 2. 电脑资源

建议至少准备：

- 4 核 CPU，推荐 8 核；
- 16 GB 内存，8 GB 只能勉强运行；
- 预留 25 GB 以上磁盘空间；
- 稳定网络，用于拉取 Docker 镜像和首次下载 BGE 模型；
- 一个可用的 OpenAI-compatible 模型 API。

PunditRAG 首次查询会下载 `BAAI/bge-m3` 和
`BAAI/bge-reranker-v2-m3`。模型缓存可能占用数 GB，CPU 环境首次加载需要较长时间。
缓存持续增长且日志没有报错时，不要中断，也不要同时发起多个查询。

### 3. 目录约定

不要把仓库放在微信临时目录、压缩包内部或桌面临时文件夹中。本文统一使用：

- Windows：`D:\workspaces\PunditRAG` 和
  `D:\workspaces\echo-adaptive-skill-training`
- macOS：`~/workspaces/PunditRAG` 和
  `~/workspaces/echo-adaptive-skill-training`

路径不同也可以，但后续命令必须换成自己的真实路径。

## 二、Windows 从零部署

### 第 1 步：安装基础软件

安装：

1. Git for Windows；
2. Docker Desktop；
3. PowerShell 7（推荐，Windows PowerShell 5.1 也可执行项目脚本）；
4. VS Code（用于编辑 `.env`，不要用 Word）。

安装 Docker Desktop 时使用 WSL 2 后端。安装完成后启动 Docker Desktop，等待左下角显示引擎正在运行。

如果不希望 Docker 镜像和虚拟磁盘占用 C 盘，应在大量拉取镜像前进入：

`Docker Desktop -> Settings -> Resources -> Advanced -> Disk image location`

将磁盘位置改到例如 `D:\DockerDesktopData`。修改后应用并重启 Docker Desktop。
不要复制别人电脑的 Docker 虚拟磁盘，也不要使用 `Reset to factory defaults` 解决普通启动问题。

打开 PowerShell，检查：

```powershell
git --version
docker version
docker compose version
wsl -l -v
```

成功标准：

- Git 能返回版本号；
- `docker version` 同时有 Client 和 Server；
- `docker compose version` 能返回 v2 版本；
- Docker Desktop 使用 WSL 2 时，相关发行版可以正常运行。

### 第 2 步：克隆两个仓库

```powershell
New-Item -ItemType Directory -Force D:\workspaces | Out-Null
Set-Location D:\workspaces

git clone https://github.com/Pitkil/PunditRAG.git
git clone https://github.com/Pitkil/echo-adaptive-skill-training.git
```

如果 GitHub 要求登录，推荐使用 Git Credential Manager 的浏览器登录。不要在聊天、截图或仓库中发送访问令牌。

检查：

```powershell
Test-Path D:\workspaces\PunditRAG\docker-compose.yml
Test-Path D:\workspaces\echo-adaptive-skill-training\docker-compose.yml
```

两个结果都应为 `True`。

### 第 3 步：配置 PunditRAG

```powershell
Set-Location D:\workspaces\PunditRAG
Copy-Item .env.docker.example .env.docker
code .env.docker
```

至少修改：

```dotenv
OPENAI_API_KEY=自己的模型API密钥
OPENAI_BASE_URL=自己的OpenAI兼容接口地址
LLM_DEFAULT_MODEL=接口实际支持的模型名

MONGO_ROOT_USERNAME=punditrag
MONGO_ROOT_PASSWORD=自己生成的高强度密码
MINIO_ROOT_USER=punditrag
MINIO_ROOT_PASSWORD=另一个高强度密码
```

`MINERU_API_TOKEN` 仅在导入需要 MinerU 解析的 PDF 时使用。只导入 Markdown、HTML 等已支持格式时可以先不使用 PDF 导入功能，但不得把示例占位值当作有效 Token。

#### Windows 有 NVIDIA 显卡

只有在 NVIDIA 驱动、WSL 2 GPU 和 Docker GPU 支持均可用时才保留默认配置：

```dotenv
BGE_DEVICE=cuda:0
BGE_FP16=1
BGE_RERANKER_DEVICE=cuda:0
BGE_RERANKER_FP16=1
```

先验证：

```powershell
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.3.1-base-ubuntu22.04 nvidia-smi
```

第二条失败时，不要继续使用 GPU 配置，改用下面的 CPU 配置。

#### Windows 没有 NVIDIA 显卡

在 `.env.docker` 中改为：

```dotenv
BGE_DEVICE=cpu
BGE_FP16=0
BGE_RERANKER_DEVICE=cpu
BGE_RERANKER_FP16=0
```

然后打开 `PunditRAG/docker-compose.yml`，在 `app` 服务中删除或注释这一行：

```yaml
gpus: all
```

`NVIDIA_VISIBLE_DEVICES` 和 `NVIDIA_DRIVER_CAPABILITIES` 在 CPU 模式下没有作用，也可以一并删除。
这是成员电脑的运行配置调整，不要未经审核提交到团队分支。

### 第 4 步：启动 PunditRAG

推荐从 ECHO 仓库调用团队脚本：

```powershell
Set-Location D:\workspaces\echo-adaptive-skill-training
powershell -ExecutionPolicy Bypass -File scripts\start_punditrag.ps1 `
  -PunditRAGRoot D:\workspaces\PunditRAG -Build `
  -TimeoutSeconds 600
```

第一次启动需要构建镜像、拉取 MongoDB、Milvus、MinIO 等依赖，几分钟到几十分钟都可能正常。

另开一个 PowerShell 查看状态：

```powershell
Set-Location D:\workspaces\PunditRAG
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs --tail 150 app
```

不要用无限循环反复打印缓存大小。日志没有错误且仍有网络传输时，等待即可。

### 第 5 步：验证 PunditRAG

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8001/health
```

两个响应都必须包含 `status: ok`。

可打开：

- 导入 API：<http://127.0.0.1:8000/docs>
- 查询工作台：<http://127.0.0.1:8001/query/html>
- 查询 API：<http://127.0.0.1:8001/docs>

### 第 6 步：配置 ECHO

```powershell
Set-Location D:\workspaces\echo-adaptive-skill-training
Copy-Item .env.example .env
code .env
```

至少填写：

```dotenv
OPENAI_API_KEY=自己的模型API密钥
OPENAI_BASE_URL=自己的OpenAI兼容接口地址
OPENAI_MODEL=接口实际支持的模型名

JWT_SECRET_KEY=至少32字符的随机字符串
SECRET_KEY=另一个至少32字符的随机字符串
SIMPLEMEM_API_KEY=至少32字符的随机字符串

PUNDITRAG_DOCKER_IMPORT_BASE_URL=http://host.docker.internal:8000
PUNDITRAG_DOCKER_QUERY_BASE_URL=http://host.docker.internal:8001
```

可以用 PowerShell 生成随机值：

```powershell
$bytes = New-Object byte[] 48
[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
[Convert]::ToBase64String($bytes)
```

每执行一次得到一个新值。三个密钥不要复用，也不要提交 `.env`。

### 第 7 步：启动 ECHO

```powershell
docker compose up --build -d
docker compose ps
docker compose exec echo-api python /workspace/scripts/bootstrap_admin.py --username admin
```

创建管理员时输入两次相同密码，密码至少 10 个字符。输入时终端不显示星号是正常现象。

检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8010/health
```

打开 <http://127.0.0.1:8010>。

## 三、macOS 从零部署

### 第 1 步：确认芯片与安装工具

点击苹果菜单中的“关于本机”，确认是 Apple Silicon（M1/M2/M3/M4）还是 Intel Mac。

安装 Docker Desktop for Mac 时必须选择对应芯片版本。启动 Docker Desktop 后，在设置中给 Docker 至少分配：

- 6 个 CPU（条件有限时至少 4 个）；
- 12 GB 内存（整机只有 16 GB 时可分配 8～10 GB）；
- 25 GB 以上可用磁盘空间。

安装 Xcode Command Line Tools 和 Homebrew：

```bash
xcode-select --install
```

Homebrew 安装完成后：

```bash
brew install git
git --version
docker version
docker compose version
uname -m
```

`uname -m` 返回 `arm64` 表示 Apple Silicon，返回 `x86_64` 表示 Intel。

### 第 2 步：克隆两个仓库

```bash
mkdir -p ~/workspaces
cd ~/workspaces

git clone https://github.com/Pitkil/PunditRAG.git
git clone https://github.com/Pitkil/echo-adaptive-skill-training.git
```

如果出现私有仓库权限错误，先让负责人邀请 GitHub 账号并接受邀请。

### 第 3 步：配置 PunditRAG 为 CPU 模式

macOS Docker 不能使用 CUDA。即使是 Apple Silicon，也不能保留 `cuda:0` 和 `gpus: all`。

```bash
cd ~/workspaces/PunditRAG
cp .env.docker.example .env.docker
open -a TextEdit .env.docker
```

填写模型 API、MongoDB 和 MinIO 凭据，并把模型配置改为：

```dotenv
BGE_DEVICE=cpu
BGE_FP16=0
BGE_RERANKER_DEVICE=cpu
BGE_RERANKER_FP16=0
```

然后用 VS Code 或文本编辑器打开 `docker-compose.yml`，在 `app` 服务中删除：

```yaml
gpus: all
```

同时可以删除：

```yaml
NVIDIA_VISIBLE_DEVICES: all
NVIDIA_DRIVER_CAPABILITIES: compute,utility
```

首次启动前检查 Compose 是否能解析：

```bash
docker compose --env-file .env.docker config >/dev/null
```

没有输出且退出码为 0，说明 YAML 结构没有被改坏。

> Apple Silicon 如果拉取某个第三方镜像时明确报告“不支持 linux/arm64”，才针对该服务增加
> `platform: linux/amd64` 后重试。不要一开始给所有服务强制 x86 模拟，否则速度会更慢。

### 第 4 步：启动并验证 PunditRAG

macOS 不执行 Windows 的 `.ps1` 启动脚本，直接在 PunditRAG 目录运行：

```bash
cd ~/workspaces/PunditRAG
docker compose --env-file .env.docker up -d --build
docker compose --env-file .env.docker ps
```

查看日志：

```bash
docker compose --env-file .env.docker logs --tail 150 app
```

健康检查：

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8001/health
```

两个接口都应返回 `status` 为 `ok`。

### 第 5 步：配置并启动 ECHO

```bash
cd ~/workspaces/echo-adaptive-skill-training
cp .env.example .env
open -a TextEdit .env
```

填写模型接口，并生成三个不同的随机密钥：

```bash
openssl rand -base64 48
openssl rand -base64 48
openssl rand -base64 48
```

分别填入：

```dotenv
JWT_SECRET_KEY=第一个随机值
SECRET_KEY=第二个随机值
SIMPLEMEM_API_KEY=第三个随机值

PUNDITRAG_DOCKER_IMPORT_BASE_URL=http://host.docker.internal:8000
PUNDITRAG_DOCKER_QUERY_BASE_URL=http://host.docker.internal:8001
```

Docker Desktop for Mac 支持 `host.docker.internal`，所以 ECHO 容器可以通过该地址访问宿主机上的 PunditRAG。

启动：

```bash
docker compose up --build -d
docker compose ps
docker compose exec echo-api python /workspace/scripts/bootstrap_admin.py --username admin
curl -fsS http://127.0.0.1:8010/health
```

打开 <http://127.0.0.1:8010>。

## 四、首次模型下载：为什么健康但第一次查询很慢

PunditRAG 的向量模型和重排模型采用延迟加载。服务进程健康不等于两个模型已经加载进内存。
第一次导入会使用 BGE-M3，第一次真实查询还会加载 BGE Reranker。

模型保存在 PunditRAG 仓库内的绑定目录：

- `PunditRAG/models/`
- `PunditRAG/cache/huggingface/`

因此：

- 停止、重建普通容器不会自动删除模型；
- 不要删除这两个目录；
- 不要把模型目录提交 Git；
- 不要在模型下载期间并发发起多个查询；
- 不要因为几分钟没有最终回答就不断重启容器。

Windows 查看一次缓存大小：

```powershell
Get-ChildItem D:\workspaces\PunditRAG\models,D:\workspaces\PunditRAG\cache\huggingface `
  -Recurse -File | Measure-Object Length -Sum
```

macOS 查看一次缓存大小：

```bash
du -sh ~/workspaces/PunditRAG/models ~/workspaces/PunditRAG/cache/huggingface
```

需要判断是否失败时，查看日志末尾，不要运行无限监控循环：

```text
docker compose --env-file .env.docker logs --tail 200 app
```

出现明确的 `timeout`、`403`、`No space left on device`、CUDA 错误或模型文件校验错误时才按错误处理。

## 五、导入正式课程材料

克隆代码只获得程序，不会自动获得负责人电脑中的 MongoDB、Milvus 索引和上传文件。每位成员的本地 PunditRAG 都是独立知识库，必须在本机重新导入。

推荐通过 ECHO 的正式导入链路完成，这样 ECHO 业务数据库会保存本地 `knowledge_base_id` 与 PunditRAG 字符串 `kb_id` 的映射。

在 ECHO 容器已经启动、管理员已经创建后执行正式导入脚本。Windows：

```powershell
Set-Location D:\workspaces\echo-adaptive-skill-training
docker compose exec echo-api python /workspace/scripts/import_official_materials.py `
  --apply --username admin
```

macOS：

```bash
cd ~/workspaces/echo-adaptive-skill-training
docker compose exec echo-api python /workspace/scripts/import_official_materials.py \
  --apply --username admin
```

导入过程必须轮询到完成。`pending` 或 `processing` 不能当作已索引；只有 PunditRAG 完成且 ECHO 同步为 `indexed` 才算成功。

导入后执行固定检索验证。Windows：

```powershell
docker compose exec echo-api python /workspace/scripts/verify_official_retrieval.py `
  --query-base-url http://host.docker.internal:8001
```

macOS：

```bash
docker compose exec echo-api python /workspace/scripts/verify_official_retrieval.py \
  --query-base-url http://host.docker.internal:8001
```

必须显式传入上面的查询地址。容器内的 `127.0.0.1` 指 ECHO 容器自身，不是宿主机上的
PunditRAG 查询服务。

如果脚本参数或路径在后续版本中变化，以 `--help` 为准：

```text
python /workspace/scripts/import_official_materials.py --help
python /workspace/scripts/verify_official_retrieval.py --help
```

## 六、最终验收清单

成员不要只发“运行了”的截图，应逐项确认：

### PunditRAG

- [ ] `docker compose ps` 中依赖服务没有持续重启；
- [ ] `GET http://127.0.0.1:8000/health` 返回 `status: ok`；
- [ ] `GET http://127.0.0.1:8001/health` 返回 `status: ok`；
- [ ] 第一次真实查询已完成 Reranker 下载和加载；
- [ ] 正式材料任务已到完成状态，不是 `pending`；
- [ ] 查询结果包含来源，且来源属于导入的 Microsoft 官方材料。

### ECHO

- [ ] `GET http://127.0.0.1:8010/health` 返回 `status: ok`；
- [ ] 可以登录管理员和学习者账号；
- [ ] 可以进入已开放课程并创建对话；
- [ ] 专业回答带 `[n]` 引用；
- [ ] 前端没有把 PunditRAG 标为 unavailable；
- [ ] 重启 Docker 后账号、知识库和模型缓存仍在。

### Git 安全

```text
git status --short
```

确认没有提交：

- `.env`、`.env.docker`；
- API Key、MongoDB/MinIO 密码；
- `models/`、`cache/`；
- 数据库、Docker volume、上传材料；
- 音频、评测原始输出和临时导出文件。

## 七、常见问题对照表

| 现象 | 最可能原因 | 处理 |
|---|---|---|
| 克隆 PunditRAG 显示 404 | 没有私有仓库权限 | 负责人邀请成员，成员接受邀请后重新克隆 |
| `docker version` 只有 Client | Docker 引擎未运行 | 启动 Docker Desktop，等待引擎完成启动 |
| `could not select device driver` 或 GPU 错误 | 无 NVIDIA/CUDA，却保留了 `gpus: all` | 改 CPU 四项配置，并删除 Compose 中的 `gpus: all` |
| macOS 启动时报 GPU 错误 | Mac 不支持 CUDA Docker 配置 | 必须使用 CPU 配置并删除 GPU 请求 |
| `8000` 健康、`8001` 首次查询超时 | Reranker 正在首次下载或加载 | 只保留一个查询，查看 `app` 日志并等待完成 |
| 缓存不断增长 | 模型仍在下载 | 网络有流量且无错误时继续等待，不要重启 |
| 缓存停止且日志报 403/超时 | Hugging Face 网络或权限问题 | 检查网络、代理、磁盘与模型仓库访问，不要重复并发下载 |
| `No space left on device` | Docker 数据盘或仓库所在磁盘已满 | 清理无关数据或扩容；不要删除正式 volume 和模型缓存 |
| MongoDB/MinIO 一直鉴权失败 | 修改了已初始化 volume 对应的密码 | 使用首次初始化时的密码；不要用新 `.env` 强行重建旧数据 |
| ECHO 显示 RAG unavailable | PunditRAG 未健康或容器地址配置错误 | 先测宿主机 8000/8001，再核对 `host.docker.internal` 地址 |
| RAG 健康但查不到正式资料 | 本机尚未导入，或任务仍 pending | 在本机重新导入并等待 `indexed`，再运行固定检索验证 |
| 队员想直接访问负责人 `127.0.0.1` | 误解 localhost | `127.0.0.1` 永远指向队员自己的电脑；应本地部署或使用经过授权的共享服务地址 |
| `8020` 在浏览器打不开 | SimpleMem 基础 Compose 不发布宿主机端口 | 正常；以 ECHO `/health` 中的 SimpleMem 状态为准 |

## 八、日常启动与停止

日常启动顺序固定为：Docker Desktop → PunditRAG → ECHO。

Windows：

```powershell
Set-Location D:\workspaces\echo-adaptive-skill-training
powershell -ExecutionPolicy Bypass -File scripts\start_punditrag.ps1 `
  -PunditRAGRoot D:\workspaces\PunditRAG
docker compose up -d
```

macOS：

```bash
cd ~/workspaces/PunditRAG
docker compose --env-file .env.docker up -d
cd ~/workspaces/echo-adaptive-skill-training
docker compose up -d
```

停止时只执行普通 `down`，不要附加 `-v`：

```text
docker compose down
```

`down` 会移除容器但保留 volume；`down -v` 会删除数据卷，可能丢失知识库或业务数据，不用于日常操作。
