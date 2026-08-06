题目：Semantic Kernel SDK 的核心定位是什么？
答案：Semantic Kernel 是一个开源 SDK，充当 AI 能力与传统代码之间的桥梁，将大语言模型、提示词模板、业务函数、插件、记忆和 Agent 组织在一起，让 AI 能真正进入业务系统。
题型：Open
用途：pretest
难度：基础
评分方法：答出“AI 编排中间层/桥梁”得 1 分；答出“组织模型、插件、函数等组件”再得 1 分；共 2 分。
资料名称：What is semantic kernel
官方链接：https://learn.microsoft.com/sr-cyrl-rs/training/modules/build-your-kernel/2-what-semantic-kernel
出处章节：全文
是否更新MIRT：是

---
题目：Kernel 在 Semantic Kernel 中的主要作用是什么？
答案：Kernel 是 Semantic Kernel 的中央编排器（调度中心），负责注册 AI 服务、加载插件、管理函数调用，并在不同组件之间传递上下文。
题型：Open
用途：pretest
难度：基础
评分方法：答出“中央编排器/调度中心”得 1 分；答出“注册服务、加载插件、管理调用”再得 1 分；共 2 分。
资料名称：Understanding the kernel in Semantic Kernel
官方链接：https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/kernel
出处章节：全文
是否更新MIRT：是

---
题目：Semantic Kernel 中的 Plugin（插件）是什么？
答案：Plugin 是一组相关函数的集合，将函数封装后供 AI 调用。Plugin 可以注册到 Kernel，Kernel 通过向 Chat Completion AI 通告或从模板中调用来使用它们。
题型：Open
用途：pretest
难度：基础
评分方法：答出“函数的集合/容器”得 1 分；答出“供 AI 调用”得 1 分；共 2 分。
资料名称：Understand native plugins - Training
官方链接：https://learn.microsoft.com/en-my/training/modules/give-your-ai-agent-skills/2-understand-native-plugins
出处章节：全文
是否更新MIRT：是

---
题目：以下关于 Kernel 的说法，哪一项是正确的？\nA. Kernel 只能用于 C# 语言\nB. Kernel 负责管理 AI 服务、插件和函数调用\nC. Kernel 是专门处理向量存储的组件\nD. Kernel 只能与 Azure OpenAI 配合使用
答案：B
题型：Choice
用途：pretest
难度：标准
评分方法：选 B 得 2 分，其他不得分。
资料名称：Understanding the kernel in Semantic Kernel
官方链接：https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/kernel
出处章节：全文
是否更新MIRT：是

---
题目：在 Semantic Kernel 中创建 Kernel 并注册 AI 服务的正确方式是？
答案：from semantic_kernel import Kernel\nfrom semantic_kernel.connectors.ai.open_ai import AzureChatCompletion\n\nkernel = Kernel()\nkernel.add_service(AzureChatCompletion(...))
题型：Open
用途：pretest
难度：标准
评分方法：正确导入 Kernel 和连接器得 1 分；正确实例化 Kernel 得 1 分；正确调用 add_service 得 1 分；共 3 分。
资料名称：Understanding the kernel in Semantic Kernel
官方链接：https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/kernel
出处章节：全文
是否更新MIRT：是

---
题目：以下哪种做法是正确的插件函数定义方式？\nA. 函数不需要描述，AI 会自动理解\nB. 函数必须包含描述其行为、输入和输出的详细信息\nC. 函数只能用 C# 编写\nD. 函数只能通过提示词模板调用
答案：B
题型：Choice
用途：pretest
难度：标准
评分方法：选 B 得 2 分，其他不得分。
资料名称：Understand native plugins - Training
官方链接：https://learn.microsoft.com/en-my/training/modules/give-your-ai-agent-skills/2-understand-native-plugins
出处章节：全文
是否更新MIRT：是

