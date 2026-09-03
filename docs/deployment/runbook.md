# ECHO 从零部署与运行手册

本手册覆盖本地开发、Docker 部署、初始化、健康检查、故障排查、备份恢复和安全边界。示例只使用
占位值；不得提交 `.env`、密钥、数据库、原始音频或个人信息。

## 环境与资源

| 项目 | 支持范围 | 建议 |
|---|---|---|
| 操作系统 | Windows 10/11、受支持的 Linux | 64 位且时间同步正常 |
| Python | 3.11、3.12、3.13 | 3.12 |
| Docker | Docker Desktop/Engine、Compose v2 | Docker 24+ |
| CPU/内存 | 4 核、8 GB | 8 核、16 GB；真实微表征另计 |
| 磁盘 | 10 GB | 20 GB，运行数据放独立 volume |

复现前记录 OS、Docker、Python、Git commit SHA 和验证时间，不能使用作者机器的隐藏配置。

## 组件与端口

| 组件 | 宿主机端口 | 说明 |
|---|---:|---|
| ECHO | 8010 | Docker 容器内监听 8000，由 `ECHO_PORT` 映射 |
| PunditRAG 导入 | 8000 | `/knowledge-bases`、`/upload`、`/status/{task_id}` |
| PunditRAG 查询 | 8001 | `/query`、`/health` |
| SimpleMem | 8020 | 基础 Compose 只在容器网络开放 |
| 微表征 | 8030 | Mock 仅联调；正式检测需返回 `mode: real` |
| MySQL（可选） | 3306 | SQLite 模式不开放数据库端口 |

`APP_PORT` 是进程监听端口；Docker 内覆盖为 8000。用户访问地址由 `ECHO_PORT` 决定，默认
`http://127.0.0.1:8010`。

## 环境变量

先执行 `Copy-Item .env.example .env`，再只在本机编辑 `.env`。

| 字段组 | 必填条件 | 说明 |
|---|---|---|
| `APP_HOST/APP_PORT/ECHO_PORT` | 否 | 监听和宿主机映射，可使用模板默认值 |
| `DB_TYPE/SQLITE_PATH` | 本地必填 | 默认 SQLite，运行文件写入 `data/` |
| `MYSQL_*` | MySQL 模式必填 | 使用专用低权限账号 |
| `JWT_SECRET_KEY/SECRET_KEY` | 必填 | 生产使用两个不同的高强度随机值 |
| `BOOTSTRAP_ADMIN_*` | 可选 | 仅首次初始化临时使用，完成后移除 |
| `OPENAI_*` | 模型功能必填 | 兼容 OpenAI 的模型端点；禁止输出密钥 |
| `PUNDITRAG_*` | 正式知识功能必填 | 导入、查询为两个独立服务 |
| `SIMPLEMEM_*` | 长期记忆必填 | ECHO 和 SimpleMem 使用相同 API Key |
| `MICRO_*` | 微表征必填 | 回调密钥不得复用用户令牌 |
| `UPLOAD_DIR/MAX_FILE_SIZE` | 否 | 上传目录在受控 volume 中并限制大小 |

模板的 `replace-me` 和空值必须在相关功能启用前替换，但真实值不得写回仓库。

## 本地启动

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# 编辑 .env
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
.\.venv\Scripts\python.exe scripts\bootstrap_admin.py --username admin
```

Compose 自动按依赖顺序启动 PunditRAG 数据服务 → PunditRAG 双 API → SimpleMem/ASR → ECHO。已有账号需要提升时显式
追加 `--promote-existing`；不要把管理员密码放进脚本、截图或报告。

## 内置 PunditRAG（正式知识检索必需）

PunditRAG 源码位于 `services/punditrag/`，根 `docker-compose.yml` 同时管理其导入 API、查询 API、
MongoDB、Milvus、Etcd 和 MinIO。队员不需要第二个仓库或第二份环境文件。默认 CPU；只有验证过
Docker NVIDIA 支持的电脑才叠加 `docker-compose.gpu.yml`。

模型、缓存、Mongo/Milvus/MinIO 数据和材料索引使用命名 volume，不进入 Git。首次初始化后不得
随意修改 `PUNDITRAG_MONGO_PASSWORD` 和 `PUNDITRAG_MINIO_PASSWORD`，否则现有 volume 会鉴权失败。
ECHO 容器通过 `http://punditrag:8000/8001` 访问双 API，不经过宿主机回环地址。

## Docker 启动

```powershell
Copy-Item .env.example .env
# 编辑 .env，至少配置模型、应用密钥和 SIMPLEMEM_API_KEY
docker compose up --build -d
docker compose ps
docker compose exec echo-api python /workspace/scripts/bootstrap_admin.py --username admin
```

