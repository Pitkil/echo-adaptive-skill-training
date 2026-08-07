# ECHO 学习模块与核心知识点

本文档严格对齐 `apps/api/catalog.py` 中定义的 12 个知识点，用于指导题库准备、资源生成和内容检查。

**知识来源限定**：仅使用 Microsoft Learn Semantic Kernel 文档（`learn.microsoft.com`）和 `microsoft/semantic-kernel` 官方仓库。


## M1：Kernel 与插件

**模块目标**：创建 Kernel、接入模型服务，并使用提示词、插件和函数调用完成对话任务。

### 知识点 1：Kernel 创建与模型服务接入

**学习目标**：掌握 Kernel 的创建方法，理解如何接入不同的 AI 模型服务。

Kernel 是 Semantic Kernel 的中央编排器（调度中心）。在最简单的意义上，Kernel 是一个依赖注入（DI）容器，管理运行 AI 应用所需的所有服务和插件。将所有服务和插件提供给 Kernel 后，AI 会根据需要无缝使用它们。

AI Service Connectors 提供了一层抽象，通过统一接口暴露来自不同提供商的多种 AI 服务类型。支持的服务包括：Chat Completion（聊天补全）、Text Generation（文本生成）、Embedding Generation（嵌入生成）等。

**Python 示例**：
```python
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

kernel = Kernel()
kernel.add_service(AzureChatCompletion(
    endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
))
```
# Semantic Kernel 知识点整理

---

## M1：Kernel 与插件

### 知识点 2：提示词与聊天完成

**学习目标**：理解提示词模板的作用，掌握创建和使用提示词模板的方法。

提示词模板允许开发者或提示词工程师创建混合了上下文、AI 指令、用户输入和函数输出的模板。Semantic Kernel 提示词模板语言是一种使用纯文本定义和组合 AI 函数的简单方式。

**提示词模板的两种使用方式**：

- 作为 **Chat Completion 流程的起点**：让 Kernel 渲染模板，并用渲染结果调用 Chat Completion AI 模型
- 作为 **插件函数**：像其他函数一样被调用

**Python 示例**：

```python
# 从提示词创建 KernelFunction
func = kernel.create_function_from_prompt("Hello {{$name}}, welcome to Semantic Kernel!")
# 带参数调用
result = await kernel.invoke(func, name="World")
```
# Semantic Kernel 知识点整理

---

## M1：Kernel 与插件（续）

### 知识点 3：插件定义与函数调用

**学习目标**：理解插件的概念，掌握如何创建和注册插件，理解 LLM 如何自动选择和调用插件函数。

插件是 Semantic Kernel SDK 的关键组件。插件将函数封装到一个集合中，供 AI 使用。在后台，Semantic Kernel 使用**函数调用（Function Calling）**来执行规划和调用代码。

- **Plugin（插件）** 是有名称的函数容器，每个插件可以包含一个或多个函数。
- 插件可以注册到 Kernel，通过向 Chat Completion AI 通告或从模板中调用来使用。
- **自动函数调用**：当 Plugin 向 Chat Completion AI 通告后，AI 可以在生成响应时选择调用这些函数，实现了从"用户告诉系统做什么"到"系统理解用户意图并自动执行"的转变。

