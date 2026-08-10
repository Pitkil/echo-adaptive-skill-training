题目：部署 Semantic Kernel 应用时，为什么不应把模型地址和密钥直接写在代码中？
答案：硬编码连接信息会增加泄露和误提交风险，也不利于不同环境使用不同配置。应通过环境变量或部署平台的密钥管理功能提供连接信息。
题型：Open
用途：pretest
难度：foundation
评分方法：答出安全或泄露风险得 1 分；答出环境隔离或便于切换配置得 1 分；答出环境变量或密钥管理方案得 1 分；共 3 分。
资料名称：How to quickly start with Semantic Kernel
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/get-started/quick-start-guide
出处章节：Add AI services
是否更新MIRT：是

---
题目：以下哪项最准确地说明“遥测数据”和“质量评测结果”的关系？
A. 遥测数据本身自动等于质量结论
B. 遥测提供日志、指标和追踪，评测程序再结合固定预期和阈值形成质量结论
C. 只要有日志就不需要测试案例
D. 模型输出流畅即可判定质量合格
答案：B
题型：Choice
用途：pretest
难度：foundation
评分方法：选 B 得 2 分，其他不得分。
资料名称：Observability in Semantic Kernel
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/concepts/enterprise-readiness/observability/
出处章节：Brief introduction to observability、Observability in Semantic Kernel
是否更新MIRT：是
