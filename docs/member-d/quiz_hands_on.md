题目：在 Semantic Kernel 中创建一个任务管理插件（TaskManagementPlugin），包含两个函数：complete_task（按 ID 标记任务为完成）和 get_task（按 ID 查询任务详情）。注册到 Kernel 后调用 complete_task 函数并验证结果。
答案：参考实现如下：\n\n```python\nfrom semantic_kernel import Kernel, kernel_function, KernelPlugin\n\nclass TaskManagementPlugin(KernelPlugin):\n    tasks = {1: {"id": 1, "name": "完成项目报告", "completed": False}}\n    \n    @kernel_function(name="complete_task", description="Marks a task as completed by its ID.")\n    def complete_task(self, id: int) -> dict | None:\n        if id in self.tasks:\n            self.tasks[id]["completed"] = True\n            return self.tasks[id]\n        return None\n    \n    @kernel_function(name="get_task", description="Gets task details by its ID.")\n    def get_task(self, id: int) -> dict | None:\n        return self.tasks.get(id)\n\n# 注册并调用\nkernel = Kernel()\nkernel.add_plugin(TaskManagementPlugin(), "TaskManagement")\nresult = await kernel.invoke("TaskManagement.complete_task", arguments={"id": 1})\n```\n\n```csharp\nusing Microsoft.SemanticKernel;\n\npublic class TaskManagementPlugin\n{\n    private readonly Dictionary<int, TaskModel> _tasks = new() { { 1, new TaskModel { Id = 1, Name = "完成项目报告", Completed = false } } };\n\n    [KernelFunction("complete_task")]\n    [Description("Marks a task as completed by its ID.")]\n    [return: Description("The updated task, or null if not found.")]\n    public TaskModel? CompleteTask(int id)\n    {\n        if (_tasks.TryGetValue(id, out var task))\n        {\n            task.Completed = true;\n            return task;\n        }\n        return null;\n    }\n\n    [KernelFunction("get_task")]\n    [Description("Gets task details by its ID.")]\n    [return: Description("The task details, or null if not found.")]\n    public TaskModel? GetTask(int id)\n    {\n        return _tasks.GetValueOrDefault(id);\n    }\n}\n\n// 注册并调用\nvar kernel = Kernel.CreateBuilder().Build();\nkernel.Plugins.AddFromType<TaskManagementPlugin>(\"TaskManagement\");\nvar result = await kernel.InvokeAsync(\"TaskManagement\", \"complete_task\", new() { [\"id\"] = 1 });\n```
题型：Open
用途：practice
难度：进阶
评分方法：1）正确创建插件类，包含两个函数各得 1 分（共 2 分）；2）正确使用 @kernel_function 装饰器/[KernelFunction] 属性并提供 description 得 1 分；3）正确注册到 Kernel 得 1 分；4）成功调用并验证结果得 1 分；共 5 分。
资料名称：Understand native plugins - Training
官方链接：https://learn.microsoft.com/en-nz/training/modules/give-your-ai-agent-skills/2-understand-native-plugins
出处章节：Creating a plugin
是否更新MIRT：否

---
题目：在 Semantic Kernel 中创建一个提示词模板插件，从提示词模板生成一个插件函数，用于生成产品描述。
答案：参考实现如下：\n\n```python\nfrom semantic_kernel import Kernel\nfrom semantic_kernel.prompt_template import PromptTemplateConfig\n\nkernel = Kernel()\n# 从提示词创建插件函数\nfunc = kernel.create_function_from_prompt(\n    prompt_template=\"Generate a product description for a {{$product_name}}. The product is a {{$product_type}}.\",\n    function_name=\"generate_product_description\",\n    plugin_name=\"ProductPlugin\"\n)\n# 调用\nresult = await kernel.invoke(\n    func,\n    arguments={\"product_name\": \"GlowBrew\", \"product_type\": \"智能咖啡机\"}\n)\nprint(result)\n```\n\n```csharp\nusing Microsoft.SemanticKernel;\nusing Microsoft.SemanticKernel.PromptTemplate;\n\nvar kernel = Kernel.CreateBuilder().Build();\nvar prompt = \"Generate a product description for a {{$product_name}}. The product is a {{$product_type}}.\";\nvar templateConfig = new PromptTemplateConfig(prompt);\nvar func = kernel.CreateFunctionFromPrompt(templateConfig, functionName: \"generate_product_description\", pluginName: \"ProductPlugin\");\nvar result = await kernel.InvokeAsync(func, new() { [\"product_name\"] = \"GlowBrew\", [\"product_type\"] = \"智能咖啡机\" });\n```\n\n要求：生成的描述应包含产品名称、类型和至少一个卖点。
题型：Open
用途：practice
难度：标准
评分方法：1）正确创建提示词模板函数得 1 分；2）模板中包含变量占位符（$product_name 和 $product_type）得 1 分；3）正确传递参数调用得 1 分；4）生成的输出包含产品名称、类型和至少一个卖点得 2 分；共 5 分。
资料名称：Use semantic kernel prompt templates
官方链接：https://learn.microsoft.com/en-us/training/modules/use-semantic-kernel-prompt-templates
出处章节：全文
是否更新MIRT：否