---
题目：当一个用户请求需要查询数据库时，Semantic Kernel 的哪些组件会参与协作？请描述协作过程。
答案：Kernel 作为调度中心接收请求；AI Service Connector 连接 LLM 理解用户意图；Plugin 中的函数执行数据库查询操作。Kernel 协调模型理解意图 → 选择合适插件函数 → 执行函数 → 将结果返回给模型生成最终回复。
题型：Open
用途：pretest
难度：进阶
评分方法：提到 Kernel 调度得 1 分；提到 AI Service/LLM 理解意图得 1 分；提到 Plugin/Function 执行操作得 1 分；描述完整协作流程得 1 分；共 4 分。
资料名称：Semantic Kernel Components
官方链接：https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/semantic-kernel-components
出处章节：全文
是否更新MIRT：是

---
题目：为什么说 Semantic Kernel 不仅仅是“调用大模型接口的 SDK”？它解决了什么问题？
答案：真实业务系统中模型需要查数据库、调接口、读知识库、处理失败兜底等。Semantic Kernel 不只是调用模型接口，而是把这些能力编排起来的中间层——把模型的推理能力和代码的执行能力连接起来，让 AI 能真正进入业务系统。
题型：Open
用途：pretest
难度：进阶
评分方法：指出“不只是调用接口”得 1 分；提到“编排/中间层”得 1 分；说明解决了模型与业务系统连接问题得 1 分；共 3 分。
资料名称：What is semantic kernel
官方链接：https://learn.microsoft.com/sr-cyrl-rs/training/modules/build-your-kernel/2-what-semantic-kernel
出处章节：全文
是否更新MIRT：是

---
题目：Semantic Kernel 的 Prompt Template 和 Plugin Function 都可以被 Kernel 调用。它们在设计目的和使用方式上有什么区别？
答案：Prompt Template 主要用于定义与 LLM 交互的提示词，包含指令、变量占位符和模板语法，通过渲染后发送给 LLM 生成响应。Plugin Function 是封装了具体业务逻辑的可执行代码（如查数据库、调 API）。两者都可以注册到 Kernel 并由其调用——Prompt Template 产生 AI 生成的内容，Plugin Function 执行确定性的业务操作。
题型：Open
用途：pretest
难度：进阶
评分方法：说明 Prompt Template 用于提示词/LLM 交互得 1 分；说明 Plugin Function 用于业务逻辑/代码执行得 1 分；说明两者都可被 Kernel 调用得 1 分；共 3 分。
资料名称：Use semantic kernel prompt templates
官方链接：https://learn.microsoft.com/en-us/training/modules/use-semantic-kernel-prompt-templates
出处章节：全文
是否更新MIRT：是

---
题目：Semantic Kernel Agent Framework 中 `Agent` 类的核心作用是什么？
答案：`Agent` 是所有 Semantic Kernel Agent 的基类，是 Agent Framework 的核心抽象。一个 Agent 实例可以参与一个或多个对话，每个 Agent 必须定义其通信协议（`AgentChannel`）。Agent 可以被直接调用执行任务，也可以通过不同的编排模式进行协调。
题型：Open
用途：pretest
难度：基础
评分方法：答出“Agent 是所有 Agent 的基类/核心抽象”得 1 分；答出“参与对话、定义通信协议”得 1 分；共 2 分。
资料名称：Semantic Kernel Agent Architecture
官方链接：https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture
出处章节：全文
是否更新MIRT：是

---
题目：Semantic Kernel 支持哪些主要的 Agent 类型？
答案：主要 Agent 类型包括：`ChatCompletionAgent`（通用基础 Agent）、`OpenAIAssistantAgent`（与 OpenAI Assistant API 集成）、`AzureAIAgent`（与 Azure AI Agent Service 集成）、`OpenAIResponsesAgent`（基于 OpenAI Responses API）、`CopilotStudioAgent`（与 Microsoft Copilot Studio 集成）。
题型：Open
用途：pretest
难度：基础
评分方法：答出 3 种以上类型得 2 分；答出全部 5 种得 3 分。
资料名称：Semantic Kernel Agent Architecture - Agent Types
官方链接：https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture
出处章节：Agent Types
是否更新MIRT：是

