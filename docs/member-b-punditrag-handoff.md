# PunditRAG 知识库切片导入交接说明

## 交接目标

本交接包提供可导入的 Microsoft Semantic Kernel 官方材料切片。负责人提供并启动 PunditRAG
导入/查询双服务后，团队共同完成真实入库和固定检索验收。

仓库中的构建产物状态为 `prepared`；本地运行库已经完成 v1.2 的 15 条导入，但仍需以最新检索
复测报告为准，不能把导入完成直接等同于所有知识点检索通过。

本地运行库当前外部知识库为 `b91a91086ffc4399aa6152d37b6e1d60`。旧 Components 文档已标记
`removed`，M1-KP4 使用 `MS-SK-CHAT-HISTORY`，Native Plugins 使用官方
`adding-native-plugins` 页面。旧版交付包中的这些条目不得继续复用。

## 交接输入

| 文件 | 用途 |
|---|---|
| `manifest.json` | 15份材料的标题、URL、版本、模块、知识点、文件和哈希 |
| `chunks.jsonl` | 291个可追溯切片 |
| `files/*.md` | 清洗后的材料文件，供ECHO材料入口上传 |
| `SHA256SUMS.txt` | 交付目录中文件完整性校验 |
| `retrieval-cases.json` | 15条固定检索案例及 v1.2 预期来源 |
| `README.md` | 来源、许可、构建和状态说明 |

完整HTML是否随包交付取决于Microsoft条款和比赛提交范围；未确认时只交清洗材料、切片、元数据、
哈希和复现脚本。

## 负责人需要提供

- PunditRAG导入服务地址，默认 `http://127.0.0.1:8000`。
- PunditRAG查询服务地址，默认 `http://127.0.0.1:8001`。
- 服务需要认证时，提供受控访问方式，不把凭据写入Git或交付报告。
- 确认服务版本、知识库命名规则、文件类型和大小限制。

## 导入前检查

在ECHO项目根目录验证切片：

```powershell
python scripts/build_official_kb_slice.py validate --output <切片目录>
```

然后分别检查：

```powershell
Invoke-RestMethod <导入服务>/health
Invoke-RestMethod <查询服务>/health
```

两个服务必须分别正常。只检查ECHO或只检查其中一个PunditRAG服务不算通过。

## 导入步骤

1. 在ECHO `.env` 中配置 `PUNDITRAG_IMPORT_BASE_URL` 和 `PUNDITRAG_QUERY_BASE_URL`。
2. 重启ECHO并访问 `/health`，确认两个依赖均为 `ok`。
3. 使用讲师或管理员账号进入ECHO内容导入入口。
4. 创建或选择 `MS-SK-OFFICIAL` 知识库。
5. 逐份上传 `files/*.md`，同时填写模块、标题、官方URL、章节和版本。
6. 保存ECHO返回或业务记录中的 `knowledge_base_id`。
7. 保存PunditRAG返回的字符串 `kb_id`、每份材料的 `document_id` 和 `task_id`。
8. 轮询每个 `task_id` 到最终状态。

PunditRAG接受上传只表示排队。`pending`和`processing`均不能记为`indexed`；只有外部任务完成且
ECHO同步成功后才算已索引。失败时保留 `index_error`、时间和处理结果。

## `import-records.json` 回填字段

每份材料至少记录：

- `material_id`
- `knowledge_base_id`
- `punditrag_kb_id`
- `document_id`
- `task_id`
- `submitted_at`
- `completed_at`
- `status`
- `index_error`
- `source_file_sha256`
- `executed_by`

汇总必须列出 total、pending、processing、indexed、failed、degraded，合计与15一致。

## 固定检索

使用 `retrieval-cases.json`。每次查询固定：

```json
{
  "scope_mode": "knowledge_base",
  "kb_ids": ["真实 PunditRAG kb_id"],
  "document_ids": [],
  "is_stream": false,
  "enable_web_search": false
}
```

逐案例保存：查询、session/trace ID、原始sources、过滤结果、最终排名、标题、URL、章节、版本、
chunk/document标识、人工相关性判断和失败原因。未登记来源、非允许域名及缺少章节/版本的结果
必须过滤。

## 完成条件

- 15份材料均有真实最终状态；失败材料有明确原因。
- M1/M2/M3和12个知识点均完成查询。
- 正式结果只来自允许的Microsoft官方来源。
- 引用可以打开并定位到相应章节和版本。
- `import-records.json`、`retrieval-report.md`和ECHO数据库记录一致。
- M3-KP4部署与质量评测单独复核；证据不足时记录缺口并补官方来源，不强行判定通过。
