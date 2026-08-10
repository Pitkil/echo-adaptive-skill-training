# ECHO 学习模块与核心知识点

本文档与 `apps/api/catalog.py` 中的三个模块、十二个知识点保持一致，用于准备固定题库、生成个性化资源和检查专业内容。

知识依据只使用 Microsoft Learn Semantic Kernel 文档和 `microsoft/semantic-kernel` 官方仓库。质量指标中的“错误率低于 5%”“难度匹配率不低于 85%”“核心知识点覆盖率不低于 90%”来自比赛要求，不表述为 Semantic Kernel 自带能力。

题目和操作示例按 Python SDK `semantic-kernel==1.41.3` 复核。团队运行和评测时应固定该版本；若升级 SDK，需重新检查示例接口后再更新题库。

## M1：Kernel 与插件

**模块目标**：创建 Kernel、接入模型服务，并使用提示词、插件和函数调用完成对话任务。

### 1. Kernel 创建与模型服务接入

- 了解 Kernel 是集中管理模型服务和插件的轻量容器。
- 能创建 `Kernel`，并通过 `add_service` 注册聊天完成服务。
- 知道连接信息应从环境变量或安全配置读取，不写入题目示例。

### 2. 提示词与聊天完成

- 了解提示词模板用于组合指令、上下文和变量。
- 能从提示词创建函数，并通过 `KernelArguments` 传入变量。
- 能说明模型服务、提示词函数和调用结果之间的关系。

### 3. 插件定义与函数调用

- 了解插件是提供给模型使用的一组相关函数。
- 能在普通 Python 类中使用 `kernel_function` 标记函数。
- 能把插件注册到 Kernel，并按插件名和函数名调用。
- 知道函数名、说明、参数类型和返回值会影响模型能否正确选用函数。

### 4. 多轮对话与执行设置

- 能使用 `ChatHistory` 保存用户消息和助手消息。
- 能在后续调用中复用同一份对话历史。
- 能说明温度、最大输出长度等设置对模型输出的影响。

## M2：Agent 与多智能体协作

**模块目标**：创建 Agent、维护对话状态和检索内容，并组织多个 Agent 分工协作。

### 5. Agent 创建与指令设计

- 能创建 `ChatCompletionAgent`，配置模型服务、名称和指令。
- 能写出职责清楚、边界明确、输出要求具体的 Agent 指令。
- 能通过统一响应接口取得 Agent 输出。

### 6. 对话线程与状态管理

- 了解 `AgentThread` 用于承载一段持续对话的状态。
- 能使用 `ChatHistoryAgentThread` 进行连续多轮交互。
- 能区分本地保存历史和由远端 Agent 服务保存线程状态两种方式。

### 7. 记忆与相关内容检索

- 了解当前 Python SDK 推荐使用 Vector Store/Collection 保存和检索记录。
- 能使用 `InMemoryCollection` 完成小规模练习，知道生产环境可替换为外部向量数据库连接器。
- 能完成建集合、写入记录、执行搜索和读取结果的基本流程。
- 不再使用已经弃用的 `SemanticTextMemory`、`VolatileMemoryStore` 或旧式 Memory Store 示例。

### 8. 多智能体分工与协作

- 能区分顺序、并发、交接和群聊等编排方式。
- 能根据任务依赖选择顺序或并发方式，而不是盲目增加 Agent。
- 能为 `SequentialOrchestration` 提供成员，启动 `InProcessRuntime`，取得结果并正常停止运行环境。
- 知道 Agent Orchestration 仍可能处于实验阶段，提交作品时应固定依赖版本。

## M3：流程、部署与质量评测

**模块目标**：使用流程框架组织任务，并完成可观测、安全控制、部署检查和质量评测。

### 9. Process Framework 步骤与事件

- 了解 Process、Step 和 Event 的职责。
- 能用 `ProcessBuilder` 添加步骤，并通过事件定义步骤之间的连接。
- 能构建流程，并使用初始事件启动流程。

### 10. 日志、跟踪与可观测性

- 了解日志、指标和追踪是可观测性的三个主要方面。
- 能配置 OpenTelemetry Provider 和 Console Exporter。
- 能通过一次真实 Kernel 调用产生可检查的遥测数据。
- 知道提示词和模型输出可能包含敏感数据，默认不启用敏感内容遥测。