---
题目：`AgentThread` 在 Agent Framework 中的作用是什么？
答案：`AgentThread` 是对话线程或对话状态的核心抽象，用于管理 Agent 的对话状态。它抽象了不同 Agent 管理对话状态的不同方式——有状态 Agent 服务将对话状态存储在服务端，无状态 Agent 则在应用本地管理完整的对话历史。
题型：Open
用途：pretest
难度：基础
评分方法：答出“对话线程/状态管理”得 1 分；说明有状态与无状态的区别得 1 分；共 2 分。
资料名称：Semantic Kernel Agent Architecture - Agent Thread
官方链接：https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture
出处章节：Agent Thread
是否更新MIRT：是

---
题目：以下关于 Semantic Kernel Agent 的描述，哪一项是正确的？\nA. Agent 只能单独工作，不能多个协作\nB. `ChatCompletionAgent` 是最常用的基础 Agent 类型\nC. Agent 不支持人类参与对话\nD. 所有 Agent 都必须使用相同的 `AgentThread` 类型
答案：B
题型：Choice
用途：pretest
难度：标准
评分方法：选 B 得 2 分，其他不得分。
资料名称：Semantic Kernel Agent Architecture
官方链接：https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture
出处章节：全文
是否更新MIRT：是

---
题目：以下哪种场景最适合使用有状态的 Agent（如 AzureAIAgent）？\nA. 每次对话都是独立的，不需要保存历史\nB. 需要跨多次对话保持对话状态和上下文\nC. 只需要一次性的简单问答\nD. 不需要与外部服务交互
答案：B
题型：Choice
用途：pretest
难度：标准
评分方法：选 B 得 2 分，其他不得分。
资料名称：Semantic Kernel Agent Architecture - Agent Thread
官方链接：https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture
出处章节：Agent Thread
是否更新MIRT：是

---
题目：使用 `invoke_stream` 方法调用 Agent 与使用 `invoke` 方法的主要区别是什么？
答案：`invoke` 返回 Agent 执行过程中的中间步骤和最终结果，作为 `AgentResponseItem` 对象的异步流。`invoke_stream` 返回流式版本，适用于需要实时反馈的场景，可以在生成过程中逐步向用户展示响应内容。
题型：Open
用途：pretest
难度：标准
评分方法：说明 `invoke` 返回完整结果得 1 分；说明 `invoke_stream` 支持流式/实时反馈得 2 分；共 3 分。
资料名称：Agent Class - Methods
官方链接：https://learn.microsoft.com/en-us/python/api/semantic-kernel/semantic_kernel.agents.agent.agent
出处章节：Methods
是否更新MIRT：是

---
题目：某系统需要处理用户请求：先查询订单状态，再根据状态决定是通知用户还是发起退款。在 Semantic Kernel Agent Framework 中，你会选择哪种编排模式来实现？请说明理由。
答案：应选择 Sequential（顺序编排）模式。因为任务有明确的先后依赖关系——必须先查询订单状态，再根据查询结果做后续决策。顺序编排按流水线方式组织 Agent，每个 Agent 依次处理任务并将输出传递给下一个 Agent，适合这种有固定执行顺序的工作流。
题型：Open
用途：pretest
难度：进阶
评分方法：选择 Sequential 得 1 分；说明“有先后依赖关系”得 1 分；解释顺序编排的工作方式得 1 分；共 3 分。
资料名称：Agent Orchestration - Semantic Kernel
官方链接：https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture
出处章节：Agent Orchestration
是否更新MIRT：是

