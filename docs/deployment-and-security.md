# 部署与安全

本文档以仓库中的 `.env.example`、PowerShell 脚本和 Compose 文件为准。命令中的密钥、账号、
模型地址均为占位信息；不得把真实值写回文档或提交到 Git。

## 系统要求

| 项目 | 最低要求 | 建议 |
|---|---|---|
| 操作系统 | Windows 10/11 或主流 Linux | Windows 11 / Ubuntu 22.04 及以上 |
| Python | 3.11、3.12 或 3.13 | 3.12，与最终验收环境保持一致 |
| Docker | 支持 Compose v2 | 当前稳定版 Docker Desktop/Engine |
| CPU/内存 | 4核、8 GiB | 8核、16 GiB；真实微表征模型按实际硬件增加资源 |
| 磁盘 | 10 GiB 可用 | 30 GiB以上，用于镜像、模型、材料和运行数据 |
| Git | 支持 Git LFS | 拉取真实微表征模型前执行 `git lfs install` |

PunditRAG 不包含在基础 `docker-compose.yml` 中，必须另行启动其导入服务和查询服务，或把
ECHO 配置为访问已经部署的实例。模型接口同样是外部依赖，不能因为 ECHO `/health` 在线就认为
整套系统已经可用。

## 组件和端口

| 组件 | 宿主机默认端口 | 说明 |
|---|---:|---|
| ECHO | 8010 | Docker 容器内监听8000；本地开发读取 `APP_PORT` |
| PunditRAG 导入服务 | 8000 | 创建知识库、上传材料、查询异步导入状态 |
| PunditRAG 查询服务 | 8001 | 执行知识库范围检索，正式查询关闭网页搜索 |
| SimpleMem | 8020 | 基础Compose仅在容器网络公开；开发覆盖只绑定127.0.0.1 |
| 微表征服务 | 8030 | Mock只能联调；比赛验收必须返回 `mode: real` |
| MySQL | 3306 | 仅在选择外部MySQL部署时使用；基础Compose默认使用SQLite |

完整的从零部署、初始化、健康检查、故障排查、备份恢复和 Smoke Test 步骤见
[`deployment/runbook.md`](deployment/runbook.md)。本文同时保留用于验收的详细配置和安全边界；
两处发生不一致时，必须先按实际脚本和Compose配置修正文档，再执行部署。

## 启动

### 环境变量

先复制模板，不要把生成的 `.env` 提交到 Git：

```powershell
Copy-Item .env.example .env
```

| 变量组 | 主要变量 | 必填条件与说明 |
|---|---|---|
| 应用 | `APP_HOST`、`APP_PORT`、`ECHO_PORT`、`CORS_ORIGINS`、`LOG_LEVEL` | 均有开发默认值；共享环境应限制CORS来源 |
| 数据库 | `DB_TYPE`、`SQLITE_PATH`、`MYSQL_*` | 默认SQLite；`DB_TYPE=mysql`时必须填写外部MySQL连接信息 |
| 身份认证 | `JWT_SECRET_KEY`、`SECRET_KEY`、`ACCESS_TOKEN_EXPIRE` | 非本地环境必须替换两个占位密钥，建议至少32个随机字符 |
| 初始管理员 | `BOOTSTRAP_ADMIN_USERNAME`、`BOOTSTRAP_ADMIN_PASSWORD` | 可选；只在初始化阶段短暂使用，随后删除环境值 |
| 模型 | `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL` | 使用生成能力时必填；禁止在日志和报告中输出密钥 |
| 视觉模型 | `VISION_API_KEY`、`VISION_BASE_URL`、`VISION_MODEL` | 使用视频抽帧/OCR相关外部视觉能力时填写 |
| PunditRAG | `PUNDITRAG_IMPORT_BASE_URL`、`PUNDITRAG_QUERY_BASE_URL`、Docker地址、超时、Top K | 真实知识库入库和检索时必填；导入与查询是两个独立服务 |
| SimpleMem | `SIMPLEMEM_BASE_URL`、Docker地址、超时、路径、`SIMPLEMEM_API_KEY` | 正常启动必须使用ECHO与SimpleMem一致且至少32字节的密钥 |
| 微表征 | `MICRO_REPRESENTATION_BASE_URL`、Docker地址、超时、端口、上传上限、回调密钥 | 回调启用时两端必须配置相同 `MICRO_CALLBACK_SECRET` |
| 文件 | `UPLOAD_DIR`、`MAX_FILE_SIZE`、`VIDEO_MAX_FILE_SIZE`、抽帧/OCR配置 | 路径必须位于受控运行目录；上传限制按字节配置 |

