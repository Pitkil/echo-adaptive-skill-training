# M1：Kernel 与插件 — 核心知识点

## 知识点 1：Semantic Kernel 是什么
**学习目标**：理解 Semantic Kernel SDK 的定位与核心价值。

Semantic Kernel 是一个开源 SDK，让开发者能够将大语言模型（LLM）集成到自己的代码中。它充当 AI 能力与传统代码之间的桥梁，简化了 AI 驱动应用的开发过程。通过 Semantic Kernel，开发者可以创建能够理解和响应自然语言提示的 AI Agent，自动完成任务、提供个性化推荐等。SK 支持 C#、Python 和 Java 等多种编程语言。

**官方出处**：
- [What is semantic kernel - Training](https://learn.microsoft.com/sr-cyrl-rs/training/modules/build-your-kernel/2-what-semantic-kernel)
- [Introduction - Build your kernel](https://learn.microsoft.com/en-in/training/modules/build-your-kernel/1-introduction)

---

## 知识点 2：Kernel（核心）— 中央编排器
**学习目标**：理解 Kernel 是 Semantic Kernel 的中心组件，掌握其创建与配置方法。

Kernel 是 Semantic Kernel 的中央组件。在最简单的意义上，Kernel 是一个依赖注入（DI）容器，管理运行 AI 应用所需的所有服务和插件。将所有服务和插件提供给 Kernel 后，AI 会根据需要无缝使用它们。

Kernel 位于系统中心，Semantic Kernel SDK 中的几乎所有组件都通过它来运行提示词或代码。这意味着开发者拥有一个**单一位置**来配置和监控 AI Agent。

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

---

## 知识点 3：AI Service Connectors（AI 服务连接器）
**学习目标**：理解如何通过连接器接入不同的 AI 模型服务。

AI Service Connectors 提供了一层抽象，通过统一接口暴露来自不同提供商的多种 AI 服务类型。支持的服务包括：Chat Completion（聊天补全）、Text Generation（文本生成）、Embedding Generation（嵌入生成）、Text to Image、Image to Text、Text to Audio 和 Audio to Text。

当某个实现注册到 Kernel 后，Chat Completion 或 Text Generation 服务会默认被任何对 Kernel 的方法调用使用。

**官方出处**：
- [Semantic Kernel Components](https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/semantic-kernel-components)

---

## 知识点 4：Plugins（插件）与 Functions（函数）
**学习目标**：理解插件的概念，掌握如何创建和注册插件。

插件是 Semantic Kernel SDK 的关键组件。插件将函数封装到一个集合中，供 AI 使用。在后台，Semantic Kernel 使用函数调用（Function Calling）来执行规划和调用代码——LLM 可以请求特定函数，Semantic Kernel 将请求路由到代码中对应的函数，结果返回给 LLM 以生成最终响应。

**Plugin（插件）** 是有名称的函数容器，每个插件可以包含一个或多个函数。插件可以注册到 Kernel，Kernel 通过两种方式使用它们：
1. **向 Chat Completion AI 通告**：让 AI 可以选择调用它们
2. **在模板渲染期间调用**：从模板中调用

函数可以来自多种来源：原生代码、OpenAPI 规范、ITextSearch 实现（用于 RAG 场景），以及提示词模板。

创建插件函数时，必须包含描述函数行为的详细信息（输入、输出、副作用），并以 AI 可以理解的方式编写。

**官方出处**：
- [Understand native plugins - Training](https://learn.microsoft.com/en-my/training/modules/give-your-ai-agent-skills/2-understand-native-plugins)
- [Create Semantic Kernel plugins - Training](https://learn.microsoft.com/en-us/training/modules/create-semantic-kernel-plugins)

---

## 知识点 5：Prompt Templates（提示词模板）
**学习目标**：理解提示词模板的作用，掌握创建和使用提示词模板的方法。

提示词模板允许开发者或提示词工程师创建混合了上下文、AI 指令、用户输入和函数输出的模板。例如，模板可以包含对 Chat Completion AI 模型的指令、用户输入的占位符，以及在调用 AI 模型前需要执行的硬编码插件调用。

Semantic Kernel 提示词模板语言是一种使用纯文本定义和组合 AI 函数的简单方式。可以用它来创建自然语言提示、生成响应、提取信息、调用其他提示，或执行任何可用文本表达的任务。

提示词模板的两种使用方式：
1. **作为 Chat Completion 流程的起点**：让 Kernel 渲染模板，并用渲染结果调用 Chat Completion AI 模型
2. **作为插件函数**：像其他函数一样被调用

使用提示词模板时，首先会被渲染（包括执行其中硬编码的函数引用），渲染后的提示词传递给 Chat Completion AI 模型，AI 生成的结果返回给调用者。

**官方出处**：
- [Semantic Kernel Components](https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/semantic-kernel-components)
- [Use semantic kernel prompt templates](https://learn.microsoft.com/en-us/training/modules/use-semantic-kernel-prompt-templates)


## M2：Agent 与多智能体协作 — 核心知识点

### 知识点 1：Agent（智能体）是什么
**学习目标**：理解 Semantic Kernel 中 Agent 的定位与核心概念。

Agent 是 Semantic Kernel Agent Framework 的核心抽象。`Agent` 类是所有 Semantic Kernel Agent 的基类[reference:75]。一个 Agent 实例可以参与一个或多个对话，一个对话也可以包含一个或多个 Agent[reference:77]。除了身份标识和描述性元数据外，每个 Agent 还必须定义其通信协议（`AgentChannel`）。

Agent Framework 的核心目标包括[reference:79]：
- 作为实现 Agent 功能的基础平台
- 支持多种不同类型的 Agent 在同一个对话中协作，各自贡献独特能力
- 支持人工输入参与协作
- 一个 Agent 可以同时参与和管理多个并发对话

Agent 可以被直接调用来执行任务，也可以通过不同的编排模式进行协调[reference:81]。这种灵活的结构使 Agent 能够适应各种对话或任务驱动的场景。

**官方出处**：
- [Agent Class - Python API](https://learn.microsoft.com/en-us/python/api/semantic-kernel/semantic_kernel.agents.agent.agent)
- [Semantic Kernel Agent Architecture](https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture)


### 知识点 2：Agent 类型
**学习目标**：了解 Semantic Kernel 支持的主要 Agent 类型及其适用场景。

Semantic Kernel Agent Framework 提供了多种内置 Agent 类型[reference:82][reference:83]：

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


### 知识点 3：Agent Thread（对话线程与状态）
**学习目标**：理解 Agent 如何管理和保持对话状态。

`AgentThread` 类是对话线程或对话状态的核心抽象[reference:84]。它抽象了不同 Agent 管理对话状态的不同方式[reference:86]：

- **有状态 Agent 服务**：对话状态存储在服务端，通过 ID 进行交互[reference:87]。例如 `AzureAIAgent` 需要匹配的 `AzureAIAgentThread`，因为 Azure AI Agent 服务将对话存储在服务端，需要特定的服务调用来创建和更新线程[reference:88]。

- **无状态 Agent**：每次调用时需要将完整的对话历史传递给 Agent，对话状态在应用本地管理[reference:90]。

有状态 Agent 通常只能与匹配的 `AgentThread` 实现配合使用，而其他类型的 Agent 可能支持多种 `AgentThread` 类型[reference:91]。

**官方出处**：
- [Semantic Kernel Agent Architecture - Agent Thread](https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture)


### 知识点 4：Agent Orchestration（多 Agent 编排）
**学习目标**：理解如何协调多个 Agent 协作完成复杂任务。

Agent Orchestration 框架使开发者能够轻松构建、管理和扩展复杂的 Agent 工作流[reference:92]。多 Agent 编排的核心价值在于：通过编排多个各自具有专长或角色的 Agent，可以解决复杂的、多方面的任务[reference:93]。

Semantic Kernel 支持多种**编排模式（Orchestration Patterns）**[reference:94][reference:95]：

- **Sequential（顺序编排）**：Agent 按流水线方式组织，每个 Agent 依次处理任务，将输出传递给序列中的下一个 Agent[reference:96]
- **Concurrent（并发编排）**：多个 Agent 并行处理同一个任务，各自独立处理输入，结果被收集和汇总[reference:97][reference:98]
- **Handoff（交接编排）**：Agent 之间通过交接方式传递任务控制权
- **Group Chat（群聊编排）**：模拟 Agent 之间的协作对话，可选包含人类参与者[reference:99]
- **Magentic**：特定编排模式

Orchestration 框架还支持**输入/输出数据转换**，使编排流程能够适配 Agent 与外部系统之间的数据格式[reference:100]，以及**人在回路（Human-in-the-loop）**，支持人工参与编排过程[reference:101]。

> **注意**：Agent Orchestration 功能目前处于实验阶段，正在积极开发中[reference:102][reference:103]。原有的 `AgentGroupChat` 编排模式已不再维护，推荐使用新的 `GroupChatOrchestration` 模式[reference:104][reference:105]。

**官方出处**：
- [Agent Orchestration - Semantic Kernel](https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture)
- [Concurrent Agent Orchestration](https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-orchestration/concurrent)


### 知识点 5：Agent 调用与响应
**学习目标**：理解如何调用 Agent 并获取响应。

Semantic Kernel Agent 支持统一的调用接口，使代码能够跨不同 Agent 类型无缝运行[reference:106]。

主要调用方法：

- **`invoke`**：调用 Agent，返回 Agent 执行过程中的中间步骤和最终结果，作为 `AgentResponseItem` 对象的异步流
- **`invoke_stream`**：流式调用 Agent，返回中间步骤和最终结果的流式版本，适用于需要实时反馈的场景
- **`get_response`**：获取 Agent 的最终响应，阻塞调用直到最终结果可用

Agent 支持两种非流式调用方法，允许以不同方式传递消息，也可以不带消息调用 Agent[reference:111]。

**官方出处**：
- [Agent Class - Methods](https://learn.microsoft.com/en-us/python/api/semantic-kernel/semantic_kernel.agents.agent.agent)
- [The Semantic Kernel Common Agent API surface](https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture)


## M3：流程、部署与质量评测 — 核心知识点

### 知识点 1：Process Framework（流程框架）概述
**学习目标**：理解 Process Framework 的定位与核心价值。

Process Framework 是 Semantic Kernel 中用于定义、序列化和执行多步骤 AI 工作流的方式[reference:112]。它是一个**有状态的、事件驱动的工作流引擎**，旨在对集成 AI 能力的复杂业务流程进行建模[reference:113]。

这个框架使开发者能够高效地创建、管理和部署业务流程，同时利用 AI 的强大能力以及现有的代码和系统。Process Framework 的核心优势包括：

- **基于 Semantic Kernel**：步骤可以利用一个或多个 Kernel Function，在流程中充分利用 Semantic Kernel 的全部能力
- **可重用性与灵活性**：步骤和流程可以在不同应用间复用，促进模块化和可扩展性
- **事件驱动架构**：利用事件和元数据触发步骤间的动作和转换
- **完整控制与可审计性**：以定义明确且可重复的方式维护流程控制，通过 OpenTelemetry 提供审计能力

**官方出处**：
- [Overview of the Process Framework](https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework)


### 知识点 2：Process 的核心概念（Process、Step、Event）
**学习目标**：掌握 Process Framework 的三个核心概念。

Process Framework 围绕三个主要实体构建[reference:116]：

**1. Process（流程）**
Process 是一个结构化的活动或任务序列，用于交付服务或产品。它是步骤的容器以及连接步骤的边（事件路由）的集合[reference:118]。一个 Process 由多个 Step 组成，以实现特定的业务目标。

**2. Step（步骤）**
Step 是流程中的一个活动，具有定义的输入和输出，为更大的目标做出贡献。每个 Step 通过调用用户定义的 Kernel Function 来执行任务。Step 可以是一个 Kernel Function 调用、一个条件分支或一个循环[reference:122]。从机制上讲，Step 被定义为一个有向图，每个 Step 都有输入、输出和要执行的函数[reference:123]。

**3. Event（事件）**
Process 利用事件驱动模型来管理工作流的执行[reference:124]。事件用于触发 Step 之间的动作和转换。

**官方出处**：
- [Overview of the Process Framework - Core Concepts](https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework)


### 知识点 3：创建和定义 Process
**学习目标**：理解如何创建和定义 Process。

创建 Process 的基本流程：

1. **定义 Step**：每个 Step 由一个类定义，该类继承自 `KernelProcessStep` 基类，并在方法上添加 `[KernelFunction]` 属性
2. **构建 Process**：使用 `ProcessBuilder` 将 Step 按有向图的方式组织起来[reference:128]
3. **执行 Process**：通过 Local Runtime 或 Dapr Runtime 执行

Process Framework 支持多种操作模式：
- **顺序执行（Sequential）**
- **并行处理（Parallel）**
- **Fan-in / Fan-out 配置**
- **Map-Reduce 策略**

Process 可以在本地开发环境和云运行时之间无缝部署[reference:130]。Process Framework 提供了**进程内运行时（in-process runtime）** ，允许开发者在本地机器或服务器上直接运行流程，无需复杂设置或额外基础设施[reference:131]。

**官方出处**：
- [How-To: Create your first Process](https://learn.microsoft.com/en-us/semantic-kernel/frameworks/process/examples/example-first-process)


### 知识点 4：可观测性（Observability）— 日志、指标与追踪
**学习目标**：理解 Semantic Kernel 的可观测性能力，掌握如何监控和分析 AI 应用。

可观测性是构建企业就绪 AI 解决方案的关键要求。可观测性通常通过**日志（Logging）、指标（Metrics）和追踪（Tracing）** 实现，它们被称为可观测性的三大支柱。

Semantic Kernel **设计为可观测的**，它发出的日志、指标和追踪兼容 **OpenTelemetry 标准**[reference:135]：

**1. Logging（日志）**
Semantic Kernel 记录来自 Kernel、Kernel 插件和函数以及 AI 连接器的有意义的事件和错误[reference:137]。

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


### 知识点 5：部署与质量评测
**学习目标**：了解 Semantic Kernel 应用的部署方式和质量评测方法。

**部署方式**：
- **本地开发**：使用 Process Framework 的 in-process runtime 在本地直接运行[reference:144]
- **容器化部署**：通过 Docker 容器部署
- **云部署**：部署到 Azure 等云平台[reference:145]

**质量评测**：
Semantic Kernel 支持通过可观测性数据对 AI 应用进行质量评测[reference:146]：
- **质量评分（Eval Suites）**：对实际流量进行质量和接地性（groundedness）评分
- **漂移检测（Drift Detection）**：检测部署后行为变化
- **版本化评测历史（Versioned Eval History）**：在发布前捕获回归问题

通过 `observe → evaluate → improve` 的闭环，持续改进 Semantic Kernel Agent 的质量[reference:147]。

**官方出处**：
- [Process Framework - Deployment](https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework)
- [Observability in Semantic Kernel](https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/enterprise-readiness/observability/)


## 官方材料清单（M1）

| 材料名称 | 官方链接 | 版本/日期 | 相关章节 |
|---|---|---|---|
| What is semantic kernel | https://learn.microsoft.com/sr-cyrl-rs/training/modules/build-your-kernel/2-what-semantic-kernel | 2025-01-23 | 全文 |
| Understanding the kernel in Semantic Kernel | https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/kernel | 2023-07-12 | 全文 |
| Semantic Kernel Components | https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/semantic-kernel-components | 2024-11-15 | 全文 |
| Understand native plugins - Training | https://learn.microsoft.com/en-my/training/modules/give-your-ai-agent-skills/2-understand-native-plugins | 2025-01-24 | 全文 |
| Build your kernel - Training | https://learn.microsoft.com/en-us/training/modules/build-your-kernel | 2025-05-27 | 全文 |
| Create Semantic Kernel plugins - Training | https://learn.microsoft.com/en-us/training/modules/create-semantic-kernel-plugins | 2025-05-27 | 全文 |
| Use semantic kernel prompt templates | https://learn.microsoft.com/en-us/training/modules/use-semantic-kernel-prompt-templates | 2025-01-24 | 全文 |


## 官方材料清单（M2）

| 材料名称 | 官方链接 | 版本/日期 | 相关章节 |
|---|---|---|---|
| Semantic Kernel Agent Architecture | https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture | 2024-09-13 | 全文 |
| Agent Class - Python API | https://learn.microsoft.com/en-us/python/api/semantic-kernel/semantic_kernel.agents.agent.agent | 2025-04-04 | 全文 |
| Concurrent Agent Orchestration | https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-orchestration/concurrent | 2025-05-19 | 全文 |
| Agent Orchestration Overview | https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-orchestration | 2025-05-19 | 全文 |
| Semantic Kernel Components | https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/semantic-kernel-components | 2024-11-15 | Agent 部分 |


## 官方材料清单（M3）

| 材料名称 | 官方链接 | 版本/日期 | 相关章节 |
|---|---|---|---|
| Overview of the Process Framework | https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework | 2024-09-28 | 全文 |
| How-To: Create your first Process | https://learn.microsoft.com/en-us/semantic-kernel/frameworks/process/examples/example-first-process | 2025-01-13 | 全文 |
| Observability in Semantic Kernel | https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/enterprise-readiness/observability/ | 2024-09-11 | 全文 |
| Process Framework - Deployment | https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework | 2024-09-28 | Key Features / Getting Started |
| Semantic Kernel integration — observe, evaluate & improve | https://prefactor.tech | — | 全文 |