题目：编写一个简单的 Semantic Kernel 应用，包含 Kernel 创建、服务注册和提示词调用，添加执行时间统计作为质量评测数据。
答案：参考实现如下：
import time
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

kernel = Kernel()
kernel.add_service(AzureChatCompletion(...))

start_time = time.time()
try:
    result = await kernel.invoke_prompt("What is Semantic Kernel?")
    elapsed = time.time() - start_time
    print(f"响应: {result}")
    print(f"执行时间: {elapsed:.2f} 秒")
    # 可在此将执行时间上报到监控系统
except Exception as e:
    elapsed = time.time() - start_time
    print(f"执行失败: {e}, 耗时: {elapsed:.2f} 秒")
题型：Open
用途：practice
难度：standard
评分方法：正确创建 Kernel 并注册服务得 1 分；正确实现时间统计得 1 分；正确处理异常得 1 分；共 3 分。
资料名称：Observability in Semantic Kernel
官方链接：https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/enterprise-readiness/observability/
出处章节：全文
是否更新MIRT：否