根 Compose 已包含 PunditRAG 与全部依赖，并使用命名 volume。NVIDIA 启动命令：

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
```

本机联调 SimpleMem：

```powershell
docker compose -f docker-compose.yml -f docker-compose.simplemem-dev.yml up --build -d
```

微表征 Mock：

```powershell
docker compose -f docker-compose.yml -f docker-compose.micro-mock.yml --profile micro-mock up --build -d
```

Mock 结果不能作为诊断或比赛评测。真实检测先拉取并校验 Git LFS 制品，再使用
`docker-compose.competition.yml`；其 `/health` 必须返回 `mode: real`。

## 初始化正式数据

1. 启动 ECHO，初始化 `catalog.py` 定义的课程、M1/M2/M3 和 12 个知识点。
2. 重复执行初始化/迁移，确认第二次幂等且无重复记录。
3. 通过题库导入入口导入 63 题，核对 `pretest/posttest/practice = 27/27/9`。
4. 运行 `python scripts/build_official_kb_slice.py build` 和 `validate`。
5. 以讲师/管理员身份通过 ECHO 内容导入入口上传，禁止直接写业务数据库。
6. 保存 ECHO `knowledge_base_id` 及 PunditRAG `kb_id/document_id/task_id`，轮询至终态。
7. 只有外部完成且 ECHO 同步为 `indexed` 才算成功；`pending/processing` 均不算。

推荐的可重复导入和验证命令：

```powershell
docker compose exec echo-api python /workspace/scripts/import_official_materials.py --apply --username admin
docker compose exec echo-api python /workspace/scripts/verify_official_retrieval.py --query-base-url http://punditrag:8001
```

## 健康检查

```powershell
Invoke-RestMethod http://127.0.0.1:8010/health
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8001/health
Invoke-RestMethod http://127.0.0.1:8020/health
Invoke-RestMethod http://127.0.0.1:8030/health
```

数据库通过只读查询验证，模型通过不含敏感数据的最小调用验证。不能只检查 ECHO；逐项记录 HTTP
状态、模式、版本、耗时和错误，并明确区分超时、未配置、Mock、降级和真实成功。

## Smoke test

验证登录、管理员初始化、讲师授权、会话、固定题下发、服务器判分、重复提交、MIRT、官方检索、
三类资源、四 Agent 记录、学习报告、SimpleMem、微表征、越权拒绝和重启恢复。结果写入
`smoke-test-report.md`，未执行项不得标记通过。

## 故障排查

| 现象 | 检查与处理 |
|---|---|
| 8010 不可访问 | 检查 `docker compose ps/logs`、`ECHO_PORT` 和端口占用 |
| 模型失败 | 检查 Base URL、模型名称、额度和 TLS；禁止打印 API Key |
| RAG pending | 用真实 `task_id` 查询导入服务；检查文件解析、队列和超时 |
| RAG failed | 保存 `index_error`，修复后重传；禁止手改 indexed |
| 检索无引用 | 核对 `kb_id` 映射、关闭网页搜索、检查 URL/章节/版本 |
| SimpleMem degraded | 核对 8020、API Key、作用域和数据库权限；不得回滚答题事实 |
| 微表征回调失败 | 核对 8030、回调密钥、任务映射和授权；Mock 不可冒充真实结果 |
| 数据库权限错误 | 检查数据目录/volume 所有权或 MySQL 最小权限账号 |

## 备份、恢复与清理

备份业务数据库、ECHO/SimpleMem volume、知识库 manifest、切片哈希以及 PunditRAG 索引或其重建
输入。恢复后复跑数据库健康、题目数量、知识库映射、固定检索和一次完整闭环。

`docker compose down` 会停止并移除容器但保留 volume。删除 volume 属于破坏性操作，必须先备份并
由负责人核对具体名称后执行。禁止对工作区、用户目录或未解析变量执行递归删除。

## 安全与提交门禁

- 最小权限、HTTPS、密钥轮换、上传 MIME/大小/超时限制和日志脱敏。
- 未授权音频不分析；多人录音未确认说话人时不进入个人档案。
- 知识库发布、权限变更、导出和删除保留审计。
- 完整官方原文是否打包取决于许可；否则只交合法切片、元数据、哈希和复现流程。

```powershell
powershell -ExecutionPolicy Bypass -File scripts\quality.ps1
powershell -ExecutionPolicy Bypass -File scripts\test.ps1
python -m compileall apps/api
docker compose config
git status --short
```

确认 `.env`、数据库、volume、上传材料、音频、缓存和临时导出未进入 Git。
