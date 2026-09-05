# 协作与开发规范

本文档是 GitHub 协作规则的唯一完整来源。四人具体任务和交付见
[team-ownership.md](team-ownership.md)。

## 最简单的协作方式

- 仓库已公开，由负责人邀请 A、B、C、D 成为 Collaborator。
- 固定成员直接 Clone 同一个仓库；外部贡献者通过 Fork 提交 PR，同样执行测试和审核。
- 四个人各使用一个固定分支：
  - `member/a-integration`：负责人主系统与总集成。
  - `member/b-micro-signal`：微表征接入。
  - `member/c-mirt-memory`：MIRT、学习情况总结与 SimpleMem。
  - `member/d-content-data`：官方材料、固定题库与评测数据。
- `main` 只保存已检查且可运行的版本，任何人都不直接向 `main` 推送。
- 每名成员先阅读 [AGENTS.md](../AGENTS.md)、本人的任务说明和本文档，再自行创建并首次 Push
  自己的固定分支；负责人不代替成员创建。
- B、C、D 的 PR 必须由负责人审核；负责人自己的 PR 在自动检查通过后可以自行合并。
- 只有负责人执行最终合并。

日常流程：

```text
固定分支修改 -> Commit -> Push -> 创建 PR -> 自动检查 -> 负责人审核 -> 合并到 main
```

不需要为每个小任务创建新分支。一个功能还没完成时，可以在固定分支继续 Commit；
完成一个能够独立检查的阶段后再创建 PR。

## 开始和同步

第一次获取仓库：

```powershell
git clone https://github.com/Pitkil/echo-adaptive-skill-training.git
cd echo-adaptive-skill-training
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

阅读 [AGENTS.md](../AGENTS.md)、[team-ownership.md](team-ownership.md) 和本文档后，自行创建固定分支。
以成员 C 为例：

```powershell
git switch main
git pull origin main
git switch -c member/c-mirt-memory
git push -u origin member/c-mirt-memory
```

每次开始工作前，在自己的固定分支执行：

```powershell
git fetch origin
git merge origin/main
```

遇到冲突时不要强制覆盖，也不要删除看不懂的代码。公共模型、数据库迁移、导航或
跨模块冲突交由负责人处理。

## 开发环境与命名

- 使用 Python 3.11、3.12 或 3.13，文件统一保存为 UTF-8。
- 禁止提交密钥、`.env`、数据库、音频、上传文件、训练数据、缓存和真实个人信息。只有比赛运行必需、
  许可和数据授权已确认、版本与 SHA-256 已冻结的推理模型制品可以进入 `models/micro_detector/`，
  且必须由 Git LFS 管理；生成 embedding、中间 checkpoint、优化器状态和重复权重不得提交。
- Python 文件、函数和变量使用 `snake_case`。
- 类使用 `PascalCase`，常量使用 `UPPER_SNAKE_CASE`。
- 布尔值使用 `is_`、`has_`、`can_` 或 `should_` 开头。
- 数据库外键使用 `{entity}_id`，时间字段使用 `_at`。
- API 使用复数资源名，例如 `/v1/resources`。
- 公共名称使用 `training_program`、`module` 和 `knowledge_point`，不得重新加入
  学校学科式 `subject`。
- 函数只完成一个明确动作；路由负责校验和组装，业务规则放入对应模块。

## 修改顺序

1. 阅读 [team-ownership.md](team-ownership.md)，确认修改属于当前成员职责。
2. 涉及公共字段或跨服务数据时，先更新接口说明和测试样例。
3. 增加或修改自动测试。
4. 实现所属模块逻辑。
5. 公共路由、数据库迁移、公共导航和最终页面接入由负责人处理。
6. 完成质量检查后 Push，并创建 PR。

## Commit

格式：

```text
type(scope): 简短说明
```

`type` 使用：

- `feat`：新增功能。
- `fix`：修复问题。
- `refactor`：调整结构但不改变功能。
- `test`：测试。
- `docs`：文档。
- `chore`：配置、依赖和工程维护。
- `revert`：撤销一个已有提交。

示例：

```text
feat(quiz): 增加固定题库预览导入
fix(mirt): 阻止重复作答更新能力
docs(team): 补充协作说明
```

一个 Commit 只包含一个能够说明和回退的改动。禁止使用“修改一下”“更新代码”等
无法判断内容的说明。

## 创建 PR

Push 固定分支后，在 GitHub 创建目标为 `main` 的 Pull Request。GitHub 会自动加载
`.github/pull_request_template.md`。

PR 必须写清：

- 修改目的和实际完成内容。
- 验证结果。
- 影响的接口、数据库、页面、材料或外部服务。
- 尚未完成的内容。
- 风险和回退方式。
- 可选的 Issue 编号、界面截图和不兼容变化。

## 冲突处理

1. 在当前固定分支执行 `git fetch origin`。
2. 执行 `git merge origin/main`。
3. 逐个文件确认双方修改目的。
4. 只解决自己职责范围内的冲突，公共冲突交由负责人处理。
5. 保留双方有效逻辑并重新运行质量检查。
6. Commit 冲突处理结果并 Push，原 PR 会自动更新。
7. 禁止强制覆盖或直接丢弃他人修改。

## 负责人审核

- 修改内容属于该成员任务，没有夹带无关文件。
- 没有密钥、数据库、音频、缓存或真实个人信息。
- 公共契约、权限、数据库和外部服务边界没有被破坏。
- 学习者端没有暴露答案、评分方法或管理员功能。
- 关键写操作具备重复提交保护。
- 新功能有测试，旧测试仍通过。
- 前端修改完成桌面端和 390px 移动端检查。
- 文档与实际代码保持一致。

审核不是重新编写成员代码。发现问题时在 PR 中指出，成员在原固定分支修改并 Push，
PR 会自动更新。

## 允许合并

同时满足以下条件才允许合并：

1. PR 描述完整，修改属于成员职责。
2. 自动检查全部通过。
3. 不包含敏感文件和运行数据。
4. 不存在未解决冲突或审核意见。
5. 涉及公共接口、数据库或部署的修改已经更新文档。
6. 负责人确认后使用普通 Merge，不使用强制推送。

为 `main` 配置保护规则：必须通过 PR、必须通过自动检查、必须解决讨论、
禁止强制推送和禁止删除。实际保护状态需在 GitHub 设置中核对；本文描述协作要求。

## 版本标签

版本标签只由负责人创建，不要求每次合并都打标签：

- `v0.1.0`：四人可以开始并行开发的稳定基础版。
- `v0.2.0`：四个成员模块完成首次集成。
- `v1.0.0`：比赛提交和最终演示版本。
