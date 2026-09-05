# ECHO Adaptive Skill Training 项目说明

## 零、Agent 开始工作前

任何新 Agent 或成员先按以下顺序了解项目，再修改代码：

1. 阅读根目录 [README.md](README.md)，确认产品定位、三个模块和启动方式。
2. 阅读 [docs/system-overview.md](docs/system-overview.md)，确认系统功能、完整流程和四个后台 Agent。
3. 阅读 [docs/team-ownership.md](docs/team-ownership.md)，确认当前任务属于 A、B、C 还是 D，不能跨边界重复实现。
4. 涉及跨服务数据时阅读 [docs/service-contracts.md](docs/service-contracts.md)；涉及题库时同时阅读 [docs/quiz-import-template.md](docs/quiz-import-template.md)。
5. 修改前阅读 [docs/collaboration.md](docs/collaboration.md)，修改后执行 [docs/testing-and-quality.md](docs/testing-and-quality.md)。
6. 涉及比赛功能取舍时，以 [docs/competition-requirements.md](docs/competition-requirements.md) 为准。

文档发生冲突时，优先级为：本文件的固定边界、赛题要求映射、系统功能说明、四人任务分工、接口契约、其他工程说明。发现冲突必须先修正文档，不得自行选择对当前实现更方便的版本。

## 一、项目定位

ECHO 是一个以对话为主要入口的个性化技能训练系统。竞赛演示领域为
“基于 Microsoft Semantic Kernel 的企业级智能体应用开发”。

学习者始终只与 ECHO 对话。系统在后台完成学习情况分析、官方资料检索、内容生成、
内容检查、答题判分、能力更新、长期记忆和下一步安排。

基于多路召回与混合向量的可追溯 RAG 检索引擎是知识检索与证据服务，不是培训内容本身。培训材料只采用 Microsoft Learn
Semantic Kernel 文档以及 `microsoft/semantic-kernel` 官方仓库和示例。

## 二、系统核心

### 1. 三个学习模块

- M1 Kernel 与插件：模型接入、提示词、插件、函数调用。
- M2 Agent 与多智能体协作：Agent、对话状态、记忆、多智能体流程。
- M3 流程、部署与质量评测：Process Framework、部署、安全、可观测和评测。

跨模块综合实践属于最终任务，不新增第四个学习模块。

### 2. 一轮对话的完整流程

1. 接收学习者的问题、答案或语音。
2. 读取当前模块、历史答题、MIRT 能力和长期记忆。
3. `TurnOrchestrator` 为本轮选择一个主要动作。
4. 需要专业知识时，通过基于多路召回与混合向量的可追溯 RAG 检索引擎检索 Microsoft 官方资料。
5. 生成回答、学习资料、实操指南或题目。
6. 检查内容、答案、难度和官方出处。
7. ECHO 向学习者展示唯一的最终回复。
8. 服务端判分并记录本轮事实。
9. 根据结果更新 MIRT、知识盲区和学习路径。

每轮只能有一个主要动作。禁止在同一轮同时进行判题、生成新题、阶段推进和资源生成。

### 3. 四个后台 Agent

- 学习情况分析 Agent：根据前测、历史作答和 MIRT 判断掌握情况。
- 内容生成 Agent：生成当前需要的回答、定制学习资料、实操指南或阶段测试。
- 内容检查 Agent：检查知识点、答案、步骤、难度、引用和发布条件。
- 下一步安排 Agent：决定本轮解释、提示、提问、练习、升降难度或进入下一知识点。

这些是后台能力，不是四个面向用户的聊天角色。学习者只看到 ECHO。

### 4. 产品角色

- 学习者：对话学习、练习、前后测和查看个人报告。
- 讲师/导师：维护课程材料与固定题库，查看授权范围内的学习情况。
- 系统管理员：管理成员身份、系统配置、服务状态和审计记录。
- Demo 模式：位于管理界面，用于展示后台协作过程，不是独立用户角色。

### 5. 最终必须交付什么

- 一个以 ECHO 对话为主入口的可运行系统，学习资料、题目、记忆和报告都服务于对话。
- 一条可查看记录的后台闭环：分析学习情况、检索官方资料、生成内容、检查内容、安排下一步。
- 定制学习资料、实操指南和阶段测试三种个性化资源。
- 固定前测、阶段测试、后测、服务器判分、MIRT 更新和个性化学习报告。
- 课程材料导入与固定题库导入两个独立入口。
- P1、P2、P3 三种学习者，以及不少于 50 组固定评测案例。
- 幻觉率低于 5%、难度适配率不低于 85%、核心知识覆盖率不低于 90%，引用可追溯率目标为 100%。

## 三、现有基础与未完成重点

本仓库从 `ECHO-main` 提炼并保留以下核心，不迁入与竞赛无关的实验文件和旧页面：