---
题目：有状态 Agent 和无状态 Agent 在对话状态管理上有什么本质区别？各适合什么场景？
答案：有状态 Agent（如 AzureAIAgent）的对话状态存储在服务端，通过 ID 进行交互，需要特定的服务调用来创建和更新线程。无状态 Agent 每次调用时需要将完整的对话历史传递给 Agent，状态在应用本地管理。有状态 Agent 适合需要跨会话保持上下文的长期对话场景；无状态 Agent 适合短期、独立的交互或对状态控制要求更高的场景。
题型：Open
用途：pretest
难度：进阶
评分方法：说明有状态“服务端存储、通过ID交互”得 1 分；说明无状态“本地管理、每次传完整历史”得 1 分；各说明一个适用场景得 1 分；共 3 分。
资料名称：Semantic Kernel Agent Architecture - Agent Thread
官方链接：https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-architecture
出处章节：Agent Thread
是否更新MIRT：是

---
题目：在多 Agent 系统中，如果两个 Agent 需要并行处理同一个任务的不同部分，然后汇总结果，应该采用什么编排模式？请说明这种模式的优势。
答案：应采用 Concurrent（并发编排）模式。多个 Agent 并行处理同一个任务，各自独立处理输入，结果被收集和汇总。这种模式的优势是提高处理效率（多个任务同时进行）、缩短总响应时间，适合可独立拆分的子任务。
题型：Open
用途：pretest
难度：进阶
评分方法：选择 Concurrent 得 1 分；说明“并行处理、各自独立”得 1 分；说明优势（效率/响应时间）得 1 分；共 3 分。
资料名称：Concurrent Agent Orchestration
官方链接：https://learn.microsoft.com/th-th/semantic-kernel/Frameworks/agent/agent-orchestration/concurrent
出处章节：全文
是否更新MIRT：是

---
题目：Semantic Kernel Process Framework 是什么？
答案：Process Framework 是 Semantic Kernel 中用于定义、序列化和执行多步骤 AI 工作流的方式，是一个有状态的、事件驱动的工作流引擎。它旨在对集成 AI 能力的复杂业务流程进行建模，提供步骤可重用、事件驱动架构、完整控制与可审计性等能力。
题型：Open
用途：pretest
难度：基础
评分方法：答出“定义和执行多步骤工作流”得 1 分；答出“有状态、事件驱动”得 1 分；答出“对业务流程建模”得 1 分；共 3 分。
资料名称：Overview of the Process Framework
官方链接：https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework
出处章节：全文
是否更新MIRT：是

---
题目：Process Framework 的三个核心概念是什么？
答案：三个核心概念是 Process（流程）——步骤的容器和事件路由的集合；Step（步骤）——流程中的一个活动，通过调用 Kernel Function 执行任务；Event（事件）——用于触发 Step 之间动作和转换的驱动机制。
题型：Open
用途：pretest
难度：基础
评分方法：答出 Process、Step、Event 各得 1 分；共 3 分。
资料名称：Overview of the Process Framework - Core Concepts
官方链接：https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework
出处章节：Core Concepts
是否更新MIRT：是

---
题目：Semantic Kernel 可观测性的三大支柱是什么？
答案：可观测性的三大支柱是日志（Logging）——记录有意义的事件和错误；指标（Metrics）——如函数执行时间、Token 使用量等；追踪（Tracing）——记录每次 Kernel Function 执行和 AI 模型调用的分布式追踪信息。三者兼容 OpenTelemetry 标准。
题型：Open
用途：pretest
难度：基础
评分方法：答出 Logging、Metrics、Tracing 各得 1 分；共 3 分。
资料名称：Observability in Semantic Kernel
官方链接：https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/enterprise-readiness/observability/
出处章节：全文
是否更新MIRT：是

---
题目：在 Process Framework 中定义 Step 的正确方式是？\nA. 直接编写一个普通的 Python 函数\nB. 创建一个继承自 `KernelProcessStep` 的类，并在方法上添加 `[KernelFunction]` 属性\nC. 在配置文件中声明 Step 的名称和参数\nD. 通过 API 动态注册 Step
答案：B
题型：Choice
用途：pretest
难度：标准
评分方法：选 B 得 2 分，其他不得分。
资料名称：How-To: Create your first Process
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/frameworks/process/examples/example-first-process
出处章节：全文
是否更新MIRT：是

