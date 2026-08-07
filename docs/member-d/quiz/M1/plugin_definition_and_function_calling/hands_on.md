题目：在 Python 中定义一个名为 TaskManagementPlugin 的插件，包含一个 complete_task 函数（按 ID 标记任务为完成），注册到 Kernel 并调用。
答案：参考实现如下：
from semantic_kernel import Kernel, kernel_function, KernelPlugin

class TaskManagementPlugin(KernelPlugin):
    tasks = {1: {"id": 1, "name": "完成项目报告", "completed": False}}

    @kernel_function(name="complete_task", description="Marks a task as completed by its ID.")
    def complete_task(self, id: int) -> dict | None:
        if id in self.tasks:
            self.tasks[id]["completed"] = True
            return self.tasks[id]
        return None

kernel = Kernel()
kernel.add_plugin(TaskManagementPlugin(), "TaskManagement")
result = await kernel.invoke("TaskManagement.complete_task", arguments={"id": 1})
题型：Open
用途：practice
难度：advanced
评分方法：正确创建继承 KernelPlugin 的类得 1 分；正确使用 @kernel_function 装饰器并提供 description 得 1 分；正确注册插件到 Kernel 得 1 分；正确调用 invoke 得 1 分；共 4 分。
资料名称：Understand native plugins - Training
官方链接：https://learn.microsoft.com/en-my/training/modules/give-your-ai-agent-skills/2-understand-native-plugins
出处章节：全文
是否更新MIRT：否