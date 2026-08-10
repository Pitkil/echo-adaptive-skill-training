题目：在 Python 中创建 Semantic Kernel 实例，并注册 Azure OpenAI 聊天完成服务。连接信息必须从 Semantic Kernel 支持的环境变量读取，不得写入代码。
答案：运行前配置 Azure OpenAI 所需环境变量，然后执行：
```python
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase

kernel = Kernel()
kernel.add_service(AzureChatCompletion())

service = kernel.get_service(type=ChatCompletionClientBase)
print(type(service).__name__)
```
题型：Open
用途：practice
难度：standard
评分方法：正确导入并创建 Kernel 得 1 分；使用 AzureChatCompletion 且未硬编码密钥得 1 分；通过 add_service 注册服务得 1 分；能从 Kernel 取得聊天服务得 1 分；共 4 分。
资料名称：Understanding the kernel in Semantic Kernel
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/concepts/kernel
出处章节：Build a kernel with services and plugins
是否更新MIRT：否
