题目：创建 ChatCompletionAgent 时，需要配置哪些核心属性？
答案：需要提供可用的模型服务（service），并设置 Name（Agent 名称）和 Instructions（职责与行为指令）。也可以通过 Kernel 组合服务和插件，但创建基础 ChatCompletionAgent 时并非必须把 Kernel 作为唯一服务入口。
题型：Open
用途：posttest
难度：standard
评分方法：答出模型服务、Name、Instructions 各得 1 分；错误表述为必须同时传入 Kernel 扣 1 分；最低 0 分，共 3 分。
资料名称：Semantic Kernel Agent Framework
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/
出处章节：Get started with ChatCompletionAgent
是否更新MIRT：是

---
题目：Agent 支持的统一调用接口中，哪个方法用于流式响应？
A. invoke
B. invoke_stream
C. get_response
D. execute
答案：B
题型：Choice
用途：posttest
难度：standard
评分方法：选 B 得 2 分，其他不得分。
资料名称：How to Stream Agent Responses
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/agent-streaming
出处章节：Streaming Agent Invocation
是否更新MIRT：是

---
题目：以下哪种写法符合 Microsoft 官方 Python 示例中基础 ChatCompletionAgent 的创建方式？
A. ChatCompletionAgent(service=AzureChatCompletion(), name="Assistant", instructions="Answer clearly.")
B. ChatCompletionAgent(database="agent.db")
C. ChatCompletionAgent(prompt_only=True)
D. ChatCompletionAgent(runtime="docker")
答案：A
题型：Choice
用途：posttest
难度：standard
评分方法：选 A 得 2 分，其他不得分。
资料名称：Semantic Kernel Agent Framework
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/
出处章节：Get started with ChatCompletionAgent
是否更新MIRT：是
