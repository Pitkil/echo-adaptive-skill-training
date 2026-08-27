# 官方材料导入核对报告

## 当前基线

| 项目 | 内容 |
|---|---|
| 清单版本 | `1.2` |
| 材料总数 | 15 |
| 覆盖知识点 | 12 |
| 知识库 | `MS-SK-OFFICIAL` |
| 外部 PunditRAG kb | `b91a91086ffc4399aa6152d37b6e1d60` |

正式来源以 `docs/member-d/official_materials_manifest.json` v1.2 为准。v1.2 已将失效 Training
URL 替换为官方 Semantic Kernel 页面，并用 Chat History 替换重复的 Components 条目。

## 真实导入结果

2026-08-27 的运行报告 `data/formal-materials/official-materials-20260827T081157Z/material-import-report.json`
显示 15/15 条材料导入任务完成，失败数为 0。当前活动材料包括：

- `MS-SK-CHAT-HISTORY`：upload `19`，用于 M1-KP4。
- `MS-SK-TRAINING-NATIVE-PLUGINS`：官方 `adding-native-plugins` 页面，用于 M1-KP3。
- `MS-SK-CONCEPTS-COMPONENTS`：旧 upload `20` 已标记 `removed`，不得作为正式证据。

每条材料均保存外部 `document_id`、`task_id`、版本、章节和状态；`completed` 只表示导入任务完成，
固定检索仍以独立复测报告为准。

## 检索复核

最新复测记录为 `retrieval-audit-v12-20260827T`：12 个知识点通过 12 个，失败 0 个。

| 知识点 | 状态 | 原因 |
|---|---|---|
| M1-KP1 | 已通过 | 活动 Kernel/Quick Start 来源可映射；未登记向量被过滤 |
| M1-KP4 | 已覆盖 | Chat History 已导入并可用于固定检索 |
| M3-KP4 | 已通过 | Observability/Process Overview 来源可映射 |
| 其他 10 个知识点 | 已通过 | 来源可映射到活动 upload 和 manifest |

检索覆盖率为 100%；这只证明官方来源可检索，不得据此直接发布幻觉率、难度适配率或引用可追溯率，
相关比赛指标仍需案例人工复核和发布审批。

## 复核要求

1. PunditRAG 查询必须关闭网页搜索，并限制在活动的官方 document 范围。
2. 返回结果必须同时映射到 ECHO 活动 upload 和 manifest 的 `material_id`。
3. 未登记或已移除 document 必须过滤并记录数量和原因。
4. 每个知识点保留原始响应、trace/session ID、最终映射和失败原因。
5. 清单、切片、导入记录和运行数据库的 URL、版本、章节必须一致。
