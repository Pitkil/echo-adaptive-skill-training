题目：在 Python 中为 Semantic Kernel 应用添加基本的异常处理和重试逻辑。
答案：参考实现如下：
import asyncio
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def invoke_with_retry(kernel, prompt):
    return await kernel.invoke_prompt(prompt)

try:
    kernel = Kernel()
    kernel.add_service(AzureChatCompletion(...))
    result = await invoke_with_retry(kernel, "Hello, world!")
    print(result)
except Exception as e:
    print(f"调用失败: {e}")
题型：Open
用途：practice
难度：advanced
评分方法：正确实现 try-except 异常捕获得 1 分；正确实现重试逻辑（@retry 或循环）得 2 分；正确调用 Kernel 得 1 分；共 4 分。
资料名称：Safety and reliability in Semantic Kernel
官方链接：https://learn.microsoft.com/en-gb/semantic-kernel/concepts/enterprise-readiness/filters?pivots=programming-language-csharp
出处章节：全文
是否更新MIRT：否