题目：在 Python 中创建一个支持多轮对话的 Semantic Kernel 应用，维护对话历史并连续进行三轮问答。
答案：参考实现如下：
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.contents import ChatHistory

kernel = Kernel()
kernel.add_service(AzureChatCompletion(...))

chat_history = ChatHistory()
chat_history.add_user_message("什么是 Semantic Kernel？")
response1 = await kernel.invoke_prompt(chat_history)
chat_history.add_assistant_message(str(response1))

chat_history.add_user_message("它支持哪些编程语言？")
response2 = await kernel.invoke_prompt(chat_history)
chat_history.add_assistant_message(str(response2))

chat_history.add_user_message("如何创建插件？")
response3 = await kernel.invoke_prompt(chat_history)
题型：Open
用途：practice
难度：advanced
评分方法：正确创建 Kernel 并注册服务得 1 分；正确使用 ChatHistory 维护对话得 1 分；每轮问答正确实现得 1 分（共 3 分）；总计 5 分。
资料名称：Conversation history and state management
官方链接：https://learn.microsoft.com/en-nz/semantic-kernel/concepts/ai-services/chat-completion/chat-history
出处章节：全文
是否更新MIRT：否