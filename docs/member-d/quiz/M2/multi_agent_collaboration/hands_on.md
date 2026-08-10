题目：在 Python 中使用 SequentialOrchestration 编排研究员和总结员两个 Agent，启动运行环境，取得最终结果并正常停止。
答案：运行前配置 Azure OpenAI 环境变量。参考实现：
```python
from semantic_kernel.agents import ChatCompletionAgent, SequentialOrchestration
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

researcher = ChatCompletionAgent(
    service=AzureChatCompletion(),
    name="Researcher",
    instructions="Explain the topic factually and provide the important details.",
)
summarizer = ChatCompletionAgent(
    service=AzureChatCompletion(),
    name="Summarizer",
    instructions="Summarize the previous agent output in three sentences.",
)

orchestration = SequentialOrchestration(members=[researcher, summarizer])
runtime = InProcessRuntime()
runtime.start()

result = await orchestration.invoke(
    task="Explain what Semantic Kernel is.",
    runtime=runtime,
)
final_text = await result.get(timeout=20)
print(final_text)
await runtime.stop_when_idle()
```
题型：Open
用途：practice
难度：advanced
评分方法：创建两个职责不同的 Agent 得 1 分；通过 members 传入 SequentialOrchestration 得 1 分；启动并传入 InProcessRuntime 得 1 分；取得结果并停止运行环境得 1 分；共 4 分。
资料名称：Sequential Agent Orchestration
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/agent-orchestration/sequential
出处章节：Set Up、Start the Runtime、Invoke、Collect Results、Stop the Runtime
是否更新MIRT：否