- ECHO 对话 Agent 与 E/C/H/O 状态流转。
- MIRT 的 U/A/R 三维能力估计与自适应选题。
- Quiz 题库导入、服务端判分、重复提交保护和答题记录。
- 学习者画像、知识盲区、难度匹配与学习路径分析。
- FastAPI、SQLAlchemy、前端页面和基础权限体系。
- 外部知识检索、长期记忆和微表征检测的接入位置。

以下内容仍需按任务文档完成，不能因为已有页面、适配器或模板就标记为完成：

- 接入真实检索引擎并导入正式 Microsoft 官方材料。
- 导入 D 准备的 63 道正式固定题，完成整套前测和后测状态。
- 实现三种真实个性化资源的生成、保存、检查和失败重做。
- 分别保存四个后台 Agent 的输入、结果、失败原因和最终决定。
- 完成学习报告、讲师查看、Demo 协作记录和管理端评测结果。
- 冻结并运行 50 组案例，计算四项比赛指标。

开发优先级固定为：正式材料与题库 -> 检索与引用 -> 生成与检查 -> 学习情况更新 ->
报告与管理端 -> 50 组评测。当前进度以
[docs/competition-requirements.md](docs/competition-requirements.md) 为准。

## 四、重要技术边界

### 1. 课程与知识

- 运行时不再使用学校学科式 `subject` 字段。
- 课程范围使用 `program_id`、`module_id`、`knowledge_point_id` 和
  `knowledge_base_id`。
- `apps/api/catalog.py` 是竞赛课程、模块和知识点的唯一代码定义。
- 不得用模型生成内容替代官方材料作为标准答案。

### 2. 数据库与 SimpleMem

- 业务数据库保存用户、权限、会话、消息、题目、作答、MIRT、资源和审计记录。
- SimpleMem 只保存跨会话语义记忆，不替代业务数据库。
- 记忆必须支持用户和组织权限过滤，不得跨用户泄露。

### 3. MIRT 与诊断证据

- MIRT 只维护 U/A/R：
  - U：理解与知识掌握。
  - A：应用与操作能力。
  - R：推理与评估能力。
- 只有允许更新 MIRT 的可评分答案才能改变 U/A/R。
- 微表征、互动表现和长期记忆只影响诊断置信度与提示方式，不直接改写 U/A/R。
- 学习情况总结必须固定输出：能力现状和变化趋势、有作答依据的知识盲区、推荐难度、
  下一知识点、推荐内容形式、推荐辅导方式、推荐原因和证据来源。
- 大模型只负责把统计结果改写成易懂文字；证据不足时明确写“暂不能判断”，模型不可用时使用固定模板。

### 4. 题库

- 固定题目用途只允许 `pretest`、`stage_test`、`posttest` 和 `practice`。
- 题目下发时不得返回答案和评分方法。
- 客户端只提交原始答案，正确性和分数必须由服务端计算。
- `counts_for_mirt` 决定本次作答是否更新能力。
- 前测、后测和正式评测题应固定，不得每次临时生成。

### 5. 个性化资源

- 资源类型为定制学习资料、实操指南和阶段测试。
- 知识点和难度主要由 MIRT、有作答证据的知识盲区和历史作答决定。
- 长期记忆用于选择解释方式和步骤多少；已确认微表征用于调整提示节奏和辅导方式，不能单独决定升降难度。
- 学习者不能手动选择资源难度。
- 没有检索引擎返回的官方证据时，资源保持未校验状态并展示待补充项；本人仍可学习和下载。
  个人资源不自动发布到课程知识库，不得伪造引用或标记为已校验。

### 6. 外部服务

- 基于多路召回与混合向量的可追溯 RAG 检索引擎：官方资料检索、证据和引用。
- SimpleMem：长期语义记忆。
- 真实微表征服务输出犹豫、猜测、思考停顿；接口可记录的其他行为类型不代表当前模型已支持。
- 外部服务不可用时必须明确返回降级原因，不能伪造成功结果。
- 所有外部调用统一放在 `apps/api/integrations`。

## 五、目录职责

```text
apps/api/
  app.py                    FastAPI 入口与公共路由
  catalog.py                三个模块和知识点定义
  database.py               业务数据模型
  resource_generation.py    个性化资源规划、生成和检查
  agent/                    ECHO、状态机和单动作编排
  MIRT/                     能力估计与学习者分析
  Quiz/                     选题、判分和题库导入
  integrations/             检索引擎、SimpleMem、微表征接口
  web/                      学习者与管理端前端
services/simplemem/         SimpleMem 8020 独立服务、持久化与作用域检索
scripts/                    环境、测试、迁移和管理员脚本
tests/unit/                 单模块与业务边界测试
tests/integration/          API 和服务组合测试
docs/                       架构、协作、分工和竞赛说明
```

