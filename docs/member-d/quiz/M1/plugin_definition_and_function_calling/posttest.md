题目：Semantic Kernel 的自动函数调用（Automatic Function Calling）如何工作？
答案：当 Plugin 向 Chat Completion AI 通告后，AI 可以在生成响应时根据用户意图自动选择调用这些函数，实现了从"用户告诉系统做什么"到"系统理解用户意图并自动执行"的转变。
题型：Open
用途：posttest
难度：standard
评分方法：说明"AI 自动选择调用函数"得 1 分；说明"从用户指定到系统自动执行"得 1 分；共 2 分。
资料名称：Understand native plugins - Training
官方链接：https://learn.microsoft.com/en-my/training/modules/give-your-ai-agent-skills/2-understand-native-plugins
出处章节：Invoke functions automatically
是否更新MIRT：是

---
题目：注册插件到 Kernel 后，以下哪种方式可以调用插件函数？
A. kernel.invoke(plugin_name="PluginName", function_name="function_name", arguments=arguments)
B. kernel.call("PluginName", "function_name")
C. kernel.execute("PluginName.function_name")
D. kernel.run("PluginName", "function_name")
答案：A
题型：Choice
用途：posttest
难度：standard
评分方法：选 A 得 2 分，其他不得分。
资料名称：Kernel Python API
官方链接：https://learn.microsoft.com/en-us/python/api/semantic-kernel/semantic_kernel.kernel%28class%29?view=semantic-kernel-python
出处章节：invoke
是否更新MIRT：是

---
题目：插件函数的名称或行为不够直观时，为什么应提供清晰的 description？
答案：description 帮助模型理解函数用途、参数和返回结果，从而提高自动函数调用时选择函数和填写参数的准确性。若函数名和类型信息已经足够清楚，description 可以保持简短，并非任何函数都强制要求长描述。
题型：Open
用途：posttest
难度：standard
评分方法：答出帮助模型理解用途或参数得 1 分；答出提高函数选择或参数填写准确性得 1 分；明确不是必须写长描述得 1 分；共 3 分。
资料名称：Provide native code to your agents
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/concepts/plugins/adding-native-plugins
出处章节：Providing the LLM with the right information、Providing more details about the functions
是否更新MIRT：是
