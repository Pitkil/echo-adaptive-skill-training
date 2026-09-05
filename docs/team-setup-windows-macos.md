# ECHO 团队一仓部署指南（Windows / macOS）

本指南面向第一次接触 Docker 的成员。PunditRAG 源码已经位于 `services/punditrag/`；只需克隆
ECHO 一个仓库、填写一份 `.env`、执行一条 Compose 启动命令。

完成标准：

1. ECHO `8010`、RAG 导入 `8000`、RAG 查询 `8001` 均健康；
2. 正式 Microsoft 材料在本机完成导入，不是 `pending`；
3. ECHO 专业回答能返回本地知识库引用；
4. 重启容器后账号、索引和模型缓存仍在。

## 一、先理解三件事

- `127.0.0.1` 只代表当前电脑，不会连接负责人电脑。
- Git 保存源码，不保存 API Key、模型、MongoDB、Milvus、MinIO、上传材料或业务数据库。
- `docker compose down` 保留 volume；`docker compose down -v` 会删除数据，不用于日常操作。

建议 8 核 CPU、16 GB 内存、30 GB 可用磁盘和稳定网络。首次会下载 Docker 镜像、BGE-M3、
BGE Reranker 与 ASR 模型，CPU 环境第一次导入和查询会较慢。

## 二、Windows 从零开始

### 1. 安装并检查工具

安装 Git for Windows 和 Docker Desktop，使用 WSL 2 后端。大量下载前打开：

`Docker Desktop -> Settings -> Resources -> Advanced -> Disk image location`

把 Docker 安装目录设为 `D:\Docker\Docker`，把磁盘映像/WSL 数据根设为
`D:\DockerDesktopData`。不要使用 Reset to factory defaults，也不要把 Docker
虚拟磁盘复制到 C 盘。

在 PowerShell 执行：

```powershell
git --version
docker version
docker compose version
wsl -l -v
```

`docker version` 必须同时显示 Client 和 Server。

### 2. 克隆唯一仓库

```powershell
New-Item -ItemType Directory -Force D:\workspaces | Out-Null
Set-Location D:\workspaces
git clone https://github.com/Pitkil/echo-adaptive-skill-training.git
Set-Location D:\workspaces\echo-adaptive-skill-training
Copy-Item .env.example .env
```

### 3. 填写 `.env`

用 VS Code 或记事本打开 `.env`，不要用 Word。至少填写：

```dotenv
OPENAI_API_KEY=自己的模型API密钥
OPENAI_BASE_URL=自己的OpenAI兼容接口地址
OPENAI_MODEL=接口支持的模型名
PUNDITRAG_LLM_MODEL=接口支持的模型名

JWT_SECRET_KEY=随机值1
SECRET_KEY=随机值2
SIMPLEMEM_API_KEY=随机值3
PUNDITRAG_MONGO_PASSWORD=随机值4
PUNDITRAG_MINIO_PASSWORD=随机值5
```

五个值不能复用。应用密钥可重复运行下面命令生成：

```powershell
$randomBytes = New-Object byte[] 48
[Security.Cryptography.RandomNumberGenerator]::Fill($randomBytes)
[Convert]::ToBase64String($randomBytes)
```

MongoDB/MinIO 密码使用不含 URI 特殊字符的十六进制值：

```powershell
$storageBytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Fill($storageBytes)
[Convert]::ToHexString($storageBytes).ToLowerInvariant()
```

不要修改模板中的容器内部地址：

```dotenv
PUNDITRAG_DOCKER_IMPORT_BASE_URL=http://punditrag:8000
PUNDITRAG_DOCKER_QUERY_BASE_URL=http://punditrag:8001
```

### 4. 选择 CPU 或 NVIDIA GPU

无 NVIDIA、未配置 Docker GPU 或不确定时，直接使用默认 CPU，不改任何 YAML：

```powershell
docker compose config
docker compose up --build -d
```

只有以下 GPU 验证成功时才用 GPU 覆盖配置：

```powershell
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.3.1-base-ubuntu22.04 nvidia-smi
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
```

### 5. 等待并检查

```powershell
docker compose ps
docker compose logs --tail 150 punditrag
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8001/health
Invoke-RestMethod http://127.0.0.1:8010/health
```

第一次构建可能需要较长时间。`echo-api` 会等 PunditRAG、SimpleMem 和 ASR 健康后再启动。
根 Compose 默认不启动微表征容器。只做接口联调时显式启用 Mock：

```powershell
docker compose --profile micro-mock up --build -d
```

正式演示或真实评测使用真实模型覆盖配置：

```powershell
docker compose -f docker-compose.yml -f docker-compose.micro-real.yml `
  --profile micro-real up --build -d