---
题目：在 Semantic Kernel 中完成以下操作：创建 Kernel 实例，注册一个 AI 服务（如 AzureChatCompletion 或 OpenAI），然后使用 Kernel 调用一个简单的提示词，返回 LLM 的响应。
答案：参考实现如下：\n\n```python\nimport os\nfrom semantic_kernel import Kernel\nfrom semantic_kernel.connectors.ai.open_ai import AzureChatCompletion, OpenAIChatCompletion\n\nkernel = Kernel()\n# 使用 Azure OpenAI\nkernel.add_service(AzureChatCompletion(\n    endpoint=os.getenv(\"AZURE_OPENAI_ENDPOINT\"),\n    api_key=os.getenv(\"AZURE_OPENAI_API_KEY\"),\n    deployment_name=os.getenv(\"AZURE_OPENAI_DEPLOYMENT_NAME\")\n))\n# 或使用 OpenAI\n# kernel.add_service(OpenAIChatCompletion(\n#     api_key=os.getenv(\"OPENAI_API_KEY\"),\n#     model_id=os.getenv(\"OPENAI_MODEL\")\n# ))\n\nresult = await kernel.invoke_prompt(\"What is the capital of France?\")\nprint(result)\n```\n\n```csharp\nusing Microsoft.SemanticKernel;\nusing Microsoft.SemanticKernel.Connectors.OpenAI;\n\nvar builder = Kernel.CreateBuilder();\nbuilder.AddAzureOpenAIChatCompletion(\n    endpoint: Environment.GetEnvironmentVariable(\"AZURE_OPENAI_ENDPOINT\"),\n    apiKey: Environment.GetEnvironmentVariable(\"AZURE_OPENAI_API_KEY\"),\n    deploymentName: Environment.GetEnvironmentVariable(\"AZURE_OPENAI_DEPLOYMENT_NAME\")\n);\nvar kernel = builder.Build();\nvar result = await kernel.InvokePromptAsync(\"What is the capital of France?\");\n```\n\n要求：调用成功并返回包含正确答案（Paris/巴黎）的响应。
题型：Open
用途：practice
难度：基础
评分方法：1）正确创建 Kernel 实例得 1 分；2）正确注册 AI 服务得 2 分（使用环境变量得 1 分，服务类型正确得 1 分）；3）成功调用提示词并返回响应得 1 分；4）响应中包含正确答案（Paris/巴黎）得 1 分；共 5 分。
资料名称：Understanding the kernel in Semantic Kernel
官方链接：https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/kernel
出处章节：全文
是否更新MIRT：否