运行数据统一写入 `data/` 或 Docker volume，不进入 Git。

## 六、环境配置

### 本地开发

要求 Python 3.11、3.12 或 3.13。

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

`setup.ps1` 会创建 `.venv`、安装开发依赖，并在缺少时复制 `.env.example` 为 `.env`。
首次运行前填写 `.env` 中的模型接口配置。

默认地址：

- ECHO：`http://127.0.0.1:8010`
- 基于多路召回与混合向量的可追溯 RAG 检索引擎：`http://127.0.0.1:8000`
- SimpleMem：`http://127.0.0.1:8020`
- 微表征服务：`http://127.0.0.1:8030`

### Docker

```powershell
Copy-Item .env.example .env
# 为 SIMPLEMEM_API_KEY 生成并填写至少 32 字节的随机密钥
docker compose up --build
```

Docker 中 ECHO 通过内部容器网络访问内置 PunditRAG 与 SimpleMem；基础配置不向宿主机发布
SimpleMem 的 `8020`。真实微表征服务仍通过配置的外部地址接入。PunditRAG 默认 CPU，只有
验证过 Docker NVIDIA 支持的电脑才叠加 `docker-compose.gpu.yml`。

## 七、编码规范

### Python

- 文件、函数和变量使用 `snake_case`。
- 类使用 `PascalCase`。
- 常量使用 `UPPER_SNAKE_CASE`。
- 布尔值优先使用 `is_`、`has_`、`can_`、`should_` 前缀。
- 数据库外键统一使用 `{entity}_id`。
- 时间字段统一以 `_at` 结尾，对外使用 ISO 8601。
- 函数只完成一个清晰动作；复杂逻辑放入对应服务，不堆在路由中。
- 新增公共函数必须写清参数、返回值和异常边界。
- 不使用宽泛的 `except Exception` 隐藏错误。

### API 与数据

- API 路径使用复数资源名，例如 `/v1/resources`。
- 新接口必须定义 Pydantic 请求和响应模型。
- 修改数据库结构必须提供可重复执行的迁移方法。
- 接口不得返回密码、答案、评分规则和内部密钥。
- 写操作必须考虑重复请求，关键流程使用 `request_id` 或 `attempt_id` 保证幂等。

### 前端

- 学习者主要入口保持为 ECHO 对话，不拆成多个相互割裂的工具页面。
- 不在前端计算题目正确性、MIRT 或权限结论。
- 身份切换和退出登录后必须清理无权限页面和缓存数据。
- 桌面与 390px 移动端不得出现横向溢出和内容遮挡。

## 八、GitHub 协作摘要

- 仓库已公开；固定成员由负责人邀请为 Collaborator，继续使用固定分支。外部贡献者通过 Fork 提交 PR。
- 四个固定分支为 `member/a-integration`、`member/b-micro-signal`、
  `member/c-mirt-memory` 和 `member/d-content-data`。
- 每名成员先阅读本文件、`docs/team-ownership.md` 和 `docs/collaboration.md`，再自行创建
  并首次 Push 自己的固定分支；负责人不代替成员创建。
- 所有人只在自己的固定分支工作，不直接修改或推送 `main`。
- B、C、D 完成一个可检查阶段后创建 PR，由负责人审核并合并。
- 负责人在 `member/a-integration` 工作，自动检查通过后可以自行合并 PR。
- 只有负责人执行最终合并；存在冲突、测试失败或审核意见未解决时不得合并。
- 每次开始新阶段前，将最新 `origin/main` 合并到自己的固定分支。
- PR 页面使用 `.github/pull_request_template.md`，完整规则只在
  [docs/collaboration.md](docs/collaboration.md) 维护，避免多份规范互相冲突。

## 九、提交前检查

```powershell
powershell -ExecutionPolicy Bypass -File scripts\quality.ps1
powershell -ExecutionPolicy Bypass -File scripts\test.ps1
python -m compileall apps/api
docker compose config
```

提交前检查 `git status`，确认没有 `.env`、数据库、上传材料、音频、缓存和临时导出文件。

## 十、运行环境维护记录

- 2026-08-29：Docker Desktop 4.88.1 曾出现“backend process exited 0x40010004”、daemon
  pipe 不可达、`wsl -l -v` 中 docker-desktop 为 Stopped 的连锁故障，根因是 Windows 侧本地
  状态陈旧导致 Linux VM 无法启动，与项目代码无关。处理：备份并清理
  `C:\Users\32354\AppData\Roaming\Docker Desktop` 与 `C:\Users\32354\AppData\Local\Docker`
  的陈旧锁/缓存（未动 `D:\DockerDesktopData` 数据盘），`wsl --shutdown` 后重启 Docker
  Desktop，daemon 恢复，项目栈与 PunditRAG、SimpleMem、微表征、ASR 重新健康。
  已新增 `scripts\ensure_docker.ps1` 一键自检脚本与
  `docs\docker-longterm-maintenance.md` 长期维护清单；后续先按“十一”流程处理，不要直接重装。

