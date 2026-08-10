题目：在 Python 中定义 `TaskManagementPlugin`，提供一个按 ID 标记任务完成的 `complete_task` 函数，将插件注册到 Kernel 并调用该函数。
答案：插件不需要继承专用插件基类；使用普通类和 `kernel_function` 即可。参考实现：
```python
from semantic_kernel import Kernel
from semantic_kernel.functions import KernelArguments, kernel_function

class TaskManagementPlugin:
    def __init__(self) -> None:
        self.tasks = {1: {"id": 1, "name": "完成项目报告", "completed": False}}

    @kernel_function(description="Mark a task as completed by its ID.")
    def complete_task(self, task_id: int) -> dict | None:
        task = self.tasks.get(task_id)
        if task is None:
            return None
        task["completed"] = True
        return task

kernel = Kernel()
kernel.add_plugin(TaskManagementPlugin(), plugin_name="TaskManagement")
result = await kernel.invoke(
    plugin_name="TaskManagement",
    function_name="complete_task",
    arguments=KernelArguments(task_id=1),
)
print(result)
```
题型：Open
用途：practice
难度：advanced
评分方法：使用普通插件类得 1 分；从 semantic_kernel.functions 导入并正确使用 kernel_function 得 1 分；通过 add_plugin 注册插件得 1 分；按插件名、函数名和参数正确调用得 1 分；共 4 分。
资料名称：Provide native code to your agents
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/concepts/plugins/adding-native-plugins
出处章节：Defining a plugin using a class、Adding a plugin using the add_plugin method
是否更新MIRT：否
