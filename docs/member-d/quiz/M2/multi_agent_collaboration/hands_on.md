题目：在 Python 中使用 Sequential Orchestration 编排两个 Agent——一个研究员 Agent（提供详细回答）和一个总结 Agent（生成摘要）。
答案：参考实现如下：
from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.agents.orchestration import SequentialOrchestration

kernel = Kernel()
kernel.add_service(AzureChatCompletion(...))

researcher = ChatCompletionAgent(
    kernel=kernel,
    name="Researcher",
    instructions="You are a researcher. Provide detailed, factual answers."
)

summarizer = ChatCompletionAgent(
    kernel=kernel,
    name="Summarizer",
    instructions="Summarize the provided text concisely in 2-3 sentences."
)

orchestration = SequentialOrchestration()
result = await orchestration.invoke(
    agents=[researcher, summarizer],
    input="Explain what a large language model is."
)
题型：Open
用途：practice
难度：advanced
评分方法：正确创建两个 Agent 各得 1 分（共 2 分）；正确使用 SequentialOrchestration 得 1 分；正确调用 invoke 得 1 分；共 4 分。
资料名称：Sequential Orchestration
官方链接：https://learn.microsoft.com/nb-no/semantic-kernel/frameworks/agent/agent-architecture
出处章节：Agent Orchestration
是否更新MIRT：否