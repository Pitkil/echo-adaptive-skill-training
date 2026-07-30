# 工程文档导航

文档按用途拆分，不要求每次修改都读完全部文件。

## 所有成员和 Agent 必读

1. [system-overview.md](system-overview.md)：系统要做什么、有哪些功能、完整学习流程和四个后台 Agent。
2. [team-ownership.md](team-ownership.md)：A、B、C、D 的具体任务、交付、验收、时间线和边界。
3. [collaboration.md](collaboration.md)：环境、命名、分支、Commit、PR、冲突处理和合并条件。
4. [testing-and-quality.md](testing-and-quality.md)：修改完成后必须通过的自动测试和比赛评测。

## 按任务阅读

| 文档 | 什么时候需要读 | 为什么保留 |
|---|---|---|
| [architecture.md](architecture.md) | 修改数据库、会话、MIRT、Quiz、Agent 编排或目录结构 | 说明数据边界和代码归属，避免把逻辑放错位置 |
| [service-contracts.md](service-contracts.md) | 接入检索引擎、SimpleMem、微表征或学习画像 | 固定跨成员交换的数据，避免联调时各写一套 |
| [quiz-import-template.md](quiz-import-template.md) | 准备或导入前测、后测、阶段测试和操作题 | 给 A、D 一份可直接使用的题库格式 |
| [competition-requirements.md](competition-requirements.md) | 决定是否增加功能、准备演示或计算指标 | 防止开发偏离赛题和固定评测要求 |
| [deployment-and-security.md](deployment-and-security.md) | 配置环境、权限、Docker、音频和正式演示 | 固定部署与隐私底线 |

## 文档职责

- 完整产品范围在 `system-overview.md` 维护，`AGENTS.md` 只保留必须始终遵守的摘要。
- 完整四人分工在 `team-ownership.md` 维护。
- 跨服务字段在 `service-contracts.md` 维护。
- Git 和编码协作细则在 `collaboration.md` 维护。
- 其他文档引用这些结论，不再重新定义另一套名称、职责或流程。