---
题目：在 Semantic Kernel 中创建一个 ChatCompletionAgent，配置系统指令（system prompt）使其充当一个“旅游规划助手”，能够回答用户关于目的地推荐的问题。调用 Agent 并验证响应。
答案：参考实现如下：\n\n```python\nfrom semantic_kernel import Kernel\nfrom semantic_kernel.agents import ChatCompletionAgent\nfrom semantic_kernel.connectors.ai.open_ai import AzureChatCompletion\n\nkernel = Kernel()\nkernel.add_service(AzureChatCompletion(...))\n\nagent = ChatCompletionAgent(\n    kernel=kernel,\n    name=\"TravelAssistant\",\n    instructions=\"You are a travel planning assistant. Recommend destinations based on user preferences.\"\n)\n\nresponse = await agent.get_response(\n    messages=[{\"role\": \"user\", \"content\": \"I want to visit a beach destination in August.\"}]\n)\nprint(response)\n```\n\n```csharp\nusing Microsoft.SemanticKernel;\nusing Microsoft.SemanticKernel.Agents;\n\nvar builder = Kernel.CreateBuilder();\nbuilder.AddAzureOpenAIChatCompletion(...);\nvar kernel = builder.Build();\n\nvar agent = new ChatCompletionAgent\n{\n    Name = \"TravelAssistant\",\n    Instructions = \"You are a travel planning assistant. Recommend destinations based on user preferences.\",\n    Kernel = kernel\n};\n\nvar response = await agent.GetResponseAsync(\"I want to visit a beach destination in August.\");\n```\n\n要求：响应应包含至少一个具体的海滩目的地推荐。
题型：Open
用途：practice
难度：标准
评分方法：1）正确创建 Kernel 并注册 AI 服务得 1 分；2）正确创建 ChatCompletionAgent 并设置 name 和 instructions 得 1 分；3）正确调用 get_response/invoke 方法得 1 分；4）响应包含具体目的地推荐得 2 分；共 5 分。
资料名称：Agent Class
官方链接：https://learn.microsoft.com/zh-cn/python/api/semantic-kernel/semantic_kernel.agents.agent(class)
出处章节：Constructor / Methods
是否更新MIRT：否

---
题目：在 Semantic Kernel 中创建两个 Agent——一个“研究员 Agent”和一个“总结 Agent”。使用 Sequential Orchestration 让研究员 Agent 先回答用户问题，然后将结果传递给总结 Agent 生成简洁摘要。
答案：参考实现思路如下：\n\n```python\nfrom semantic_kernel import Kernel\nfrom semantic_kernel.agents import ChatCompletionAgent\nfrom semantic_kernel.agents.orchestration import SequentialOrchestration\n\nkernel = Kernel()\n# 注册 AI 服务\n\nresearcher = ChatCompletionAgent(\n    kernel=kernel,\n    name=\"Researcher\",\n    instructions=\"You are a researcher. Provide detailed, factual answers to user questions.\"\n)\n\nsummarizer = ChatCompletionAgent(\n    kernel=kernel,\n    name=\"Summarizer\",\n    instructions=\"You are a summarizer. Summarize the provided text concisely in 2-3 sentences.\"\n)\n\norchestration = SequentialOrchestration()\nresult = await orchestration.invoke(\n    agents=[researcher, summarizer],\n    input=\"Explain what a large language model is.\"\n)\n# result 包含研究员的详细回答和总结的摘要\n```\n\n```csharp\nusing Microsoft.SemanticKernel;\nusing Microsoft.SemanticKernel.Agents;\nusing Microsoft.SemanticKernel.Agents.Orchestration;\n\nvar builder = Kernel.CreateBuilder();\nbuilder.AddAzureOpenAIChatCompletion(...);\nvar kernel = builder.Build();\n\nvar researcher = new ChatCompletionAgent\n{\n    Name = \"Researcher\",\n    Instructions = \"You are a researcher. Provide detailed, factual answers.\",\n    Kernel = kernel\n};\n\nvar summarizer = new ChatCompletionAgent\n{\n    Name = \"Summarizer\",\n    Instructions = \"Summarize the provided text concisely in 2-3 sentences.\",\n    Kernel = kernel\n};\n\nvar orchestration = new SequentialOrchestration();\nvar result = await orchestration.InvokeAsync(\n    agents: new[] { researcher, summarizer },\n    input: \"Explain what a large language model is.\"\n);\n```\n\n要求：最终输出包含两个部分——研究员的详细回答和总结的简要摘要。
题型：Open
用途：practice
难度：进阶
评分方法：1）正确创建两个 Agent（研究员和总结）各得 1 分（共 2 分）；2）正确使用 SequentialOrchestration 得 1 分；3）研究员输出详细回答得 1 分；4）总结 Agent 成功生成摘要得 1 分；共 5 分。
资料名称：Sequential Orchestration
官方链接：https://learn.microsoft.com/zh-hk/semantic-kernel/Frameworks/agent/agent-orchestration/sequential
出处章节：全文
是否更新MIRT：否

