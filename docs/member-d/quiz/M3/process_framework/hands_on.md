题目：在 Python 中创建包含两个 Step 的 Process：第一个 Step 规范化产品名称，第二个 Step 根据规范化名称生成摘要。使用事件连接两个步骤并启动流程。
答案：该示例不调用模型，因此可以直接检查 Process 的步骤、事件和启动方式：
```python
from semantic_kernel import Kernel
from semantic_kernel.functions import kernel_function
from semantic_kernel.processes import ProcessBuilder
from semantic_kernel.processes.kernel_process import KernelProcessStep
from semantic_kernel.processes.local_runtime.local_event import KernelProcessEvent
from semantic_kernel.processes.local_runtime.local_kernel_process import start

class NormalizeNameStep(KernelProcessStep):
    @kernel_function
    def normalize_name(self, product_name: str) -> str:
        return product_name.strip().title()

class BuildSummaryStep(KernelProcessStep):
    @kernel_function
    def build_summary(self, product_name: str) -> str:
        summary = f"Product: {product_name}"
        print(summary)
        return summary

builder = ProcessBuilder(name="ProductSummary")
normalize_step = builder.add_step(NormalizeNameStep)
summary_step = builder.add_step(BuildSummaryStep)

builder.on_input_event("Start").send_event_to(target=normalize_step)
normalize_step.on_function_result().send_event_to(
    target=summary_step,
    function_name="build_summary",
    parameter_name="product_name",
)

process = builder.build()
async with await start(
    process=process,
    kernel=Kernel(),
    initial_event=KernelProcessEvent(id="Start", data="  glowbrew  "),
) as process_context:
    await process_context.get_state()
```
题型：Open
用途：practice
难度：advanced
评分方法：定义两个继承 KernelProcessStep 且包含 kernel_function 的步骤得 1 分；通过 ProcessBuilder 添加步骤得 1 分；使用输入事件和函数结果事件连接步骤得 1 分；使用 start 和 KernelProcessEvent 启动得 1 分；共 4 分。
资料名称：How-To - Create your first Process
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/frameworks/process/examples/example-first-process
出处章节：Define the process flow、Build and run the Process
是否更新MIRT：否
