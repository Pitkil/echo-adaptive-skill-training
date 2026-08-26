# Semantic Kernel 官方材料审计记录

## 审计基线

- 审计日期：2026-08-26
- 清单来源：`docs/member-d/official_materials_manifest.json`
- 清单版本：1.0
- 培训项目：`MS-SK-ENGINEERING`
- 知识库：`MS-SK-OFFICIAL`
- 允许来源：`learn.microsoft.com`、`github.com/microsoft/semantic-kernel`
- 审计范围：15 份登记材料、M1/M2/M3 共 12 个知识点

本记录只表示来源与覆盖审计，不表示材料已经下载、切片、导入或索引。只有取得真实文件、
计算哈希并完成 PunditRAG 异步任务后，材料状态才能从 `pending` 更新。

## 逐项审计

| 材料 ID | 模块 | 当前核验结果 | 需要处理 |
|---|---|---|---|
| MS-SK-CONCEPTS-KERNEL | M1 | 官方页面可读取；当前页面显示更新日期 2025-04-16 | 重新记录访问日期和页面版本，不能沿用清单中的 2023-07-12 |
| MS-SK-TRAINING-BUILD-KERNEL | M1 | 官方培训 URL 已登记，但本次抓取未取得正文 | 材料获取阶段直接检查 HTTP 状态、课程单元及许可；失败时记录真实原因 |
| MS-SK-CONCEPTS-COMPONENTS | M1 | 官方页面可读取；当前页面显示更新日期 2024-12-06 | 更新版本；该页可覆盖组件、提示模板和插件概览，但不足以单独证明多轮对话能力 |
| MS-SK-TRAINING-NATIVE-PLUGINS | M1 | 官方搜索可确认所属培训模块及“Understand native plugins”单元 | 获取阶段核验单元 URL；保存课程模块与具体单元关系 |
| MS-SK-CONCEPTS-PLUGINS | M1 | 官方页面可读取，并重定向到带结尾斜杠的规范 URL | manifest 使用规范 URL；记录插件、函数调用及导入方式章节 |
| MS-SK-TRAINING-PROMPT-TEMPLATES | M1 | URL 已登记，本次抓取未取得正文 | 获取阶段核验 pivot 页面；若不稳定，改用同域官方 Prompt Templates 文档并保留替换记录 |
| MS-SK-AGENT-ARCHITECTURE | M2 | 官方页面可读取；当前页面显示更新日期 2025-05-28 | 更新版本；分别切出 Agent、Agent Thread、Agent Orchestration 章节 |
| MS-SK-AGENT-PYTHON-API | M2 | 原类级 URL 本次不可稳定读取；官方模块级 API 页面可检索 | 优先采用带 `view=semantic-kernel-python` 的规范模块/API URL并记录访问日期 |
| MS-SK-AGENT-CONCURRENT | M2 | 官方页面可读取；当前页面显示更新日期 2025-07-21 | 更新版本；标记 Agent Orchestration 为实验性能力 |
| MS-SK-AGENT-SEQUENTIAL | M2 | 官方页面可读取；内容明确说明顺序流水线及中间输出 | 更新访问日期；标记实验性能力并切出定义、运行时、调用、结果章节 |
| MS-SK-VECTOR-STORE | M2 | 官方页面可读取，标题明确标注 Preview | 保存 Preview 状态、访问日期和具体连接器/抽象章节，不将预览能力描述为稳定 GA |
| MS-SK-PROCESS-OVERVIEW | M3 | 官方页面可读取；当前页面显示更新日期 2024-11-08 | 更新版本；标记 Process Framework 为实验性能力 |
| MS-SK-PROCESS-FIRST | M3 | 官方页面可读取；示例包含版本化包命令、步骤、状态和事件 | 按概览、步骤、流程构建、运行分段，保留实验性警告 |
| MS-SK-OBSERVABILITY | M3 | 官方页面可读取 | 记录访问日期；按日志、指标、跟踪和 OpenTelemetry 相关章节切片 |
| MS-SK-FILTERS | M3 | 官方页面可读取 | 记录访问日期；按函数调用、提示渲染、自动函数调用过滤器等章节切片 |

## 知识点覆盖结论

| 知识点 | 当前覆盖判断 | 处理决定 |
|---|---|---|
| M1-KP1 Kernel 创建与模型服务接入 | 充分 | 使用 Kernel、Build your kernel、Components |
| M1-KP2 提示词与聊天完成 | 基本充分 | 获取 Prompt Templates 页面后复核章节级覆盖 |
| M1-KP3 插件定义与函数调用 | 充分 | 使用 Plugins 与 Native Plugins |
| M1-KP4 多轮对话与执行设置 | 已补齐基础覆盖 | Quick Start 中的 ChatHistory 与执行设置内容已映射到该知识点；集体检索时继续核对召回质量 |
| M2-KP1 Agent 创建与指令设计 | 充分 | Agent Architecture 与 Python API |
| M2-KP2 对话线程与状态管理 | 充分 | Agent Architecture 的 Agent Thread 章节 |
| M2-KP3 记忆与相关内容检索 | 基本充分 | Vector Stores 可覆盖相关内容检索；切片中明确其 Preview 状态 |
| M2-KP4 多智能体分工与协作 | 充分 | Agent Architecture、Concurrent、Sequential |
| M3-KP1 Process Framework 步骤与事件 | 充分 | Process Overview 与 First Process |
| M3-KP2 日志、跟踪与可观测性 | 充分 | Observability |
| M3-KP3 过滤、安全与异常处理 | 基本充分 | Filters 可覆盖过滤；后续需核对异常处理与安全内容是否需要官方补充来源 |
| M3-KP4 部署与质量评测 | 有基础证据但仍需实测 | Process/Observability 提供流程审计与可观测基础；真实RAG测试时必须单独核对部署和评测查询，不足时再补官方来源 |

## 候选补强来源

以下来源均属于允许的 Microsoft 官方范围。加入正式 manifest 前须完成版本、章节、许可和
文件获取验证，并记录是“新增”还是“替换”，不得静默修改原15份清单。

1. Chat History：
   `https://learn.microsoft.com/en-us/semantic-kernel/concepts/ai-services/chat-completion/chat-history`
2. Function Calling：
   `https://learn.microsoft.com/en-us/semantic-kernel/concepts/ai-services/chat-completion/function-calling/`
3. Semantic Kernel 评测：
   `https://learn.microsoft.com/en-us/azure/machine-learning/prompt-flow/how-to-evaluate-semantic-kernel?view=azureml-api-2`

## 进入切片阶段前的门禁

- 15份材料逐条取得真实 HTTP 状态，抓取失败与链接失效分开记录。
- 每份材料确定规范 URL、访问日期、页面版本或 Git commit/tag/path。
- 明确每份材料许可和是否允许把完整原文放入独立交付包。
- M1-KP4 已由 Quick Start 补齐映射；M3-KP3 和 M3-KP4 在真实检索阶段继续核对覆盖质量。
- 原始文件未取得、哈希未计算时，`local_file` 和 `sha256` 保持为空。
- PunditRAG 未完成真实异步索引前，`import_status` 保持 `pending`。
