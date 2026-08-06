题目：Semantic Kernel SDK 如何充当 AI 能力与传统代码之间的桥梁？
答案：Semantic Kernel SDK 作为 AI 能力与传统代码之间的桥梁，通过 Kernel 统一管理 AI 服务、插件和函数，将 LLM 的推理能力与业务系统的确定性代码连接起来。开发者可以通过 Kernel 调用提示词或代码，Kernel 始终可用于检索必要的服务和插件。
题型：Open
用途：posttest
难度：基础
评分方法：答出"Kernel 统一管理 AI 服务和插件"得 1 分；答出"连接 LLM 推理与业务代码"得 1 分；共 2 分。
资料名称：Understanding the kernel in Semantic Kernel
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/concepts/kernel
出处章节：全文
是否更新MIRT：是

---
题目：Kernel 作为 Dependency Injection（DI）容器在 Semantic Kernel 中起到什么作用？
答案：Kernel 本质上是一个 DI 容器，管理运行 AI 应用所需的所有服务和插件。将所有服务和插件提供给 Kernel 后，AI 会根据需要无缝使用它们。这意味着开发者拥有一个单一位置来配置和监控 AI Agent。
题型：Open
用途：posttest
难度：基础
评分方法：答出"DI 容器/管理服务和插件"得 1 分；答出"单一位置配置和监控"得 1 分；共 2 分。
资料名称：Understanding the kernel in Semantic Kernel
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/concepts/kernel
出处章节：全文
是否更新MIRT：是

---
题目：Semantic Kernel 中 Plugin 和 Function 的关系是什么？
答案：Plugin 是函数的容器，将多个相关函数封装到一个有名称的集合中供 AI 使用。每个 Plugin 可以包含一个或多个 Function。Function 可以来自原生代码、OpenAPI 规范或提示词模板。在后台，Semantic Kernel 使用函数调用（Function Calling）来执行规划和调用代码——LLM 可以请求特定函数，Semantic Kernel 将请求路由到代码中的对应函数。
题型：Open
用途：posttest
难度：基础
评分方法：答出"Plugin 是函数的容器"得 1 分；答出"函数调用/Function Calling 路由机制"得 1 分；共 2 分。
资料名称：Understand native plugins - Training
官方链接：https://learn.microsoft.com/en-us/training/modules/give-your-ai-agent-skills/2-understand-native-plugins
出处章节：全文
是否更新MIRT：是

---
题目：以下哪一项是 Semantic Kernel 中 Kernel 的核心职责？\nA. 仅负责向量存储和检索\nB. 管理 AI 服务、插件和函数调用的中央编排器\nC. 专门处理提示词模板渲染\nD. 仅用于 C# 语言的依赖注入
答案：B
题型：Choice
用途：posttest
难度：标准
评分方法：选 B 得 2 分，其他不得分。
资料名称：Understanding the kernel in Semantic Kernel
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/concepts/kernel
出处章节：全文
是否更新MIRT：是

---
题目：在 Semantic Kernel 中，为了让 AI 能够正确使用插件函数，开发者需要提供什么？
答案：开发者创建的插件必须包含描述函数行为的详细信息，包括函数的输入、输出和副作用，并且这些信息必须以 AI 可以理解的方式撰写。在 C# 中使用 [KernelFunction]、[Description] 和 [return: Description] 属性提供元数据；在 Python 中使用 @kernel_function 装饰器并提供 description 参数。
题型：Open
用途：posttest
难度：标准
评分方法：答出"需要提供函数描述元数据"得 1 分；举出 C# 或 Python 的具体实现方式得 1 分；共 2 分。
资料名称：Understand native plugins - Training
官方链接：https://learn.microsoft.com/en-us/training/modules/give-your-ai-agent-skills/2-understand-native-plugins
出处章节：全文
是否更新MIRT：是

---
题目：Semantic Kernel 的 Prompt Template 与直接硬编码提示词相比有什么优势？
答案：Prompt Template 允许开发者创建混合了上下文、AI 指令、用户输入和函数输出的可复用模板。通过支持变量、函数调用和参数，开发者可以创建可复用且动态的模板，而不需要复杂的程序代码。模板可以包含对 Chat Completion AI 模型的指令、用户输入的占位符，以及在调用 AI 模型前需要执行的硬编码插件调用。
题型：Open
用途：posttest
难度：标准
评分方法：答出"可复用/动态模板"得 1 分；答出"支持变量和函数调用"得 1 分；共 2 分。
资料名称：Use semantic kernel prompt templates
官方链接：https://learn.microsoft.com/en-us/training/modules/use-semantic-kernel-prompt-templates
出处章节：全文
是否更新MIRT：是

