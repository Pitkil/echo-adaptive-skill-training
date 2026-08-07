题目：在 Python 中创建 Semantic Kernel 实例，并注册 Azure OpenAI 聊天补全服务。
答案：参考实现如下：
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

kernel = Kernel()
kernel.add_service(
    AzureChatCompletion(
        deployment_name="your-deployment-name",
        endpoint="https://your-endpoint.openai.azure.com/",
        api_key="your-api-key"
    )
)

题型：Open
用途：practice
难度：standard
评分方法：正确导入 Kernel 和 AzureChatCompletion 得 1 分；正确实例化 Kernel 得 1 分；正确调用 add_service 并传入 AzureChatCompletion 得 2 分；共 4 分。
资料名称：How to build your kernel - Training
官方链接：https://learn.microsoft.com/en-my/training/modules/build-your-kernel/4-how-build-your-kernel
出处章节：全文
是否更新MIRT：否