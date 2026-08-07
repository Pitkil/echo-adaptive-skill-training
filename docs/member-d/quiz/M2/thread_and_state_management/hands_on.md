题目：在 Python 中创建 ChatCompletionAgent，使用 ChatHistoryAgentThread 管理对话线程，进行多轮对话。
答案：参考实现如下：
from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent, ChatHistoryAgentThread
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

kernel = Kernel()
kernel.add_service(AzureChatCompletion(...))

agent = ChatCompletionAgent(
    kernel=kernel,
    name="Assistant",
    instructions="You are a helpful assistant."
)

thread = ChatHistoryAgentThread()
response1 = await agent.get_response(
    messages=[{"role": "user", "content": "Hello"}],
    thread=thread
)
response2 = await agent.get_response(
    messages=[{"role": "user", "content": "What was my first question?"}],
    thread=thread
)
题型：Open
用途：practice
难度：advanced
评分方法：正确创建 Agent 得 1 分；正确创建 ChatHistoryAgentThread 得 1 分；多轮对话使用同一 thread 得 2 分；共 4 分。
资料名称：Semantic Kernel Agent Architecture
官方链接：https://learn.microsoft.com/nb-no/semantic-kernel/frameworks/agent/agent-architecture
出处章节：Agent Thread
是否更新MIRT：否