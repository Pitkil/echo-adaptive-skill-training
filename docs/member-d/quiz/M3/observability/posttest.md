题目：Semantic Kernel 发出哪些主要指标（Metrics）用于监控？
答案：主要指标包括：`semantic_kernel.function.invocation.duration`（函数执行时间）、`semantic_kernel.function.invocation.token_usage.prompt`（提示词 Token 使用量）和 `semantic_kernel.function.invocation.token_usage.completion`（补全 Token 使用量）。
题型：Open
用途：posttest
难度：standard
评分方法：答出"执行时间"得 1 分；答出"Token 使用量"得 1 分；共 2 分。
资料名称：Observability in Semantic Kernel
官方链接：https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/enterprise-readiness/observability/
出处章节：Metrics
是否更新MIRT：是

---
题目：Semantic Kernel 的分布式追踪中，每次什么操作被记录为 Activity？
A. 仅 LLM 调用
B. 每次 Kernel Function 执行和每次 AI 模型调用
C. 仅插件调用
D. 仅日志记录
答案：B
题型：Choice
用途：posttest
难度：standard
评分方法：选 B 得 2 分，其他不得分。
资料名称：Observability in Semantic Kernel
官方链接：https://learn.microsoft.com/ar-sa/semantic-kernel/concepts/enterprise-readiness/observability/
出处章节：Tracing
是否更新MIRT：是