```

### 6. 创建管理员

```powershell
docker compose exec echo-api python /workspace/scripts/bootstrap_admin.py --username admin
```

按提示输入两次密码。终端输入密码时不显示字符是正常现象。随后打开
<http://127.0.0.1:8010>。

## 三、macOS 从零开始

### 1. 安装并检查工具

按 Apple Silicon 或 Intel 芯片安装对应的 Docker Desktop，并为 Docker 分配至少 4 核 CPU、
8～12 GB 内存和 30 GB 磁盘。安装 Git 后执行：

```bash
git --version
docker version
docker compose version
uname -m
```

### 2. 克隆和配置

```bash
mkdir -p ~/workspaces
cd ~/workspaces
git clone https://github.com/Pitkil/echo-adaptive-skill-training.git
cd echo-adaptive-skill-training
cp .env.example .env
```

打开 `.env`，填写与 Windows 相同的模型字段和五个独立随机值。三个应用密钥可重复运行：

```bash
openssl rand -base64 48
```

MongoDB/MinIO 密码分别运行 `openssl rand -hex 32` 生成，避免把 `/`、`@`、`:` 等 URI 特殊字符
直接放进 MongoDB 连接串。

macOS 不支持 Docker CUDA，始终使用根 Compose 的默认 CPU 配置；不要叠加
`docker-compose.gpu.yml`，也无需修改任何 YAML。

### 3. 启动和检查

```bash
docker compose config >/dev/null
docker compose up --build -d
docker compose ps
docker compose logs --tail 150 punditrag
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8001/health
curl -fsS http://127.0.0.1:8010/health
docker compose exec echo-api python /workspace/scripts/bootstrap_admin.py --username admin
```

打开 <http://127.0.0.1:8010>。

默认 CPU 栈不包含微表征容器；未启用 `micro-mock` 或 `micro-real` profile 时，ECHO 健康检查中的微表征降级项属于预期状态。需要联调 Mock 时执行：

```bash
docker compose --profile micro-mock up --build -d
```

## 四、首次导入正式课程材料

每台新电脑都要执行一次。源码中有导入清单和复现脚本，但不会把负责人机器的数据库与索引提交
到 Git。

Windows：

```powershell
Set-Location D:\workspaces\echo-adaptive-skill-training
docker compose exec echo-api python /workspace/scripts/import_official_materials.py `
  --apply --username admin
docker compose exec echo-api python /workspace/scripts/verify_official_retrieval.py `
  --query-base-url http://punditrag:8001
```

macOS：

```bash
cd ~/workspaces/echo-adaptive-skill-training
docker compose exec echo-api python /workspace/scripts/import_official_materials.py \
  --apply --username admin
docker compose exec echo-api python /workspace/scripts/verify_official_retrieval.py \
  --query-base-url http://punditrag:8001
```

导入接受只表示排队。`pending`、`processing` 都不算完成，必须等待 `indexed`。查询验证必须使用
容器内部地址 `http://punditrag:8001`，不能写 `127.0.0.1` 或 `host.docker.internal`。

## 五、端口与数据位置

| 组件 | 宿主机地址 | 持久化位置 |
| --- | --- | --- |
| ECHO | `http://127.0.0.1:8010` | `echo-data` volume |
| PunditRAG 导入 | `http://127.0.0.1:8000` | Mongo/Milvus/MinIO volumes |
| PunditRAG 查询 | `http://127.0.0.1:8001` | 模型与 Hugging Face cache volumes |
| MinIO 控制台 | `http://127.0.0.1:9101` | `punditrag-minio-data` volume |
| SimpleMem | 仅容器网络 `8020` | `simplemem-data` volume |
| ASR | `http://127.0.0.1:8040` | `asr-model-cache` volume |

所有命名 volume 都由 Docker 管理。Windows 是否占用 C 盘取决于 Docker Desktop 的磁盘映像位置，
不是仓库目录。

## 六、日常使用

启动：

```text
docker compose up -d
```

停止但保留数据：

```text
docker compose down
```

更新代码后：

```text
git pull
docker compose up --build -d
```

不要日常使用 `down -v`、`volume prune` 或 Reset to factory defaults。

## 七、常见问题

| 现象 | 原因与处理 |
| --- | --- |
| `docker version` 只有 Client | Docker 引擎未启动；启动 Docker Desktop 并等待 |
| macOS 或无显卡机器报 GPU 错误 | 错用了 GPU 覆盖；只运行根 `docker-compose.yml` |
| `8000/8001` 启动慢 | 第一次拉镜像或加载依赖；查看 `docker compose logs punditrag` |
| 第一次导入/查询很慢 | BGE 模型正在下载或 CPU 加载；不要并发查询或反复重启 |
| ECHO 显示 RAG unavailable | 先检查 8000/8001，再确认 `.env` 内部地址是 `http://punditrag:*` |
| RAG 健康但无资料 | 本机尚未导入或任务未到 `indexed` |
| Mongo/MinIO 鉴权失败 | 初始化 volume 后改了密码；恢复首次密码或按备份迁移，不能硬改数据库状态 |
| `8020` 浏览器打不开 | 正常；SimpleMem 默认只开放给 ECHO 容器 |
| 磁盘不足 | 扩容 Docker 数据盘；不要删除正式 volume 和模型缓存 |

## 八、提交前安全检查

```text
git status --short
```

不得提交 `.env`、API Key、密码、模型、cache、数据库、Docker volume、上传材料、音频或评测运行输出。