### 11. 过滤、安全与异常处理

- 了解 Function Invocation、Prompt Render 和 Auto Function Invocation 三类过滤器。
- 能使用过滤器记录调用、检查参数、处理异常或阻止不合规操作。
- 能说明服务端内容过滤与应用层过滤的边界。
- 不把第三方重试库示例写成 Semantic Kernel 官方安全机制。

### 12. 部署与质量评测

- 能从环境变量加载连接配置，并避免提交密钥。
- 能记录请求是否成功、响应耗时和输出检查结果。
- 能根据固定输入、固定预期结果和统一评分方法重复运行评测。
- 能区分 Semantic Kernel 提供的遥测数据与 ECHO 根据比赛要求计算的质量指标。

## 官方材料清单

以下只登记材料级信息。导入 RAG 后的切片编号和内容哈希由检索系统自动生成。

| 模块 | 材料名称 | 官方链接 | 相关章节 | 登记日期 |
|---|---|---|---|---|
| M1 | Understanding the kernel in Semantic Kernel | https://learn.microsoft.com/en-us/semantic-kernel/concepts/kernel | Build a kernel with services and plugins | 2026-08-10 |
| M1 | Kernel Python API | https://learn.microsoft.com/en-us/python/api/semantic-kernel/semantic_kernel.kernel%28class%29?view=semantic-kernel-python | invoke、invoke_prompt | 2026-08-10 |
| M1 | Provide native code to your agents | https://learn.microsoft.com/en-us/semantic-kernel/concepts/plugins/adding-native-plugins | Defining a plugin using a class、Adding a plugin | 2026-08-10 |
| M1 | Chat history | https://learn.microsoft.com/en-us/semantic-kernel/concepts/ai-services/chat-completion/chat-history | Creating a chat history object | 2026-08-10 |
| M2 | Semantic Kernel Agent Framework | https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/ | Agent types and basic use | 2026-08-10 |
| M2 | Agent architecture | https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/agent-architecture | Agent、Agent Thread | 2026-08-10 |
| M2 | Agent streaming | https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/agent-streaming | Python thread example | 2026-08-10 |
| M2 | Vector Stores | https://learn.microsoft.com/en-us/semantic-kernel/concepts/vector-store-connectors/ | Create collection、upsert、search | 2026-08-10 |
| M2 | Python Vector Store migration | https://learn.microsoft.com/en-us/semantic-kernel/support/migration/vectorstore-python-june-2025 | Retire legacy memory stores | 2026-08-10 |
| M2 | Sequential Orchestration | https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/agent-orchestration/sequential | Setup、runtime、invoke、result | 2026-08-10 |
| M2 | Concurrent Orchestration | https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/agent-orchestration/concurrent | When to use concurrent orchestration | 2026-08-10 |
| M3 | Create your first Process | https://learn.microsoft.com/en-us/semantic-kernel/frameworks/process/examples/example-first-process | Define flow、build and run | 2026-08-10 |
| M3 | Observability in Semantic Kernel | https://learn.microsoft.com/en-us/semantic-kernel/concepts/enterprise-readiness/observability/ | Logging、metrics、tracing | 2026-08-10 |
| M3 | Telemetry with console | https://learn.microsoft.com/en-us/semantic-kernel/concepts/enterprise-readiness/observability/telemetry-with-console | Python OpenTelemetry setup | 2026-08-10 |
| M3 | Semantic Kernel Filters | https://learn.microsoft.com/en-us/semantic-kernel/concepts/enterprise-readiness/filters | Filter types、Python registration | 2026-08-10 |

## 出题和检查规则

1. 每道题必须属于一个学习模块和一个知识点。
2. 前测、后测和操作题必须填写答案、评分方法、难度、官方材料和具体章节。
3. 官方页面能够打开不等于出处正确；对应章节必须直接支持答案中的关键结论。
4. 操作题使用 Python，不能保留 `...`、未导入对象或无法解释的伪代码。
5. 需要模型凭据的示例统一使用环境变量约定，不在题库中填写真实地址和密钥。
6. 只有答案明确、能够稳定判分的固定题才允许更新 MIRT；操作题默认不更新。
7. SDK 处于预览或实验状态的功能必须在材料和答案中注明，并在项目依赖中固定版本。