`.env.example` 是字段全集。新增、删除或重命名变量时，应同时更新模板、本文档、Compose和测试。

### 本地开发

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# 编辑 .env，至少填写所需模型配置和安全密钥
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

`setup.ps1` 创建 `.venv`、安装开发依赖，并仅在缺少时复制 `.env.example`。`dev.ps1` 不会启动
PunditRAG、SimpleMem或微表征；这些服务需要分别启动。使用仓库内SimpleMem联调：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_simplemem.ps1 -AllowInsecureDevelopment
```

无鉴权模式只允许回环开发环境。共享或比赛环境必须配置 `SIMPLEMEM_API_KEY`。

### 基础 Docker

```powershell
Copy-Item .env.example .env
# 为 SIMPLEMEM_API_KEY 生成并填写至少 32 字节的随机密钥
docker compose up --build
```

基础Compose启动ECHO和SimpleMem。它不会启动PunditRAG双服务、外部模型或真实微表征服务。
容器内ECHO通过 `host.docker.internal` 访问另行运行在宿主机的PunditRAG和微表征服务；Linux环境
若不支持该名称，需要显式配置可达地址或Compose网络，不得照抄地址后假定可用。

首次启动后创建管理员：

```powershell
docker compose exec echo-api python /workspace/scripts/bootstrap_admin.py --username admin
```

命令交互式读取密码，不把密码写入命令历史。已有账号提升时追加 `--promote-existing`。

上述命令只启动 ECHO。需要联调微表征接口时，显式启动不含模型的 Mock 8030 服务：

```powershell
docker compose -f docker-compose.yml -f docker-compose.micro-mock.yml --profile micro-mock up --build
```

覆盖配置将 ECHO 的容器内检测地址设为 `http://micro-detector:8030`，并等待 Mock 的 `/health`
健康检查通过。Mock 服务只验证跨服务契约，并通过 `/health` 的 `mode: mock` 明确标识；固定检测事件不能作为
真实诊断或评测结果。真实检测
服务后续保持同一接口，使用独立重依赖镜像和外部数据卷。

真实微表征检测使用私有仓库中由 Git LFS 管理的冻结离线推理制品。首次 Clone 后执行：

```powershell
git lfs install
git lfs pull
powershell -ExecutionPolicy Bypass -File scripts\verify_micro_model.ps1
powershell -ExecutionPolicy Bypass -File scripts\start_competition.ps1
```

`models/micro_detector/` 只保存 WavLM 推理权重、三类行为原型、许可说明和校验清单。FAISS 索引在运行时
根据三个原型向量内存构建，不提交持久化索引。训练音频、生成 embedding、缓存和个人数据不得进入 Git。
组委会交付由 `scripts/export_competition.ps1` 从冻结提交生成，脚本会将 Git LFS 指针替换为已校验的真实权重。
比赛覆盖配置仅将检测服务发布到宿主机 `127.0.0.1:8030`，不允许局域网直接访问无鉴权接口；
上传音频按流式读取并默认限制为 100 MiB，超限文件立即删除。可通过
`MICRO_DETECTOR_MAX_AUDIO_BYTES` 调整上限。`scripts/start_competition.ps1` 会在模型校验和镜像构建前
确认 `SIMPLEMEM_API_KEY` 已设置且至少包含 32 个 UTF-8 字节。

需要启用检测服务事件回调时，在 ECHO 与 8030 服务中配置相同的 `MICRO_CALLBACK_SECRET`，
8030 使用 `X-Micro-Service-Key` 请求头调用回调。该值为空时回调入口保持关闭；不得使用普通
学习者或导师登录令牌代替服务身份。生产部署应通过密钥管理系统注入，不写入 Git。

