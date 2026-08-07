# ECHO 学习模块与核心知识点

本文档对齐 `apps/api/catalog.py` 中定义的 12 个知识点，用于指导后续题库准备、资源生成和内容检查。

**知识来源限定**：仅使用 Microsoft Learn Semantic Kernel 文档（`learn.microsoft.com`）和 `microsoft/semantic-kernel` 官方仓库。非 Microsoft 来源不作为知识依据。


## M1：Kernel 与插件

### 知识点 1：Kernel（核心概念）

**学习目标**：理解 Kernel 是 Semantic Kernel 的中央编排器，掌握其创建与配置方法。

Kernel 是 Semantic Kernel 的中央组件。在最简单的意义上，Kernel 是一个依赖注入（DI）容器，管理运行 AI 应用所需的所有服务和插件。将所有服务和插件提供给 Kernel 后，AI 会根据需要无缝使用它们。

当通过 Kernel 调用一个提示词时，Kernel 会：
1. 选择最佳的 AI 服务来运行提示词
2. 使用提供的提示词模板构建提示词
3. 将提示词发送给 AI 服务
4. 接收并解析响应
5. 将 LLM 的响应返回给应用

在整个过程中，开发者可以创建事件和中间件，在每一步触发操作，如日志记录、状态更新和负责任的 AI 实践。

