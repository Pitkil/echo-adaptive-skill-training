题目：在 Python 中为 Kernel 注册 Function Invocation Filter，记录函数调用前后状态，并在函数抛出异常时记录后继续向上抛出。
答案：该示例使用本地插件，不需要模型凭据：
```python
from typing import Awaitable, Callable

from semantic_kernel import Kernel
from semantic_kernel.filters import FilterTypes, FunctionInvocationContext
from semantic_kernel.functions import KernelArguments, kernel_function

class CalculatorPlugin:
    @kernel_function
    def divide(self, left: float, right: float) -> float:
        return left / right

async def audit_filter(
    context: FunctionInvocationContext,
    next_filter: Callable[[FunctionInvocationContext], Awaitable[None]],
) -> None:
    print(f"Invoking {context.function.plugin_name}.{context.function.name}")
    try:
        await next_filter(context)
    except Exception as exc:
        print(f"Invocation failed: {type(exc).__name__}")
        raise
    print(f"Invoked {context.function.plugin_name}.{context.function.name}")

kernel = Kernel()
kernel.add_filter(FilterTypes.FUNCTION_INVOCATION, audit_filter)
kernel.add_plugin(CalculatorPlugin(), plugin_name="Calculator")
result = await kernel.invoke(
    plugin_name="Calculator",
    function_name="divide",
    arguments=KernelArguments(left=8, right=2),
)
print(result)
```
题型：Open
用途：practice
难度：advanced
评分方法：正确声明过滤器上下文和 next 回调得 1 分；调用前后均有记录得 1 分；异常被记录并继续抛出得 1 分；通过 add_filter 注册并触发过滤器得 1 分；共 4 分。
资料名称：What are Filters?
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/concepts/enterprise-readiness/filters
出处章节：Function Invocation Filter - Python
是否更新MIRT：否