ECHO 对宿主机默认使用 `8010`；Docker 容器内监听 `8000`。PunditRAG 导入/查询、SimpleMem、
微表征分别默认使用 `8000`、`8001`、`8020`、`8030`，不要把 ECHO 容器内端口与 PunditRAG
导入端口混淆。
SimpleMem 服务位于 `services/simplemem`，默认监听 `8020`，使用独立 SQLite 数据库和
Docker volume。部署环境应设置非空 `SIMPLEMEM_API_KEY`，ECHO 与 SimpleMem 必须使用相同值。
未设置密钥时 SimpleMem 默认拒绝启动；基础 Compose 只在容器内部网络公开 `8020`，不发布到
宿主机。仅本机联调且明确接受无鉴权风险时，可以使用回环地址覆盖配置：

```powershell
docker compose -f docker-compose.yml -f docker-compose.simplemem-dev.yml up --build
```

该覆盖配置把 `8020` 绑定到宿主机 `127.0.0.1`，将 ECHO 的访问地址固定为容器网络中的
`http://simplemem:8020`，并为 ECHO 与 SimpleMem 配置相同的固定开发服务密钥。
`http://host.docker.internal:8020` 仅用于容器访问另行启动在宿主机上的服务；地址可解析不等于
服务已运行。开发覆盖不得用于共享或生产环境。直接无鉴权启动仍需显式设置
`SIMPLEMEM_ALLOW_INSECURE_DEV=true`，且服务会拒绝任何非回环 `SIMPLEMEM_HOST`。
完整服务不可用时保留事实记录并返回降级原因，不伪造成功状态。

## 初始化正式数据

1. ECHO启动时创建业务表并保证固定课程、三个模块和12个知识点存在。
2. 使用讲师或管理员账号，通过题库导入流程导入63道正式题；也可以在受控环境运行：

   ```powershell
   .\.venv\Scripts\python.exe scripts\import_formal_quiz.py --help
   ```

   先阅读帮助并显式填写要求的账号、文件和服务地址，不把密码写入脚本或报告。
3. 核对题量为前测27、后测27、操作/练习9，并检查学习者接口不返回答案或评分方法。
4. 使用 `scripts/build_official_kb_slice.py` 构建和验证材料：

   ```powershell
   .\.venv\Scripts\python.exe scripts\build_official_kb_slice.py build
   .\.venv\Scripts\python.exe scripts\build_official_kb_slice.py validate
   ```

5. 通过ECHO材料导入接口上传，不直接写数据库。保存 ECHO `knowledge_base_id`、PunditRAG
   `kb_id`、`document_id`和`task_id`，轮询到真实终态。`pending`和`processing`不算已索引。
6. P1/P2/P3属于根据真实可评分作答形成的学习者画像。测试账号可以预置，但不得伪造能力证据；
   需要差异画像时导入或执行对应的脱敏固定作答案例。

## 健康检查

先访问ECHO聚合健康接口：

```powershell
Invoke-RestMethod http://127.0.0.1:8010/health | ConvertTo-Json -Depth 8
```

响应必须分别显示数据库以及 `punditrag_import`、`punditrag_query`、`simplemem`、
`micro_representation`。`unavailable`或`not_configured`是降级证据，不得改写成正常。

再直接检查外部服务，避免聚合接口掩盖地址配置错误：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8001/health
Invoke-RestMethod http://127.0.0.1:8020/health
Invoke-RestMethod http://127.0.0.1:8030/health
```

真实微表征比赛验收还必须执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_competition.ps1
```

该命令要求8030返回 `status=ok`、`mode=real` 和非空检测器版本。Mock健康不代表真实检测通过。

## 从零 Smoke Test

在未复用现有数据库和Docker volume的环境中执行并记录：

1. OS、Python、Docker/Compose版本和commit SHA。
2. 从 `.env.example` 建立配置，使用测试密钥和脱敏账号。
3. 启动全部组件并逐个记录健康状态和耗时。
4. 运行数据库初始化/迁移两次，确认第二次无重复数据。
5. 导入63题并核对27/27/9、服务器判分和相同 `attempt_id` 幂等。
6. 导入知识库材料，等待每个任务进入最终状态并记录 indexed/failed 数量。
7. 运行冻结检索案例，验证知识库范围、来源过滤、章节、版本和链接。
8. 登录学习者账号，完成一次作答、诊断、检索、资源生成/检查和下一步安排闭环。
9. 检查四个后台Agent的输入、结果、失败原因和最终决定。
10. 验证讲师授权范围、管理员服务状态和未授权数据不可见。
11. 重启服务，确认会话、题目、能力、资源和材料状态恢复。
12. 执行全部质量门禁并填写 `docs/deployment/smoke-test-report.md`；未执行项保持未通过。