---
题目：假设你正在构建一个智能客服系统，需要让 AI 能够查询订单状态、处理退款和发送通知。请说明你会如何使用 Semantic Kernel 的 Kernel、Plugin 和 Function Calling 来实现这些能力，并解释它们之间的协作关系。
答案：首先创建 Kernel 实例作为中央编排器，注册所需的 AI 服务。然后创建三个 Plugin——OrderPlugin（查询订单状态）、RefundPlugin（处理退款）、NotificationPlugin（发送通知），每个 Plugin 中封装对应的 Function，并使用 [KernelFunction] 和 [Description] 属性提供详细的函数描述。将这些 Plugin 注册到 Kernel。当用户提出请求时，Kernel 通过 Function Calling 机制让 LLM 理解用户意图并自动选择合适的 Function 执行。Kernel 将执行结果返回给 LLM 生成最终回复。三者协作：Kernel 负责调度，Plugin 封装业务逻辑，Function Calling 实现 AI 的自动决策。
题型：Open
用途：posttest
难度：进阶
评分方法：说明 Kernel 作为调度中心得 1 分；说明 Plugin 封装业务逻辑得 1 分；说明 Function Calling 实现自动决策得 1 分；共 3 分。
资料名称：Understand native plugins - Training + Understanding the kernel
官方链接：https://learn.microsoft.com/en-us/training/modules/give-your-ai-agent-skills/2-understand-native-plugins
出处章节：全文
是否更新MIRT：是

---
题目：Semantic Kernel 的自动函数调用（Automatic Function Calling）如何提升 AI 应用的智能化水平？请结合传统"用户明确指定操作"的模式进行对比说明。
答案：传统模式下，用户需要明确告诉系统执行什么操作（如"调用 complete_task 函数"），系统被动响应。而 Semantic Kernel 的自动函数调用使 LLM 能够根据用户输入自动判断需要调用哪个函数。当 Plugin 向 Chat Completion AI 通告后，AI 可以在生成响应时选择调用这些函数，实现了从"用户告诉系统做什么"到"系统理解用户意图并自动执行"的转变。这使应用能够更智能地响应用户输入，减少了用户的操作负担，提升了交互的自然度和效率。
题型：Open
用途：posttest
难度：进阶
评分方法：说明传统模式"用户明确指定"得 1 分；说明自动调用"AI 自主判断"得 1 分；说明智能化提升效果得 1 分；共 3 分。
资料名称：Understand native plugins - Training
官方链接：https://learn.microsoft.com/en-us/training/modules/give-your-ai-agent-skills/2-understand-native-plugins
出处章节：全文
是否更新MIRT：是

---
题目：Kernel 作为"中央编排器"在 Semantic Kernel 应用架构中处于什么位置？它与 AI Service Connectors 和 Plugins 之间是什么关系？
答案：Kernel 处于 Semantic Kernel 架构的中心位置。所有组件通过 Kernel 进行交互——AI Service Connectors 注册到 Kernel 提供 AI 能力，Plugins 注册到 Kernel 提供业务功能。当应用需要执行任务时，通过 Kernel 统一调度：Kernel 选择合适的 AI 服务处理提示词，同时根据 LLM 的决策调用对应的 Plugin Functions。Kernel 相当于"大脑中枢"，AI Service Connectors 是"感官"（感知外部 AI 能力），Plugins 是"手脚"（执行具体操作），三者通过 Kernel 协同完成复杂任务。
题型：Open
用途：posttest
难度：进阶
评分方法：说明 Kernel 处于中心位置得 1 分；说明与 AI Service Connectors 的关系得 1 分；说明与 Plugins 的关系得 1 分；共 3 分。
资料名称：Understanding the kernel in Semantic Kernel
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/concepts/kernel
出处章节：全文
是否更新MIRT：是

---
题目：Semantic Kernel Agent Framework 的核心设计目标是什么？
答案：Agent Framework 的核心目标包括：作为实现 Agent 功能的基础平台；支持多种不同类型的 Agent 在同一个对话中协作，各自贡献独特能力，同时整合人类输入；一个 Agent 可以同时参与和管理多个并发对话。
题型：Open
用途：posttest
难度：基础
评分方法：答出"Agent 功能的基础平台"得 1 分；答出"多 Agent 协作+人类输入"得 1 分；共 2 分。
资料名称：Semantic Kernel Agent Architecture
官方链接：https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture
出处章节：全文
是否更新MIRT：是

