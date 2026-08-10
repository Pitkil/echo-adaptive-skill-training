题目：Process Framework 中 Step（步骤）的作用是什么？它如何执行任务？
答案：Step 是流程中的一个活动，具有定义的输入和输出，通过调用用户定义的 Kernel Function 来执行任务。Step 利用 Kernel 中注册的 AI 服务和插件完成具体工作。
题型：Open
用途：posttest
难度：standard
评分方法：说明"流程中的活动、有输入输出"得 1 分；说明"通过 Kernel Function 执行"得 1 分；共 2 分。
资料名称：Overview of the Process Framework
官方链接：https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework
出处章节：Core Concepts
是否更新MIRT：是

---
题目：Process Framework 中 Event（事件）的作用是什么？
A. 记录日志
B. 触发 Step 之间的动作和转换
C. 存储数据
D. 配置参数
答案：B
题型：Choice
用途：posttest
难度：standard
评分方法：选 B 得 2 分，其他不得分。
资料名称：Overview of the Process Framework
官方链接：https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework
出处章节：Core Concepts
是否更新MIRT：是

---
题目：Process Framework 中 Event（事件）驱动模型对工作流设计有哪些好处？请至少说明两点。
答案：1）解耦——Step 之间通过事件通信而非直接调用，降低耦合度，便于独立修改和替换单个 Step；2）灵活性——通过不同事件路由可以实现条件分支、循环和并行等复杂控制流；3）可扩展性——新增 Step 只需订阅/发布相应事件，不影响现有 Step 的逻辑。
题型：Open
用途：posttest
难度：advanced
评分方法：答出“解耦/降低耦合”得 1 分；答出“灵活性/条件分支等控制流”得 1 分；共 2 分。
资料名称：Overview of the Process Framework
官方链接：https://learn.microsoft.com/en-sg/semantic-kernel/frameworks/process/process-framework
出处章节：Key Features
是否更新MIRT：是