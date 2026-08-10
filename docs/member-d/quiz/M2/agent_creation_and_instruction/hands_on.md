题目：在 Python 中创建名为 `TravelAssistant` 的 ChatCompletionAgent，设置清楚的旅行规划职责，并调用 Agent 获取一次响应。
答案：运行前配置 Azure OpenAI 环境变量。参考实现：
```python
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

agent = ChatCompletionAgent(
    service=AzureChatCompletion(),
    name="TravelAssistant",
    instructions=(
        "You are a travel planning assistant. Recommend destinations "
        "based on user preferences and explain the reason briefly."
    ),
)
response = await agent.get_response(
    messages="I want a quiet beach destination in August."
)
print(response)
```
题型：Open
用途：practice
难度：standard
评分方法：提供模型服务得 1 分；名称为 TravelAssistant 得 1 分；指令包含职责和输出要求得 1 分；正确调用 get_response 得 1 分；共 4 分。
资料名称：Semantic Kernel Agent Framework
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/
出处章节：Get started with ChatCompletionAgent
是否更新MIRT：否
