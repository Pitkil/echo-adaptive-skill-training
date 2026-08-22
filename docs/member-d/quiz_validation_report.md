# 固定题库验证报告

## 1. 冻结结果

| 项目 | 结果 |
|------|------|
| 报告日期 | 2026-08-22 |
| 题库版本 | 1.0 |
| 正式题总数 | 63 道 |
| Manifest | `quiz_formal_manifest.json` |
| 导入预览 | 通过 |
| 冻结状态 | 已冻结 |

本次冻结以 `Quiz.import_from_document.extract_quiz_preview()` 的实际解析结果为准。此前 3 道候选操作题仍会被导入器当作普通 `practice` 题，现已从正式数据目录移除；Manifest 中 2 条没有对应源题目的记录也已删除。

## 2. 数量分布

| 模块 | pretest | posttest | practice | 合计 |
|------|---------|----------|----------|------|
| M1（Kernel 与插件） | 9 | 9 | 3 | 21 |
| M2（Agent 与多智能体协作） | 9 | 9 | 3 | 21 |
| M3（流程、部署与质量评测） | 9 | 9 | 3 | 21 |
| **合计** | **27** | **27** | **9** | **63** |

| 难度 | 数量 |
|------|------|
| foundation | 24 |
| standard | 32 |
| advanced | 7 |
| **合计** | **63** |

## 3. 自动核对项

- 63 个 `question_id` 全部唯一。
- 33 个 Markdown 文件均可由正式导入器解析，且合计正好 63 道。
- Manifest 的文件路径、题目序号、用途、难度、出处和 `counts_for_mirt` 与解析结果逐项一致。
- 用途仅包含 `pretest`、`posttest`、`practice`；前测和后测参与 MIRT，练习题不参与 MIRT。
- 所有题目都有可执行评分方法，并包含 Microsoft 官方标题、链接和章节。
- 来源域名仅允许 `learn.microsoft.com` 与 `github.com/microsoft/semantic-kernel`。

## 4. 结论

63 道正式固定题可以冻结并进入导入验证。题库数据完整性由 `tests/unit/test_member_d_content_data.py` 持续检查；后续修改题目源文件时必须同步更新 Manifest 并通过测试。

**报告人**：成员 D（member/d-content-data）
**审核状态**：A 已复核
**冻结建议**：通过
