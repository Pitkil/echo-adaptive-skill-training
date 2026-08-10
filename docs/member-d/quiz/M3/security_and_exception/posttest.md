题目：Prompt Render Filter 可以在提示词发送给模型之前完成哪些安全处理？
答案：可以查看或修改即将发送的提示词，例如删除个人信息、补充安全约束；也可以通过覆盖结果阻止不合规提示词继续发送。
题型：Open
用途：posttest
难度：standard
评分方法：答出查看或修改提示词得 1 分；答出个人信息处理或安全约束得 1 分；答出可以阻止提交得 1 分；共 3 分。
资料名称：What are Filters?
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/concepts/enterprise-readiness/filters
出处章节：Prompt Render Filter
是否更新MIRT：是

---
题目：Function Invocation Filter 在调用发生异常时可以做什么？
A. 只能忽略异常
B. 记录或处理异常，并根据规则决定重试、替代处理或继续抛出
C. 自动删除整个 Kernel
D. 自动修改模型部署
答案：B
题型：Choice
用途：posttest
难度：standard
评分方法：选 B 得 2 分，其他不得分。
资料名称：What are Filters?
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/concepts/enterprise-readiness/filters
出处章节：Function Invocation Filter
是否更新MIRT：是