---
题目：在 Semantic Kernel 中创建一个 Agent，为其配置一个插件函数（如天气查询函数），通过自动函数调用（Automatic Function Calling）让 AI 自动选择并调用该函数来回答用户问题。
答案：参考实现如下：\n\n```python\nfrom semantic_kernel import Kernel, kernel_function, KernelPlugin\nfrom semantic_kernel.agents import ChatCompletionAgent\n\nclass WeatherPlugin(KernelPlugin):\n    @kernel_function(name=\"get_weather\", description=\"Gets the current weather for a given city.\")\n    def get_weather(self, city: str) -> str:\n        # 模拟天气查询\n        return f\"The weather in {city} is sunny, 25°C.\"\n\nkernel = Kernel()\nkernel.add_plugin(WeatherPlugin(), \"Weather\")\nkernel.add_service(AzureChatCompletion(...))\n\nagent = ChatCompletionAgent(\n    kernel=kernel,\n    name=\"WeatherAssistant\",\n    instructions=\"You help users check weather. Use the get_weather function when needed.\"\n)\n\nresponse = await agent.get_response(\"What's the weather in Tokyo?\")\n# AI 应自动调用 get_weather 函数\nprint(response)\n```\n\n```csharp\nusing Microsoft.SemanticKernel;\nusing Microsoft.SemanticKernel.Agents;\n\npublic class WeatherPlugin\n{\n    [KernelFunction(\"get_weather\")]\n    [Description(\"Gets the current weather for a given city.\")]\n    public string GetWeather(string city) => $\"The weather in {city} is sunny, 25°C.\";\n}\n\nvar builder = Kernel.CreateBuilder();\nbuilder.AddAzureOpenAIChatCompletion(...);\nbuilder.Plugins.AddFromType<WeatherPlugin>(\"Weather\");\nvar kernel = builder.Build();\n\nvar agent = new ChatCompletionAgent\n{\n    Name = \"WeatherAssistant\",\n    Instructions = \"You help users check weather. Use the get_weather function when needed.\",\n    Kernel = kernel\n};\n\nvar response = await agent.GetResponseAsync(\"What's the weather in Tokyo?\");\n```\n\n要求：Agent 能够自动识别需要查询天气，调用 get_weather 函数，并在响应中包含天气信息。
题型：Open
用途：practice
难度：进阶
评分方法：1）正确创建包含 get_weather 函数的插件得 1 分；2）正确注册插件到 Kernel 得 1 分；3）Agent 正确配置 instructions 引导自动调用得 1 分；4）AI 自动调用函数并返回天气信息得 2 分；共 5 分。
资料名称：Understand native plugins - Training - Invoke functions automatically
官方链接：https://learn.microsoft.com/en-nz/training/modules/give-your-ai-agent-skills/2-understand-native-plugins
出处章节：Invoke functions automatically
是否更新MIRT：否

