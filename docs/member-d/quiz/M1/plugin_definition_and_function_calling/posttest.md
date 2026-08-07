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
A. kernel.invoke("PluginName.function_name", arguments)
B. kernel.call("PluginName", "function_name")
C. kernel.execute("PluginName.function_name")
D. kernel.run("PluginName", "function_name")
答案：A
题型：Choice
用途：posttest
难度：standard
评分方法：选 A 得 2 分，其他不得分。
资料名称：Understand native plugins - Training
官方链接：https://learn.microsoft.com/en-my/training/modules/give-your-ai-agent-skills/2-understand-native-plugins
出处章节：全文
是否更新MIRT：是

---
题目：在 Semantic Kernel 中创建插件函数时，为什么必须提供函数描述（description）？
答案：函数描述帮助 AI 模型理解函数的用途、输入和输出，使 LLM 能够在自动函数调用（Automatic Function Calling）中正确选择和使用该函数。没有清晰的描述，AI 无法准确判断何时调用该函数以及如何填充参数。
题型：Open
用途：posttest
难度：standard
评分方法：答出“帮助 AI 理解函数用途”得 1 分；答出“使 LLM 能正确选择和使用函数”得 1 分；共 2 分。
资料名称：Understand native plugins - Training
官方链接：https://learn.microsoft.com/en-my/training/modules/give-your-ai-agent-skills/2-understand-native-plugins
出处章节：Creating a plugin
是否更新MIRT：是