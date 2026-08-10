题目：在 Python 中创建 ChatCompletionAgent，使用同一个 ChatHistoryAgentThread 完成两轮连续对话，并在结束后删除线程资源。
答案：运行前配置 Azure OpenAI 环境变量。参考实现：
```python
from semantic_kernel.agents import ChatCompletionAgent, ChatHistoryAgentThread
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

agent = ChatCompletionAgent(
    service=AzureChatCompletion(),
    name="Assistant",
    instructions="Answer clearly and remember the current conversation.",
)
thread = ChatHistoryAgentThread()

first = await agent.get_response(messages="My project is named ECHO.", thread=thread)
second = await agent.get_response(messages="What is my project name?", thread=thread)
print(first)
print(second)

await thread.delete()
```
题型：Open
用途：practice
难度：advanced
评分方法：正确创建 Agent 得 1 分；创建 ChatHistoryAgentThread 得 1 分；两轮调用复用同一 thread 得 1 分；结束后删除线程资源得 1 分；共 4 分。
资料名称：How to Stream Agent Responses
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/agent-streaming
出处章节：Python、Agent Thread
是否更新MIRT：否