- 2026-08-27：本地 ECHO/PunditRAG 正式知识库按 manifest v1.2 复核完成，外部 kb 为
  `b91a91086ffc4399aa6152d37b6e1d60`；15 份活动材料导入完成，固定 12 个知识点检索在关闭网页搜索、
  限定活动 document_ids 后 12/12 通过。`MS-SK-CONCEPTS-COMPONENTS` upload 20 已标记 `removed`，
  不得从旧交付包恢复；v1.2 审核包位于 `data/deliveries/b-v1.2-final/`（运行数据不提交 Git）。

- 2026-08-26：负责人 Windows 主机的 Docker Desktop 已升级并验证为 4.88.1。程序安装目录为
  `D:\Docker\Docker`，WSL 默认数据根和 `CustomWslDistroDir` 均为
  `D:\DockerDesktopData`。镜像、容器和卷位于
  `D:\DockerDesktopData\disk\docker_data.vhdx`；C 盘只允许 Docker Desktop 必需的小型配置、日志、
  临时安装缓存和 Socket，不得存放 Docker 虚拟磁盘。重装或升级时必须同时传入
  `--installation-dir=D:\Docker\Docker` 和
  `--wsl-default-data-root=D:\DockerDesktopData`，不得使用“Reset to factory defaults”。
- 主机存储复核：`C:\Users\<user>\AppData\Local\Docker` 下不应出现 `.vhdx`/`.vhd`；
  `docker version` 必须同时返回 Client 和 Server；`docker desktop status` 必须为 `running`。

## 十一、Docker Desktop 故障处理与长期维护

> 本机运行依赖 Docker Desktop 4.88.1。故障时先按本节处理，不要直接重装或重置。
> 详细清单见 [docs/docker-longterm-maintenance.md](docs/docker-longterm-maintenance.md)。

### 1. 固定路径与红线（不得违反）

- 安装目录固定为 `D:\Docker\Docker`；WSL 数据根固定为 `D:\DockerDesktopData`。
- 数据盘 `D:\DockerDesktopData`（含 `disk\docker_data.vhdx`、`main\ext4.vhdx`）
  永不清理、不移动、不执行“Reset to factory defaults”。
- C 盘只允许 Docker Desktop 必需的小型配置、日志、临时缓存和 Socket；
  `C:\Users\<user>\AppData\Local\Docker` 下不应出现 `.vhdx`/`.vhd`。
- 重装或升级必须同时传 `--installation-dir=D:\Docker\Docker` 和
  `--wsl-default-data-root=D:\DockerDesktopData`。

### 2. 出错时的标准处理顺序

先运行一键自检（自动启动并等待 daemon，正常则直接 PASS）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\ensure_docker.ps1
```

仍未恢复时使用受控重启（只重启运行时，不删数据）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\ensure_docker.ps1 -Force
```

手动确认三连：

```powershell
wsl -l -v        # docker-desktop 应为 Running
docker version   # Client 和 Server 都必须有输出
docker ps        # 能看到项目容器
```

确认 Docker 健康后再启动项目栈：

```powershell
docker compose up -d
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8010/api/health -TimeoutSec 20
```

### 3. 故障分级判断

| 现象 | 判断 | 处理 |
| --- | --- | --- |
| `docker ps` 报 pipe 找不到、daemon 未运行 | Docker 引擎未启动 | `ensure_docker.ps1 -Force`；仍失败则 `wsl --shutdown` 后重启 Docker Desktop |
| `wsl -l -v` 中 docker-desktop 为 Stopped | WSL VM 未启动 | 启动 Docker Desktop 并等待，必要时 `wsl --shutdown` 后再启动 |
| 8000/8001/8030/8010 端口不通 | 内置服务、外部微表征或容器未起 | 先确认第 2 节通过，再 `docker compose up -d` 并复查 `/health` |
| 直连 `127.0.0.1:8020` 失败 | 正常现象 | SimpleMem 默认不发布到宿主机，只在容器内部网络可达；以 ECHO `/health` 中 simplemem 状态为准 |

### 4. 恢复判定与红线

- 恢复标准：`docker version` 同时返回 Client 和 Server；`docker ps` 能列出容器；
  `GET /api/health` 返回 `status: ok` 且 `unavailable_count: 0`。
- 外部服务（检索引擎、SimpleMem、微表征、ASR）未恢复时，不得把降级输出当作
  正式评测证据；继续修复环境而不是伪造结果。
- 症状重复出现且按上述流程无法恢复时，把当次日志与现象追加到“十、运行环境维护记录”，
  再决定是否重装（重装也必须带固定参数）。