---
题目：在 Semantic Kernel 中创建一个最简单的 Process，包含两个 Step：Step1 接收用户输入的产品名称并生成产品信息（GatherProductInfoStep），Step2 使用 LLM 根据产品信息生成产品描述文档（GenerateDocumentationStep）。使用 ProcessBuilder 构建并执行该 Process。
答案：参考实现如下：\n\n```python\nfrom semantic_kernel import Kernel\nfrom semantic_kernel.processes import ProcessBuilder, KernelProcessStep\n\nclass GatherProductInfoStep(KernelProcessStep):\n    @kernel_function\n    def gather_product_information(self, product_name: str) -> str:\n        return f\"Product: {product_name}, Category: Electronics, Price: $299\"\n\nclass GenerateDocumentationStep(KernelProcessStep):\n    @kernel_function\n    def generate_documentation(self, product_info: str) -> str:\n        # 可在此调用 LLM 生成文档\n        return f\"Documentation for {product_info}: This product is a high-quality device.\"\n\nkernel = Kernel()\n# 注册 AI 服务\n\nbuilder = ProcessBuilder(\"DocumentationProcess\")\nstep1 = builder.add_step(GatherProductInfoStep)\nstep2 = builder.add_step(GenerateDocumentationStep)\n\nbuilder.add_edge(step1, step2)  # step1 输出 -> step2 输入\n\nprocess = builder.build()\nresult = await process.run(\n    kernel=kernel,\n    initial_data={\"product_name\": \"GlowBrew\"}\n)\n```\n\n```csharp\nusing Microsoft.SemanticKernel;\nusing Microsoft.SemanticKernel.Process;\n\npublic class GatherProductInfoStep : KernelProcessStep\n{\n    [KernelFunction]\n    public string GatherProductInformation(string productName)\n    {\n        return $\"Product: {productName}, Category: Electronics, Price: $299\";\n    }\n}\n\npublic class GenerateDocumentationStep : KernelProcessStep\n{\n    [KernelFunction]\n    public string GenerateDocumentation(string productInfo)\n    {\n        return $\"Documentation for {productInfo}: This product is a high-quality device.\";\n    }\n}\n\nvar builder = new ProcessBuilder(\"DocumentationProcess\");\nvar step1 = builder.AddStepFromType<GatherProductInfoStep>();\nvar step2 = builder.AddStepFromType<GenerateDocumentationStep>();\nbuilder.AddEdge(step1, step2);\nvar process = builder.Build();\nvar result = await process.RunAsync(kernel, initialData: new() { [\"productName\"] = \"GlowBrew\" });\n```\n\n要求：Process 执行成功，step1 的输出正确传递给 step2，step2 生成文档。
题型：Open
用途：practice
难度：进阶
评分方法：1）正确创建两个 Step 类（继承 KernelProcessStep）各得 1 分（共 2 分）；2）正确使用 ProcessBuilder 添加 Step 和 Edge 得 1 分；3）step1 正确生成产品信息得 1 分；4）step2 成功接收并生成文档得 1 分；共 5 分。
资料名称：How-To: Create your first Process
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/frameworks/process/examples/example-first-process
出处章节：Define the process steps / Build the process
是否更新MIRT：否

---
题目：在 Semantic Kernel 应用中启用 OpenTelemetry 可观测性，配置日志和追踪，执行一次 Kernel Function 调用，验证日志和追踪数据是否正常输出。
答案：参考实现如下：\n\n```python\nimport logging\nfrom semantic_kernel import Kernel\nfrom semantic_kernel.telemetry import setup_telemetry\n\n# 配置日志\nlogging.basicConfig(level=logging.INFO)\nlogger = logging.getLogger(__name__)\n\n# 设置 OpenTelemetry（需安装 opentelemetry 相关包）\n# from opentelemetry import trace\n# from opentelemetry.sdk.trace import TracerProvider\n# from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor\n# provider = TracerProvider()\n# provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))\n# trace.set_tracer_provider(provider)\n\n# setup_telemetry()  # Semantic Kernel 的 telemetry 设置\n\nkernel = Kernel()\n# 注册服务和插件\n\n# 执行函数调用，应产生日志和追踪\nresult = await kernel.invoke_prompt(\"Hello, world!\")\n# 检查控制台是否有日志输出和 span 导出\n```\n\n```csharp\nusing Microsoft.SemanticKernel;\nusing Microsoft.Extensions.Logging;\nusing Microsoft.Extensions.DependencyInjection;\n\nvar builder = Kernel.CreateBuilder();\n// 配置日志\nbuilder.Services.AddLogging(configure => configure.AddConsole().SetMinimumLevel(LogLevel.Information));\n// 配置 OpenTelemetry（需安装 OpenTelemetry 相关包）\n// builder.Services.AddOpenTelemetry()...\n\nvar kernel = builder.Build();\nvar result = await kernel.InvokePromptAsync(\"Hello, world!\");\n// 检查控制台是否有日志输出\n```\n\n要求：执行过程中产生日志输出（至少包含函数调用开始/结束信息），且追踪数据正常生成（可通过控制台导出或工具查看）。
题型：Open
用途：practice
难度：标准
评分方法：1）正确配置日志系统（logging.basicConfig 或 AddLogging）得 1 分；2）执行 Kernel Function 调用产生日志得 2 分（有开始/结束或执行记录）；3）正确配置 OpenTelemetry 追踪得 1 分；4）追踪数据正常生成/导出得 1 分；共 5 分。
资料名称：Observability in Semantic Kernel
官方链接：https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/enterprise-readiness/observability/
出处章节：全文
是否更新MIRT：否