**官方出处**：
- [Understanding the kernel in Semantic Kernel](https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/kernel)
- [Build your kernel - Training](https://learn.microsoft.com/en-us/training/modules/build-your-kernel)


### 知识点 2：插件（Plugins）

**学习目标**：理解插件的概念，掌握如何创建和注册插件。

插件是 Semantic Kernel SDK 的关键组件。插件将函数封装到一个集合中，供 AI 使用。在后台，Semantic Kernel 使用函数调用（Function Calling）来执行规划和调用代码——LLM 可以请求特定函数，Semantic Kernel 将请求路由到代码中对应的函数，结果返回给 LLM 以生成最终响应。

**Plugin（插件）** 是有名称的函数容器，每个插件可以包含一个或多个函数。插件可以注册到 Kernel，Kernel 通过两种方式使用它们：
1. **向 Chat Completion AI 通告**：让 AI 可以选择调用它们
2. **在模板渲染期间调用**：从模板中调用

函数可以来自多种来源：原生代码、OpenAPI 规范、ITextSearch 实现（用于 RAG 场景），以及提示词模板。

创建插件函数时，必须包含描述函数行为的详细信息（输入、输出、副作用），并以 AI 可以理解的方式编写。

**官方出处**：
- [Understand native plugins - Training](https://learn.microsoft.com/en-my/training/modules/give-your-ai-agent-skills/2-understand-native-plugins)
- [Create Semantic Kernel plugins - Training](https://learn.microsoft.com/en-us/training/modules/give-your-ai-agent-skills/)


### 知识点 3：AI 服务连接器（AI Service Connectors）

**学习目标**：理解如何通过连接器接入不同的 AI 模型服务。

AI Service Connectors 提供了一层抽象，通过统一接口暴露来自不同提供商的多种 AI 服务类型。支持的服务包括：Chat Completion（聊天补全）、Text Generation（文本生成）、Embedding Generation（嵌入生成）、Text to Image、Image to Text、Text to Audio 和 Audio to Text。

当某个实现注册到 Kernel 后，Chat Completion 或 Text Generation 服务会默认被任何对 Kernel 的方法调用使用。

**官方出处**：
- [Semantic Kernel Components](https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/semantic-kernel-components)


### 知识点 4：函数调用（Function Calling）

**学习目标**：理解 LLM 如何自动选择和调用插件函数。

Semantic Kernel SDK 使 LLM 能够自动调用插件函数。自动调用函数让应用能够更智能地响应用户输入——AI 可以自行判断需要调用哪个函数来完成用户请求，而不需要用户明确指定。

插件向 Chat Completion AI 通告后，AI 可以在生成响应时选择调用这些函数。这实现了从“用户告诉系统做什么”到“系统理解用户意图并自动执行”的转变。

**官方出处**：
- [Semantic Kernel Components](https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/semantic-kernel-components)
- [Understand native plugins - Training](https://learn.microsoft.com/en-my/training/modules/give-your-ai-agent-skills/2-understand-native-plugins)


## M2：Agent 与多智能体协作

### 知识点 1：Agent（智能体）

**学习目标**：理解 Semantic Kernel 中 Agent 的定位与核心概念。

Agent 是 Semantic Kernel Agent Framework 的核心抽象。`Agent` 类是所有 Semantic Kernel Agent 的基类。一个 Agent 实例可以参与一个或多个对话，一个对话也可以包含一个或多个 Agent。除了身份标识和描述性元数据外，每个 Agent 还必须定义其通信协议（`AgentChannel`）。

Agent Framework 的核心目标包括：
- 作为实现 Agent 功能的基础平台
- 支持多种不同类型的 Agent 在同一个对话中协作，各自贡献独特能力
- 支持人工输入参与协作
- 一个 Agent 可以同时参与和管理多个并发对话

Agent 可以被直接调用来执行任务，也可以通过不同的编排模式进行协调。Agent 支持 `invoke`、`invoke_stream` 和 `get_response` 等统一调用接口。
**官方出处**：
- [Agent Class - Python API](https://learn.microsoft.com/en-us/python/api/semantic-kernel/semantic_kernel.agents.agent.agent)
- [Semantic Kernel Agent Architecture](https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture)


### 知识点 2：Agent 类型

**学习目标**：了解 Semantic Kernel 支持的主要 Agent 类型及其适用场景。

Semantic Kernel Agent Framework 提供了多种内置 Agent 类型：

| Agent 类型 | 说明 |
|---|---|
| `ChatCompletionAgent` | 基于 Chat Completion 的通用 Agent，最常用的基础类型 |
| `OpenAIAssistantAgent` | 与 OpenAI Assistant API 集成的 Agent |
| `AzureAIAgent` | 与 Azure AI Agent Service 集成的 Agent |
| `OpenAIResponsesAgent` | 基于 OpenAI Responses API 的 Agent |
| `CopilotStudioAgent` | 与 Microsoft Copilot Studio 集成的 Agent |

每种 Agent 类型针对不同的后端服务进行了适配，开发者可以根据实际需求选择合适的类型。

**官方出处**：
- [Semantic Kernel Agent Architecture - Agent Types](https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture)


### 知识点 3：对话线程与状态（Agent Thread）

**学习目标**：理解 Agent 如何管理和保持对话状态。

`AgentThread` 类是对话线程或对话状态的核心抽象。它抽象了不同 Agent 管理对话状态的不同方式：

- **有状态 Agent 服务**：对话状态存储在服务端，通过 ID 进行交互。例如 `AzureAIAgent` 需要匹配的 `AzureAIAgentThread`，因为 Azure AI Agent 服务将对话存储在服务端，需要特定的服务调用来创建和更新线程。

- **无状态 Agent**：每次调用时需要将完整的对话历史传递给 Agent，对话状态在应用本地管理。

有状态 Agent 通常只能与匹配的 `AgentThread` 实现配合使用，而其他类型的 Agent 可能支持多种 `AgentThread` 类型。

**官方出处**：
- [Semantic Kernel Agent Architecture - Agent Thread](https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture)


### 知识点 4：多 Agent 编排（Agent Orchestration）

**学习目标**：理解如何协调多个 Agent 协作完成复杂任务。

Agent Orchestration 框架使开发者能够轻松构建、管理和扩展复杂的 Agent 工作流。多 Agent 编排的核心价值在于：通过编排多个各自具有专长或角色的 Agent，可以解决复杂的、多方面的任务。

Semantic Kernel 支持多种**编排模式（Orchestration Patterns）**：

- **Sequential（顺序编排）**：Agent 按流水线方式组织，每个 Agent 依次处理任务，将输出传递给序列中的下一个 Agent
- **Concurrent（并发编排）**：多个 Agent 并行处理同一个任务，各自独立处理输入，结果被收集和汇总
- **Handoff（交接编排）**：Agent 之间通过交接方式传递任务控制权
- **Group Chat（群聊编排）**：模拟 Agent 之间的协作对话，可选包含人类参与者

Orchestration 框架还支持**输入/输出数据转换**，使编排流程能够适配 Agent 与外部系统之间的数据格式，以及**人在回路（Human-in-the-loop）**，支持人工参与编排过程。

> **注意**：Agent Orchestration 功能目前处于实验阶段，正在积极开发中。原有的 `AgentGroupChat` 编排模式已不再维护，推荐使用新的 `GroupChatOrchestration` 模式。

**官方出处**：
- [Agent Orchestration - Semantic Kernel](https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture)
- [Concurrent Agent Orchestration](https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-orchestration/concurrent)


## M3：流程、部署与质量评测

### 知识点 1：Process Framework

**学习目标**：理解 Process Framework 的定位、核心概念与核心价值。

Process Framework 是 Semantic Kernel 中用于定义、序列化和执行多步骤 AI 工作流的方式。它是一个**有状态的、事件驱动的工作流引擎**，旨在对集成 AI 能力的复杂业务流程进行建模。

Process Framework 围绕三个主要实体构建：

**1. Process（流程）**
Process 是一个结构化的活动或任务序列，用于交付服务或产品。它是步骤的容器以及连接步骤的边（事件路由）的集合。一个 Process 由多个 Step 组成，以实现特定的业务目标。

**2. Step（步骤）**
Step 是流程中的一个活动，具有定义的输入和输出，为更大的目标做出贡献。每个 Step 通过调用用户定义的 Kernel Function 来执行任务。Step 可以是一个 Kernel Function 调用、一个条件分支或一个循环。从机制上讲，Step 被定义为一个有向图，每个 Step 都有输入、输出和要执行的函数。

**3. Event（事件）**
Process 利用事件驱动模型来管理工作流的执行。事件用于触发 Step 之间的动作和转换。

Process Framework 的核心优势包括：
- **基于 Semantic Kernel**：步骤可以利用一个或多个 Kernel Function
- **可重用性与灵活性**：步骤和流程可以在不同应用间复用
- **事件驱动架构**：利用事件和元数据触发步骤间的动作和转换
- **完整控制与可审计性**：通过 OpenTelemetry 提供审计能力

**官方出处**：
- [Overview of the Process Framework](https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework)


### 知识点 2：Process 的定义与执行

**学习目标**：理解如何创建、构建和执行 Process。

创建 Process 的基本流程：

1. **定义 Step**：每个 Step 由一个类定义，该类继承自 `KernelProcessStep` 基类，并在方法上添加 `[KernelFunction]` 属性
2. **构建 Process**：使用 `ProcessBuilder` 将 Step 按有向图的方式组织起来
3. **执行 Process**：通过 Local Runtime 或 Dapr Runtime 执行

Process Framework 支持多种操作模式：
- **顺序执行（Sequential）**
- **并行处理（Parallel）**
- **Fan-in / Fan-out 配置**
- **Map-Reduce 策略**

Process 可以在本地开发环境和云运行时之间无缝部署。Process Framework 提供了**进程内运行时（in-process runtime）** ，允许开发者在本地机器或服务器上直接运行流程，无需复杂设置或额外基础设施。

**官方出处**：
- [How-To: Create your first Process](https://learn.microsoft.com/en-us/semantic-kernel/frameworks/process/examples/example-first-process)
- [Overview of the Process Framework](https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework)


### 知识点 3：可观测性（Observability）

**学习目标**：理解 Semantic Kernel 的可观测性能力，掌握如何监控和分析 AI 应用。

可观测性是构建企业就绪 AI 解决方案的关键要求。可观测性通常通过**日志（Logging）、指标（Metrics）和追踪（Tracing）** 实现，它们被称为可观测性的三大支柱。

Semantic Kernel **设计为可观测的**，它发出的日志、指标和追踪兼容 **OpenTelemetry 标准**：

**1. Logging（日志）**
Semantic Kernel 记录来自 Kernel、Kernel 插件和函数以及 AI 连接器的有意义的事件和错误。

**2. Metrics（指标）**
Semantic Kernel 从 Kernel Function 和 AI 连接器发出指标，包括：
- `semantic_kernel.function.invocation.duration`：函数执行时间（秒）
- `semantic_kernel.function.streaming.duration`：函数流式执行时间（秒）
- `semantic_kernel.function.invocation.token_usage.prompt`：提示词 Token 使用量
- `semantic_kernel.function.invocation.token_usage.completion`：补全 Token 使用量

**3. Tracing（追踪）**
Semantic Kernel 支持分布式追踪。每次 Kernel Function 执行和每次 AI 模型调用都被记录为一个 Activity。所有 Activity 由名为 `Microsoft.SemanticKernel` 的 Activity Source 生成。

> **注意**：敏感数据（如 Kernel Function 参数和结果）在 Trace 级别记录。

**官方出处**：
- [Observability in Semantic Kernel](https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/enterprise-readiness/observability/)


### 知识点 4：部署与质量评测

**学习目标**：了解 Semantic Kernel 应用的部署方式和质量评测方法。

**部署方式**：
- **本地开发**：使用 Process Framework 的 in-process runtime 在本地直接运行
- **容器化部署**：通过 Docker 容器部署
- **云部署**：部署到 Azure 等云平台

**质量评测**：
Semantic Kernel 支持通过可观测性数据对 AI 应用进行质量评测：
- **质量评分（Eval Suites）**：对实际流量进行质量和接地性（groundedness）评分
- **漂移检测（Drift Detection）**：检测部署后行为变化
- **版本化评测历史（Versioned Eval History）**：在发布前捕获回归问题

通过 `observe → evaluate → improve` 的闭环，持续改进 Semantic Kernel Agent 的质量。

**官方出处**：
- [Overview of the Process Framework](https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework)
- [Observability in Semantic Kernel](https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/enterprise-readiness/observability/)


## 官方材料清单

以下材料仅限 Microsoft 官方来源，用于基于多路召回与混合向量的可追溯 RAG 检索引擎导入和引用。

### M1：Kernel 与插件

| 材料名称 | 官方链接 | 版本/日期 | 相关章节 |
|---|---|---|---|
| Understanding the kernel in Semantic Kernel | https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/kernel | 2023-07-12 | 全文 |
| Create Semantic Kernel plugins - Training | https://learn.microsoft.com/en-us/training/modules/give-your-ai-agent-skills/ | 2025-05-27 | 全文 |
| Semantic Kernel Components | https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/semantic-kernel-components | 2024-11-15 | 全文 |
| Understand native plugins - Training | https://learn.microsoft.com/en-my/training/modules/give-your-ai-agent-skills/2-understand-native-plugins | 2025-01-24 | 全文 |
| Create Semantic Kernel plugins - Training | https://learn.microsoft.com/en-us/training/modules/create-semantic-kernel-plugins | 2025-05-27 | 全文 |

### M2：Agent 与多智能体协作

| 材料名称 | 官方链接 | 版本/日期 | 相关章节 |
|---|---|---|---|
| Semantic Kernel Agent Architecture | https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture | 2024-09-13 | 全文 |
| Agent Class - Python API | https://learn.microsoft.com/en-us/python/api/semantic-kernel/semantic_kernel.agents.agent.agent | 2025-04-04 | 全文 |
| Concurrent Agent Orchestration | https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-orchestration/concurrent | 2025-05-19 | 全文 |
| Agent Orchestration Overview | https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-orchestration | 2025-05-19 | 全文 |

### M3：流程、部署与质量评测

| 材料名称 | 官方链接 | 版本/日期 | 相关章节 |
|---|---|---|---|
| Overview of the Process Framework | https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework | 2024-09-28 | 全文 |
| How-To: Create your first Process | https://learn.microsoft.com/en-us/semantic-kernel/frameworks/process/examples/example-first-process | 2025-01-13 | 全文 |
| Observability in Semantic Kernel | https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/enterprise-readiness/observability/ | 2024-09-11 | 全文 |