题目：为一次 Semantic Kernel 提示词调用编写可重复的质量检查函数，记录成功状态、耗时、关键词覆盖率和是否通过。连接信息必须来自环境变量。
答案：Semantic Kernel 负责模型调用；关键词覆盖率和通过规则是 ECHO 的评测逻辑。参考实现：
```python
from time import perf_counter

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

async def run_case(
    kernel: Kernel,
    prompt: str,
    required_terms: list[str],
    max_latency_ms: float,
) -> dict:
    started = perf_counter()
    try:
        response = await kernel.invoke_prompt(prompt)
        text = str(response)
        succeeded = True
        error = None
    except Exception as exc:
        text = ""
        succeeded = False
        error = type(exc).__name__

    elapsed_ms = (perf_counter() - started) * 1000
    matched = sum(term.lower() in text.lower() for term in required_terms)
    coverage = matched / len(required_terms) if required_terms else 1.0
    return {
        "succeeded": succeeded,
        "elapsed_ms": round(elapsed_ms, 2),
        "coverage": round(coverage, 4),
        "passed": succeeded and coverage == 1.0 and elapsed_ms <= max_latency_ms,
        "error": error,
    }

kernel = Kernel()
kernel.add_service(AzureChatCompletion())
report = await run_case(
    kernel,
    "Name the two main things managed by a Semantic Kernel kernel.",
    ["service", "plugin"],
    max_latency_ms=10000,
)
print(report)
```
题型：Open
用途：practice
难度：standard
评分方法：连接信息未硬编码得 1 分；记录成功状态和错误得 1 分；记录耗时和关键词覆盖率得 1 分；根据固定阈值形成 passed 结果得 1 分；共 4 分。
资料名称：Observability in Semantic Kernel
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/concepts/enterprise-readiness/observability/
出处章节：Logging、Metrics、Tracing
是否更新MIRT：否