---
题目：在 Semantic Kernel Process Framework 中创建一个包含条件分支的 Process：用户输入一个数字，Step1 判断数字是否大于 10；如果大于 10，进入 Step2a（输出“数字较大”）；否则进入 Step2b（输出“数字较小”）。使用 ProcessBuilder 的事件驱动机制实现分支。
答案：参考实现如下：\n\n```python\nfrom semantic_kernel.processes import ProcessBuilder, KernelProcessStep, ProcessEvent\n\nclass CheckNumberStep(KernelProcessStep):\n    @kernel_function\n    def check_number(self, number: int) -> str:\n        if number > 10:\n            return \"large\"\n        return \"small\"\n\nclass LargeNumberStep(KernelProcessStep):\n    @kernel_function\n    def handle_large(self, message: str) -> str:\n        return f\"Number is large: {message}\"\n\nclass SmallNumberStep(KernelProcessStep):\n    @kernel_function\n    def handle_small(self, message: str) -> str:\n        return f\"Number is small: {message}\"\n\nbuilder = ProcessBuilder(\"ConditionalProcess\")\nstep1 = builder.add_step(CheckNumberStep)\nstep2a = builder.add_step(LargeNumberStep)\nstep2b = builder.add_step(SmallNumberStep)\n\n# 通过事件控制分支：step1 输出 \"large\" 触发 step2a，输出 \"small\" 触发 step2b\nbuilder.add_edge(step1, step2a, condition=lambda result: result == \"large\")\nbuilder.add_edge(step1, step2b, condition=lambda result: result == \"small\")\n\nprocess = builder.build()\nresult_large = await process.run(kernel=kernel, initial_data={\"number\": 15})\nresult_small = await process.run(kernel=kernel, initial_data={\"number\": 5})\n```\n\n```csharp\nusing Microsoft.SemanticKernel;\nusing Microsoft.SemanticKernel.Process;\n\npublic class CheckNumberStep : KernelProcessStep\n{\n    [KernelFunction]\n    public string CheckNumber(int number) => number > 10 ? \"large\" : \"small\";\n}\n\npublic class LargeNumberStep : KernelProcessStep\n{\n    [KernelFunction]\n    public string HandleLarge(string message) => $\"Number is large: {message}\";\n}\n\npublic class SmallNumberStep : KernelProcessStep\n{\n    [KernelFunction]\n    public string HandleSmall(string message) => $\"Number is small: {message}\";\n}\n\nvar builder = new ProcessBuilder(\"ConditionalProcess\");\nvar step1 = builder.AddStepFromType<CheckNumberStep>();\nvar step2a = builder.AddStepFromType<LargeNumberStep>();\nvar step2b = builder.AddStepFromType<SmallNumberStep>();\n\n// 通过事件控制分支\nbuilder.AddEdge(step1, step2a, condition: result => result == \"large\");\nbuilder.AddEdge(step1, step2b, condition: result => result == \"small\");\n\nvar process = builder.Build();\nvar resultLarge = await process.RunAsync(kernel, initialData: new() { [\"number\"] = 15 });\nvar resultSmall = await process.RunAsync(kernel, initialData: new() { [\"number\"] = 5 });\n```\n\n要求：输入 15 时进入 LargeNumberStep，输出“数字较大”；输入 5 时进入 SmallNumberStep，输出“数字较小”。
题型：Open
用途：practice
难度：进阶
评分方法：1）正确创建三个 Step（判断、大数处理、小数处理）各得 1 分（共 3 分）；2）正确使用条件边（add_edge with condition）实现分支得 1 分；3）输入 15 和 5 分别进入正确分支并输出预期结果得 1 分；共 5 分。
资料名称：How-To: Create your first Process
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/frameworks/process/examples/example-first-process
出处章节：全文
是否更新MIRT：否