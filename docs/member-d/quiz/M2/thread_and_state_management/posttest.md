题目：有状态 Agent 和无状态 Agent 在对话状态管理上有什么本质区别？
答案：有状态 Agent 的对话状态存储在服务端，通过 ID 进行交互；无状态 Agent 每次调用时需要将完整的对话历史传递给 Agent，状态在应用本地管理。
题型：Open
用途：posttest
难度：standard
评分方法：说明有状态"服务端存储、通过 ID 交互"得 1 分；说明无状态"本地管理、每次传完整历史"得 1 分；共 2 分。
资料名称：Semantic Kernel Agent Architecture
官方链接：https://learn.microsoft.com/nb-no/semantic-kernel/frameworks/agent/agent-architecture
出处章节：Agent Thread
是否更新MIRT：是

---
题目：AzureAIAgent 为什么需要匹配的 AzureAIAgentThread？
A. 为了提升性能
B. 因为 Azure AI Agent 服务将对话存储在服务端，需要特定的服务调用
C. 为了兼容旧版本
D. 因为 Python 和 C# 的差异
答案：B
题型：Choice
用途：posttest
难度：standard
评分方法：选 B 得 2 分，其他不得分。
资料名称：Semantic Kernel Agent Architecture
官方链接：https://learn.microsoft.com/nb-no/semantic-kernel/frameworks/agent/agent-architecture
出处章节：Agent Thread
是否更新MIRT：是