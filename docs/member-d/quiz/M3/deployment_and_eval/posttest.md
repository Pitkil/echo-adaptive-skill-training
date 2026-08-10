题目：为什么生产环境通常不应启用包含提示词和模型输出的敏感遥测？
答案：提示词和模型输出可能包含个人信息、业务数据或机密内容。默认应只启用非敏感诊断；只有在权限、保存期限和脱敏措施明确时，才可以在受控环境短期启用敏感遥测。
题型：Open
用途：posttest
难度：standard
评分方法：答出提示词或输出包含敏感信息得 1 分；答出默认使用非敏感诊断得 1 分；答出受控启用条件得 1 分；共 3 分。
资料名称：Inspection of telemetry data with the console
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/concepts/enterprise-readiness/observability/telemetry-with-console
出处章节：Environment variables、Important
是否更新MIRT：是

---
题目：需要比较两次 Kernel 函数调用的执行性能时，以下哪个指标最直接？
A. semantic_kernel.function.invocation.duration
B. HTTP 状态文本
C. Agent 名称长度
D. 提示词文件大小
答案：A
题型：Choice
用途：posttest
难度：standard
评分方法：选 A 得 2 分，其他不得分。
资料名称：Observability in Semantic Kernel
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/concepts/enterprise-readiness/observability/
出处章节：Metrics
是否更新MIRT：是