---
题目：Semantic Kernel 中的 `Agent` 抽象类提供了什么基础结构？
答案：`Agent` 抽象类是所有类型 Agent 的核心抽象，提供可扩展的基础结构。一个 Agent 实例可以参与一个或多个对话。除了身份标识和描述性元数据外，每个 Agent 还必须定义其通信协议（`AgentChannel`）。Agent 可以被直接调用执行任务，也可以通过不同的编排模式进行协调。
题型：Open
用途：posttest
难度：基础
评分方法：答出"所有 Agent 的基类/核心抽象"得 1 分；答出"定义通信协议/可被编排"得 1 分；共 2 分。
资料名称：Agent Class
官方链接：https://learn.microsoft.com/en-us/python/api/semantic-kernel/semantic_kernel.agents.agent.agent
出处章节：全文
是否更新MIRT：是

---
题目：`AgentThread` 如何抽象不同 Agent 的对话状态管理方式？
答案：`AgentThread` 抽象了不同 Agent 管理对话状态的不同方式。有状态的 Agent 服务（如 AzureAIAgent）将对话状态存储在服务端，通过 ID 进行交互；无状态 Agent 每次调用时需要将完整的对话历史传递给 Agent，状态在应用本地管理。有状态 Agent 通常只能与匹配的 `AgentThread` 实现配合使用。
题型：Open
用途：posttest
难度：基础
评分方法：说明有状态"服务端存储、通过ID交互"得 1 分；说明无状态"本地管理、每次传完整历史"得 1 分；共 2 分。
资料名称：Semantic Kernel Agent Architecture - Agent Thread
官方链接：https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture
出处章节：Agent Thread
是否更新MIRT：是

---
题目：以下哪种 Agent 类型最适合与 Azure AI Agent Service 集成？\nA. `ChatCompletionAgent`\nB. `OpenAIAssistantAgent`\nC. `AzureAIAgent`\nD. `CopilotStudioAgent`
答案：C
题型：Choice
用途：posttest
难度：标准
评分方法：选 C 得 2 分，其他不得分。
资料名称：Semantic Kernel Agent Architecture - Agent Types
官方链接：https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture
出处章节：Agent Types
是否更新MIRT：是

---
题目：在 Sequential Orchestration（顺序编排）中，Agent 是如何组织和工作？
答案：在顺序编排中，Agent 被组织在管道中，每个 Agent 依次处理任务，并将其输出传递给序列中的下一个 Agent。这适合工作流程中每个步骤都以上一个步骤为基础构建的场景，例如文档审查、数据处理流水线或多阶段推理。
题型：Open
用途：posttest
难度：标准
评分方法：说明"管道/流水线"组织得 1 分；说明"依次处理、传递输出"得 1 分；共 2 分。
资料名称：Sequential Orchestration
官方链接：https://learn.microsoft.com/zh-hk/semantic-kernel/Frameworks/agent/agent-orchestration/sequential
出处章节：全文
是否更新MIRT：是

---
题目：Concurrent Orchestration（并发编排）适合什么类型的任务场景？
答案：并发编排适合各种观点或解决方案具有价值的场景，例如头脑风暴、集成推理或投票系统。多个 Agent 并行处理同一个任务，各自独立处理输入，结果被收集和汇总。这种方法让多个 Agent 从不同角度分析问题，产生多样化的解决方案。
题型：Open
用途：posttest
难度：标准
评分方法：答出"头脑风暴/多角度分析"得 1 分；答出"并行处理、独立输入、汇总结果"得 1 分；共 2 分。
资料名称：Concurrent Orchestration
官方链接：https://learn.microsoft.com/zh-hk/semantic-kernel/Frameworks/agent/agent-orchestration/concurrent
出处章节：全文
是否更新MIRT：是

---
题目：某内容创作平台需要实现"用户输入主题 → AI 生成大纲 → AI 扩写成文章 → AI 检查语法和风格 → 返回最终文章"的自动化流程。你会选择哪种 Agent 编排模式？请说明理由和实现思路。
答案：应选择 Sequential（顺序编排）模式。因为任务有明确的先后依赖关系——大纲是扩写的基础，扩写后的文章是检查的输入，每一步都依赖前一步的输出。实现思路：定义四个 Agent——OutlinerAgent（生成大纲）、WriterAgent（扩写成文章）、EditorAgent（检查语法和风格）、ReviewerAgent（最终审核）。使用 SequentialOrchestration 按顺序编排这四个 Agent，每个 Agent 的输出作为下一个 Agent 的输入。可通过 ResponseCallback 观察每个阶段的中间输出。
题型：Open
用途：posttest
难度：进阶
评分方法：选择 Sequential 得 1 分；说明"有先后依赖关系"得 1 分；描述实现思路得 1 分；共 3 分。
资料名称：Sequential Orchestration
官方链接：https://learn.microsoft.com/zh-hk/semantic-kernel/Frameworks/agent/agent-orchestration/sequential
出处章节：全文
是否更新MIRT：是

