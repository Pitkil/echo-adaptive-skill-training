题目：在 Python 中配置 Semantic Kernel 的 OpenTelemetry 可观测性，启用控制台追踪导出。
答案：参考实现如下：
import logging
from semantic_kernel import Kernel
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

# 配置日志
logging.basicConfig(level=logging.INFO)

# 配置 OpenTelemetry
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)

kernel = Kernel()
# 执行函数调用，追踪数据将输出到控制台
result = await kernel.invoke_prompt("Hello, world!")
题型：Open
用途：practice
难度：advanced
评分方法：正确配置 TracerProvider 得 1 分；正确添加 ConsoleSpanExporter 得 1 分；执行 Kernel 调用产生追踪得 2 分；共 4 分。
资料名称：Observability in Semantic Kernel
官方链接：https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/enterprise-readiness/observability/
出处章节：全文
是否更新MIRT：否