## 故障排查

| 现象 | 检查 | 处理原则 |
|---|---|---|
| 8010无法访问 | `docker compose ps`、ECHO日志、`APP_PORT/ECHO_PORT` | 区分宿主机端口和容器8000，不修改数据库掩盖启动错误 |
| 模型调用失败 | 模型地址、模型名、凭据注入和超时 | 不输出密钥；模型不可用时保留固定模板或明确降级 |
| PunditRAG一直pending | 导入8000健康、`task_id`、状态接口和错误字段 | pending不改成indexed；保存超时和服务错误后重试 |
| 查询无结果 | 查询8001、外部 `kb_id` 映射、材料终态、固定案例 | 禁止临时打开网页搜索冒充知识库命中 |
| SimpleMem不可用 | 8020健康、容器网络地址、两端API key | 保留业务库事实，记录降级，不回滚答题或改变U/A/R |
| 微表征不可用 | 8030健康、mock/real模式、模型校验、回调密钥 | Mock只做契约联调；未授权音频不提交 |
| 数据库权限错误 | `DB_TYPE`、路径/连接、volume权限 | 不删除数据库；先备份并记录错误，再修正权限 |
| 上传失败 | MIME、扩展名、大小、目录权限和解析超时 | 不放宽安全限制规避失败；记录具体拒绝原因 |

## 备份与恢复

- SQLite：停止写入后备份 `SQLITE_PATH` 指向的文件；MySQL使用组织批准的逻辑/物理备份方案。
- Docker：分别备份 `echo-data`、`simplemem-data` 和真实微表征运行数据卷；不要只备份Compose文件。
- 知识库：备份允许保存的源文件、manifest、chunks、SHA256SUMS、PunditRAG索引或其官方导出、
  ECHO/PunditRAG ID映射和导入记录。
- 模型：保存Git LFS版本、许可证和SHA-256清单，不保存训练音频或生成embedding。
- 恢复后必须重新执行哈希校验、服务健康检查、固定检索、权限检查和一次重启恢复测试。

恢复演练应使用副本，不直接覆盖唯一运行数据。备份中同样不得包含明文密钥。

## 停止与安全清理

停止基础服务：

```powershell
docker compose down
```

该命令默认保留命名volume。删除volume、数据库、上传材料或模型属于破坏性操作，只能在明确确认
目标环境、完成备份并获得负责人授权后执行。不得对仓库根目录、用户目录、磁盘根目录或由未解析
环境变量生成的路径执行递归删除。

## 权限

- 学习者：本人会话、作答、画像、资源和授权语音。
- 讲师/导师：授权范围内的培训录音、知识库和学习证据。
- 系统管理员：成员身份、服务配置、审计和数据生命周期。
- Demo：管理界面中的脱敏展示模式，不是独立账号角色。

公开注册只创建学习者账号，不提供公开提权接口。首次部署通过交互式脚本创建管理员：

```powershell
docker compose exec echo-api python /workspace/scripts/bootstrap_admin.py --username admin
```

已有账号需要提升时追加 `--promote-existing`。系统始终禁止降级组织内最后一名有效管理员。

## 安全底线

- 生产环境必须替换 JWT 密钥并启用 HTTPS。
- 原始音频进入受控对象存储，不进入 Git。
- 未授权音频不分析；撤回后停止用于后续诊断。
- 多人录音未确认说话人时不绑定个人。
- 上传必须限制 MIME、扩展名、大小和解析超时。
- 外部检索结果按不可信输入处理。
- 权限变更、知识库发布、数据导出和删除必须留审计记录。

## 演示冻结

第 4 周第 6 天冻结镜像、环境变量模板、知识库版本、模型版本、50 组评测数据和演示脚本。
第 7 天只做提交检查与录制备份。