---
题目：`AzureAIAgent` 为什么需要匹配的 `AzureAIAgentThread`？如果使用了不匹配的线程类型会发生什么？
答案：`AzureAIAgent` 需要匹配的 `AzureAIAgentThread`，因为 Azure AI Agent 服务将对话存储在服务端，需要通过特定的服务调用来创建和更新线程。如果使用了不同的 Agent 线程类型，系统会因为意外的线程类型快速失败并抛出异常，以提醒调用者。这种设计保证了有状态 Agent 与特定线程实现之间的类型安全。
题型：Open
用途：posttest
难度：进阶
评分方法：说明"服务端存储对话、需要特定服务调用"得 1 分；说明"不匹配会快速失败并抛异常"得 1 分；共 2 分。
资料名称：Semantic Kernel Agent Architecture - Agent Thread
官方链接：https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture
出处章节：Agent Thread
是否更新MIRT：是

---
题目：Agent Orchestration 功能目前处于什么状态？开发者在使用时需要注意什么？
答案：Agent Orchestration 功能目前处于实验（experimental）阶段，正在积极开发中，在进入预览或发布候选阶段之前可能会发生重大变化。原有的 `AgentGroupChat` 编排模式已不再维护，推荐开发者使用新的编排模式，如 `GroupChatOrchestration`。开发者在使用时应关注版本更新和迁移指南，避免在生产环境中依赖实验性 API。
题型：Open
用途：posttest
难度：进阶
评分方法：说明"实验阶段、可能重大变化"得 1 分；说明"旧模式不再维护、推荐新模式"得 1 分；共 2 分。
资料名称：Semantic Kernel Agent Architecture - Agent Orchestration
官方链接：https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture
出处章节：Agent Orchestration
是否更新MIRT：是

---
题目：Semantic Kernel Process Framework 的核心价值是什么？
答案：Process Framework 是一个强大的编排 SDK，旨在简化 AI 集成流程的开发和执行。它使开发者能够高效地创建、管理和部署业务流程，同时利用 AI 的强大能力以及现有代码和系统。Process Framework 提供了一种稳健的复杂工作流自动化解决方案。
题型：Open
用途：posttest
难度：基础
评分方法：答出"简化 AI 工作流开发和执行"得 1 分；答出"利用 AI 能力+现有系统"得 1 分；共 2 分。
资料名称：Process Framework
官方链接：https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework
出处章节：全文
是否更新MIRT：是

---
题目：Process Framework 中的 Process、Step 和 Event 各自扮演什么角色？
答案：Process（流程）是为实现特定业务目标而排列的 Step 集合。Step（步骤）是流程中的一个活动，具有定义的输入和输出，通过调用用户定义的 Kernel Function 执行任务。Event（事件）利用事件驱动模型来管理工作流执行，用于触发 Step 之间的动作和转换。
题型：Open
用途：posttest
难度：基础
评分方法：答出 Process、Step、Event 各得 1 分；共 3 分。
资料名称：Process Framework - Core Concepts
官方链接：https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework
出处章节：Core Concepts
是否更新MIRT：是

---
题目：可观测性（Observability）的三大支柱是什么？Semantic Kernel 如何支持它们？
答案：可观测性的三大支柱是日志（Logging）、指标（Metrics）和追踪（Tracing）。Semantic Kernel 设计为可观测的，发出的日志、指标和追踪兼容 OpenTelemetry 标准。开发者可以使用喜欢的可观测性工具来监控和分析基于 Semantic Kernel 构建的服务行为。
题型：Open
用途：posttest
难度：基础
评分方法：答出 Logging、Metrics、Tracing 各得 1 分；共 3 分。
资料名称：Observability in Semantic Kernel
官方链接：https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/enterprise-readiness/observability/
出处章节：全文
是否更新MIRT：是

---
题目：以下哪一项是 Process Framework 的关键特性？\nA. 仅支持顺序执行，不支持并行\nB. 步骤可以复用 Kernel Function，具有事件驱动架构\nC. 不支持 OpenTelemetry 审计\nD. 只能用于 C# 语言
答案：B
题型：Choice
用途：posttest
难度：标准
评分方法：选 B 得 2 分，其他不得分。
资料名称：Process Framework - Key Features
官方链接：https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework
出处章节：Key Features
是否更新MIRT：是

