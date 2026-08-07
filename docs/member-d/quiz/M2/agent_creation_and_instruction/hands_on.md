题目：在 Python 中创建一个 ChatCompletionAgent，命名为 "TravelAssistant"，指令为 "You are a travel planning assistant. Recommend destinations based on user preferences."，调用 Agent 获取响应。
答案：参考实现如下：
from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

kernel = Kernel()
kernel.add_service(AzureChatCompletion(...))

agent = ChatCompletionAgent(
    kernel=kernel,
    name="TravelAssistant",
    instructions="You are a travel planning assistant. Recommend destinations based on user preferences."
)

response = await agent.get_response(
    messages=[{"role": "user", "content": "I want to visit a beach destination in August."}]
)
print(response)
题型：Open
用途：practice
难度：standard
评分方法：正确创建 Kernel 并注册服务得 1 分；正确创建 ChatCompletionAgent 并设置 name 和 instructions 得 2 分；正确调用 get_response 得 1 分；共 4 分。
资料名称：Semantic Kernel Agent Architecture
官方链接：https://learn.microsoft.com/nb-no/semantic-kernel/frameworks/agent/agent-architecture
出处章节：Agent
是否更新MIRT：否