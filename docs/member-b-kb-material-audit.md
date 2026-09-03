# Semantic Kernel 官方材料审计记录

## 当前基线

- 清单版本：`1.2`
- 材料数量：`15`
- 覆盖范围：M1、M2、M3 共 12 个知识点
- 知识库：`MS-SK-OFFICIAL`
- 允许来源：`learn.microsoft.com`、`github.com/microsoft/semantic-kernel`

本文件以 `docs/member-d/official_materials_manifest.json` v1.2 和运行时导入记录为准。旧版
ZIP 中的 Components 条目和已失效的 Training URL 不得继续作为正式来源。

## 已确认的三处替换

| 原条目 | 当前正式条目 | 原因 |
|---|---|---|
| `MS-SK-TRAINING-BUILD-KERNEL` 的旧 Training URL | `https://learn.microsoft.com/en-us/semantic-kernel/get-started/quick-start-guide` | 旧地址重定向到无关的 Azure AI Agent 培训路径 |
| `MS-SK-CONCEPTS-COMPONENTS` | `MS-SK-CHAT-HISTORY`：`https://learn.microsoft.com/en-us/semantic-kernel/concepts/ai-services/chat-completion/chat-history` | Components 与 KP1/KP2 重复，不能为 M1-KP4 提供直接证据 |
| `MS-SK-TRAINING-NATIVE-PLUGINS` 的旧 Training URL | `https://learn.microsoft.com/en-us/semantic-kernel/concepts/plugins/adding-native-plugins` | 旧地址重定向到无关的 Microsoft Foundry/Azure Agent 学习路径 |

替换关系、版本和知识点映射已经写入 manifest v1.2；不得只修改导入记录而不更新清单。

## 本地真实导入结果

2026-08-27 在本地 ECHO/PunditRAG 环境复核：

- 15 条正式材料均有 `completed` 导入状态；活动材料为 15 条。
- `MS-SK-CHAT-HISTORY` 使用 upload `19`，外部 document 为 `49fe147ad21b496abea13139f3bd1c02`。
- `MS-SK-TRAINING-NATIVE-PLUGINS` 使用官方 `adding-native-plugins`，外部 document 为
  `d3f42fa08de641d891b548a5f2bbd324`。
- 旧 `MS-SK-CONCEPTS-COMPONENTS` upload `20` 已标记 `removed`，不得再进入正式检索范围。
- 外部知识库标识为 `b91a91086ffc4399aa6152d37b6e1d60`。

导入完成不等于所有固定检索都通过。检索复测使用 ECHO 活动 upload、manifest 和外部
document_id 三重映射，未登记或已移除向量不会进入正式证据。

## 检索复核结果

最新本地复测记录：`retrieval-audit-v12-20260827T`（真实 Docker ECHO 数据库和 PunditRAG）。

| 项目 | 结果 | 处理 |
|---|---:|---|
| 知识点总数 | 12 | 固定案例 |
| 通过 | 12 | 保留原始响应和映射 |
| 失败 | 0 | 12/12 通过 |
| M1-KP1 | 已通过 | 活动 Kernel/Quick Start 来源可映射 |
| M3-KP4 | 已通过 | Observability/Process Overview 来源可映射 |

M1-KP4 已由 Chat History 材料覆盖；M3-KP1 已由 Process First 和 Process Overview 覆盖。
检索覆盖已达到 12/12，但这不替代资源事实声明检查、50 组案例和比赛指标的人工复核。

## 交付门禁

- 切片 manifest、chunks、材料文件和 SHA-256 必须来自同一 v1.2 构建。
- 外部导入记录必须与 ECHO `uploads` 表和 manifest 的 URL、版本、章节一致。
- 检索请求必须关闭网页搜索，并过滤未登记 document/vector。
- 每个知识点必须保存原始响应、最终映射、过滤数量、失败原因和运行时间。
- PunditRAG 仍返回历史或未登记向量时，不得把结果写入正式引用或资源。