---
题目：Semantic Kernel 发出的以下哪个指标用于监控函数执行时间？\nA. `semantic_kernel.function.invocation.token_usage.prompt`\nB. `semantic_kernel.function.invocation.duration`\nC. `semantic_kernel.function.streaming.token_usage.completion`\nD. `semantic_kernel.function.invocation.token_usage.completion`
答案：B
题型：Choice
用途：posttest
难度：标准
评分方法：选 B 得 2 分，其他不得分。
资料名称：Observability in Semantic Kernel - Metrics
官方链接：https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/enterprise-readiness/observability/
出处章节：Metrics
是否更新MIRT：是

---
题目：Process Framework 中的 Step 如何执行任务？它是如何与 Kernel 交互的？
答案：Process Framework 中的每个 Step 通过调用用户定义的 Kernel Function 来执行任务。Step 利用 Semantic Kernel 的 Kernel 能力——Kernel 中注册了 AI 服务和插件，Step 可以调用这些 Kernel Function 来完成具体工作。Step 通过事件驱动模型触发执行，当接收到触发事件时，Step 调用对应的 Kernel Function，处理完成后发出后续事件驱动流程继续。
题型：Open
用途：posttest
难度：标准
评分方法：说明"通过 Kernel Function 执行任务"得 1 分；说明"与 Kernel 交互调用服务和插件"得 1 分；共 2 分。
资料名称：Process Framework
官方链接：https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework
出处章节：Introduction / Key Features
是否更新MIRT：是

---
题目：某电商平台需要自动化处理退货流程：接收退货申请 → 验证订单信息 → 检查商品状态 → 批准或拒绝退货 → 更新库存 → 发送通知。请说明如何使用 Process Framework 设计这个流程。
答案：使用 Process Framework 设计包含 6 个 Step 的顺序流程：Step1 接收退货申请（解析用户输入）；Step2 验证订单信息（调用 OrderPlugin 查询订单）；Step3 检查商品状态（调用 InventoryPlugin 检查商品）；Step4 决策批准/拒绝（条件分支 Step，通过 Event 控制流向）；Step5a 批准（更新库存、发起退款）/ Step5b 拒绝（记录拒绝原因）；Step6 发送通知（调用 NotificationPlugin）。每个 Step 通过调用 Kernel Function 执行。流程具有事件驱动特性，Step 之间通过事件解耦，便于后续扩展（如增加人工审核环节）。
题型：Open
用途：posttest
难度：进阶
评分方法：描述合理的 Step 划分得 1 分；提到条件分支/Event 控制得 1 分；提到调用 Kernel Function 得 1 分；共 3 分。
资料名称：Process Framework
官方链接：https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework
出处章节：全文
是否更新MIRT：是

---
题目：Process Framework 的"事件驱动架构"如何提升工作流的可扩展性和可维护性？
答案：事件驱动架构通过解耦 Step 之间的直接依赖提升可扩展性和可维护性。Step 之间通过事件通信而非直接调用，新增 Step 只需订阅/发布相应事件，不影响现有 Step。这种设计使开发者可以灵活地插入、替换或移除 Step，而不需要修改整个流程的逻辑。同时，事件驱动模型支持条件分支、循环和并行等复杂控制流。配合 OpenTelemetry 的审计能力，每个 Step 的执行和事件触发都可以被记录和追踪，便于问题排查和流程优化。
题型：Open
用途：posttest
难度：进阶
评分方法：说明"解耦/独立扩展"得 1 分；说明"支持复杂控制流"得 1 分；说明"审计/可追踪"得 1 分；共 3 分。
资料名称：Process Framework - Key Features
官方链接：https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework
出处章节：Key Features
是否更新MIRT：是

---
题目：Semantic Kernel 的可观测性能力如何支持企业级 AI 应用的质量保证和持续改进？
答案：Semantic Kernel 通过 OpenTelemetry 兼容的日志、指标和追踪提供全面的可观测性。具体支持包括：1）性能监控——通过 function.invocation.duration 等指标监控函数执行时间；2）成本控制——通过 Token 使用量指标（prompt/completion）监控 API 调用成本；3）分布式追踪——每次 Kernel Function 执行和 AI 模型调用都被记录为 Activity；4）质量评测——对实际流量进行质量和接地性（groundedness）评分。这些能力使企业能够在生产环境中持续监控 AI 应用的健康状况，及时发现性能瓶颈和异常行为，并通过 observe → evaluate → improve 的闭环持续改进 Agent 质量。
题型：Open
用途：posttest
难度：进阶
评分方法：每个合理的应用场景得 1 分，最多 4 分。
资料名称：Observability in Semantic Kernel
官方链接：https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/enterprise-readiness/observability/
出处章节：全文
是否更新MIRT：是