**官方出处**：
- [Understand native plugins - Training](https://learn.microsoft.com/en-my/training/modules/give-your-ai-agent-skills/2-understand-native-plugins)
- [Create Semantic Kernel plugins - Training](https://learn.microsoft.com/en-us/training/modules/give-your-ai-agent-skills/)

---

### 知识点 4：多轮对话与执行设置

**学习目标**：理解如何管理多轮对话的上下文和状态，掌握执行设置（如温度、最大令牌数等）的配置方法。

在多轮对话场景中，需要维护对话的上下文和状态。Semantic Kernel 通过 Kernel 和 Agent 的配合，支持在多轮对话中保持上下文连续性。开发者可以通过配置执行设置（Execution Settings）来控制 LLM 的生成行为，如温度（Temperature）、最大令牌数（MaxTokens）等。

**官方出处**：
- [Conversation history and state management](https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/kernel)（相关章节）

---

## M2：Agent 与多智能体协作

**模块目标**：创建 Agent、维护对话状态和记忆，并组织多个 Agent 分工协作。

---

### 知识点 5：Agent 创建与指令设计

**学习目标**：理解 Agent 的核心概念，掌握创建 Agent 和设计指令的方法。

Agent 是 Semantic Kernel Agent Framework 的核心抽象。`Agent` 类是所有 Semantic Kernel Agent 的基类。一个 Agent 实例可以参与一个或多个对话，每个 Agent 必须定义其通信协议（`AgentChannel`）。

Semantic Kernel Agent Framework 提供了多种内置 Agent 类型：
- `ChatCompletionAgent`（通用基础）
- `OpenAIAssistantAgent`
- `AzureAIAgent`
- `OpenAIResponsesAgent`
- `CopilotStudioAgent`

Agent 支持统一的调用接口：`invoke`、`invoke_stream`、`get_response`。

**官方出处**：
- [Agent Class - Python API](https://learn.microsoft.com/en-us/python/api/semantic-kernel/semantic_kernel.agents.agent.agent)
- [Semantic Kernel Agent Architecture](https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture)

---

### 知识点 6：对话线程与状态管理

**学习目标**：理解 Agent 如何管理和保持对话状态。

`AgentThread` 类是对话线程或对话状态的核心抽象。它抽象了不同 Agent 管理对话状态的不同方式：

- **有状态 Agent 服务**：对话状态存储在服务端，通过 ID 进行交互。例如 `AzureAIAgent` 需要匹配的 `AzureAIAgentThread`。
- **无状态 Agent**：每次调用时需要将完整的对话历史传递给 Agent，状态在应用本地管理。

**官方出处**：
- [Semantic Kernel Agent Architecture - Agent Thread](https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture)

---

### 知识点 7：记忆与相关内容检索

**学习目标**：理解 Semantic Kernel 的记忆机制，掌握如何为 Agent 配置记忆和检索相关内容。

**记忆（Memory）** 是 Semantic Kernel Agent Framework 的重要组成部分。通过记忆，Agent 可以跨会话保留用户信息、历史对话内容和关键事实。Semantic Kernel 支持多种记忆存储后端，包括内存存储、向量数据库等。

`ITextSearch` 接口提供了文本搜索和检索能力，支持语义搜索、关键词搜索和混合搜索。

**官方出处**：
- [Memory in Semantic Kernel](https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture)（相关章节）
- [ITextSearch Interface](https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture)

---

### 知识点 8：多智能体分工与协作

**学习目标**：理解如何协调多个 Agent 协作完成复杂任务。

Agent Orchestration 框架使开发者能够构建、管理和扩展复杂的 Agent 工作流。Semantic Kernel 支持多种编排模式：

- **Sequential（顺序编排）**：Agent 按流水线方式组织，依次处理任务
- **Concurrent（并发编排）**：多个 Agent 并行处理，结果被收集和汇总
- **Handoff（交接编排）**：Agent 之间通过交接方式传递任务控制权
- **Group Chat（群聊编排）**：模拟 Agent 之间的协作对话

> **注意**：Agent Orchestration 功能目前处于实验阶段。原有的 `AgentGroupChat` 模式已不再维护，推荐使用 `GroupChatOrchestration`。

**官方出处**：
- [Agent Orchestration - Semantic Kernel](https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-orchestration/concurrent)
- [Concurrent Agent Orchestration](https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-orchestration/concurrent)

---

## M3：流程、部署与质量评测

**模块目标**：使用流程框架组织任务，完成可观测、安全、部署和质量评测。

---

### 知识点 9：Process Framework 步骤与事件

**学习目标**：理解 Process Framework 的定位，掌握 Process、Step 和 Event 三个核心概念。

Process Framework 是 Semantic Kernel 中用于定义、序列化和执行多步骤 AI 工作流的方式。它是一个有状态的、事件驱动的工作流引擎。

Process Framework 围绕三个主要实体构建：

1. **Process（流程）**：步骤的容器以及连接步骤的边（事件路由）的集合。
2. **Step（步骤）**：流程中的一个活动，通过调用用户定义的 Kernel Function 执行任务。
3. **Event（事件）**：用于触发 Step 之间的动作和转换。

**官方出处**：
- [Overview of the Process Framework](https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework)

---

### 知识点 10：日志、跟踪与可观测性

**学习目标**：理解 Semantic Kernel 的可观测性能力，掌握如何通过日志、指标和追踪监控 AI 应用。

可观测性通常通过 **日志（Logging）**、**指标（Metrics）** 和 **追踪（Tracing）** 实现。

Semantic Kernel 设计为可观测的，发出的日志、指标和追踪兼容 OpenTelemetry 标准：

- **Logging（日志）**：记录 Kernel、插件和 AI 连接器的有意义事件和错误
- **Metrics（指标）**：包括 `function.invocation.duration`、`function.invocation.token_usage.prompt`、`function.invocation.token_usage.completion` 等
- **Tracing（追踪）**：每次 Kernel Function 执行和 AI 模型调用都被记录为 Activity

**官方出处**：
- [Observability in Semantic Kernel](https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/enterprise-readiness/observability/)

---

### 知识点 11：过滤、安全与异常处理

**学习目标**：了解 Semantic Kernel 的安全机制和异常处理方式。

Semantic Kernel 支持在企业级场景中保障 AI 应用的安全性：

- **内容过滤（Content Filtering）**：对输入和输出内容进行安全过滤
  - **服务端过滤（Service-side Filtering）**：利用 Azure OpenAI 等服务自带的内容过滤能力
  - **客户端过滤（Client-side Filtering）**：在应用层实现自定义过滤逻辑
- **异常处理**：为 API 调用、服务连接等场景提供明确的异常类型
- **重试策略**：支持配置自动重试和超时策略

**官方出处**：
- [Safety and reliability in Semantic Kernel](https://learn.microsoft.com/en-us/semantic-kernel/concepts/enterprise-readiness/observability/?pivots=programming-language-csharp)

---

### 知识点 12：部署与质量评测

**学习目标**：了解 Semantic Kernel 应用的部署方式和质量评测方法。

**部署方式**：
- **本地开发**：使用 Process Framework 的 in-process runtime
- **容器化部署**：通过 Docker 容器部署
- **云部署**：部署到 Azure 等云平台

**质量评测**：通过可观测性数据对 AI 应用进行质量评测，包括质量评分、漂移检测和版本化评测历史。

**官方出处**：
- [Overview of the Process Framework](https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework)
- [Observability in Semantic Kernel](https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/enterprise-readiness/observability/)

## 官方材料清单

以下材料仅限 Microsoft 官方来源，用于 RAG 检索引擎导入和引用。

### M1：Kernel 与插件

| 材料名称 | 官方链接 | 版本/日期 | 相关章节 |
|---------|---------|----------|---------|
| Understanding the kernel in Semantic Kernel | [链接](https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/kernel) | 2023-07-12 | 全文 |
| Build your kernel - Training | [链接](https://learn.microsoft.com/en-us/training/modules/build-your-kernel) | 2025-05-27 | 全文 |
| Semantic Kernel Components | [链接](https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/semantic-kernel-components) | 2024-11-15 | 全文 |
| Understand native plugins - Training | [链接](https://learn.microsoft.com/en-my/training/modules/give-your-ai-agent-skills/2-understand-native-plugins) | 2025-01-24 | 全文 |
| Create plugins for Semantic Kernel | [链接](https://learn.microsoft.com/en-us/semantic-kernel/concepts/plugins) | 2025-01-24 | 全文 |
| Prompt templates | [链接](https://learn.microsoft.com/en-us/training/modules/create-plugins-semantic-kernel/3-use-semantic-kernel-prompt-templates?pivots=csharp) | 2025-01-24 | 全文 |

### M2：Agent 与多智能体协作

| 材料名称 | 官方链接 | 版本/日期 | 相关章节 |
|---------|---------|----------|---------|
| Semantic Kernel Agent Architecture | [链接](https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture) | 2024-09-13 | 全文 |
| Agent Class - Python API | [链接](https://learn.microsoft.com/en-us/python/api/semantic-kernel/semantic_kernel.agents.agent.agent) | 2025-04-04 | 全文 |
| Concurrent Agent Orchestration | [链接](https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-orchestration/concurrent) | 2025-05-19 | 全文 |

### M3：流程、部署与质量评测

| 材料名称 | 官方链接 | 版本/日期 | 相关章节 |
|---------|---------|----------|---------|
| Overview of the Process Framework | [链接](https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework) | 2024-09-28 | 全文 |
| How-To: Create your first Process | [链接](https://learn.microsoft.com/en-us/semantic-kernel/frameworks/process/examples/example-first-process) | 2025-01-13 | 全文 |
| Observability in Semantic Kernel | [链接](https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/enterprise-readiness/observability/) | 2024-09-11 | 全文 |
| Safety and reliability in Semantic Kernel - Training | [链接](https://learn.microsoft.com/en-us/semantic-kernel/concepts/enterprise-readiness/observability/?pivots=programming-language-csharp) | 2025-01-24 | 全文 |