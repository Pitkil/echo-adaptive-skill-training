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
不代表每个固定检索案例都通过。

## 检索复核

最新复测记录为 `data/formal-materials/retrieval-20260827T0845Z`：12 个知识点通过 10 个，失败 2 个。

| 知识点 | 状态 | 原因 |
|---|---|---|
| M1-KP1 | 待处理 | 查询仍可能返回已移除 Components 的历史向量，未形成可映射的正式证据 |
| M1-KP4 | 已覆盖 | Chat History 已导入并可用于固定检索 |
| M3-KP4 | 待处理 | 固定查询发生超时，需要检查查询服务负载和超时配置 |
| 其他 10 个知识点 | 已通过 | 来源可映射到活动 upload 和 manifest |

在 M1-KP1 的历史向量清理、M3-KP4 超时复测完成前，不得把检索覆盖率写成 100%，也不得据此发布
正式幻觉率或引用可追溯率。

## 复核要求

1. PunditRAG 查询必须关闭网页搜索，并限制在活动的官方 document 范围。
2. 返回结果必须同时映射到 ECHO 活动 upload 和 manifest 的 `material_id`。
3. 未登记或已移除 document 必须过滤并记录数量和原因。
4. 每个知识点保留原始响应、trace/session ID、最终映射和失败原因。
5. 清单、切片、导入记录和运行数据库的 URL、版本、章节必须一致。
