题目：在 Python 中创建提示词函数，模板内容为 `Hello {{$name}}, welcome to Semantic Kernel!`，然后传入 `name="World"` 并调用。
答案：运行前配置 Azure OpenAI 环境变量。参考实现：
```python
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.functions import KernelArguments

kernel = Kernel()
kernel.add_service(AzureChatCompletion())

function = kernel.create_function_from_prompt(
    "Hello {{$name}}, welcome to Semantic Kernel!"
)
result = await kernel.invoke(
    function=function,
    arguments=KernelArguments(name="World"),
)
print(result)
```
题型：Open
用途：practice
难度：standard
评分方法：正确注册模型服务得 1 分；正确创建提示词函数得 1 分；模板包含 {{$name}} 得 1 分；通过 KernelArguments 传入 World 并调用得 1 分；共 4 分。
资料名称：Kernel Python API
官方链接：https://learn.microsoft.com/en-us/python/api/semantic-kernel/semantic_kernel.kernel%28class%29?view=semantic-kernel-python
出处章节：invoke、invoke_prompt
是否更新MIRT：否
