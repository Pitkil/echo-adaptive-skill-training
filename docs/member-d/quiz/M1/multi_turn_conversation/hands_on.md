题目：在 Python 中使用同一份 ChatHistory 连续完成三轮对话，并把每轮模型回复写回历史。温度设置为 0.2。
答案：运行前配置 Azure OpenAI 环境变量。参考实现：
```python
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import (
    AzureChatCompletion,
    AzureChatPromptExecutionSettings,
)
from semantic_kernel.contents import ChatHistory

kernel = Kernel()
service = AzureChatCompletion()
kernel.add_service(service)
settings = AzureChatPromptExecutionSettings(temperature=0.2)
history = ChatHistory(system_message="Answer briefly and accurately.")

questions = [
    "什么是 Semantic Kernel？",
    "它如何管理插件？",
    "请结合前两轮内容总结。",
]
for question in questions:
    history.add_user_message(question)
    response = await service.get_chat_message_content(
        chat_history=history,
        settings=settings,
    )
    history.add_assistant_message(str(response))
    print(response)
```
题型：Open
用途：practice
难度：advanced
评分方法：创建并复用同一 ChatHistory 得 1 分；每轮写入用户消息得 1 分；每轮把助手回复写回历史得 1 分；正确设置 temperature=0.2 得 1 分；共 4 分。
资料名称：Chat history
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/concepts/ai-services/chat-completion/chat-history
出处章节：Creating a chat history object、Adding messages to a chat history
是否更新MIRT：否
