题目：为 Python Semantic Kernel 应用配置 OpenTelemetry 控制台追踪，执行一次真实提示词调用并在控制台查看 Span。不得启用敏感提示词和输出遥测。
答案：运行前配置 Azure OpenAI 环境变量，并安装官方页面列出的 OpenTelemetry 依赖。参考实现：
```python
import os

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import set_tracer_provider
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

os.environ["SEMANTICKERNEL_EXPERIMENTAL_GENAI_ENABLE_OTEL_DIAGNOSTICS"] = "true"

resource = Resource.create({"service.name": "echo-sk-training"})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
set_tracer_provider(provider)

kernel = Kernel()
kernel.add_service(AzureChatCompletion())
result = await kernel.invoke_prompt("Explain Semantic Kernel in one sentence.")
print(result)
provider.shutdown()
```
题型：Open
用途：practice
难度：advanced
评分方法：创建 TracerProvider 得 1 分；添加 ConsoleSpanExporter 得 1 分；只启用非敏感诊断开关得 1 分；注册模型服务并产生一次真实调用 Span 得 1 分；共 4 分。
资料名称：Inspection of telemetry data with the console
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/concepts/enterprise-readiness/observability/telemetry-with-console
出处章节：Environment variables、Code、Spans
是否更新MIRT：否
