# ECHO 部署说明与专业知识库切片任务验收清单

## 验收基线

- 任务：ECHO 部署说明与 Microsoft Semantic Kernel 专业知识库切片
- 项目分支：`member/b-micro-signal`
- 已推送提交：`d02a187`
- 作品标识：`MS-SK-ENGINEERING`
- 知识库标识：`MS-SK-OFFICIAL`
- 切片版本：`1.0`，来源版本统一记录为 `accessed-2026-08-26`
- 本次复核日期：`2026-08-27`

状态说明：`通过`表示已有可复验证据；`待外部服务`表示必须取得真实 PunditRAG
结果后才能完成；`未执行`表示尚未在任务书要求的干净环境运行。`pending`、`prepared`
和`processing`均不等于`indexed`。

## 任务书最终验收项

| 编号 | 验收要求 | 状态 | 当前证据 | 后续动作 |
|---|---|---|---|---|
| A1 | 15条材料不再全部pending，状态与真实PunditRAG任务一致 | 待外部服务 | `official_materials_manifest.json`仍为15条pending；交付包`import-records.json`的indexed为0 | 获取导入/查询双服务，保存kb、document、task ID并轮询真实终态 |
| A2 | manifest、chunks、files、SHA256SUMS相互一致 | 通过 | 15份材料、291个切片、15个Markdown文件；知识库级22条哈希通过验证器 | PunditRAG导入后重新冻结最终包 |
| A3 | 固定检索覆盖M1/M2/M3，来源、引用、章节和版本可验证 | 待外部服务 | 已准备15个案例并覆盖12个知识点；`retrieval-report.md`真实执行数为0 | 禁用网页搜索运行全部案例，保存原始响应、过滤和人工判断 |
| A4 | 干净环境从零部署成功且无隐藏步骤 | 未执行 | `environment-matrix.json`仍为pending，环境列表为空 | 在未复用数据库和volume的环境按文档完整部署 |
| A5 | 部署文档覆盖本地与Docker，环境变量无真实值 | 通过 | `docs/deployment-and-security.md`和交付PDF覆盖两种方式、端口、变量、初始化、备份恢复 | 干净环境验收时核对命令可执行性 |
| A6 | 外部服务异常明确降级，健康检查不只验证ECHO | 通过（静态） | 文档覆盖数据库、模型、PunditRAG双服务、SimpleMem、微表征及降级；项目自动测试通过 | 干净环境再次记录真实HTTP状态、版本、耗时和错误 |
| A7 | 交付包通过敏感信息、重复、路径、哈希和可打开性检查 | 通过 | 无空文件和重复内容；路径与哈希通过；JSON/JSONL/Markdown/PDF可打开；ZIP CRC通过 | 每次更新包后重复全部检查 |
| A8 | 作品名、版本和知识库标识完全一致 | 通过（静态） | 作品使用`MS-SK-ENGINEERING`，知识库使用`MS-SK-OFFICIAL`，材料版本有明确访问日期 | 真实导入后核对外部kb映射和服务版本 |

## 已执行证据

| 检查 | 结果 |
|---|---|
| `scripts/quality.ps1` | 通过 |
| `pytest` | 248 passed |
| `python -m compileall -q apps/api services` | 通过 |
| `docker compose config` | 通过；当前机器仅提示用户Docker配置文件不可读 |
| 切片验证器 | `valid materials=15 chunks=291` |
| 知识库级SHA-256 | 22条全部通过 |
| 交付根目录SHA-256 | 更新包时重新生成并验证 |
| 文件可打开性 | 27个UTF-8文本、5个JSON、291条JSONL、1个5页PDF通过 |
| 敏感信息检查 | 未发现私钥、真实API Key或Bearer Token |

## 干净环境待执行记录

以下项目必须写入`deployment/environment-matrix.json`和
`deployment/smoke-test-report.md`，没有真实结果时不得勾选：

1. OS、Python、Docker、Compose和commit SHA。
2. 从`.env.example`开始，不使用作者机器遗留配置。
3. ECHO、业务数据库、模型、PunditRAG导入8000、查询8001、SimpleMem 8020、
   微表征8030的健康、版本、耗时和错误。
4. 数据库初始化或迁移连续执行两次且无重复数据。
5. 63题按27/27/9导入，验证服务端判分和重复提交。
6. 学习者闭环、四个后台Agent记录、三类资源、报告和权限隔离。
7. 服务重启后的会话、题目、能力、资源和材料状态恢复。

## PunditRAG待执行记录

负责人需提供导入服务、查询服务、认证方式和知识库创建或选择权限。联调时必须记录：

- ECHO `knowledge_base_id`与PunditRAG `kb_id`映射；
- 每份材料的`document_id`、`task_id`、提交时间、轮询历史、终态和错误；
- 15个固定查询的trace/session ID、原始sources、过滤结果、最终排名和引用；
- 允许域名、标题、URL、章节、版本、chunk/document标识及人工相关性判断。

## 当前结论

材料元数据、切片构建、部署说明、静态验证和独立交付包已经完成并可复验。
任务书的最终验收尚未完成，阻塞项为真实PunditRAG导入/检索和干净环境从零部署。
在这些记录补齐前，PR和交付说明必须明确标注“待联调/待干净环境验收”。
