题目：在 Python 中创建一个提示词模板函数，模板内容为 "Hello {{$name}}, welcome to Semantic Kernel!"，然后调用该函数并传入参数 name="World"。
答案：参考实现如下：
from semantic_kernel import Kernel

kernel = Kernel()
func = kernel.create_function_from_prompt("Hello {{$name}}, welcome to Semantic Kernel!")
result = await kernel.invoke(func, name="World")
print(result)
题型：Open
用途：practice
难度：standard
评分方法：正确调用 create_function_from_prompt 得 1 分；模板中包含 {{$name}} 变量得 1 分；正确调用 invoke 并传入参数得 2 分；共 4 分。
资料名称：使用 Semantic Kernel 提示範本 - Training
官方链接：https://learn.microsoft.com/en-us/python/api/semantic-kernel/semantic_kernel.kernel.kernel
出处章节：全文
是否更新MIRT：否