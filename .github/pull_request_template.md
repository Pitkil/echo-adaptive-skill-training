## 关联任务

填写任务名称或 Issue 编号；没有 Issue 时填写“无”。

## 修改目的

说明本次 PR 要解决的问题。

## 主要修改

- 列出实际完成的内容。

## 验证结果

- [ ] `powershell -ExecutionPolicy Bypass -File scripts\quality.ps1`
- [ ] `powershell -ExecutionPolicy Bypass -File scripts\test.ps1`
- [ ] `python -m compileall apps/api`
- [ ] `docker compose config`
- [ ] 涉及前端时已检查桌面端和 390px 移动端

## 影响范围

说明涉及的接口、数据库、页面、题库、课程材料或外部服务。

## 界面截图

涉及前端时添加修改前后截图；不涉及则填写“不涉及”。

## 不兼容变化

是否会影响其他成员现有代码、接口或数据；没有则填写“无”。

## 未完成内容

明确列出仍未完成或需要其他成员配合的事项；没有则填写“无”。

## 风险与回退方式

- 风险：
- 回退：

## 提交前确认

- [ ] 已阅读 `AGENTS.md`、本人的任务说明和 `docs/collaboration.md`
- [ ] 本 PR 内容属于当前成员职责
- [ ] 当前固定分支已同步最新 `main`
- [ ] 未提交 `.env`、密钥、数据库、音频、上传文件、缓存或真实个人信息
- [ ] 未直接修改或推送 `main`
- [ ] 已解决所有冲突和审核意见