---
题目：以下哪种方式可以监控 Semantic Kernel 应用的执行情况？\nA. 只能通过控制台输出查看\nB. 通过 OpenTelemetry 兼容的日志、指标和追踪进行监控\nC. 只能使用 Azure Application Insights\nD. Semantic Kernel 不支持任何形式的监控
答案：B
题型：Choice
用途：pretest
难度：标准
评分方法：选 B 得 2 分，其他不得分。
资料名称：Observability in Semantic Kernel
官方链接：https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/enterprise-readiness/observability/
出处章节：全文
是否更新MIRT：是

---
题目：Process Framework 支持哪些操作模式？
答案：Process Framework 支持顺序执行（Sequential）、并行处理（Parallel）、Fan-in/Fan-out 配置和 Map-Reduce 策略。Process 可以在本地开发环境和云运行时之间无缝部署，提供了进程内运行时（in-process runtime），无需复杂设置即可运行。
题型：Open
用途：pretest
难度：标准
评分方法：答出 Sequential、Parallel、Fan-in/Fan-out、Map-Reduce 中的 3 种得 2 分；答出全部 4 种得 3 分。
资料名称：Overview of the Process Framework
官方链接：https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework
出处章节：Key Features
是否更新MIRT：是

---
题目：一个 AI 应用需要在用户提交请求后执行以下步骤：验证输入 → 调用 LLM 生成初步方案 → 调用审核函数检查方案合规性 → 如不合规则重新生成 → 返回最终结果。在 Process Framework 中，你会如何设计这个流程？请说明关键设计点。
答案：设计包含 4-5 个 Step 的 Sequential 流程：Step1 验证输入；Step2 调用 LLM 生成方案；Step3 审核方案（条件判断 Step）；Step4a（通过）返回结果 / Step4b（不通过）返回 Step2 重新生成。关键设计点包括：使用条件分支（Event）控制流程走向、每个 Step 通过 Kernel Function 实现、利用 Process 的有状态特性保存重试次数防止死循环。
题型：Open
用途：pretest
难度：进阶
评分方法：描述合理的 Step 划分得 1 分；提到条件分支/Event 控制得 1 分；提到状态管理或重试控制得 1 分；共 3 分。
资料名称：How-To: Create your first Process
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/frameworks/process/examples/example-first-process
出处章节：全文
是否更新MIRT：是

---
题目：Semantic Kernel 通过 OpenTelemetry 发出的指标（Metrics）可以用于哪些运维和评测场景？
答案：可观测性指标可用于：1）性能监控——通过 function.invocation.duration 监控函数执行时间，发现性能瓶颈；2）成本控制——通过 Token 使用量指标监控 API 调用成本；3）质量评测——对实际流量进行质量和接地性（groundedness）评分；4）漂移检测——检测部署后行为变化；5）回归测试——在发布前通过版本化评测历史捕获回归问题。
题型：Open
用途：pretest
难度：进阶
评分方法：每个合理场景得 1 分，最多 4 分。
资料名称：Observability in Semantic Kernel
官方链接：https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/enterprise-readiness/observability/
出处章节：全文
是否更新MIRT：是

---
题目：Process Framework 的“事件驱动”架构对工作流设计有什么好处？请结合 Step 之间的数据传递说明。
答案：事件驱动架构的好处包括：1）解耦——Step 之间通过事件通信而非直接调用，降低耦合度；2）灵活性——可以通过不同事件路由实现条件分支、循环和并行等复杂控制流；3）可扩展性——新增 Step 只需订阅/发布相应事件，不影响现有 Step。在数据传递方面，Step 通过 EmitEventAsync 携带数据参数传递结果，后续 Step 通过事件数据获取前序 Step 的输出，实现数据流转。
题型：Open
用途：pretest
难度：进阶
评分方法：说明解耦得 1 分；说明灵活性/控制流得 1 分；说明数据传递机制得 1 分；共 3 分。
资料名称：Overview of the Process Framework
官方链接：https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework
出处章节：全文
是否更新MIRT：是